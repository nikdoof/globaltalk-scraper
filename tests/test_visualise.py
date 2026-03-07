"""
Tests for globaltalk.visualise

Covers:
  - to_mermaid (zone branches, leaf deduplication, excluded types,
                include_infrastructure flag, empty snapshot, special characters)
  - to_d3 (tree structure, included types filter, empty zones omitted,
           all-types mode, empty snapshot)
"""

import unittest

from globaltalk.visualise import (
    _D3_INCLUDED_TYPES,
    _MERMAID_EXCLUDED_TYPES,
    to_d3,
    to_mermaid,
)
from tests.fixtures import (
    SNAPSHOT_BASIC,
    SNAPSHOT_EMPTY,
    SNAPSHOT_MULTI_JROUTER,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _snapshot(zones, nodes):
    """Build a minimal snapshot dict from raw zones and nodes lists."""
    return {"format": "v1", "zones": zones, "nodes": nodes}


def _node(obj, typ, address, zone, socket="4"):
    return {
        "object": obj,
        "type": typ,
        "address": address,
        "socket": socket,
        "zone": zone,
    }


# ---------------------------------------------------------------------------
# to_mermaid
# ---------------------------------------------------------------------------


class TestToMermaidStructure(unittest.TestCase):
    """Verify the top-level Mermaid output structure."""

    def test_output_is_fenced_mermaid_block(self):
        out = to_mermaid(SNAPSHOT_BASIC)
        self.assertTrue(out.startswith("```mermaid\n"))
        self.assertTrue(out.strip().endswith("```"))

    def test_output_contains_mindmap_directive(self):
        out = to_mermaid(SNAPSHOT_BASIC)
        self.assertIn("mindmap\n", out)

    def test_output_contains_globaltalk_root(self):
        out = to_mermaid(SNAPSHOT_BASIC)
        self.assertIn("root)GlobalTalk(", out)

    def test_output_ends_with_newline(self):
        self.assertTrue(to_mermaid(SNAPSHOT_BASIC).endswith("\n"))

    def test_empty_snapshot_produces_minimal_block(self):
        out = to_mermaid(SNAPSHOT_EMPTY)
        self.assertIn("```mermaid", out)
        self.assertIn("mindmap", out)
        self.assertIn("root)GlobalTalk(", out)


class TestToMermaidZones(unittest.TestCase):
    """Verify that zones appear as branches."""

    def test_non_empty_zone_appears(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        out = to_mermaid(data)
        self.assertIn("Doofnet", out)

    def test_zone_with_no_included_nodes_omitted(self):
        # A zone whose only nodes are of excluded types should not appear.
        data = _snapshot(
            ["InfraOnly"],
            [_node("jrouter v1", "AppleRouter", "1.1", "InfraOnly")],
        )
        out = to_mermaid(data)
        self.assertNotIn("InfraOnly", out)

    def test_multiple_zones_both_present(self):
        data = _snapshot(
            ["ZoneA", "ZoneB"],
            [
                _node("mac-a", "Workstation", "1.1", "ZoneA"),
                _node("mac-b", "Workstation", "2.1", "ZoneB"),
            ],
        )
        out = to_mermaid(data)
        self.assertIn("ZoneA", out)
        self.assertIn("ZoneB", out)

    def test_zone_ordering_matches_snapshot(self):
        data = _snapshot(
            ["ZoneB", "ZoneA"],
            [
                _node("x", "Workstation", "1.1", "ZoneB"),
                _node("y", "Workstation", "2.1", "ZoneA"),
            ],
        )
        out = to_mermaid(data)
        self.assertLess(out.index("ZoneB"), out.index("ZoneA"))


class TestToMermaidLeaves(unittest.TestCase):
    """Verify leaf (device) handling."""

    def test_device_object_name_appears_as_leaf(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        out = to_mermaid(data)
        self.assertIn("nas-afp", out)

    def test_multi_endpoint_device_appears_only_once(self):
        # nas-afp registers multiple NBP endpoints but should be a single leaf.
        data = _snapshot(
            ["Doofnet"],
            [
                _node("nas-afp", "AFPServer", "1.1", "Doofnet"),
                _node("nas-afp", "Workstation", "1.1", "Doofnet"),
                _node("nas-afp", "TimeLord", "1.1", "Doofnet"),
            ],
        )
        out = to_mermaid(data, exclude_types=[])
        # Count occurrences — should appear exactly once as a leaf.
        # The zone label also contains the name in quotes so we count the
        # leaf-specific indented form.
        leaf_count = out.count('"nas-afp"')
        self.assertEqual(leaf_count, 1)

    def test_different_devices_both_appear(self):
        data = _snapshot(
            ["Doofnet"],
            [
                _node("nas-afp", "AFPServer", "1.1", "Doofnet"),
                _node("HP Printer", "LaserWriter", "1.2", "Doofnet"),
            ],
        )
        out = to_mermaid(data)
        self.assertIn("nas-afp", out)
        self.assertIn("HP Printer", out)


class TestToMermaidExcludedTypes(unittest.TestCase):
    """Verify the default and custom type exclusion logic."""

    def test_default_excluded_types_not_in_output(self):
        for typ in _MERMAID_EXCLUDED_TYPES:
            data = _snapshot(
                ["Doofnet"],
                [_node("infra-device", typ, "1.1", "Doofnet")],
            )
            out = to_mermaid(data)
            with self.subTest(excluded_type=typ):
                self.assertNotIn("infra-device", out)

    def test_include_infrastructure_flag_shows_excluded_types(self):
        data = _snapshot(
            ["Doofnet"],
            [
                _node("workstation", "Workstation", "1.1", "Doofnet"),
                _node("jrouter v1", "AppleRouter", "1.2", "Doofnet"),
            ],
        )
        out = to_mermaid(data, exclude_types=[])
        self.assertIn("jrouter v1", out)

    def test_custom_exclude_list_applied(self):
        data = _snapshot(
            ["Doofnet"],
            [
                _node("a-printer", "LaserWriter", "1.1", "Doofnet"),
                _node("a-mac", "Workstation", "1.2", "Doofnet"),
            ],
        )
        out = to_mermaid(data, exclude_types=["LaserWriter"])
        self.assertNotIn("a-printer", out)
        self.assertIn("a-mac", out)

    def test_empty_exclude_list_includes_all_types(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("jrouter v1", "AppleRouter", "1.1", "Doofnet")],
        )
        out = to_mermaid(data, exclude_types=[])
        self.assertIn("jrouter v1", out)

    def test_afpserver_included_by_default(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        out = to_mermaid(data)
        self.assertIn("nas-afp", out)


class TestToMermaidLabelEscaping(unittest.TestCase):
    """Verify that special characters in names are escaped for Mermaid."""

    def test_double_quote_in_object_name_escaped(self):
        data = _snapshot(
            ["Doofnet"],
            [_node('My "Special" Mac', "Workstation", "1.1", "Doofnet")],
        )
        out = to_mermaid(data)
        # The raw double-quote must not appear unescaped inside a label string.
        # Our escaping wraps in double-quotes and escapes internal quotes.
        self.assertNotIn('"My "Special" Mac"', out)
        self.assertIn('\\"', out)

    def test_double_quote_in_zone_name_escaped(self):
        data = _snapshot(
            ['Zone"A'],
            [_node("mac", "Workstation", "1.1", 'Zone"A')],
        )
        out = to_mermaid(data)
        self.assertIn('\\"', out)

    def test_snapshot_basic_produces_output(self):
        # Smoke test: SNAPSHOT_BASIC should not raise and should produce output.
        out = to_mermaid(SNAPSHOT_BASIC)
        self.assertGreater(len(out), 50)


# ---------------------------------------------------------------------------
# to_d3
# ---------------------------------------------------------------------------


class TestToD3Structure(unittest.TestCase):
    """Verify the top-level D3 output structure."""

    def test_returns_dict(self):
        result = to_d3(SNAPSHOT_BASIC)
        self.assertIsInstance(result, dict)

    def test_root_name_is_globaltalk(self):
        result = to_d3(SNAPSHOT_BASIC)
        self.assertEqual(result["name"], "GlobalTalk")

    def test_has_children_key(self):
        result = to_d3(SNAPSHOT_BASIC)
        self.assertIn("children", result)

    def test_children_is_list(self):
        result = to_d3(SNAPSHOT_BASIC)
        self.assertIsInstance(result["children"], list)

    def test_empty_snapshot_has_empty_children(self):
        result = to_d3(SNAPSHOT_EMPTY)
        self.assertEqual(result["children"], [])

    def test_zone_entries_have_name_and_children(self):
        result = to_d3(SNAPSHOT_BASIC)
        for zone_entry in result["children"]:
            with self.subTest(zone=zone_entry.get("name")):
                self.assertIn("name", zone_entry)
                self.assertIn("children", zone_entry)


class TestToD3Zones(unittest.TestCase):
    """Verify zone-level entries."""

    def test_zones_with_included_nodes_appear(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        result = to_d3(data)
        zone_names = [z["name"] for z in result["children"]]
        self.assertIn("Doofnet", zone_names)

    def test_zones_with_no_included_nodes_omitted(self):
        # A zone that only has AppleRouter nodes (not in default included set)
        # should not appear in the output.
        data = _snapshot(
            ["InfraZone"],
            [_node("jrouter v1", "AppleRouter", "1.1", "InfraZone")],
        )
        result = to_d3(data)
        zone_names = [z["name"] for z in result["children"]]
        self.assertNotIn("InfraZone", zone_names)

    def test_empty_zone_omitted(self):
        # A zone listed in zones but with no nodes at all should not appear.
        data = _snapshot(
            ["EmptyZone", "Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        result = to_d3(data)
        zone_names = [z["name"] for z in result["children"]]
        self.assertNotIn("EmptyZone", zone_names)
        self.assertIn("Doofnet", zone_names)

    def test_zone_ordering_matches_snapshot(self):
        data = _snapshot(
            ["ZoneB", "ZoneA"],
            [
                _node("x", "AFPServer", "1.1", "ZoneB"),
                _node("y", "Workstation", "2.1", "ZoneA"),
            ],
        )
        result = to_d3(data)
        zone_names = [z["name"] for z in result["children"]]
        self.assertEqual(zone_names.index("ZoneB"), 0)
        self.assertEqual(zone_names.index("ZoneA"), 1)


class TestToD3Nodes(unittest.TestCase):
    """Verify node-level (leaf) entries within zones."""

    def test_node_name_is_object_dash_type(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        result = to_d3(data)
        zone = result["children"][0]
        node = zone["children"][0]
        self.assertEqual(node["name"], "nas-afp - AFPServer")

    def test_node_has_value_of_one(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        result = to_d3(data)
        node = result["children"][0]["children"][0]
        self.assertEqual(node["value"], 1)

    def test_multiple_nodes_in_zone(self):
        data = _snapshot(
            ["Doofnet"],
            [
                _node("mac-a", "Workstation", "1.1", "Doofnet"),
                _node("mac-b", "Workstation", "1.2", "Doofnet"),
            ],
        )
        result = to_d3(data)
        zone = result["children"][0]
        self.assertEqual(len(zone["children"]), 2)

    def test_nodes_assigned_to_correct_zone(self):
        data = _snapshot(
            ["ZoneA", "ZoneB"],
            [
                _node("mac-a", "Workstation", "1.1", "ZoneA"),
                _node("mac-b", "AFPServer", "2.1", "ZoneB"),
            ],
        )
        result = to_d3(data)
        by_zone = {z["name"]: z["children"] for z in result["children"]}
        self.assertEqual(len(by_zone["ZoneA"]), 1)
        self.assertEqual(by_zone["ZoneA"][0]["name"], "mac-a - Workstation")
        self.assertEqual(len(by_zone["ZoneB"]), 1)
        self.assertEqual(by_zone["ZoneB"][0]["name"], "mac-b - AFPServer")


class TestToD3IncludedTypes(unittest.TestCase):
    """Verify the included_types filter."""

    def test_default_included_types_present(self):
        for typ in _D3_INCLUDED_TYPES:
            data = _snapshot(
                ["Doofnet"],
                [_node("device", typ, "1.1", "Doofnet")],
            )
            result = to_d3(data)
            with self.subTest(included_type=typ):
                self.assertEqual(len(result["children"]), 1)
                self.assertEqual(len(result["children"][0]["children"]), 1)

    def test_applerouter_excluded_by_default(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("jrouter v1", "AppleRouter", "1.1", "Doofnet")],
        )
        result = to_d3(data)
        self.assertEqual(result["children"], [])

    def test_all_types_flag_includes_applerouter(self):
        data = _snapshot(
            ["Doofnet"],
            [_node("jrouter v1", "AppleRouter", "1.1", "Doofnet")],
        )
        result = to_d3(data, include_types=[])
        zone_names = [z["name"] for z in result["children"]]
        self.assertIn("Doofnet", zone_names)

    def test_custom_include_list_applied(self):
        data = _snapshot(
            ["Doofnet"],
            [
                _node("a-printer", "LaserWriter", "1.1", "Doofnet"),
                _node("a-mac", "Workstation", "1.2", "Doofnet"),
            ],
        )
        result = to_d3(data, include_types=["LaserWriter"])
        zone = result["children"][0]
        node_names = [n["name"] for n in zone["children"]]
        self.assertIn("a-printer - LaserWriter", node_names)
        self.assertNotIn("a-mac - Workstation", node_names)

    def test_none_include_types_uses_default(self):
        # Passing include_types=None should behave identically to the default.
        data = _snapshot(
            ["Doofnet"],
            [_node("nas-afp", "AFPServer", "1.1", "Doofnet")],
        )
        result_default = to_d3(data)
        result_none = to_d3(data, include_types=None)
        self.assertEqual(result_default, result_none)

    def test_empty_include_list_includes_all_types(self):
        data = _snapshot(
            ["Doofnet"],
            [
                _node("mac", "Workstation", "1.1", "Doofnet"),
                _node("router", "AppleRouter", "1.2", "Doofnet"),
                _node("printer", "LaserWriter", "1.3", "Doofnet"),
            ],
        )
        result = to_d3(data, include_types=[])
        zone = result["children"][0]
        self.assertEqual(len(zone["children"]), 3)

    def test_multi_jrouter_snapshot_with_all_types(self):
        result = to_d3(SNAPSHOT_MULTI_JROUTER, include_types=[])
        # Both zones should appear when all types are included.
        zone_names = [z["name"] for z in result["children"]]
        self.assertIn("ZoneA", zone_names)
        self.assertIn("ZoneB", zone_names)


class TestToD3Serialisability(unittest.TestCase):
    """Verify the output can be serialised to JSON without errors."""

    def test_basic_snapshot_is_json_serialisable(self):
        import json

        result = to_d3(SNAPSHOT_BASIC)
        # Should not raise
        serialised = json.dumps(result)
        self.assertGreater(len(serialised), 10)

    def test_empty_snapshot_is_json_serialisable(self):
        import json

        result = to_d3(SNAPSHOT_EMPTY)
        serialised = json.dumps(result)
        self.assertIn("GlobalTalk", serialised)


if __name__ == "__main__":
    unittest.main()
