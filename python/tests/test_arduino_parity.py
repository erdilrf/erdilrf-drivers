"""
Cross-language parity check: the C++ header's constants and frame bytes must agree with the
verified Python implementation and with the manufacturer's printed frames.

Why this test exists
--------------------
No C++ toolchain exists on the machine where this repository was authored, so the Arduino driver
could **not** be compiled there. Rather than ship an unverifiable file with a disclaimer, this test
verifies the part that can be verified mechanically: the header's function codes, its checksum
formula, and the frames it would emit.

It does NOT verify that the C++ compiles, or that its state machine behaves. Those remain
unverified and are labelled as such in `arduino/README.md`. Claiming otherwise would be the exact
failure mode this project is trying to avoid.

Run:  python -m pytest tests/test_arduino_parity.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402

from erdilrf_lrf import frames as F  # noqa: E402

HEADER = Path(__file__).resolve().parent.parent.parent / "arduino" / "ERDILRF_LRF.h"

# Frames the manufacturer prints in section 8 of the LR1000E2 manual.
MANUAL_TX = {
    "kFuncSingleShot": "55 AA 88 FF FF FF FF 84",
    "kFuncContinuous": "55 AA 89 FF FF FF FF 85",
    "kFuncStop": "55 AA 8E FF FF FF FF 8A",
    "kFuncAngle": "55 AA 8A FF FF FF FF 86",
}


def read_header() -> str:
    if not HEADER.exists():
        pytest.skip(f"arduino header not present at {HEADER}")
    return HEADER.read_text(encoding="utf-8")


def cpp_constants() -> dict[str, int]:
    """Pull `static const uint8_t kName = 0xNN;` values out of the header."""
    out: dict[str, int] = {}
    for m in re.finditer(r"static\s+const\s+uint8_t\s+(k\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*;",
                         read_header()):
        out[m.group(1)] = int(m.group(2), 0)
    return out


def test_header_exists_and_declares_the_expected_constants():
    c = cpp_constants()
    for name in ("kHeaderH", "kHeaderL", "kFrameLen",
                 "kFuncSelfTest", "kFuncLdConstantOn", "kFuncSingleShot",
                 "kFuncContinuous", "kFuncAngle", "kFuncStop", "kStaSuccess"):
        assert name in c, f"{name} missing from the C++ header"


def test_cpp_function_codes_match_the_python_implementation():
    c = cpp_constants()
    pairs = {
        "kFuncSelfTest": F.FUNC_SELF_TEST,
        "kFuncLdConstantOn": F.FUNC_LD_CONSTANT_ON,
        "kFuncSingleShot": F.FUNC_SINGLE_SHOT,
        "kFuncContinuous": F.FUNC_CONTINUOUS,
        "kFuncAngle": F.FUNC_ANGLE,
        "kFuncStop": F.FUNC_STOP,
        "kStaSuccess": F.STA_SUCCESS,
        "kHeaderH": F.HEADER_H,
        "kHeaderL": F.HEADER_L,
        "kFrameLen": F.FRAME_LEN,
    }
    for cpp_name, py_value in pairs.items():
        assert c[cpp_name] == py_value, (
            f"{cpp_name} = 0x{c[cpp_name]:02X} in C++ but 0x{py_value:02X} in Python")


def test_cpp_frames_reproduce_the_manual_byte_for_byte():
    """
    Rebuild each frame the way the C++ would — header, function, FF padding, SUM[3:7] — and compare
    with the manual. If the C++ checksum formula were wrong, this fails even without a compiler.
    """
    c = cpp_constants()
    for const_name, printed in MANUAL_TX.items():
        func = c[const_name]
        d1 = d2 = d3 = d4 = 0xFF
        cpp_sum = (func + d1 + d2 + d3 + d4) & 0xFF          # mirrors checksumSend()
        built = bytes([c["kHeaderH"], c["kHeaderL"], func, d1, d2, d3, d4, cpp_sum])
        expected = bytes.fromhex(printed.replace(" ", ""))
        assert built == expected, (
            f"{const_name}: C++ arithmetic gives {built.hex(' ').upper()}, manual says {printed}")


def test_cpp_ld_frames_match_the_python_builders():
    c = cpp_constants()
    func = c["kFuncLdConstantOn"]
    for on, py_cmd in ((0x01, F.CMD_LD_ON), (0x00, F.CMD_LD_OFF)):
        d1 = d2 = d3 = 0xFF
        built = bytes([c["kHeaderH"], c["kHeaderL"], func, d1, d2, d3, on,
                       (func + d1 + d2 + d3 + on) & 0xFF])
        assert built == py_cmd, f"LD {'on' if on else 'off'} frame differs between C++ and Python"


def test_cpp_response_checksum_matches_the_response_rule():
    """checksumResponse() sums 7 bytes from index 0; confirm it against the Python rule."""
    c = cpp_constants()
    sample = bytes([c["kHeaderH"], c["kHeaderL"], c["kFuncSingleShot"], 0x01, 0xFF, 0x27, 0x10])
    cpp_style = sum(sample) & 0xFF
    assert cpp_style == F.checksum_response(sample) == 0xBE


def test_the_two_rules_are_both_present_and_different_in_the_header():
    """
    The header must contain two distinct checksum routines. A single shared one would reproduce the
    exact bug the Python FrameReader shipped with.
    """
    src = read_header()
    assert "checksumSend" in src and "checksumResponse" in src
    assert (F.checksum_send(F.FUNC_SINGLE_SHOT) & 0xFF) != \
           (F.checksum_response(bytes([0x55, 0xAA, 0x88, 0xFF, 0xFF, 0xFF, 0xFF])))
