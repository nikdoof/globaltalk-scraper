#!/usr/bin/env python3
"""
GlobalTalk Visualisations

Converts a GlobalTalk JSON snapshot into visualisation formats for exploring
the network topology.

Formatters
----------
mermaid
    Produces a Mermaid mindmap showing zones and the devices within them,
    suitable for embedding in Markdown documents (e.g. GitHub README files
    or Obsidian notes).

d3
    Produces a hierarchical JSON tree suitable for use with D3.js visualisations
    such as a sunburst or tree chart.
"""

import json
import sys
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Mermaid formatter
# ---------------------------------------------------------------------------

# Node types to suppress from the mindmap — router infrastructure entries
# clutter the diagram without adding much meaning for most viewers.
_MERMAID_EXCLUDED_TYPES = {"netatalk", "AppleRouter", "TimeLord"}


def to_mermaid(data: Dict[str, Any], exclude_types: Optional[List[str]] = None) -> str:
    """Render a GlobalTalk snapshot as a Mermaid mindmap string.

    The output is a fenced Mermaid code block ready to paste into Markdown.
    Each AppleTalk zone becomes a branch off the root, and the unique device
    objects within each zone are its leaves.

    Args:
        data: A validated GlobalTalk snapshot dictionary.
        exclude_types: NBP type strings to omit from the diagram.  Defaults to
            ``{"netatalk", "AppleRouter", "TimeLord"}`` — infrastructure nodes
            that are rarely interesting in a topology overview.  Pass an empty
            list to include everything.

    Returns:
        A string containing the complete fenced Mermaid mindmap block.
    """
    if exclude_types is None:
        excluded = _MERMAID_EXCLUDED_TYPES
    else:
        excluded = set(exclude_types)

    nodes: List[Dict[str, Any]] = data.get("nodes", [])
    zones: List[str] = data.get("zones", [])

    body = ""
    for zone in zones:
        zone_nodes = [
            n for n in nodes if n.get("zone") == zone and n.get("type") not in excluded
        ]
        if not zone_nodes:
            continue

        # Deduplicate by object name within the zone so multi-endpoint devices
        # appear only once as a leaf.
        unique_objects = dict.fromkeys(n["object"] for n in zone_nodes)

        # Mermaid mindmap node labels cannot contain unescaped parentheses,
        # quotes, or backticks — wrap in double-quotes and escape any internal
        # double-quotes.
        def _label(name: str) -> str:
            escaped = name.replace('"', '\\"')
            return f'"{escaped}"'

        leaves = "\n".join(f"      {_label(obj)}" for obj in unique_objects)
        body += f"    {_label(zone)}\n{leaves}\n"

    return f"```mermaid\nmindmap\n  root)GlobalTalk(\n{body}```\n"


# ---------------------------------------------------------------------------
# D3 formatter
# ---------------------------------------------------------------------------

# Default set of NBP types included in the D3 tree.  These are the types most
# useful for a network-device sunburst; routers and infrastructure are omitted
# by default because they are present in every zone and dominate the chart.
_D3_INCLUDED_TYPES = {
    "AFPServer",
    "Workstation",
    "ImageWriter",
    "LaserWriter",
    "Darwin",
}


def to_d3(
    data: Dict[str, Any], include_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Build a D3-compatible hierarchical data structure from a GlobalTalk snapshot.

    The returned dictionary has the shape::

        {
            "name": "GlobalTalk",
            "children": [
                {
                    "name": "<zone name>",
                    "children": [
                        {"name": "<object> - <type>", "value": 1},
                        ...
                    ]
                },
                ...
            ]
        }

    Zones with no matching nodes are omitted so they don't create empty
    wedges in a sunburst chart.

    Args:
        data: A validated GlobalTalk snapshot dictionary.
        include_types: NBP type strings to include.  Defaults to
            ``{"AFPServer", "Workstation", "ImageWriter", "LaserWriter",
            "Darwin"}``.  Pass ``None`` to use the default, or an explicit
            list (including an empty one) to override it.

    Returns:
        A plain Python dictionary ready to be serialised with ``json.dumps``.
    """
    if include_types is None:
        included = _D3_INCLUDED_TYPES
    else:
        included = set(include_types)

    nodes: List[Dict[str, Any]] = data.get("nodes", [])
    zones: List[str] = data.get("zones", [])

    zone_children = []
    for zone in zones:
        zone_nodes = [
            n
            for n in nodes
            if n.get("zone") == zone and (not included or n.get("type") in included)
        ]
        if not zone_nodes:
            continue

        zone_children.append(
            {
                "name": zone,
                "children": [
                    {
                        "name": f"{n['object']} - {n['type']}",
                        "value": 1,
                    }
                    for n in zone_nodes
                ],
            }
        )

    return {"name": "GlobalTalk", "children": zone_children}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``visualise`` CLI subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="globaltalk visualise",
        description="Convert a GlobalTalk JSON snapshot into a visualisation format",
    )

    subparsers = parser.add_subparsers(
        dest="format",
        metavar="format",
        required=True,
    )

    # ── mermaid ──────────────────────────────────────────────────────────────
    mermaid_parser = subparsers.add_parser(
        "mermaid",
        help="Mermaid mindmap — embed in Markdown documents",
    )
    mermaid_parser.add_argument(
        "filename",
        help="Path to a GlobalTalk JSON snapshot",
    )
    mermaid_parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="File to write output to (default: stdout)",
    )
    mermaid_parser.add_argument(
        "--include-infrastructure",
        action="store_true",
        help=(
            "Include infrastructure node types (netatalk, AppleRouter, TimeLord) "
            "that are excluded by default"
        ),
    )

    # ── d3 ───────────────────────────────────────────────────────────────────
    d3_parser = subparsers.add_parser(
        "d3",
        help="D3.js hierarchical JSON — use with sunburst or tree charts",
    )
    d3_parser.add_argument(
        "filename",
        help="Path to a GlobalTalk JSON snapshot",
    )
    d3_parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="File to write output to (default: stdout)",
    )
    d3_parser.add_argument(
        "--all-types",
        action="store_true",
        help=(
            "Include all NBP device types instead of the default subset "
            "(AFPServer, Workstation, ImageWriter, LaserWriter, Darwin)"
        ),
    )

    args = parser.parse_args(argv)

    # Load the snapshot — shared by both subcommands.
    try:
        with open(args.filename, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        sys.stderr.write(f"globaltalk visualise: file not found: {args.filename}\n")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"globaltalk visualise: invalid JSON: {exc}\n")
        sys.exit(1)

    if args.format == "mermaid":
        exclude = [] if args.include_infrastructure else None
        args.output.write(to_mermaid(data, exclude_types=exclude))

    elif args.format == "d3":
        include = None if not args.all_types else []
        result = to_d3(data, include_types=include)
        json.dump(result, args.output, indent=2)
        args.output.write("\n")

    if args.output is not sys.stdout:
        args.output.close()


if __name__ == "__main__":
    main()
