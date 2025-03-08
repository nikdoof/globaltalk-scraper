#!/usr/bin/env python3
"""
Reads a GlobalTalk Scraper JSON file and dumps a hierarchical layout for use with D3
"""

import argparse
import sys
import json

# Object types to include in the export
INCLUDED_TYPES = ['AFPServer', 'Workstation', 'ImageWriter', 'LaserWriter', 'Darwin']


def main():
    parser = argparse.ArgumentParser("sunburst")
    parser.add_argument("json", type=argparse.FileType("r"))
    parser.add_argument("--output", type=argparse.FileType("w"), default=sys.stdout)
    args = parser.parse_args()

    obj = json.load(args.json)

    data = {
        "name": "GlobalTalk",
        "children": [
            {
                "name": x,
                "children": [
                    {"name": "{0} - {1}".format(y["object"], y['type']), "children": []}
                    for y in obj["nodes"]
                    if y["zone"] == x and y['type'] in INCLUDED_TYPES
                ],
            }
            for x in obj["zones"]
        ],
    }

    args.output.write(json.dumps(data))


if __name__ == "__main__":
    main()
