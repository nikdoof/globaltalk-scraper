#!/usr/bin/env python3
"""
GlobalTalk Scraper

Uses netatalk's `getzones` and `nbplkup` to discover devices on the GlobalTalk
network and return structured data about zones and nodes.
"""

import concurrent.futures
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

NBPLKUP_RESULTS = re.compile(r"^(.*):(.*)\s(\d*\.\d*:\d*)$")


def check_prerequisites() -> List[str]:
    """Check that required netatalk binaries are available.

    Returns a list of missing command names. An empty list means all
    prerequisites are satisfied.
    """
    missing = []
    for cmd in ["getzones", "nbplkup"]:
        if not shutil.which(cmd):
            missing.append(cmd)
    return missing


def getzones() -> List[str]:
    """Return a list of AppleTalk zone names using ``getzones``.

    Returns an empty list if the command fails or times out.
    """
    try:
        result = subprocess.run(
            ["getzones"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return [x.strip() for x in result.stdout.split("\n") if x.strip() != ""]
    except subprocess.CalledProcessError as e:
        logging.error("Failed to run getzones: %s", e)
        return []
    except subprocess.TimeoutExpired:
        logging.error("getzones command timed out")
        return []


def nbplkup(zone: str) -> List[Dict[str, str]]:
    """Look up members of a zone and return a list of node dictionaries.

    Each node dict contains the keys: ``object``, ``type``, ``address``,
    ``socket``, and ``zone``.

    Returns an empty list if the command fails or times out.
    """
    zone_results = []

    # Set the charset to mac-roman to avoid translation issues with some
    # device names (e.g. AsanteTalk hardware).
    environ = os.environ.copy()
    environ["ATALK_UNIX_CHARSET"] = "mac-roman"

    try:
        cmd = subprocess.run(
            ["nbplkup", f"@{zone}"],
            capture_output=True,
            text=True,
            encoding="mac-roman",
            env=environ,
            timeout=60,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logging.error("Failed to lookup zone %s: %s", zone, e)
        return []
    except subprocess.TimeoutExpired:
        logging.error("nbplkup timed out for zone %s", zone)
        return []

    for line in cmd.stdout.split("\n"):
        if line.strip() == "":
            continue

        rec = NBPLKUP_RESULTS.match(line.strip())
        if rec is None:
            logging.debug("Could not parse line: %s", line.strip())
            continue

        try:
            obj, endpoint_type, address_raw = rec.groups()
            address, socket = address_raw.split(":")
            zone_results.append(
                {
                    "object": obj.strip(),
                    "type": endpoint_type.strip(),
                    "address": address,
                    "socket": socket,
                    "zone": zone,
                }
            )
        except (ValueError, AttributeError) as e:
            logging.warning("Error parsing line '%s': %s", line.strip(), e)
            continue

    return zone_results


def deduplicate_nodes(nodes: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], int]:
    """Remove duplicate nodes based on address, socket, type, and object name.

    Returns a ``(unique_nodes, duplicate_count)`` tuple.
    """
    seen: set = set()
    unique_nodes = []

    for node in nodes:
        key = (node["address"], node["socket"], node["type"], node["object"])
        if key not in seen:
            seen.add(key)
            unique_nodes.append(node)

    duplicates = len(nodes) - len(unique_nodes)
    if duplicates > 0:
        logging.info("Removed %d duplicate node(s)", duplicates)

    return unique_nodes, duplicates


def scrape(
    zones: Optional[List[str]] = None,
    workers: int = 10,
    dedupe: bool = True,
) -> Dict:
    """Scrape the GlobalTalk network and return a result dictionary.

    Args:
        zones: Optional list of zone names to restrict scanning to. When
            ``None`` all zones discovered by ``getzones`` are scanned.
        workers: Number of concurrent zone-scan threads.
        dedupe: When ``True`` duplicate nodes are removed from the results.

    Returns:
        A dictionary with the keys ``format``, ``zones``, and ``nodes``.

    Raises:
        RuntimeError: If required netatalk binaries are missing, no zones are
            found, or none of the requested zones exist.
    """
    missing = check_prerequisites()
    if missing:
        raise RuntimeError(
            f"Missing required commands: {', '.join(missing)}. "
            "Is netatalk installed and on your PATH?"
        )

    all_zones = getzones()
    if not all_zones:
        raise RuntimeError("No zones found or error retrieving zones")

    if zones:
        zones_to_scan = [z for z in all_zones if z in zones]
        if not zones_to_scan:
            raise RuntimeError(f"None of the specified zones exist: {zones}")
        logging.info("Scanning %d of %d zones", len(zones_to_scan), len(all_zones))
    else:
        zones_to_scan = all_zones

    result: Dict = {
        "format": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "zones": all_zones,
        "nodes": [],
    }

    def _lookup_zone(zone: str) -> Optional[List[Dict[str, str]]]:
        logging.info("Scanning %s", zone)
        nodes = nbplkup(zone)
        logging.info("Found %d nodes in %s", len(nodes), zone)
        return nodes

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_lookup_zone, zone): zone for zone in zones_to_scan}
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            zone_nodes = future.result()
            if zone_nodes:
                result["nodes"].extend(zone_nodes)
            logging.info("Progress: %d/%d zones scanned", completed, len(zones_to_scan))

    total_nodes = len(result["nodes"])
    if dedupe:
        result["nodes"], _ = deduplicate_nodes(result["nodes"])

    logging.info(
        "%d zones, %d unique nodes (scanned %d total)",
        len(result["zones"]),
        len(result["nodes"]),
        total_nodes,
    )

    return result


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``scrape`` CLI subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="globaltalk scrape",
        description="Scrape the GlobalTalk network and emit a JSON snapshot",
    )
    parser.add_argument(
        "--zone",
        nargs="*",
        default=None,
        help="Restrict scan to these zone names (default: all zones)",
    )
    parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="File to write JSON output to (default: stdout)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent zone scans (default: 10)",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable removal of duplicate nodes",
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

    logging.debug("Arguments: %s", args)

    try:
        result = scrape(
            zones=args.zone,
            workers=args.workers,
            dedupe=not args.no_dedupe,
        )
    except RuntimeError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    json.dump(result, args.output, indent=2)
    args.output.write("\n")

    if args.output is not sys.stdout:
        args.output.close()


if __name__ == "__main__":
    main()
