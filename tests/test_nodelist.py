"""
Tests for globaltalk.nodelist

Covers:
  - resolve_address (valid IPs, invalid inputs)
  - parse_input (blank lines, comments, inline comments, unresolvable hosts)
  - _dump_peers_yaml (empty list, single peer, multiple peers)
  - _merge_yaml_peers (existing peers block, no peers block, peers at EOF,
                       blank separator handling)
  - build_nodelist (output to file, merge, stdout path, error paths)
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from globaltalk.nodelist import (
    _dump_peers_yaml,
    _merge_yaml_peers,
    build_nodelist,
    parse_input,
    resolve_address,
)
from tests.fixtures import (
    JROUTER_YAML_PEERS_AT_EOF,
    JROUTER_YAML_WITH_PEERS,
    JROUTER_YAML_WITHOUT_PEERS,
    NODELIST_LINES_BASIC,
    NODELIST_LINES_EMPTY,
    NODELIST_LINES_WITH_COMMENTS,
)

# ---------------------------------------------------------------------------
# resolve_address
# ---------------------------------------------------------------------------


class TestResolveAddress(unittest.TestCase):
    def test_valid_ipv4_returned_unchanged(self):
        self.assertEqual(resolve_address("127.0.0.1"), "127.0.0.1")

    def test_valid_ipv4_with_whitespace_stripped(self):
        self.assertEqual(resolve_address("  192.168.1.1  "), "192.168.1.1")

    def test_empty_string_returns_none(self):
        self.assertIsNone(resolve_address(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(resolve_address("   "))

    def test_invalid_address_returns_none(self):
        self.assertIsNone(resolve_address("not.a.valid.hostname.invalid"))

    def test_localhost_resolves(self):
        # localhost should always resolve to 127.0.0.1 on any POSIX system.
        result = resolve_address("localhost")
        self.assertEqual(result, "127.0.0.1")

    def test_hostname_resolution_uses_first_ipv4(self):
        # Mock getaddrinfo to return a known IPv4 result.
        fake_result = [
            (2, 1, 6, "", ("10.0.0.1", 0)),  # AF_INET = 2
        ]
        with patch("globaltalk.nodelist.socket.getaddrinfo", return_value=fake_result):
            result = resolve_address("router.example.com")
        self.assertEqual(result, "10.0.0.1")

    def test_unresolvable_hostname_falls_back_to_ip_check(self):
        # getaddrinfo raises gaierror, but the input is already a valid IP.
        import socket as _socket

        with patch(
            "globaltalk.nodelist.socket.getaddrinfo",
            side_effect=_socket.gaierror("name not found"),
        ):
            result = resolve_address("192.168.0.1")
        self.assertEqual(result, "192.168.0.1")

    def test_unresolvable_hostname_and_invalid_ip_returns_none(self):
        import socket as _socket

        with patch(
            "globaltalk.nodelist.socket.getaddrinfo",
            side_effect=_socket.gaierror("name not found"),
        ):
            result = resolve_address("notavalidhostname.invalid")
        self.assertIsNone(result)

    def test_ipv6_address_returns_none(self):
        # We only support IPv4; an IPv6 literal should not be returned.
        result = resolve_address("::1")
        # ::1 fails inet_aton, so should return None.
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# parse_input
# ---------------------------------------------------------------------------


class TestParseInput(unittest.TestCase):
    def _parse(self, lines):
        """Run parse_input with resolve_address patched to return the address
        as-is for any dotted-decimal IP, and None for anything else."""
        import socket as _socket

        def _resolve(addr):
            try:
                _socket.inet_aton(addr)
                return addr
            except OSError:
                return None

        with patch("globaltalk.nodelist.resolve_address", side_effect=_resolve):
            return parse_input(lines)

    def test_basic_fixture_returns_two_ips(self):
        result = self._parse(NODELIST_LINES_BASIC)
        self.assertEqual(result, ["127.0.0.1", "192.168.1.1"])

    def test_blank_lines_skipped(self):
        lines = ["\n", "   \n", "127.0.0.1\n", "\n"]
        result = self._parse(lines)
        self.assertEqual(result, ["127.0.0.1"])

    def test_comment_lines_skipped(self):
        lines = ["# this is a comment\n", "127.0.0.1\n"]
        result = self._parse(lines)
        self.assertEqual(result, ["127.0.0.1"])

    def test_inline_comment_ignored(self):
        # Text after whitespace on the same line as an address should be
        # ignored — only the first token is used.
        lines = ["192.168.1.1   # this is the router\n"]
        result = self._parse(lines)
        self.assertEqual(result, ["192.168.1.1"])

    def test_with_comments_fixture(self):
        result = self._parse(NODELIST_LINES_WITH_COMMENTS)
        self.assertEqual(result, ["127.0.0.1", "192.168.1.254"])

    def test_empty_fixture_returns_empty_list(self):
        result = self._parse(NODELIST_LINES_EMPTY)
        self.assertEqual(result, [])

    def test_unresolvable_address_excluded(self):
        lines = ["127.0.0.1\n", "bad.hostname.invalid\n", "10.0.0.1\n"]
        result = self._parse(lines)
        self.assertNotIn("bad.hostname.invalid", result)
        self.assertEqual(result, ["127.0.0.1", "10.0.0.1"])

    def test_order_preserved(self):
        lines = ["10.0.0.3\n", "10.0.0.1\n", "10.0.0.2\n"]
        result = self._parse(lines)
        self.assertEqual(result, ["10.0.0.3", "10.0.0.1", "10.0.0.2"])

    def test_duplicates_preserved(self):
        # parse_input intentionally does not deduplicate — that responsibility
        # belongs to the caller.
        lines = ["127.0.0.1\n", "127.0.0.1\n"]
        result = self._parse(lines)
        self.assertEqual(result, ["127.0.0.1", "127.0.0.1"])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(parse_input([]), [])

    def test_line_without_newline_parsed(self):
        # Files read with readlines() include \n, but parse_input should also
        # handle lines without a trailing newline.
        result = self._parse(["127.0.0.1"])
        self.assertEqual(result, ["127.0.0.1"])

    def test_unresolvable_address_emits_warning(self):
        with patch(
            "globaltalk.nodelist.resolve_address",
            side_effect=lambda a: None,
        ):
            with self.assertLogs("root", level="WARNING") as log:
                parse_input(["bad.hostname.invalid\n"])
        self.assertTrue(any("Could not resolve" in m for m in log.output))


# ---------------------------------------------------------------------------
# _dump_peers_yaml
# ---------------------------------------------------------------------------


class TestDumpPeersYaml(unittest.TestCase):
    def test_empty_list_produces_empty_block(self):
        result = _dump_peers_yaml([])
        self.assertEqual(result, "peers: []\n")

    def test_single_peer(self):
        result = _dump_peers_yaml(["1.2.3.4"])
        self.assertIn("peers:", result)
        self.assertIn("- 1.2.3.4", result)

    def test_multiple_peers(self):
        peers = ["1.2.3.4", "5.6.7.8", "9.10.11.12"]
        result = _dump_peers_yaml(peers)
        self.assertIn("peers:", result)
        for peer in peers:
            self.assertIn(f"- {peer}", result)

    def test_peers_appear_after_header(self):
        result = _dump_peers_yaml(["1.2.3.4", "5.6.7.8"])
        lines = result.splitlines()
        self.assertEqual(lines[0], "peers:")
        self.assertIn("- 1.2.3.4", lines[1:])
        self.assertIn("- 5.6.7.8", lines[1:])

    def test_output_ends_with_newline(self):
        self.assertTrue(_dump_peers_yaml(["1.2.3.4"]).endswith("\n"))
        self.assertTrue(_dump_peers_yaml([]).endswith("\n"))

    def test_order_preserved(self):
        peers = ["10.0.0.3", "10.0.0.1", "10.0.0.2"]
        result = _dump_peers_yaml(peers)
        lines = [ln for ln in result.splitlines() if ln.startswith("- ")]
        self.assertEqual(lines, ["- 10.0.0.3", "- 10.0.0.1", "- 10.0.0.2"])

    def test_valid_yaml_structure(self):
        # Verify manually that the output is parseable as YAML without
        # importing pyyaml — we just check the structural invariants.
        result = _dump_peers_yaml(["1.2.3.4", "5.6.7.8"])
        lines = result.strip().splitlines()
        self.assertEqual(lines[0], "peers:")
        for line in lines[1:]:
            self.assertTrue(line.startswith("- "), msg=f"Expected list item: {line!r}")


# ---------------------------------------------------------------------------
# _merge_yaml_peers
# ---------------------------------------------------------------------------


class TestMergeYamlPeers(unittest.TestCase):
    def _write(self, content: str, tmp_dir: str) -> str:
        path = os.path.join(tmp_dir, "jrouter.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_replaces_existing_peers_block(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_WITH_PEERS, d)
            result = _merge_yaml_peers(path, ["1.2.3.4", "5.6.7.8"])
        self.assertIn("- 1.2.3.4", result)
        self.assertIn("- 5.6.7.8", result)
        self.assertNotIn("- 10.0.0.1", result)
        self.assertNotIn("- 10.0.0.2", result)

    def test_preserves_other_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_WITH_PEERS, d)
            result = _merge_yaml_peers(path, ["1.2.3.4"])
        self.assertIn("network:", result)
        self.assertIn("zone: Doofnet", result)
        self.assertIn("some_other_key: value", result)

    def test_appends_peers_when_not_present(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_WITHOUT_PEERS, d)
            result = _merge_yaml_peers(path, ["1.2.3.4"])
        self.assertIn("peers:", result)
        self.assertIn("- 1.2.3.4", result)
        # Original keys must still be present
        self.assertIn("network:", result)
        self.assertIn("some_other_key: value", result)

    def test_replaces_peers_at_end_of_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_PEERS_AT_EOF, d)
            result = _merge_yaml_peers(path, ["9.9.9.9"])
        self.assertIn("- 9.9.9.9", result)
        self.assertNotIn("- 10.0.0.1", result)

    def test_empty_peers_list_produces_empty_block(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_WITH_PEERS, d)
            result = _merge_yaml_peers(path, [])
        self.assertIn("peers: []", result)
        self.assertNotIn("- 10.0.0.1", result)

    def test_raises_file_not_found_for_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            _merge_yaml_peers("/nonexistent/path/jrouter.yaml", ["1.2.3.4"])

    def test_output_ends_with_newline(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_WITH_PEERS, d)
            result = _merge_yaml_peers(path, ["1.2.3.4"])
        self.assertTrue(result.endswith("\n"))

    def test_multiple_peers_all_present(self):
        peers = ["1.1.1.1", "2.2.2.2", "3.3.3.3"]
        with tempfile.TemporaryDirectory() as d:
            path = self._write(JROUTER_YAML_WITHOUT_PEERS, d)
            result = _merge_yaml_peers(path, peers)
        for peer in peers:
            self.assertIn(f"- {peer}", result)

    def test_blank_separator_added_when_appending_to_non_empty_file(self):
        # When peers key is absent and the file doesn't end with a blank line,
        # a blank separator line should be inserted before the peers block.
        content = "network:\n  zone: Doofnet\nsome_key: value\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(content, d)
            result = _merge_yaml_peers(path, ["1.2.3.4"])
        # There should be a blank line separating the existing content from peers.
        self.assertIn("\n\npeers:", result)


# ---------------------------------------------------------------------------
# build_nodelist
# ---------------------------------------------------------------------------


class TestBuildNodelist(unittest.TestCase):
    def _write_input(self, lines: list[str], tmp_dir: str) -> str:
        path = os.path.join(tmp_dir, "nodes.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        return path

    def _patched_build(self, lines, **kwargs):
        """Run build_nodelist with resolve_address patched to handle IPs only."""
        import socket as _socket

        def _resolve(addr):
            try:
                _socket.inet_aton(addr)
                return addr
            except OSError:
                return None

        with tempfile.TemporaryDirectory() as d:
            input_path = self._write_input(lines, d)
            with patch("globaltalk.nodelist.resolve_address", side_effect=_resolve):
                result = build_nodelist(input_path=input_path, **kwargs)
        return result

    def test_returns_list_of_peers(self):
        result = self._patched_build(["127.0.0.1\n", "192.168.1.1\n"])
        self.assertEqual(result, ["127.0.0.1", "192.168.1.1"])

    def test_raises_value_error_when_both_output_and_merge_given(self):
        with tempfile.TemporaryDirectory() as d:
            input_path = self._write_input(["127.0.0.1\n"], d)
            with self.assertRaises(ValueError):
                build_nodelist(
                    input_path=input_path,
                    output_path="/tmp/out.yaml",
                    merge_path="/tmp/merge.yaml",
                )

    def test_raises_file_not_found_for_missing_input(self):
        with self.assertRaises(FileNotFoundError):
            build_nodelist(input_path="/nonexistent/nodes.txt")

    def test_writes_output_file(self):
        import socket as _socket

        def _resolve(addr):
            try:
                _socket.inet_aton(addr)
                return addr
            except OSError:
                return None

        with tempfile.TemporaryDirectory() as d:
            input_path = self._write_input(["127.0.0.1\n", "10.0.0.1\n"], d)
            output_path = os.path.join(d, "out.yaml")
            with patch("globaltalk.nodelist.resolve_address", side_effect=_resolve):
                build_nodelist(input_path=input_path, output_path=output_path)
            with open(output_path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("peers:", content)
        self.assertIn("- 127.0.0.1", content)
        self.assertIn("- 10.0.0.1", content)

    def test_merges_into_existing_yaml(self):
        import socket as _socket

        def _resolve(addr):
            try:
                _socket.inet_aton(addr)
                return addr
            except OSError:
                return None

        with tempfile.TemporaryDirectory() as d:
            input_path = self._write_input(["1.2.3.4\n"], d)
            merge_path = os.path.join(d, "jrouter.yaml")
            with open(merge_path, "w", encoding="utf-8") as fh:
                fh.write(JROUTER_YAML_WITH_PEERS)
            with patch("globaltalk.nodelist.resolve_address", side_effect=_resolve):
                build_nodelist(input_path=input_path, merge_path=merge_path)
            with open(merge_path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("- 1.2.3.4", content)
        self.assertNotIn("- 10.0.0.1", content)
        self.assertIn("network:", content)

    def test_empty_peers_emits_warning(self):
        with tempfile.TemporaryDirectory() as d:
            input_path = self._write_input(["# only a comment\n"], d)
            with patch("globaltalk.nodelist.resolve_address", return_value=None):
                with self.assertLogs("root", level="WARNING") as log:
                    build_nodelist(input_path=input_path)
        self.assertTrue(any("No valid peers" in m for m in log.output))

    def test_no_output_target_returns_peers_only(self):
        # When neither output_path nor merge_path is given, peers are returned
        # but no file is written.
        result = self._patched_build(["127.0.0.1\n"])
        self.assertEqual(result, ["127.0.0.1"])


if __name__ == "__main__":
    unittest.main()
