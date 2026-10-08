"""
Golden-vector tests.

Every TX frame asserted here is a byte string **printed in the manufacturer's manual**.
If a future change breaks one of these, the change contradicts the primary source.

Run:  python -m pytest -q          (from python/)
      python tests/test_vectors.py (no pytest needed)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402  (optional; see __main__ block)

from erdilrf_lrf import frames as F  # noqa: E402


# ------------------------------------------------------------------ TX golden vectors
# Each (name, built_frame, manual_frame). The manual prints these hex strings verbatim.

TX_VECTORS = [
    ("single-shot", F.CMD_SINGLE_SHOT, "55 AA 88 FF FF FF FF 84"),
    ("continuous", F.CMD_CONTINUOUS, "55 AA 89 FF FF FF FF 85"),
    ("stop", F.CMD_STOP, "55 AA 8E FF FF FF FF 8A"),
    ("angle", F.CMD_ANGLE, "55 AA 8A FF FF FF FF 86"),
    ("LD on", F.CMD_LD_ON, "55 AA 86 FF FF FF 01 84"),
    ("LD off", F.CMD_LD_OFF, "55 AA 86 FF FF FF 00 83"),
]


def test_tx_frames_match_the_manual():
    for name, built, printed in TX_VECTORS:
        expected = bytes.fromhex(printed.replace(" ", ""))
        assert built == expected, (
            f"{name}: built {built.hex(' ').upper()} != manual {printed}")


def test_the_six_manual_frames_are_the_six_we_claim():
    assert len(TX_VECTORS) == 6


def test_checksum_ranges_differ_between_directions():
    """
    The manual's own note 1: command and response frames use different checksum ranges.
    Prove the two functions genuinely disagree on the same payload, so nobody "simplifies"
    them into one.
    """
    func, d1, d2, d3, d4 = F.FUNC_SINGLE_SHOT, 0x01, 0xFF, 0x27, 0x10
    as_send = F.checksum_send(func, d1, d2, d3, d4)
    as_resp = F.checksum_response(bytes([F.HEADER_H, F.HEADER_L, func, d1, d2, d3, d4]))
    assert as_send != as_resp, "the two checksum ranges collapsed into one"


def test_manual_send_checksums_recompute_independently():
    """Recompute each printed TX checksum from the rule instead of trusting the printout."""
    for name, built, _printed in TX_VECTORS:
        recomputed = (built[2] + built[3] + built[4] + built[5] + built[6]) & 0xFF
        assert built[7] == recomputed, f"{name}: byte 7 is not SUM[3:7]"


# ------------------------------------------------------------------ RX decoding

def test_distance_golden_values():
    """reported = measured x 10 -> register holds tenths of a metre."""
    cases = [(0x00, 0x0A, 1.0), (0x00, 0x64, 10.0), (0x03, 0xE8, 100.0), (0x27, 0x10, 1000.0)]
    for hi, lo, metres in cases:
        raw = bytes([0x55, 0xAA, F.FUNC_SINGLE_SHOT, 0x01, 0xFF, hi, lo, 0x00])
        raw = raw[:7] + bytes([F.checksum_response(raw[:7])])
        assert F.decode_distance(F.parse_frame(raw)) == pytest.approx(metres)


def test_continuous_response_decodes_like_single_shot():
    body = bytes([0x55, 0xAA, F.FUNC_CONTINUOUS, 0x01, 0xFF, 0x01, 0xF4])  # 500 -> 50.0 m
    frame = F.parse_frame(body + bytes([F.checksum_response(body)]))
    assert F.decode_distance(frame) == pytest.approx(50.0)


def test_failed_measurement_raises_but_or_none_returns_none():
    body = bytes([0x55, 0xAA, F.FUNC_SINGLE_SHOT, 0x00, 0xFF, 0x00, 0x00])
    frame = F.parse_frame(body + bytes([F.checksum_response(body)]))
    with pytest.raises(F.ProtocolError):
        F.decode_distance(frame)
    assert F.decode_distance_or_none(frame) is None


def test_angle_uses_same_scaling():
    body = bytes([0x55, 0xAA, F.FUNC_ANGLE, 0x01, 0xFF, 0x00, 0x5A])  # 90 -> 9.0 deg
    frame = F.parse_frame(body + bytes([F.checksum_response(body)]))
    assert F.decode_angle(frame) == pytest.approx(9.0)


def test_self_test_carries_error_code_only_on_failure():
    ok = bytes([0x55, 0xAA, F.FUNC_SELF_TEST, 0x01, 0x00, 0x00, 0x00])
    okf = F.parse_frame(ok + bytes([F.checksum_response(ok)]))
    assert okf.is_self_test and okf.error_code == 0x00
    assert "succeeded" in F.summarise(okf).sta_meaning

    bad = bytes([0x55, 0xAA, F.FUNC_SELF_TEST, 0x00, 0x00, 0x00, 0x2A])
    badf = F.parse_frame(bad + bytes([F.checksum_response(bad)]))
    assert badf.error_code == 0x2A
    s = F.summarise(badf)
    assert "FAILED" in s.sta_meaning and "0x2A" in s.detail


# ------------------------------------------------------------------ set baud

def test_set_baud_selector_sits_in_the_function_position():
    """The manual prints the baud frame as `55 AA TYPE FF FF FF FF SUM` — TYPE is byte 2."""
    for baud, code in F.BAUD_CODES.items():
        frame = F.set_baud_command(baud)
        assert frame[0] == 0x55 and frame[1] == 0xAA
        assert frame[2] == code, f"{baud} should select TYPE=0x{code:02X}"
        assert frame[3:7] == b"\xff\xff\xff\xff"
        assert frame[7] == (code + 0xFF * 4) & 0xFF


def test_all_nine_documented_baud_rates_present():
    assert sorted(F.BAUD_CODES) == [9600, 14400, 19200, 38400, 56000, 57600, 115200, 128000, 230400]


def test_unsupported_baud_is_rejected():
    with pytest.raises(F.ProtocolError):
        F.set_baud_command(12345)


# ------------------------------------------------------------------ parser robustness

def test_bad_header_rejected():
    with pytest.raises(F.ProtocolError, match="bad header"):
        F.parse_frame(bytes([0x54, 0xAA, 0x88, 0xFF, 0xFF, 0xFF, 0xFF, 0x84]))


def test_bad_checksum_rejected_and_can_be_bypassed():
    bad = bytes([0x55, 0xAA, 0x88, 0x01, 0xFF, 0x00, 0x0A, 0x00])
    with pytest.raises(F.ProtocolError, match="checksum mismatch"):
        F.parse_frame(bad)
    f = F.parse_frame(bad, verify_checksum=False)
    assert f.checksum_ok is False and F.decode_distance(f) == pytest.approx(1.0)


def test_wrong_length_rejected():
    for n in (0, 1, 7, 9):
        with pytest.raises(F.ProtocolError):
            F.parse_frame(bytes(n))


def rx(func, d1=0xFF, d2=0xFF, d3=0xFF, d4=0xFF):
    """Build a valid module -> host frame using the response-side checksum rule."""
    body = bytes([0x55, 0xAA, func, d1, d2, d3, d4])
    return body + bytes([F.checksum_response(body)])


def test_reader_reassembles_a_frame_split_at_every_offset():
    frame = rx(F.FUNC_SINGLE_SHOT, 0x01, 0xFF, 0x03, 0xE8)
    for cut in range(1, len(frame)):
        r = F.FrameReader()
        got = r.feed(frame[:cut]) + r.feed(frame[cut:])
        assert len(got) == 1 and got[0].raw == frame, f"failed when split at {cut}"


def test_reader_resynchronises_after_leading_garbage():
    frame = rx(F.FUNC_CONTINUOUS, 0x01, 0xFF, 0x00, 0x64)
    r = F.FrameReader()
    got = r.feed(b"\x00\x13\x37" + frame)
    assert len(got) == 1 and got[0].raw == frame
    assert r.errors and "discarded" in r.errors[0]


def test_reader_survives_a_corrupt_frame_and_finds_the_next_one():
    corrupt = bytearray(rx(F.FUNC_STOP, 0x01))
    corrupt[7] ^= 0xFF                      # break the checksum
    good = rx(F.FUNC_ANGLE, 0x01, 0xFF, 0x00, 0x5A)
    r = F.FrameReader()
    got = r.feed(bytes(corrupt) + good)
    assert [f.raw for f in got] == [good]
    assert any("checksum mismatch" in e for e in r.errors)


def test_reader_handles_dribbled_single_bytes():
    frame = rx(F.FUNC_SINGLE_SHOT, 0x01, 0xFF, 0x00, 0x0A)
    r = F.FrameReader()
    got = []
    for b in frame:
        got += r.feed(bytes([b]))
    assert len(got) == 1 and got[0].raw == frame
    assert F.decode_distance(got[0]) == pytest.approx(1.0)


def test_reader_keeps_half_header_across_chunks():
    frame = rx(F.FUNC_STOP, 0x01)
    r = F.FrameReader()
    assert r.feed(b"\x55") == []
    assert [f.raw for f in r.feed(b"\xaa" + frame[2:])] == [frame]


def test_reader_defaults_to_response_direction():
    """A host reads module -> host frames, so the response rule must be the default."""
    assert F.FrameReader()._direction == "response"


def test_command_direction_reader_accepts_transmitted_frames():
    """
    Regression guard. The first release of FrameReader validated everything with the response
    rule and therefore rejected every command frame it was ever handed — a real bug found by
    these tests, not by inspection.
    """
    r = F.FrameReader(direction="command")
    got = r.feed(F.CMD_SINGLE_SHOT + F.CMD_STOP)
    assert [f.raw for f in got] == [F.CMD_SINGLE_SHOT, F.CMD_STOP]
    assert all(f.checksum_ok for f in got)
    assert all(f.direction == "command" for f in got)


def test_a_command_frame_is_rejected_by_a_response_reader_and_vice_versa():
    """
    The two checksum rules must not be interchangeable in either direction.

    Note the two different failure contracts, which are deliberate:
      * parse_frame() raises ProtocolError — it was handed exactly one frame.
      * FrameReader.feed() does NOT raise — it is a stream resynchroniser, so a bad frame goes
        to .errors and the stream keeps going. Asserting "raises" against feed() is a test bug.
    """
    resp = rx(F.FUNC_SINGLE_SHOT, 0x01, 0xFF, 0x00, 0x0A)

    # parse_frame: raise
    with pytest.raises(F.ProtocolError, match="checksum mismatch"):
        F.parse_frame(F.CMD_SINGLE_SHOT)                      # command bytes, response rule
    with pytest.raises(F.ProtocolError, match="checksum mismatch"):
        F.parse_frame(resp, direction="command")              # response bytes, command rule

    # FrameReader: swallow, record, keep going
    r1 = F.FrameReader()
    assert r1.feed(F.CMD_SINGLE_SHOT) == []
    assert any("checksum mismatch" in e for e in r1.errors)

    r2 = F.FrameReader(direction="command")
    assert r2.feed(resp) == []
    assert any("checksum mismatch" in e for e in r2.errors)


def test_error_message_names_which_checksum_rule_was_applied():
    """A confusing checksum failure should tell the integrator which direction was assumed."""
    try:
        F.parse_frame(F.CMD_SINGLE_SHOT)
    except F.ProtocolError as exc:
        assert "SUM[1:7]" in str(exc)
    else:
        pytest.fail("expected ProtocolError")
    try:
        F.parse_frame(rx(F.FUNC_STOP), direction="command")
    except F.ProtocolError as exc:
        assert "SUM[3:7]" in str(exc)
    else:
        pytest.fail("expected ProtocolError")


def test_unknown_direction_rejected():
    with pytest.raises(F.ProtocolError):
        F.FrameReader(direction="sideways")
    with pytest.raises(F.ProtocolError):
        F.parse_frame(rx(F.FUNC_STOP), direction="sideways")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
