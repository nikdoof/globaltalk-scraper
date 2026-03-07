# GlobalTalk Toolkit

A collection of tools for the [GlobalTalk](https://github.com/nikdoof/globaltalk-scraper) network — a large, community-operated AppleTalk network connecting retro Apple computers and modern applications worldwide.

## Tools

| Command | Description |
|---|---|
| `globaltalk scrape` | Scrape the GlobalTalk network using netatalk and emit a JSON snapshot |
| `globaltalk metrics` | Convert a JSON snapshot into Prometheus metrics for node_exporter |
| `globaltalk nodelist` | Convert a list of hostnames/IPs into a jrouter YAML peer configuration |

## Requirements

- Python 3.13+
- `netatalk` installed and working (required by `globaltalk scrape` and `globaltalk metrics` live mode)

## Installation

### With uv (recommended)

```sh
uv tool install globaltalk
```

Or run without installing:

```sh
uvx globaltalk --help
```

### With pip

```sh
pip install globaltalk
```

### With Nix / NixOS

Run directly from the flake without installing:

```sh
nix run github:nikdoof/globaltalk-scraper -- --help
```

Add to a NixOS system configuration:

```nix
{
  inputs.globaltalk.url = "github:nikdoof/globaltalk-scraper";

  outputs = { nixpkgs, globaltalk, ... }: {
    nixosConfigurations.mymachine = nixpkgs.lib.nixosSystem {
      modules = [
        globaltalk.nixosModules.default
        {
          # Run a scrape every 5 minutes and write Prometheus metrics
          services.globaltalk.scrape.enable = true;
          services.globaltalk.metrics.enable = true;
        }
      ];
    };
  };
}
```

See [NixOS Module Options](#nixos-module) below for the full option set.

---

## Usage

### `globaltalk scrape`

Discovers all zones and nodes on the network using netatalk's `getzones` and `nbplkup`, and emits a JSON snapshot.

```sh
# Scrape all zones, print JSON to stdout
globaltalk scrape

# Write to a file
globaltalk scrape --output /var/lib/globaltalk/scrape.json

# Restrict to specific zones
globaltalk scrape --zone Doofnet RetroZone

# Tune concurrency (default: 10 worker threads)
globaltalk scrape --workers 20
```

**Options:**

```
positional arguments:
  (none)

options:
  --zone [ZONE ...]   Restrict scan to these zone names (default: all zones)
  --output FILE       File to write JSON output to (default: stdout)
  --workers N         Number of concurrent zone scans (default: 10)
  --no-dedupe         Disable removal of duplicate nodes
  --debug             Enable debug logging
  --quiet             Suppress info logging
```

---

### `globaltalk metrics`

Converts a GlobalTalk JSON snapshot into Prometheus metrics for use with
[node_exporter's textfile collector](https://github.com/prometheus/node_exporter#textfile-collector).

Can read from a pre-existing snapshot file, or scrape the network live.

```sh
# From a snapshot file
globaltalk metrics /var/lib/globaltalk/scrape.json

# Write to a .prom file
globaltalk metrics /var/lib/globaltalk/scrape.json \
  --output /var/lib/prometheus/node-exporter/globaltalk.prom

# Live scrape — no intermediate file needed
globaltalk metrics

# Live scrape restricted to specific zones
globaltalk metrics --zone Doofnet RetroZone

# Custom metric name prefix (default: globaltalk)
globaltalk metrics snapshot.json --prefix gt
```

**Options:**

```
positional arguments:
  filename            Path to a GlobalTalk JSON snapshot (omit to scrape live)

options:
  --output FILE       File to write metrics to (default: stdout)
  --prefix PREFIX     Metric name prefix (default: globaltalk)
  --debug             Enable debug logging
  --quiet             Suppress info logging

live scrape options:
  --zone [ZONE ...]   Restrict live scrape to these zone names (default: all zones)
  --workers N         Number of concurrent zone scans (default: 10)
  --no-dedupe         Disable duplicate-node removal during live scrape
```

**Metrics produced:**

| Metric | Type | Description |
|---|---|---|
| `globaltalk_zones` | gauge | Total number of AppleTalk zones |
| `globaltalk_unique_devices` | gauge | Number of unique devices by AppleTalk address |
| `globaltalk_total_nodes` | gauge | Total number of registered network endpoints |
| `globaltalk_zone_devices{zone}` | gauge | Number of endpoints per zone |
| `globaltalk_device_types{type}` | gauge | Number of endpoints by NBP type |
| `globaltalk_multihomed_devices` | gauge | Devices with more than one registered endpoint |
| `globaltalk_jrouter_versions{version}` | gauge | Count of jRouter instances by version |

---

### `globaltalk nodelist`

Converts a plain-text list of hostnames or IP addresses into a
[jrouter](https://github.com/sfiera/jrouter)-compatible YAML peer configuration.
jrouter is a modern recreation of Apple Internet Router (AIR) used within GlobalTalk.

```sh
# Print YAML to stdout
globaltalk nodelist peers.txt

# Write to a new file
globaltalk nodelist peers.txt --output jrouter.yaml

# Merge into an existing jrouter config (replaces the 'peers' key in-place)
globaltalk nodelist peers.txt --merge /etc/jrouter/config.yaml
```

**Input file format** — one hostname or IP address per line, leading columns only.
Blank lines and lines starting with `#` are ignored.

```
# GlobalTalk peers
router.example.com
192.168.1.1
atalk.friend.net   # comments after the address are fine too
```

**Options:**

```
positional arguments:
  input               Input file containing DNS names or IP addresses

options:
  -o, --output FILE   Write a new YAML file at this path (default: stdout)
  -m, --merge FILE    Merge peer list into an existing YAML file
  --debug             Enable debug logging
  --quiet             Suppress info logging
```

---

## JSON Snapshot Format

The `globaltalk scrape` command produces a JSON file consumed by `globaltalk metrics`
and any other tooling. The current format version is `v1`.

```json
{
  "format": "v1",
  "zones": [
    "Doofnet",
    "RetroZone"
  ],
  "nodes": [
    {
      "object": "nas-afp",
      "type": "AFPServer",
      "address": "5311.212",
      "socket": "128",
      "zone": "Doofnet"
    },
    {
      "object": "nas-afp",
      "type": "Workstation",
      "address": "5311.212",
      "socket": "4",
      "zone": "Doofnet"
    },
    {
      "object": "nas-afp",
      "type": "TimeLord",
      "address": "5311.212",
      "socket": "129",
      "zone": "Doofnet"
    },
    {
      "object": "HP LJ Pro 200 Color",
      "type": "LaserWriter",
      "address": "5311.212",
      "socket": "130",
      "zone": "Doofnet"
    },
    {
      "object": "jrouter v0.0.12",
      "type": "AppleRouter",
      "address": "5311.1",
      "socket": "253",
      "zone": "Doofnet"
    }
  ]
}
```

| Field | Description |
|---|---|
| `format` | Schema version — always `"v1"` |
| `zones` | All AppleTalk zones visible from this host |
| `nodes[].object` | NBP object name |
| `nodes[].type` | NBP type string (e.g. `AFPServer`, `Workstation`, `AppleRouter`) |
| `nodes[].address` | AppleTalk network.node address (e.g. `5311.212`) |
| `nodes[].socket` | NBP socket number |
| `nodes[].zone` | Zone this endpoint was discovered in |

---

## NixOS Module

When using the Nix flake, a NixOS module is provided under `nixosModules.default`.

### `services.globaltalk.scrape`

| Option | Type | Default | Description |
|---|---|---|---|
| `enable` | bool | `false` | Enable the scraper systemd timer |
| `interval` | string | `"5m"` | How often to scrape (systemd calendar expression) |
| `outputFile` | string | `/var/lib/globaltalk/scrape.json` | Path for the JSON snapshot |
| `workers` | int | `10` | Concurrent zone-scan threads |
| `zones` | list of string | `[]` | Zones to scan (empty = all) |
| `extraArgs` | list of string | `[]` | Extra arguments passed to `globaltalk scrape` |

### `services.globaltalk.metrics`

| Option | Type | Default | Description |
|---|---|---|---|
| `enable` | bool | `false` | Enable the metrics generator |
| `inputFile` | string | scrape `outputFile` | JSON snapshot to read |
| `outputFile` | string | `/var/lib/prometheus/node-exporter/globaltalk.prom` | Path for the `.prom` file |
| `prefix` | string | `"globaltalk"` | Metric name prefix |
| `extraArgs` | list of string | `[]` | Extra arguments passed to `globaltalk metrics` |

When both `scrape` and `metrics` are enabled, the metrics generator runs automatically after each scrape.

---

## Development

```sh
# Set up the environment
uv sync

# Run the CLI
uv run globaltalk --help

# Lint
uv run ruff check
```
