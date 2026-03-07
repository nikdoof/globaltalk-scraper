#!/usr/bin/env python3
"""
GlobalTalk Node List

Converts a text file of DNS names and IP addresses into a jrouter-compatible
YAML configuration file.  jrouter is a modern recreation of Apple Internet
Router (AIR) used within the GlobalTalk network.

The YAML output is intentionally kept simple (a single ``peers`` list) so that
it can be produced without any external dependencies using a small hand-rolled
emitter.
"""

import logging
import socket
import sys
from typing import List, Optional

# ---------------------------------------------------------------------------
# YAML helpers (no external dependency)
# ---------------------------------------------------------------------------


def _dump_peers_yaml(peers: List[str]) -> str:
    """Serialise a list of peer IP strings as a minimal YAML document.

    Only handles the ``peers`` key with a list of scalar strings — which is
    exactly the structure jrouter expects.  No general-purpose YAML library is
    required.

    Example output::

        peers:
        - 1.2.3.4
        - 5.6.7.8
    """
    if not peers:
        return "peers: []\n"

    lines = ["peers:"]
    for peer in peers:
        lines.append(f"- {peer}")
    lines.append("")  # trailing newline
    return "\n".join(lines)


def _merge_yaml_peers(path: str, peers: List[str]) -> str:
    """Load a YAML file at *path*, replace (or add) its ``peers`` key, and
    return the updated document as a string.

    This is intentionally minimal: it preserves all other lines in the file
    verbatim and only replaces the ``peers`` block.  If no ``peers`` block
    exists it is appended at the end.

    Assumptions / known limitations
    --------------------------------
    - The ``peers:`` key must be at the **top level** of the file (no leading
      whitespace).  A ``peers:`` key that is indented under another key (i.e.
      nested) will be incorrectly matched and replaced.  This is not a concern
      for standard jrouter configs, where ``peers`` is always a top-level key.

    - The end of the ``peers`` block is detected as the next line that begins
      with a non-space, non-hyphen character.  Blank lines between peer entries
      would therefore terminate the block early — avoid them in the peers list.

    - Line endings are normalised to Unix (``\\n``) on write.  If the original
      file used Windows line endings (``\\r\\n``), ``str.splitlines()`` strips
      the ``\\r`` on read and the output will use ``\\n`` throughout.  This is
      intentional — jrouter runs on Unix systems.

    Raises:
        FileNotFoundError: if *path* does not exist.
    """
    with open(path, "r", encoding="utf-8") as fh:
        original = fh.read()

    lines = original.splitlines()

    # Find the start of the existing ``peers:`` block (if any).
    peers_start: Optional[int] = None
    peers_end: Optional[int] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("peers:"):
            peers_start = i
            # The block ends at the next top-level key (line that starts with
            # a non-space, non-hyphen character after peers_start), or EOF.
            for j in range(i + 1, len(lines)):
                next_line = lines[j]
                if (
                    next_line
                    and not next_line[0].isspace()
                    and not next_line.startswith("-")
                ):
                    peers_end = j
                    break
            if peers_end is None:
                peers_end = len(lines)
            break

    new_peers_block = _dump_peers_yaml(peers).rstrip("\n").splitlines()

    if peers_start is not None:
        updated = lines[:peers_start] + new_peers_block + lines[peers_end:]
    else:
        # Append, with a blank separator if the file is non-empty.
        if lines and lines[-1].strip() != "":
            updated = lines + [""] + new_peers_block
        else:
            updated = lines + new_peers_block

    return "\n".join(updated) + "\n"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def resolve_address(address: str) -> Optional[str]:
    """Resolve a DNS hostname or validate a bare IP address.

    Returns the resolved IPv4 address string, or ``None`` if the address
    cannot be resolved or is invalid.
    """
    address = address.strip()
    if not address:
        return None

    try:
        result = socket.getaddrinfo(address, None, socket.AF_INET)
        for res in result:
            if res[0] == socket.AF_INET:
                return res[4][0]
    except socket.gaierror:
        # Not resolvable as a hostname — check whether it is already a
        # valid dotted-decimal IPv4 address.
        try:
            socket.inet_aton(address)
            return address
        except OSError:
            return None

    return None


def parse_input(lines: List[str]) -> List[str]:
    """Parse lines from a node-list file and return a list of resolved IPs.

    Each non-blank, non-comment line is expected to start with a hostname or
    IP address (additional columns are ignored).

    Args:
        lines: Raw lines from the input file (newlines need not be stripped).

    Returns:
        A list of resolved IPv4 address strings (duplicates preserved in order).
    """
    peers: List[str] = []

    for line_num, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = line.split()
        address = tokens[0] if tokens else ""
        if not address:
            continue

        resolved = resolve_address(address)
        if resolved:
            logging.debug("Resolved %s -> %s", address, resolved)
            peers.append(resolved)
        else:
            logging.warning(
                "Could not resolve '%s' on line %d — skipping", address, line_num
            )

    return peers


def parse_input_file(path: str) -> List[str]:
    """Read *path* and return a list of resolved IPv4 peer addresses.

    Raises:
        FileNotFoundError: if *path* does not exist.
        OSError: on other read errors.
    """
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    return parse_input(lines)


def build_nodelist(
    input_path: str,
    output_path: Optional[str] = None,
    merge_path: Optional[str] = None,
) -> List[str]:
    """Build a jrouter peer list from *input_path* and write YAML output.

    Args:
        input_path: Path to the text file of hostnames / IP addresses.
        output_path: If given, write a new YAML file at this path.
        merge_path: If given, merge the peer list into an existing YAML file
            at this path (replacing the ``peers`` key in-place).

    Returns:
        The list of resolved peer IP addresses.

    Raises:
        ValueError: If both *output_path* and *merge_path* are supplied.
        FileNotFoundError: If *input_path* or *merge_path* (when merging) do
            not exist.
    """
    if output_path and merge_path:
        raise ValueError("Specify either output_path or merge_path, not both")

    peers = parse_input_file(input_path)

    if not peers:
        logging.warning("No valid peers found in '%s'", input_path)

    if merge_path:
        content = _merge_yaml_peers(merge_path, peers)
        with open(merge_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        logging.info("Merged %d peer(s) into '%s'", len(peers), merge_path)
    elif output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(_dump_peers_yaml(peers))
        logging.info("Wrote %d peer(s) to '%s'", len(peers), output_path)

    return peers


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``nodelist`` CLI subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="globaltalk nodelist",
        description="Convert a GlobalTalk node list to a jrouter YAML configuration",
    )
    parser.add_argument(
        "input",
        help="Input file containing DNS names or IP addresses (one per line)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write a new YAML file at this path (default: stdout)",
    )
    parser.add_argument(
        "-m",
        "--merge",
        help="Merge peer list into an existing YAML file (replaces 'peers' key)",
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

    if args.output and args.merge:
        logging.error("Cannot specify both --output and --merge")
        sys.exit(1)

    try:
        peers = build_nodelist(
            input_path=args.input,
            output_path=args.output,
            merge_path=args.merge,
        )
    except FileNotFoundError as exc:
        logging.error("%s", exc)
        sys.exit(1)
    except ValueError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    # No file target — emit to stdout
    if not args.output and not args.merge:
        sys.stdout.write(_dump_peers_yaml(peers))


if __name__ == "__main__":
    main()
