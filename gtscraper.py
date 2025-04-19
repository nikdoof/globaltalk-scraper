#!/usr/bin/env python3
"""
GlobalTalk Scraper

A script that uses netatalk's `getzones` and `nbplkup` to discover devices on
the GlobalTalk network, and create some nice visualisations of the network.

Created for MARCHintosh 2025
"""

import argparse
import concurrent.futures
import json
import logging
import os
import re
import shutil
import subprocess
import sys

NPBLKUP_RESULTS = re.compile(r"^(.*):(.*)\s(\d*\.\d*:\d*)$")


def getzones() -> list[str]:
    """Returns a list of AppleTalk zones using `getzones`"""
    result = subprocess.run(["getzones"], capture_output=True, text=True)
    return [x.strip() for x in result.stdout.split("\n") if x.strip() != ""]


def nbplkup(zone: str) -> list[(str, str)]:
    """Lookup members of a zone, and return a list of name and address tuples"""
    if zone not in getzones():
        logging.warning("%s not currently a known zone", zone)
        return []

    zone_results = []

    # Define the charset for the console as 'mac-roman' to avoid any
    # translation issues with some device names (AsanteTalk and such)
    environ = os.environ.copy()
    environ["ATALK_UNIX_CHARSET"] = "mac-roman"

    cmd = subprocess.run(
        ["nbplkup", "@{0}".format(zone)],
        capture_output=True,
        text=True,
        encoding="mac-roman",
        env=environ,
    )

    # Use regex to split the row nicely
    for node in [
        NPBLKUP_RESULTS.match(x.strip()).groups()
        for x in cmd.stdout.split("\n")
        if x.strip() != ""
    ]:
        object, endpoint_type, address = node
        address, socket = address.split(":")
        zone_results.append(
            {
                "object": object.strip(),
                "type": endpoint_type.strip(),
                "address": address,
                "socket": socket,
                "zone": zone,
            }
        )
    return zone_results


def main():
    parser = argparse.ArgumentParser("gtscraper")
    parser.add_argument(
        "--zone",
        nargs="*",
        required=False,
        default=None,
        help="Scan selected zones",
    )
    parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="Filename to write the resulting JSON to",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="The number of concurrent zone scans to run",
    )
    args = parser.parse_args()

    if args.debug:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.ERROR
    else:
        level = logging.INFO
    logging.basicConfig(level=level, stream=sys.stderr)

    logging.debug("Arguments: %s", args)

    # Check we have the pre-reqs to actually run
    for cmd in ["getzones", "nbplkup"]:
        if not shutil.which(cmd):
            logging.error(
                "%s is missing from your PATH, is netatalk installed and working?", cmd
            )
            return

    # Init the results dict
    zone_results = {
        "format": "v1",
        "zones": getzones(),
        "nodes": [],
    }

    # Subfunction to run
    def lookup_zone(zone) -> list[(str, str)]:
        if args.zone and zone != args.zone:
            return None
        logging.info("Scanning %s", zone)
        return nbplkup(zone)

    # Use ThreadPoolExecutor for concurrent execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(lookup_zone, zone): zone for zone in zone_results["zones"]
        }

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                zone_results["nodes"].extend(result)

    nodes = len(zone_results["nodes"])
    zones = len(zone_results["zones"])

    print("{0} zones, {1} nodes".format(zones, nodes), file=sys.stderr)

    # Dump out the resulting JSON to stdout
    args.output.write(json.dumps(zone_results))


if __name__ == "__main__":
    main()
