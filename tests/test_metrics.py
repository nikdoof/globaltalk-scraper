"""
Tests for globaltalk.metrics

Covers:
  - escape_label_value
  - load_data (valid, invalid, missing fields, unknown format version)
  - _snapshot_age_seconds
  - generate_metrics (all metric families, prefix, empty snapshot)
  - _write_metrics_output (atomic write, stdout passthrough, cleanup on error)
"""

import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from globaltalk.metrics import (
    _snapshot_age_seconds,
    _write_metrics_output,
    escape_label_value,
    generate_metrics,
    load_data,
)
from tests.fixtures import (
    SNAPSHOT_BASIC,
    SNAPSHOT_EMPTY,
    SNAPSHOT_MULTI_JROUTER,
    SNAPSHOT_NO_TIMESTAMP,
    SNAPSHOT_UNKNOWN_FORMAT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metrics(data, prefix="globaltalk") -> str:
    """Run generate_metrics and return the full output as a string."""
    buf = io.StringIO()
    generate_metrics(data, buf, prefix=prefix)
    return buf.getvalue()


def _lines(data, prefix="globaltalk") -> list[str]:
    """Return non-empty, non-comment lines from generate_metrics output."""
    return [
        line
        for line in _metrics(data, prefix=prefix).splitlines()
        if line and not line.startswith("#")
    ]


def _find_line(lines: list[str], prefix: str) -> str:
    """Return the first line starting with *prefix*, or raise AssertionError."""
    return next(ln for ln in lines if ln.startswith(prefix))


# ---------------------------------------------------------------------------
# escape_label_value
# ---------------------------------------------------------------------------


class TestEscapeLabelValue(unittest.TestCase):
    def test_plain_string_unchanged(self):
        self.assertEqual(escape_label_value("Doofnet"), "Doofnet")

    def test_backslash_escaped(self):
        self.assertEqual(escape_label_value("a\\b"), "a\\\\b")

    def test_double_quote_escaped(self):
        self.assertEqual(escape_label_value('say "hello"'), 'say \\"hello\\"')

    def test_newline_escaped(self):
        self.assertEqual(escape_label_value("line1\nline2"), "line1\\nline2")

    def test_all_three_special_chars(self):
        result = escape_label_value('back\\slash\nnew"quote')
        self.assertEqual(result, 'back\\\\slash\\nnew\\"quote')

    def test_empty_string(self):
        self.assertEqual(escape_label_value(""), "")

    def test_already_escaped_backslash(self):
        # A literal \\ in the input should become \\\\ in the output.
        self.assertEqual(escape_label_value("\\\\"), "\\\\\\\\")


# ---------------------------------------------------------------------------
# load_data
# ---------------------------------------------------------------------------


class TestLoadData(unittest.TestCase):
    def _write_json(self, data, tmp_dir) -> str:
        path = os.path.join(tmp_dir, "snapshot.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_valid_snapshot_returns_dict(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_json(SNAPSHOT_BASIC, d)
            result = load_data(path)
        self.assertIsInstance(result, dict)
        self.assertIn("zones", result)
        self.assertIn("nodes", result)

    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_data("/nonexistent/path/snapshot.json")

    def test_malformed_json_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w") as fh:
                fh.write("this is not json {{{")
            with self.assertRaises(ValueError) as ctx:
                load_data(path)
        self.assertIn("Failed to decode JSON", str(ctx.exception))

    def test_json_array_root_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_json(["not", "a", "dict"], d)
            with self.assertRaises(ValueError) as ctx:
                load_data(path)
        self.assertIn("JSON root must be an object", str(ctx.exception))

    def test_missing_nodes_key_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_json({"zones": []}, d)
            with self.assertRaises(ValueError) as ctx:
                load_data(path)
        self.assertIn("'nodes' and 'zones'", str(ctx.exception))

    def test_missing_zones_key_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_json({"nodes": []}, d)
            with self.assertRaises(ValueError) as ctx:
                load_data(path)
        self.assertIn("'nodes' and 'zones'", str(ctx.exception))

    def test_unknown_format_version_logs_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_json(SNAPSHOT_UNKNOWN_FORMAT, d)
            with self.assertLogs("root", level="WARNING") as log:
                result = load_data(path)
        self.assertIsNotNone(result)
        self.assertTrue(
            any("Unknown format version" in msg for msg in log.output),
            msg=f"Expected warning not found in: {log.output}",
        )

    def test_known_format_version_no_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_json(SNAPSHOT_BASIC, d)
            # assertLogs would fail if nothing is logged, so we just verify
            # load_data succeeds without raising.
            result = load_data(path)
        self.assertEqual(result["format"], "v1")


# ---------------------------------------------------------------------------
# _snapshot_age_seconds
# ---------------------------------------------------------------------------


class TestSnapshotAgeSeconds(unittest.TestCase):
    def test_returns_none_when_field_absent(self):
        self.assertIsNone(_snapshot_age_seconds(SNAPSHOT_NO_TIMESTAMP))

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(_snapshot_age_seconds({"generated_at": ""}))

    def test_returns_none_for_invalid_timestamp(self):
        self.assertIsNone(_snapshot_age_seconds({"generated_at": "not-a-date"}))

    def test_returns_float_for_valid_timestamp(self):
        # Use a timestamp 60 seconds in the past.
        ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        age = _snapshot_age_seconds({"generated_at": ts})
        self.assertIsNotNone(age)
        self.assertIsInstance(age, float)
        # Allow ±5 s tolerance for test execution time.
        self.assertAlmostEqual(age, 60.0, delta=5.0)

    def test_naive_timestamp_treated_as_utc(self):
        # A timestamp without tzinfo should be treated as UTC and still return
        # a sensible age rather than raising.
        ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        age = _snapshot_age_seconds({"generated_at": ts})
        self.assertIsNotNone(age)
        self.assertAlmostEqual(age, 30.0, delta=5.0)

    def test_age_is_positive_for_past_timestamp(self):
        ts = "2020-01-01T00:00:00+00:00"
        age = _snapshot_age_seconds({"generated_at": ts})
        self.assertGreater(age, 0)


# ---------------------------------------------------------------------------
# generate_metrics — structure and content
# ---------------------------------------------------------------------------


class TestGenerateMetricsStructure(unittest.TestCase):
    """Verify that all expected metric families are present with correct types."""

    def _has_meta(self, output: str, name: str, metric_type: str) -> bool:
        return (
            f"# HELP {name} " in output
            and f"# TYPE {name} {metric_type}" in output
        )

    def test_zones_metric_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_zones", "gauge"))

    def test_unique_devices_metric_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_unique_devices", "gauge"))

    def test_total_nodes_metric_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_total_nodes", "gauge"))

    def test_zone_devices_metric_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_zone_devices", "gauge"))

    def test_device_types_metric_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_device_types", "gauge"))

    def test_multihomed_devices_metric_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_multihomed_devices", "gauge"))

    def test_jrouter_versions_metric_present_when_jrouter_exists(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(self._has_meta(out, "globaltalk_jrouter_versions", "gauge"))

    def test_snapshot_age_metric_present_when_generated_at_exists(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertTrue(
            self._has_meta(out, "globaltalk_snapshot_age_seconds", "gauge")
        )

    def test_snapshot_age_metric_absent_when_no_timestamp(self):
        out = _metrics(SNAPSHOT_NO_TIMESTAMP)
        self.assertNotIn("snapshot_age_seconds", out)

    def test_jrouter_metric_absent_when_no_jrouter_nodes(self):
        out = _metrics(SNAPSHOT_NO_TIMESTAMP)
        self.assertNotIn("jrouter_versions", out)


class TestGenerateMetricsValues(unittest.TestCase):
    """Verify that metric values are numerically correct."""

    def test_zones_count(self):
        lines = _lines(SNAPSHOT_BASIC)
        zones_line = _find_line(lines, "globaltalk_zones ")
        self.assertEqual(zones_line, "globaltalk_zones 2")

    def test_total_nodes_count(self):
        lines = _lines(SNAPSHOT_BASIC)
        total_line = _find_line(lines, "globaltalk_total_nodes ")
        self.assertEqual(total_line, f"globaltalk_total_nodes {len(SNAPSHOT_BASIC['nodes'])}")

    def test_unique_devices_count(self):
        # SNAPSHOT_BASIC has 4 distinct addresses: 5311.212, 5311.100, 5311.1, 6100.5
        lines = _lines(SNAPSHOT_BASIC)
        ud_line = _find_line(lines, "globaltalk_unique_devices ")
        self.assertEqual(ud_line, "globaltalk_unique_devices 4")

    def test_multihomed_count(self):
        # 5311.212 (nas-afp) has 4 endpoints → multihomed; others have 1 each
        lines = _lines(SNAPSHOT_BASIC)
        mh_line = _find_line(lines, "globaltalk_multihomed_devices ")
        self.assertEqual(mh_line, "globaltalk_multihomed_devices 1")

    def test_zone_devices_label_and_count(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertIn('globaltalk_zone_devices{zone="Doofnet"}', out)
        self.assertIn('globaltalk_zone_devices{zone="RetroZone"}', out)
        # RetroZone has exactly 1 node
        self.assertIn('globaltalk_zone_devices{zone="RetroZone"} 1', out)

    def test_zone_devices_count_for_doofnet(self):
        out = _metrics(SNAPSHOT_BASIC)
        doofnet_nodes = [n for n in SNAPSHOT_BASIC["nodes"] if n["zone"] == "Doofnet"]
        expected = f'globaltalk_zone_devices{{zone="Doofnet"}} {len(doofnet_nodes)}'
        self.assertIn(expected, out)

    def test_device_type_labels_present(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertIn('globaltalk_device_types{type="AFPServer"}', out)
        self.assertIn('globaltalk_device_types{type="Workstation"}', out)
        self.assertIn('globaltalk_device_types{type="LaserWriter"}', out)

    def test_jrouter_version_label_and_count(self):
        out = _metrics(SNAPSHOT_BASIC)
        self.assertIn('globaltalk_jrouter_versions{version="v0.0.12"} 1', out)

    def test_jrouter_multiple_versions(self):
        out = _metrics(SNAPSHOT_MULTI_JROUTER)
        self.assertIn('globaltalk_jrouter_versions{version="v0.0.12"} 2', out)
        self.assertIn('globaltalk_jrouter_versions{version="v0.0.13"} 1', out)

    def test_empty_snapshot_produces_zero_values(self):
        lines = _lines(SNAPSHOT_EMPTY)
        zones_line = _find_line(lines, "globaltalk_zones ")
        total_line = _find_line(lines, "globaltalk_total_nodes ")
        ud_line = _find_line(lines, "globaltalk_unique_devices ")
        mh_line = _find_line(lines, "globaltalk_multihomed_devices ")
        self.assertEqual(zones_line, "globaltalk_zones 0")
        self.assertEqual(total_line, "globaltalk_total_nodes 0")
        self.assertEqual(ud_line, "globaltalk_unique_devices 0")
        self.assertEqual(mh_line, "globaltalk_multihomed_devices 0")

    def test_empty_snapshot_no_zone_devices_lines(self):
        out = _metrics(SNAPSHOT_EMPTY)
        self.assertNotIn("zone_devices{", out)

    def test_empty_snapshot_no_device_type_lines(self):
        out = _metrics(SNAPSHOT_EMPTY)
        self.assertNotIn("device_types{", out)


class TestGenerateMetricsPrefix(unittest.TestCase):
    """Verify that the prefix parameter is applied to all metric names."""

    def test_custom_prefix_applied(self):
        out = _metrics(SNAPSHOT_BASIC, prefix="gt")
        self.assertIn("gt_zones ", out)
        self.assertIn("gt_unique_devices ", out)
        self.assertIn("gt_total_nodes ", out)
        self.assertIn("gt_zone_devices{", out)
        self.assertIn("gt_device_types{", out)
        self.assertIn("gt_multihomed_devices ", out)
        self.assertIn("gt_jrouter_versions{", out)

    def test_custom_prefix_not_default_name(self):
        out = _metrics(SNAPSHOT_BASIC, prefix="gt")
        self.assertNotIn("globaltalk_zones", out)

    def test_default_prefix_is_globaltalk(self):
        buf = io.StringIO()
        generate_metrics(SNAPSHOT_BASIC, buf)
        self.assertIn("globaltalk_zones", buf.getvalue())


class TestGenerateMetricsLabelEscaping(unittest.TestCase):
    """Verify that special characters in zone/type/version names are escaped."""

    def _snapshot_with_zone(self, zone_name: str) -> dict:
        return {
            "format": "v1",
            "zones": [zone_name],
            "nodes": [
                {
                    "object": "test",
                    "type": "Workstation",
                    "address": "1.1",
                    "socket": "4",
                    "zone": zone_name,
                }
            ],
        }

    def test_zone_with_backslash(self):
        out = _metrics(self._snapshot_with_zone("Zone\\A"))
        self.assertIn('zone="Zone\\\\A"', out)

    def test_zone_with_double_quote(self):
        out = _metrics(self._snapshot_with_zone('Zone"A'))
        self.assertIn('zone="Zone\\"A"', out)

    def test_zone_with_newline(self):
        out = _metrics(self._snapshot_with_zone("Zone\nA"))
        self.assertIn('zone="Zone\\nA"', out)


# ---------------------------------------------------------------------------
# _write_metrics_output — atomic writes
# ---------------------------------------------------------------------------


class TestWriteMetricsOutput(unittest.TestCase):
    def test_stdout_uses_direct_write(self):
        """When output is stdout, generate_metrics is called directly."""
        buf = io.StringIO()
        buf.name = "<stdout>"
        _write_metrics_output(SNAPSHOT_BASIC, buf)
        self.assertIn("globaltalk_zones", buf.getvalue())

    def test_file_output_is_atomic(self):
        """Writing to a real file should produce the correct content via
        atomic rename and leave no .tmp file behind."""
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "out.prom")
            # Pre-create the target so we can verify it is replaced.
            with open(target, "w") as fh:
                fh.write("old content\n")

            with open(target, "w", encoding="utf-8") as fh:
                _write_metrics_output(SNAPSHOT_BASIC, fh)

            # Temp file must be gone
            self.assertFalse(os.path.exists(target + ".tmp"))

            # Target must have new content
            with open(target, encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("globaltalk_zones", content)
            self.assertNotIn("old content", content)

    def test_tmp_file_cleaned_up_on_error(self):
        """If generate_metrics raises, the .tmp file must be removed."""
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "out.prom")

            with open(target, "w", encoding="utf-8") as fh:
                with patch(
                    "globaltalk.metrics.generate_metrics",
                    side_effect=RuntimeError("boom"),
                ):
                    with self.assertRaises(RuntimeError):
                        _write_metrics_output(SNAPSHOT_BASIC, fh)

            self.assertFalse(os.path.exists(target + ".tmp"))

    def test_custom_prefix_passed_through(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "out.prom")
            with open(target, "w", encoding="utf-8") as fh:
                _write_metrics_output(SNAPSHOT_BASIC, fh, prefix="myprefix")
            with open(target, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("myprefix_zones", content)
        self.assertNotIn("globaltalk_zones", content)


if __name__ == "__main__":
    unittest.main()
