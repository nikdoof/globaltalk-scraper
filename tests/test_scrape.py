"""
Tests for globaltalk.scrape

Covers the pure-function logic that can be exercised without netatalk:
  - NBPLKUP_RESULTS regex parsing (via nbplkup line processing)
  - deduplicate_nodes
  - check_prerequisites (mocked)
  - scrape() error paths (mocked)
"""

import unittest
from unittest.mock import MagicMock, patch

from globaltalk.scrape import (
    NBPLKUP_RESULTS,
    check_prerequisites,
    deduplicate_nodes,
    scrape,
)
from tests.fixtures import (
    NBPLKUP_INVALID_LINES,
    NBPLKUP_VALID_LINES,
)


class TestNbplkupRegex(unittest.TestCase):
    """Tests for the NBPLKUP_RESULTS compiled regex."""

    def _parse(self, line: str):
        """Return the regex match object for a line, or None."""
        return NBPLKUP_RESULTS.match(line.strip())

    # ── valid lines ──────────────────────────────────────────────────────────

    def test_afp_server_line(self):
        line = "nas-afp:AFPServer                              5311.212:128"
        m = self._parse(line)
        self.assertIsNotNone(m)
        obj, typ, addr = m.groups()
        self.assertEqual(obj.strip(), "nas-afp")
        self.assertEqual(typ.strip(), "AFPServer")
        self.assertEqual(addr, "5311.212:128")

    def test_workstation_line(self):
        line = "nas-afp:Workstation                            5311.212:4"
        m = self._parse(line)
        self.assertIsNotNone(m)
        obj, typ, addr = m.groups()
        self.assertEqual(obj.strip(), "nas-afp")
        self.assertEqual(typ.strip(), "Workstation")
        self.assertEqual(addr, "5311.212:4")

    def test_object_with_spaces(self):
        line = "HP LJ Pro 200 Color:LaserWriter                5311.100:130"
        m = self._parse(line)
        self.assertIsNotNone(m)
        obj, typ, addr = m.groups()
        self.assertEqual(obj.strip(), "HP LJ Pro 200 Color")
        self.assertEqual(typ.strip(), "LaserWriter")
        self.assertEqual(addr, "5311.100:130")

    def test_jrouter_version_string(self):
        line = "jrouter v0.0.12:AppleRouter                    5311.1:253"
        m = self._parse(line)
        self.assertIsNotNone(m)
        obj, typ, addr = m.groups()
        self.assertEqual(obj.strip(), "jrouter v0.0.12")
        self.assertEqual(typ.strip(), "AppleRouter")
        self.assertEqual(addr, "5311.1:253")

    def test_object_name_with_colon(self):
        """A colon in the object name should still parse correctly because the
        regex is greedy on the left and anchors the address:socket on the right."""
        line = "My Server: v2:AFPServer                        9999.1:128"
        m = self._parse(line)
        self.assertIsNotNone(m)
        _obj, typ, addr = m.groups()
        self.assertEqual(typ.strip(), "AFPServer")
        self.assertEqual(addr, "9999.1:128")

    def test_all_valid_fixture_lines_match(self):
        for line in NBPLKUP_VALID_LINES:
            with self.subTest(line=line):
                self.assertIsNotNone(self._parse(line))

    # ── address splitting ────────────────────────────────────────────────────

    def test_address_socket_split(self):
        line = "nas-afp:AFPServer                              5311.212:128"
        m = self._parse(line)
        _obj, _typ, addr_raw = m.groups()
        address, socket = addr_raw.split(":")
        self.assertEqual(address, "5311.212")
        self.assertEqual(socket, "128")

    # ── invalid lines ────────────────────────────────────────────────────────

    def test_blank_line_does_not_match(self):
        self.assertIsNone(self._parse(""))

    def test_whitespace_only_line_does_not_match(self):
        self.assertIsNone(self._parse("   "))

    def test_line_without_address_does_not_match(self):
        self.assertIsNone(self._parse("this line has no address at the end"))

    def test_line_missing_colon_separator_does_not_match(self):
        self.assertIsNone(self._parse("missingcolon 1234.56:78"))

    def test_all_invalid_fixture_lines_do_not_match(self):
        for line in NBPLKUP_INVALID_LINES:
            with self.subTest(line=repr(line)):
                self.assertIsNone(self._parse(line))


