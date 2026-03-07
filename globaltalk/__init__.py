"""
GlobalTalk toolkit

A collection of tools for interacting with the GlobalTalk network — a large,
community-operated AppleTalk network connecting retro Apple computers and
modern applications worldwide.

Submodules
----------
scrape
    Discover zones and nodes on the GlobalTalk network using netatalk's
    ``getzones`` and ``nbplkup`` utilities.

metrics
    Convert a GlobalTalk JSON snapshot into Prometheus metrics for use with
    the node_exporter textfile collector.

nodelist
    Convert a list of hostnames / IP addresses into a jrouter-compatible
    YAML peer configuration.

visualise
    Convert a GlobalTalk JSON snapshot into visualisation formats (Mermaid
    mindmap, D3.js hierarchical JSON).
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "scrape",
    "metrics",
    "nodelist",
    "visualise",
]
