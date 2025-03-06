#!/usr/bin/env python3
"""
Reads a GlobalTalk Scraper JSON file and create a mermaid graph
with the data
"""

import argparse
import sys
import json


def jsontomermaid(gts_obj) -> str:
    map = ""
    for zone in gts_obj["zones"]:
        nodes = [x for x in gts_obj["nodes"] if x["zone"] == zone]
        if not len(nodes):
            continue
        map += "  {0}\n{1}\n".format(
            zone, "\n".join(set(["    " + x["object"] for x in nodes]))
        )

    return "```mermaid\nmindmap\nroot)GlobalTalk(\n{0}\n```".format(map)


def main():
    parser = argparse.ArgumentParser("mermaid")
    parser.add_argument("json", type=argparse.FileType("r"))
    parser.add_argument("--output", type=argparse.FileType("w"), default=sys.stdout)
    args = parser.parse_args()

    obj = json.load(args.json)
    args.output.write(jsontomermaid(obj))


if __name__ == "__main__":
    main()
