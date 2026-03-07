#!/usr/bin/env python3
"""
GlobalTalk Metrics

Converts a GlobalTalk JSON snapshot into Prometheus metrics suitable for use
with the node_exporter textfile collector.

The JSON snapshot can be supplied as a file path, or omitted entirely to run a
live scrape of the network on the fly (requires netatalk to be installed).
"""

import collections
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import IO, Any, Dict, List, Optional


def escape_label_value(value: str) -> str:
    """Escape special characters in a Prometheus label value."""
    value = value.replace("\\", "\\\\")
    value = value.replace("\n", "\\n")
    value = value.replace('"', '\\"')
    return value


def _write_meta(output: IO[str], name: str, metric_type: str, help_text: str) -> None:
    """Write Prometheus HELP and TYPE comment lines."""
    output.write(f"# HELP {name} {help_text}\n")
    output.write(f"# TYPE {name} {metric_type}\n")


def load_data(path: str) -> Dict[str, Any]:
    """Load and validate a GlobalTalk JSON snapshot from *path*.

    Returns the parsed dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is malformed or the structure is invalid.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to decode JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    if "nodes" not in data or "zones" not in data:
        raise ValueError("JSON must contain 'nodes' and 'zones' fields")

    if "format" in data and data["format"] != "v1":
        logging.warning("Unknown format version '%s', expected 'v1'", data["format"])

    return data


def _snapshot_age_seconds(data: Dict[str, Any]) -> float | None:
    """Return the age of the snapshot in seconds, or ``None`` if the
    ``generated_at`` field is absent or unparseable."""
    raw = data.get("generated_at")
    if not raw:
        return None
    try:
        generated_at = datetime.fromisoformat(raw)
        # fromisoformat preserves tzinfo when present; make sure we compare
        # against UTC either way.
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - generated_at).total_seconds()
    except (ValueError, TypeError):
        logging.warning("Could not parse generated_at value: %r", raw)
        return None


def generate_metrics(
    data: Dict[str, Any],
    output: IO[str],
    prefix: str = "globaltalk",
) -> None:
    """Write Prometheus metrics derived from *data* to *output*.

    Args:
        data: A validated GlobalTalk snapshot dictionary (as returned by
            :func:`load_data`).
        output: A writable text stream.
        prefix: Metric name prefix (default: ``globaltalk``).
    """
    nodes: List[Dict[str, Any]] = data["nodes"]
    zones: List[str] = data["zones"]

    # Snapshot age (only present when generated_at is in the data)
    age = _snapshot_age_seconds(data)
    if age is not None:
        _write_meta(
            output,
            f"{prefix}_snapshot_age_seconds",
            "gauge",
            "Seconds elapsed since the snapshot was generated",
        )
        output.write(f"{prefix}_snapshot_age_seconds {age:.3f}\n")

    # Total zones
    _write_meta(output, f"{prefix}_zones", "gauge", "Total number of AppleTalk zones")
    output.write(f"{prefix}_zones {len(zones)}\n")

    # Unique devices (by AppleTalk address)
    devices = collections.Counter(node.get("address", "Unknown") for node in nodes)
    _write_meta(
        output,
        f"{prefix}_unique_devices",
        "gauge",
        "Number of unique devices by address",
    )
    output.write(f"{prefix}_unique_devices {len(devices)}\n")

    # Total nodes / endpoints
    _write_meta(
        output,
        f"{prefix}_total_nodes",
        "gauge",
        "Total number of network nodes",
    )
    output.write(f"{prefix}_total_nodes {len(nodes)}\n")

    # Endpoints per zone
    zone_counts = collections.Counter(node.get("zone", "Unknown") for node in nodes)
    _write_meta(
        output,
        f"{prefix}_zone_devices",
        "gauge",
        "Number of devices per zone",
    )
    for zone, count in sorted(zone_counts.items()):
        output.write(
            f'{prefix}_zone_devices{{zone="{escape_label_value(zone)}"}} {count}\n'
        )

    # Device type breakdown
    type_counts = collections.Counter(node.get("type", "Unknown") for node in nodes)
    _write_meta(
        output,
        f"{prefix}_device_types",
        "gauge",
        "Number of devices by type",
    )
    for device_type, count in sorted(type_counts.items()):
        output.write(
            f'{prefix}_device_types{{type="{escape_label_value(device_type)}"}} {count}\n'
        )

    # Multi-homed devices (more than one endpoint registered for a single address)
    nodes_per_device = collections.Counter(
        node.get("address", "Unknown") for node in nodes
    )
    multihomed = sum(1 for count in nodes_per_device.values() if count > 1)
    _write_meta(
        output,
        f"{prefix}_multihomed_devices",
        "gauge",
        "Number of devices with multiple network endpoints",
    )
    output.write(f"{prefix}_multihomed_devices {multihomed}\n")

    # jRouter version breakdown
    jrouter_pattern = re.compile(r"^jrouter\s+(.+)", re.IGNORECASE)
    jrouter_versions: collections.Counter = collections.Counter()
    for node in nodes:
        match = jrouter_pattern.match(node.get("object", ""))
        if match:
            jrouter_versions[match.group(1).strip()] += 1

    if jrouter_versions:
        _write_meta(
            output,
            f"{prefix}_jrouter_versions",
            "gauge",
            "Count of jRouter instances by version",
        )
        for version, count in sorted(jrouter_versions.items()):
            output.write(
                f'{prefix}_jrouter_versions{{version="{escape_label_value(version)}"}} {count}\n'
            )


def _write_metrics_output(
    data: Dict[str, Any],
    output: IO[str],
    prefix: str = "globaltalk",
) -> None:
    """Write metrics to *output*, using an atomic replace when *output* is a
    real file path rather than stdout.

    Writing directly to the target ``.prom`` file risks node_exporter reading
    a partial file if the process is interrupted mid-write.  Instead we write
    to a sibling ``.tmp`` file and then use ``os.replace()`` to atomically
    move it into place.  ``os.replace()`` is atomic on POSIX when source and
    destination are on the same filesystem, which is always true here.

    When *output* is stdout (or any non-file-backed stream) we fall back to
    writing directly.
    """
    # Detect whether output is a real file by checking for a name attribute
    # that isn't one of the special stdio names.
    output_path = getattr(output, "name", None)
    is_real_file = output_path is not None and output_path not in (
        "<stdout>",
        "<stderr>",
        "<stdin>",
    )

    if is_real_file:
        tmp_path = output_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as tmp:
                generate_metrics(data, tmp, prefix=prefix)
            os.replace(tmp_path, output_path)
        except Exception:
            # Clean up the temp file if anything went wrong, then re-raise so
            # the caller can handle/log the error.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    else:
        generate_metrics(data, output, prefix=prefix)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``metrics`` CLI subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="globaltalk metrics",
        description=(
            "Convert a GlobalTalk JSON snapshot into Prometheus metrics. "
            "When no snapshot file is given, the network is scraped live "
            "(requires netatalk)."
        ),
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Path to a GlobalTalk JSON snapshot (omit to scrape live)",
    )
    parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="File to write metrics to (default: stdout)",
    )
    parser.add_argument(
        "--prefix",
        default="globaltalk",
        help="Metric name prefix (default: globaltalk)",
    )

    # Live-scrape options — only meaningful when no filename is given.
    scrape_group = parser.add_argument_group(
        "live scrape options",
        "Used when no snapshot file is provided (requires netatalk)",
    )
    scrape_group.add_argument(
        "--zone",
        nargs="*",
        default=None,
        metavar="ZONE",
        help="Restrict live scrape to these zone names (default: all zones)",
    )
    scrape_group.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent zone scans for live scrape (default: 10)",
    )
    scrape_group.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable duplicate-node removal during live scrape",
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--quiet", action="store_true", help="Suppress info logging")
    args = parser.parse_args(argv)

    if args.debug:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.ERROR
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.filename is not None:
        # ── Load from a JSON snapshot file ──────────────────────────────────
        if args.zone or args.workers != 10 or args.no_dedupe:
            logging.warning(
                "Live scrape options (--zone, --workers, --no-dedupe) are "
                "ignored when a snapshot file is provided"
            )
        try:
            data = load_data(args.filename)
        except FileNotFoundError:
            logging.error("File not found: %s", args.filename)
            sys.exit(1)
        except ValueError as exc:
            logging.error("%s", exc)
            sys.exit(1)
    else:
        # ── Live scrape ──────────────────────────────────────────────────────
        from globaltalk.scrape import scrape

        try:
            data = scrape(
                zones=args.zone,
                workers=args.workers,
                dedupe=not args.no_dedupe,
            )
        except RuntimeError as exc:
            logging.error("%s", exc)
            sys.exit(1)

    _write_metrics_output(data, args.output, prefix=args.prefix)

    if args.output is not sys.stdout:
        args.output.close()


if __name__ == "__main__":
    main()
