#!/usr/bin/env python3
"""
GlobalTalk CLI

Unified entry point for the globaltalk toolkit.

Usage:
    globaltalk <command> [options]

Commands:
    scrape      Scrape the GlobalTalk network and emit a JSON snapshot
    metrics     Convert a JSON snapshot into Prometheus metrics
    nodelist    Convert a node list into a jrouter YAML configuration
"""

import sys

from globaltalk import __version__

COMMANDS = {
    "scrape": "globaltalk.scrape",
    "metrics": "globaltalk.metrics",
    "nodelist": "globaltalk.nodelist",
    "visualise": "globaltalk.visualise",
}

HELP = """\
usage: globaltalk <command> [options]

GlobalTalk network toolkit.

commands:
  scrape      Scrape the GlobalTalk network and emit a JSON snapshot
  metrics     Convert a JSON snapshot into Prometheus metrics
  nodelist    Convert a node list into a jrouter YAML configuration
  visualise   Convert a JSON snapshot into a visualisation format

Run 'globaltalk <command> --help' for help on a specific command.
Run 'globaltalk --version' to print the version and exit.
"""


def main() -> None:
    # Pull the subcommand out of argv before delegating, so that each
    # submodule's argparse instance only sees its own arguments.
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.stdout.write(HELP)
        sys.exit(0)

    if sys.argv[1] in ("-V", "--version"):
        sys.stdout.write(f"globaltalk {__version__}\n")
        sys.exit(0)

    command = sys.argv[1]

    if command not in COMMANDS:
        sys.stderr.write(f"globaltalk: unknown command '{command}'\n\n")
        sys.stderr.write(HELP)
        sys.exit(1)

    # Replace argv so the subcommand's own argparse sees a clean slate.
    sys.argv = [f"globaltalk {command}", *sys.argv[2:]]

    module_name = COMMANDS[command]

    # Import lazily so that only the required submodule is loaded.
    import importlib

    module = importlib.import_module(module_name)
    module.main()


if __name__ == "__main__":
    main()
