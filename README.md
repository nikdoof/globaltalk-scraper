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
            "object": "nas-afp",
            "type": "TimeLord",
            "address": "5311.212",
            "socket": "129",
            "zone": "Doofnet"
        },
        {
            "object": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "socket": "128",
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
            "object": "nas-afp",
            "type": "netatalk",
            "address": "5311.212",
            "socket": "4",
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
            "object": "jrouter v0.0.12",
            "type": "AppleRouter",
            "address": "5311.1",
            "socket": "253",
            "zone": "Doofnet"
        }
    ]
}
```