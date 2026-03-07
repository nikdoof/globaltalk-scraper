"""
Shared test fixtures and sample data for the globaltalk test suite.
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Sample snapshot data
# ---------------------------------------------------------------------------

# A minimal but representative snapshot matching the v1 format produced by
# globaltalk scrape.  Used as the baseline for metrics and visualise tests.
SNAPSHOT_BASIC: Dict[str, Any] = {
    "format": "v1",
    "generated_at": "2025-01-15T12:00:00+00:00",
    "zones": ["Doofnet", "RetroZone"],
    "nodes": [
        # Doofnet — multi-endpoint device (nas-afp appears 4 times = multihomed)
        {
            "object": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "socket": "128",
            "zone": "Doofnet",
        },
        {
            "object": "nas-afp",
            "type": "Workstation",
            "address": "5311.212",
            "socket": "4",
            "zone": "Doofnet",
        },
        {
            "object": "nas-afp",
            "type": "TimeLord",
            "address": "5311.212",
            "socket": "129",
            "zone": "Doofnet",
        },
        {
            "object": "nas-afp",
            "type": "netatalk",
            "address": "5311.212",
            "socket": "4",
            "zone": "Doofnet",
        },
        {
            "object": "HP LJ Pro 200 Color",
            "type": "LaserWriter",
            "address": "5311.100",
            "socket": "130",
            "zone": "Doofnet",
        },
        # jrouter — used to test jrouter_versions metric
        {
            "object": "jrouter v0.0.12",
            "type": "AppleRouter",
            "address": "5311.1",
            "socket": "253",
            "zone": "Doofnet",
        },
        # RetroZone — single device, single endpoint
        {
            "object": "retro-mac",
            "type": "Workstation",
            "address": "6100.5",
            "socket": "4",
            "zone": "RetroZone",
        },
    ],
}

# A snapshot with no generated_at field — tests graceful degradation of the
# snapshot_age_seconds metric.
SNAPSHOT_NO_TIMESTAMP: Dict[str, Any] = {
    "format": "v1",
    "zones": ["Doofnet"],
    "nodes": [
        {
            "object": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "socket": "128",
            "zone": "Doofnet",
        },
    ],
}

# A snapshot with an unknown format version — tests that a warning is issued
# but processing still proceeds.
SNAPSHOT_UNKNOWN_FORMAT: Dict[str, Any] = {
    "format": "v99",
    "generated_at": "2025-01-15T12:00:00+00:00",
    "zones": ["Doofnet"],
    "nodes": [
        {
            "object": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "socket": "128",
            "zone": "Doofnet",
        },
    ],
}

# A snapshot with two jrouter versions — tests that the version counter
# handles multiple distinct versions correctly.
SNAPSHOT_MULTI_JROUTER: Dict[str, Any] = {
    "format": "v1",
    "generated_at": "2025-01-15T12:00:00+00:00",
    "zones": ["ZoneA", "ZoneB"],
    "nodes": [
        {
            "object": "jrouter v0.0.12",
            "type": "AppleRouter",
            "address": "1.1",
            "socket": "253",
            "zone": "ZoneA",
        },
        {
            "object": "jrouter v0.0.12",
            "type": "AppleRouter",
            "address": "1.2",
            "socket": "253",
            "zone": "ZoneA",
        },
        {
            "object": "jrouter v0.0.13",
            "type": "AppleRouter",
            "address": "2.1",
            "socket": "253",
            "zone": "ZoneB",
        },
    ],
}

# An empty snapshot — tests that all metrics are produced with zero values and
# that the visualisers don't crash on empty input.
SNAPSHOT_EMPTY: Dict[str, Any] = {
    "format": "v1",
    "generated_at": "2025-01-15T12:00:00+00:00",
    "zones": [],
    "nodes": [],
}

# ---------------------------------------------------------------------------
# Sample nbplkup output lines
# ---------------------------------------------------------------------------

# Well-formed lines as produced by nbplkup.
NBPLKUP_VALID_LINES: List[str] = [
    "nas-afp:AFPServer                              5311.212:128",
    "nas-afp:Workstation                            5311.212:4",
    "HP LJ Pro 200 Color:LaserWriter                5311.100:130",
    "jrouter v0.0.12:AppleRouter                    5311.1:253",
    # Object name with a colon in it — the regex should handle this because it
    # is greedy on the left and anchors on the address:socket at the right.
    "My Server: v2:AFPServer                        9999.1:128",
]

# Lines that should be silently skipped.
NBPLKUP_INVALID_LINES: List[str] = [
    "",
    "   ",
    "this line has no address at the end",
    "missingcolon 1234.56:78",
]

# ---------------------------------------------------------------------------
# Sample node-list file content (as lists of lines for parse_input)
# ---------------------------------------------------------------------------

NODELIST_LINES_BASIC: List[str] = [
    "# GlobalTalk peer nodes\n",
    "127.0.0.1\n",
    "192.168.1.1\n",
    "\n",
    "  \n",  # whitespace-only line — should be skipped
]

NODELIST_LINES_WITH_COMMENTS: List[str] = [
    "127.0.0.1   # loopback — always present\n",
    "# 10.0.0.1  this whole line is a comment\n",
    "192.168.1.254\n",
]

NODELIST_LINES_EMPTY: List[str] = [
    "# Only comments here\n",
    "\n",
]

# ---------------------------------------------------------------------------
# Sample jrouter YAML content (as strings for _merge_yaml_peers tests)
# ---------------------------------------------------------------------------

JROUTER_YAML_WITH_PEERS = """\
network:
  zone: Doofnet
  net: 5311

peers:
- 10.0.0.1
- 10.0.0.2

some_other_key: value
"""

JROUTER_YAML_WITHOUT_PEERS = """\
network:
  zone: Doofnet
  net: 5311

some_other_key: value
"""

JROUTER_YAML_PEERS_AT_EOF = """\
network:
  zone: Doofnet

peers:
- 10.0.0.1
"""
