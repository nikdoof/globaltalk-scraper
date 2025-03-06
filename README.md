# GlobalTalk Scraper

A script to scrape out a AppleTalk network layout using `netatalk` tools `getzones` and `nbplkup`. 

## Running

This requires a working `netatalk` installation to work correctly.

## Example Output

This is an example of the JSON file produced, filtered down to one Zone.

```json
{
    "format": "v1",
    "zones": [
        "Doofnet",
    ],
    "nodes": [
        {
            "name": "nas-afp",
            "type": "TimeLord",
            "address": "5311.212",
            "port": "129",
            "zone": "Doofnet"
        },
        {
            "name": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "port": "128",
            "zone": "Doofnet"
        },
        {
            "name": "HP LJ Pro 200 Color",
            "type": "LaserWriter",
            "address": "5311.212",
            "port": "130",
            "zone": "Doofnet"
        },
        {
            "name": "nas-afp",
            "type": "netatalk",
            "address": "5311.212",
            "port": "4",
            "zone": "Doofnet"
        },
        {
            "name": "nas-afp",
            "type": "Workstation",
            "address": "5311.212",
            "port": "4",
            "zone": "Doofnet"
        },
        {
            "name": "jrouter v0.0.12",
            "type": "AppleRouter",
            "address": "5311.1",
            "port": "253",
            "zone": "Doofnet"
        }
    ]
}
```