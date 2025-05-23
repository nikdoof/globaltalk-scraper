#!/usr/bin/env python3

import argparse
import json
import sys
import collections


def main():
    parser = argparse.ArgumentParser(
        description="Parses a GlobalTalk data JSON into Prometheus Metrics"
    )
    parser.add_argument("filename", help="Path to the JSON file")
    parser.add_argument("--output", type=argparse.FileType("w"), default=sys.stdout)
    args = parser.parse_args()

    try:
        with open(args.filename, "r", encoding="utf-8") as file:
            globaltalk_data = json.load(file)
    except FileNotFoundError:
        print(f"Error: File '{args.filename}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON - {e}")
        sys.exit(1)

    # Number of zones
    args.output.write('globaltalk_zones {0}\n'.format(len(globaltalk_data['zones'])))

    # Unique Devices
    devices = collections.Counter(node.get("address", "Unknown") for node in globaltalk_data['nodes'])
    args.output.write('globaltalk_unique_devices {0}\n'.format(len(devices)))

    # Endpoints per zone
    zone_counts = collections.Counter(node.get("zone", "Unknown") for node in globaltalk_data['nodes'])
    for k, v in zone_counts.items():
        args.output.write('globaltalk_zone_devices{{zone="{0}"}} {1}\n'.format(k, v))

    # Count of device types
    device_type_counts = collections.Counter(node.get("type", "Unknown") for node in globaltalk_data['nodes'])
    for k, v in device_type_counts.items():
        args.output.write('globaltalk_device_types{{type="{0}"}} {1}\n'.format(k, v))

    # jRouter versions
    jrouter_versions = collections.Counter(node.get("object", "Unknown") for node in globaltalk_data['nodes'] if node.get("object", "Unknown").startswith('jrouter'))
    for k, v in jrouter_versions.items():
        args.output.write('globaltalk_jrouter_versions{{version="{0}"}} {1}\n'.format(k.replace('jrouter ', ''), v))

if __name__ == "__main__":
    main()