class TestDeduplicateNodes(unittest.TestCase):
    """Tests for deduplicate_nodes()."""

    def _node(self, address="1.1", socket="4", typ="Workstation", obj="mac"):
        return {
            "address": address,
            "socket": socket,
            "type": typ,
            "object": obj,
            "zone": "TestZone",
        }

    def test_no_duplicates_returned_unchanged(self):
        nodes = [
            self._node(address="1.1"),
            self._node(address="1.2"),
            self._node(address="1.3"),
        ]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 3)
        self.assertEqual(dupes, 0)

    def test_exact_duplicates_removed(self):
        node = self._node()
        nodes = [node.copy(), node.copy(), node.copy()]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 1)
        self.assertEqual(dupes, 2)

    def test_same_address_different_socket_not_duplicate(self):
        nodes = [
            self._node(address="1.1", socket="4"),
            self._node(address="1.1", socket="128"),
        ]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 2)
        self.assertEqual(dupes, 0)

    def test_same_address_different_type_not_duplicate(self):
        nodes = [
            self._node(address="1.1", typ="AFPServer"),
            self._node(address="1.1", typ="Workstation"),
        ]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 2)
        self.assertEqual(dupes, 0)

    def test_same_address_different_object_not_duplicate(self):
        nodes = [
            self._node(address="1.1", obj="alpha"),
            self._node(address="1.1", obj="beta"),
        ]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 2)
        self.assertEqual(dupes, 0)

    def test_order_preserved(self):
        """The first occurrence of each unique node should be kept."""
        nodes = [
            self._node(address="1.3"),
            self._node(address="1.1"),
            self._node(address="1.2"),
            self._node(address="1.1"),  # duplicate of index 1
        ]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual([n["address"] for n in unique], ["1.3", "1.1", "1.2"])
        self.assertEqual(dupes, 1)

    def test_empty_list(self):
        unique, dupes = deduplicate_nodes([])
        self.assertEqual(unique, [])
        self.assertEqual(dupes, 0)

    def test_single_node(self):
        unique, dupes = deduplicate_nodes([self._node()])
        self.assertEqual(len(unique), 1)
        self.assertEqual(dupes, 0)

    def test_duplicate_count_is_accurate(self):
        node = self._node()
        nodes = [node.copy()] * 10
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 1)
        self.assertEqual(dupes, 9)

    def test_zone_field_does_not_affect_deduplication(self):
        """Two nodes with the same address/socket/type/object but different
        zones are considered duplicates — zone is not part of the key."""
        nodes = [
            {**self._node(), "zone": "ZoneA"},
            {**self._node(), "zone": "ZoneB"},
        ]
        unique, dupes = deduplicate_nodes(nodes)
        self.assertEqual(len(unique), 1)
        self.assertEqual(dupes, 1)


class TestCheckPrerequisites(unittest.TestCase):
    """Tests for check_prerequisites()."""

    def test_all_present_returns_empty_list(self):
        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/getzones"):
            missing = check_prerequisites()
        self.assertEqual(missing, [])

    def test_all_missing_returns_both_commands(self):
        with patch("globaltalk.scrape.shutil.which", return_value=None):
            missing = check_prerequisites()
        self.assertIn("getzones", missing)
        self.assertIn("nbplkup", missing)

    def test_one_missing_returns_that_command(self):
        def _which(cmd):
            return "/usr/bin/getzones" if cmd == "getzones" else None

        with patch("globaltalk.scrape.shutil.which", side_effect=_which):
            missing = check_prerequisites()
        self.assertEqual(missing, ["nbplkup"])


