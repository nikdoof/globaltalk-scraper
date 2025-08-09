#!/usr/bin/env python3
"""
nodelist2jrouter - Convert GlobalTalk node list to jrouter YAML configuration

This script converts a text file containing DNS names and IP addresses
to a YAML file suitable for use with jrouter (AppleTalk protocol support).
"""

import argparse
import socket
import sys
import yaml
import logging


def resolve_address(address: str) -> str | None:
    """Resolve a DNS name or validate an IP address."""
    address = address.strip()
    if not address:
        return None

    try:
        # Try to resolve as hostname first
        result = socket.getaddrinfo(address, None, socket.AF_INET)
        for res in result:
            if res[0] == socket.AF_INET:
                # Return the first valid IPv4 address
                return res[4][0]
    except socket.gaierror:
        # If resolution fails, check if it's already a valid IP
        try:
            socket.inet_aton(address)
            return address
        except socket.error:
            return None


def parse_input_file(input_file: str) -> list[str]:
    """Parse the input text file and extract valid IP addresses."""
    peers = []

    try:
        with open(input_file, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Split by whitespace and take the first token
                address = line.split()[0] if line.split() else ""

                if address:
                    resolved_ip = resolve_address(address)
                    if resolved_ip:
                        peers.append(resolved_ip)
                        logging.debug(f"Resolved {address} -> {resolved_ip}")
                    else:
                        logging.debug(
                            f"Warning: Could not resolve '{address}' on line {line_num}"
                        )

    except FileNotFoundError:
        logging.error(f"Error: Input file '{input_file}' not found")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error reading input file: {e}")
        sys.exit(1)

    return peers


def load_yaml_file(yaml_file: str) -> dict:
    """Load existing YAML file."""
    try:
        with open(yaml_file, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error(f"Error: YAML file '{yaml_file}' not found")
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file: {e}")


def write_yaml_file(data: dict, output_file: str) -> None:
    """Write data to YAML file."""
    try:
        with open(output_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logging.info(
            f"Successfully wrote {len(data.get('peers', []))} peers to '{output_file}'"
        )
    except Exception as e:
        logging.error(f"Error writing output file: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert GlobalTalk node list to jrouter YAML configuration"
    )
    parser.add_argument(
        "input", help="Input text file containing DNS names/IP addresses"
    )
    parser.add_argument("-o", "--output", help="Output YAML file")
    parser.add_argument(
        "-m", "--merge", help="Merge with existing YAML file (replaces peers key)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    if args.output and args.merge:
        logging.error("Cannot specify both --output and --merge")
        return

    # Parse input file and resolve addresses
    peers = parse_input_file(args.input)

    if not peers:
        logging.warning("No valid peers found in input file")

    # Prepare output data
    if args.merge:
        # Load existing YAML and replace peers key
        data = load_yaml_file(args.merge)
        data["peers"] = peers
        write_yaml_file(data, args.merge)
    elif args.output:
        # Create new YAML file with just peers
        data = {"peers": peers}
        write_yaml_file(data, args.output)
    else:
        # Output to stdout
        data = {"peers": peers}
        yaml.dump(data, sys.stdout, default_flow_style=False, sort_keys=False)


if __name__ == "__main__":
    main()
