#!/usr/bin/env python3
"""
GlobalTalk Scraper

A script that uses netatalk's `getzones` and `nbplkup` to discover devices on
the GlobalTalk network, and create some nice visualisations of the network.

Created for MARCHintosh 2025
"""

import logging
import subprocess
import re
import json
import sys
import os

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
        name, endpoint_type, address = node
        address, port = address.split(":")
        zone_results.append(
            {
                "name": name.strip(),
                "type": endpoint_type.strip(),
                "address": address,
                "port": port,
                "zone": zone,
            }
        )
    return zone_results


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    zone_results = {}
    
    # Iterate the zones and scan them
    for zone in getzones():
        logging.info("Scanning %s", zone)
        node_data = nbplkup(zone) 
        zone_results[zone] = node_data

    nodes = sum([len(x) for x in zone_results.values()])
    zones = len(zone_results.keys())

    print('{0} zones, {1} nodes'.format(zones, nodes), file=sys.stderr)

    # Dump out the resulting JSON to stdout
    sys.stdout.write(json.dumps(zone_results))


if __name__ == "__main__":
    main()
