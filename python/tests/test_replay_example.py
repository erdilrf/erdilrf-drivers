"""Offline controls for the JSONL example; no hardware or optional dependencies."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest import mock
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "python/examples/replay_jsonl.py"
FIXTURE = ROOT / "python/examples/fixtures/uart-synthetic.jsonl"
EXPECTED = ROOT / "python/examples/fixtures/uart-synthetic.expected.json"
SPEC = importlib.util.spec_from_file_location("replay_example", EXAMPLE)
EXAMPLE_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXAMPLE_MODULE)


def row(direction, data, origin="synthetic"):
    return json.dumps({"origin": origin, "direction": direction, "hex": data})


class ReplayExampleTests(unittest.TestCase):
    def test_interleaved_fragments_coalesced_frames_and_error_retention(self):
        raw = FIXTURE.read_bytes()
        report = EXAMPLE_MODULE.replay(raw)
        self.assertEqual(report, json.loads(EXPECTED.read_text()))
        self.assertEqual(report["input_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual([r["completed_at_row"] for r in report["accepted_frames"]],
                         [3, 4, 5, 5, 6, 6, 8])
        self.assertEqual([r["direction"] for r in report["accepted_frames"]],
                         ["command", "response", "command", "command",
                          "response", "response", "response"])
        self.assertEqual(len(report["parser_errors"]), 1)
        self.assertEqual(report["parser_errors"][0]["observed_at_row"], 7)
        self.assertIn("checksum mismatch", report["parser_errors"][0]["message"])

    def test_malformed_inputs_are_denied(self):
        bad = [b"", b"\xff", b"\n", b"{}", b"[]", b"null", b"{",
               b'{"origin":"synthetic","origin":"synthetic"}',
               row("tx", "55 AA").encode(), row("response", "5 AA").encode(),
               row("response", "GG").encode(), row("response", "55  AA").encode(),
               row("response", "").encode(),
               json.dumps({"origin": "synthetic", "direction": "response",
                           "hex": "55", "unexpected": 1}).encode(),
               (row("response", "55") + "\n\n" + row("response", "AA")).encode(),
               (row("response", "55") + "\n" +
                row("response", "AA", origin="captured")).encode(),
               (row("response", "55") + "\n" +
                '{"origin":"synthetic","direction":"response","hex":NaN}').encode()]
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(EXAMPLE_MODULE.ReplayError):
                    EXAMPLE_MODULE.replay(raw)

    def test_input_limits_are_enforced(self):
        bad = [b"x" * (EXAMPLE_MODULE.MAX_INPUT_BYTES + 1),
               ((row("response", "55") + "\n") *
                (EXAMPLE_MODULE.MAX_ROWS + 1)).encode(),
               row("response", " ".join(["55"] *
                   (EXAMPLE_MODULE.MAX_CHUNK_BYTES + 1))).encode()]
        for raw in bad:
            with self.assertRaises(EXAMPLE_MODULE.ReplayError):
                EXAMPLE_MODULE.replay(raw)

    def test_incomplete_tail_gets_no_invented_flush_or_completeness_verdict(self):
        raw = row("response", "55 AA 88").encode()
        report = EXAMPLE_MODULE.replay(raw)
        self.assertEqual(report["accepted_frames"], [])
        self.assertEqual(report["parser_errors"], [])
        self.assertEqual(report["input_sha256"], hashlib.sha256(raw).hexdigest())

    def test_changed_decoder_pin_is_denied(self):
        pins = {**EXAMPLE_MODULE.SOURCE_PINS,
                "python/src/erdilrf_lrf/frames.py": "0" * 64}
        with mock.patch.object(EXAMPLE_MODULE, "SOURCE_PINS", pins):
            with self.assertRaisesRegex(EXAMPLE_MODULE.ReplayError, "pin changed"):
                EXAMPLE_MODULE.replay(FIXTURE.read_bytes())

    def test_cli_is_read_only_and_does_not_open_serial_or_network(self):
        real_open = io.open

        def read_only_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError("unexpected file write")
            return real_open(file, mode, *args, **kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("io.open", side_effect=read_only_open), \
                mock.patch.object(socket, "socket", side_effect=AssertionError("network")), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
                mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
                mock.patch.dict(sys.modules, {"serial": None}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = EXAMPLE_MODULE.main([str(FIXTURE)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), EXPECTED.read_text())


if __name__ == "__main__":
    unittest.main()
