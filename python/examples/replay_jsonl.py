#!/usr/bin/env python3
"""Replay direction-labelled chunks offline using the reviewed framing source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from erdilrf_lrf import __version__, frames


REFERENCE_COMMIT = "904025b3c38302aea510ba97c370ed17c4844e6e"
PACKAGE_VERSION = "0.2.0"
SOURCE_PINS = {
    "python/src/erdilrf_lrf/frames.py":
        "3d8cd26c5d3aad0267093f8ba4c4ef82173b3bb603c55e342ed706ac9a96147f",
    "protocol/PROTOCOL.md":
        "52fd09b319484980bc65eb0f87a479a8d66df48dd3a9f44848b474f6f93ba995",
    "python/pyproject.toml":
        "600a1484ed057057e0ec33d2d2707284a248affda24377617683fbf7c146f87a",
}
MAX_INPUT_BYTES = 1024 * 1024
MAX_ROWS = 4096
MAX_CHUNK_BYTES = 4096
HEX = re.compile(r"[0-9A-Fa-f]{2}(?: [0-9A-Fa-f]{2})*\Z")


class ReplayError(ValueError):
    """The input or local decoder does not match this example's contract."""


def decoder_identity() -> dict:
    root = Path(__file__).resolve().parents[2]
    expected_parser = root / "python/src/erdilrf_lrf/frames.py"
    if Path(frames.__file__).resolve() != expected_parser:
        raise ReplayError("use the reviewed checkout's python/src on PYTHONPATH")
    if __version__ != PACKAGE_VERSION:
        raise ReplayError("package version differs from the reviewed source")
    for relative, expected in SOURCE_PINS.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ReplayError("reviewed source pin changed: " + relative)
    return {"reference_commit": REFERENCE_COMMIT, "package_version": __version__,
            "source_sha256": dict(SOURCE_PINS)}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ReplayError("non-finite JSON number")


def validated_rows(raw: bytes) -> list:
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ReplayError("input must contain 1 to 1048576 bytes")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise ReplayError("input must be UTF-8 JSONL") from None
    if not lines or len(lines) > MAX_ROWS:
        raise ReplayError("input row limit exceeded")
    rows = []
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line, object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
        except (ValueError, ReplayError):
            raise ReplayError("invalid JSON at row " + str(number)) from None
        if (not isinstance(row, dict) or set(row) != {"origin", "direction", "hex"}
                or row["origin"] not in ("synthetic", "captured")
                or row["direction"] not in ("command", "response")
                or not isinstance(row["hex"], str)
                or len(row["hex"]) > MAX_CHUNK_BYTES * 3 - 1
                or HEX.fullmatch(row["hex"]) is None):
            raise ReplayError("invalid chunk schema at row " + str(number))
        rows.append(row)
    if len({row["origin"] for row in rows}) != 1:
        raise ReplayError("use one declared origin per input file")
    return rows


def replay(raw: bytes) -> dict:
    identity = decoder_identity()
    rows = validated_rows(raw)
    readers = {direction: frames.FrameReader(direction=direction)
               for direction in ("command", "response")}
    accepted, errors = [], []
    for number, row in enumerate(rows, 1):
        reader = readers[row["direction"]]
        previous_errors = len(reader.errors)
        for frame in reader.feed(bytes.fromhex(row["hex"])):
            accepted.append({"completed_at_row": number, "direction": frame.direction,
                             "raw_hex": frame.raw.hex(" ").upper()})
        for message in reader.errors[previous_errors:]:
            errors.append({"observed_at_row": number, "direction": row["direction"],
                           "message": message})
    return {"schema_version": 1, "software_replay_only": True, "decoder": identity,
            "input_sha256": hashlib.sha256(raw).hexdigest(), "input_bytes": len(raw),
            "declared_origin": rows[0]["origin"], "chunk_count": len(rows),
            "accepted_frames": accepted, "parser_errors": errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="direction-labelled UTF-8 JSONL file")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        report = replay(raw)
    except (ReplayError, OSError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