class TestScrapeErrorPaths(unittest.TestCase):
    """Tests for scrape() error handling without netatalk."""

    def test_raises_when_prerequisites_missing(self):
        with patch("globaltalk.scrape.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                scrape()
        self.assertIn("Missing required commands", str(ctx.exception))

    def test_raises_when_no_zones_found(self):
        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=[]):
                with self.assertRaises(RuntimeError) as ctx:
                    scrape()
        self.assertIn("No zones found", str(ctx.exception))

    def test_raises_when_specified_zones_do_not_exist(self):
        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=["Doofnet"]):
                with self.assertRaises(RuntimeError) as ctx:
                    scrape(zones=["NonExistentZone"])
        self.assertIn("None of the specified zones exist", str(ctx.exception))

    def test_successful_scrape_structure(self):
        """scrape() returns a correctly structured dict when everything works."""
        fake_nodes = [
            {
                "object": "nas-afp",
                "type": "AFPServer",
                "address": "5311.212",
                "socket": "128",
                "zone": "Doofnet",
            }
        ]
        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=["Doofnet"]):
                with patch("globaltalk.scrape.nbplkup", return_value=fake_nodes):
                    result = scrape()

        self.assertEqual(result["format"], "v1")
        self.assertIn("generated_at", result)
        self.assertIn("zones", result)
        self.assertIn("nodes", result)
        self.assertEqual(result["zones"], ["Doofnet"])
        self.assertEqual(len(result["nodes"]), 1)

    def test_generated_at_is_iso_format(self):
        """generated_at should be a valid ISO 8601 timestamp."""
        from datetime import datetime

        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=["Doofnet"]):
                with patch("globaltalk.scrape.nbplkup", return_value=[]):
                    result = scrape()

        # Should not raise
        dt = datetime.fromisoformat(result["generated_at"])
        self.assertIsNotNone(dt.tzinfo)  # must be timezone-aware

    def test_dedupe_enabled_by_default(self):
        duplicate_node = {
            "object": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "socket": "128",
            "zone": "Doofnet",
        }
        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=["Doofnet"]):
                # nbplkup is called once per zone; return the same node twice
                # by making nbplkup return two identical entries
                with patch(
                    "globaltalk.scrape.nbplkup",
                    return_value=[duplicate_node, duplicate_node],
                ):
                    result = scrape()

        self.assertEqual(len(result["nodes"]), 1)

    def test_dedupe_disabled(self):
        duplicate_node = {
            "object": "nas-afp",
            "type": "AFPServer",
            "address": "5311.212",
            "socket": "128",
            "zone": "Doofnet",
        }
        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=["Doofnet"]):
                with patch(
                    "globaltalk.scrape.nbplkup",
                    return_value=[duplicate_node, duplicate_node],
                ):
                    result = scrape(dedupe=False)

        self.assertEqual(len(result["nodes"]), 2)

    def test_zone_filter_restricts_scan(self):
        """When zones= is given, only matching zones should be scanned."""
        nbplkup_mock = MagicMock(return_value=[])
        all_zones = ["Doofnet", "RetroZone", "AnotherZone"]

        with patch("globaltalk.scrape.shutil.which", return_value="/usr/bin/x"):
            with patch("globaltalk.scrape.getzones", return_value=all_zones):
                with patch("globaltalk.scrape.nbplkup", nbplkup_mock):
                    result = scrape(zones=["Doofnet"])

        # nbplkup should only have been called with Doofnet
        called_zones = [call.args[0] for call in nbplkup_mock.call_args_list]
        self.assertEqual(called_zones, ["Doofnet"])
        # But all_zones should still appear in the result
        self.assertEqual(result["zones"], all_zones)


if __name__ == "__main__":
    unittest.main()
