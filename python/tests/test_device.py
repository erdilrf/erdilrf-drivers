"""
Device-layer tests against a scripted fake transport.

No hardware, no serial port, no pyserial. This is the point of injecting the transport: the whole
driver is exercised on a machine that has never seen a rangefinder.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402

from erdilrf_lrf import frames as F  # noqa: E402
from erdilrf_lrf.device import DeviceTimeout, Rangefinder  # noqa: E402


def rx(func, d1=0xFF, d2=0xFF, d3=0xFF, d4=0xFF):
    body = bytes([0x55, 0xAA, func, d1, d2, d3, d4])
    return body + bytes([F.checksum_response(body)])


def metres(m):
    raw = int(round(m * 10))
    return rx(F.FUNC_SINGLE_SHOT, 0x01, 0xFF, (raw >> 8) & 0xFF, raw & 0xFF)


class FakeTransport:
    """
    Models a real link, not a static buffer.

    A module only speaks after it is spoken to, so the script is released **one entry per write()**.
    A static queue cannot express "the answer arrives after the command", which is precisely the
    ordering the driver has to get right — an earlier static model let a genuine flush bug pass and
    it produced 11 failures once corrected.

    `preamble` is bytes readable *before* any write: stale traffic left over from a previous
    conversation.
    """

    def __init__(self, script: list[bytes] | None = None, *, preamble: bytes = b"",
                 chunk: int = 64):
        self.script = list(script or [])
        self.queue = bytearray(preamble)
        self.written: list[bytes] = []
        self.chunk = chunk
        self.closed = False

    def write(self, data: bytes) -> int:
        self.written.append(bytes(data))
        if self.script:
            self.queue.extend(self.script.pop(0))
        return len(data)

    def read(self, size: int) -> bytes:
        n = min(size, self.chunk, len(self.queue))
        out = bytes(self.queue[:n])
        del self.queue[:n]
        return out

    def close(self) -> None:
        self.closed = True


# ------------------------------------------------------------------ happy paths


def test_single_shot_returns_metres():
    t = FakeTransport([metres(123.4)])
    rf = Rangefinder(t)
    assert rf.single_shot() == pytest.approx(123.4)
    assert t.written == [F.CMD_SINGLE_SHOT]


def test_single_shot_returns_none_on_failed_measurement():
    """STA != 1 means the shot failed. That is data, not an exception."""
    t = FakeTransport([rx(F.FUNC_SINGLE_SHOT, 0x00, 0xFF, 0x00, 0x00)])
    assert Rangefinder(t).single_shot() is None


def test_single_shot_times_out_when_the_module_is_silent():
    rf = Rangefinder(FakeTransport([]), timeout=0.05)
    with pytest.raises(DeviceTimeout, match="no response"):
        rf.single_shot()


def test_single_shot_survives_a_dribbling_transport():
    t = FakeTransport([metres(7.0)], chunk=1)
    assert Rangefinder(t).single_shot() == pytest.approx(7.0)


def test_single_shot_survives_a_noisy_line():
    """Leading garbage before the real frame must not break acquisition."""
    t = FakeTransport([b"\x00\xff\x13" + metres(7.0)])
    assert Rangefinder(t).single_shot() == pytest.approx(7.0)


def test_stale_bytes_from_a_previous_command_are_not_mistaken_for_the_answer():
    """
    A frame from an earlier conversation is already readable when the call starts; the command's own
    answer follows. The driver must discard the stale one, because returning it hands the caller a
    plausible, wrong distance with no error — the worst failure mode this driver can have.
    """
    t = FakeTransport([metres(2.0)], preamble=metres(1.0))
    rf = Rangefinder(t, timeout=0.2)
    assert rf.single_shot() == pytest.approx(2.0)


def test_a_frame_for_another_command_is_kept_visible_not_returned():
    """An interleaved foreign frame must not be mistaken for the answer, but must not vanish."""
    t = FakeTransport([rx(F.FUNC_ANGLE, 0x01, 0xFF, 0x00, 0x0A) + metres(9.0)])
    rf = Rangefinder(t, timeout=0.2)
    assert rf.single_shot() == pytest.approx(9.0)
    assert [f.func for f in rf.unsolicited] == [F.FUNC_ANGLE]


# ------------------------------------------------------------------ continuous mode


def test_stream_yields_requested_count_and_stops_the_module():
    frames = b"".join(rx(F.FUNC_CONTINUOUS, 0x01, 0xFF, (int(m * 10) >> 8) & 0xFF, int(m * 10) & 0xFF)
                      for m in (5.0, 10.0, 15.0))
    t = FakeTransport([frames, rx(F.FUNC_STOP, 0x01)])
    rf = Rangefinder(t, timeout=0.2)
    assert list(rf.stream(count=3)) == pytest.approx([5.0, 10.0, 15.0])
    assert t.written[0] == F.CMD_CONTINUOUS
    assert F.CMD_STOP in t.written, "continuous mode was never stopped"


def test_stream_reports_failed_shots_as_none():
    frames = (rx(F.FUNC_CONTINUOUS, 0x00, 0xFF, 0x00, 0x00)
              + rx(F.FUNC_CONTINUOUS, 0x01, 0xFF, 0x00, 0x64))
    rf = Rangefinder(FakeTransport([frames, rx(F.FUNC_STOP, 0x01)]), timeout=0.2)
    out = list(rf.stream(count=2))
    assert out[0] is None and out[1] == pytest.approx(10.0)


def test_stream_stops_the_module_even_when_the_consumer_abandons_it():
    frames = b"".join(rx(F.FUNC_CONTINUOUS, 0x01, 0xFF, 0x00, 0x0A) for _ in range(50))
    t = FakeTransport([frames, rx(F.FUNC_STOP, 0x01)])
    rf = Rangefinder(t, timeout=0.2)
    gen = rf.stream()
    next(gen)
    gen.close()                                   # abandoning must still send STOP
    assert F.CMD_STOP in t.written


# ------------------------------------------------------------------ angle / self-test / config


def test_angle_decodes_degrees():
    t = FakeTransport([rx(F.FUNC_ANGLE, 0x01, 0xFF, 0x00, 0x7B)])   # 123 -> 12.3 deg
    assert Rangefinder(t).angle() == pytest.approx(12.3)


def test_angle_returns_none_when_the_module_reports_failure():
    t = FakeTransport([rx(F.FUNC_ANGLE, 0x00, 0xFF, 0x00, 0x00)])
    assert Rangefinder(t).angle() is None


def test_self_test_is_captured_and_surfaced():
    """The self-test is emitted once at power-on, so it is readable before anything is sent."""
    st_frame = rx(F.FUNC_SELF_TEST, 0x01, 0x00, 0x00, 0x00)
    t = FakeTransport([metres(3.0)], preamble=st_frame)
    rf = Rangefinder(t, timeout=0.2)
    st = rf.read_self_test()
    assert st is not None and st.sta == F.STA_SUCCESS
    assert rf.self_test is st
    assert rf.single_shot() == pytest.approx(3.0)


def test_a_failing_self_test_is_visible_not_swallowed():
    t = FakeTransport([], preamble=rx(F.FUNC_SELF_TEST, 0x00, 0x00, 0x00, 0x2A))
    rf = Rangefinder(t, timeout=0.2)
    st = rf.read_self_test()
    assert st is not None and st.sta == F.STA_FAILURE and st.error_code == 0x2A
    assert "FAILED" in F.summarise(st).sta_meaning


def test_unsolicited_self_test_during_a_ranging_call_is_kept():
    """A self-test arriving mid-conversation must be recorded, not silently dropped."""
    t = FakeTransport([rx(F.FUNC_SELF_TEST, 0x01, 0x00, 0x00, 0x00) + metres(42.0)])
    rf = Rangefinder(t, timeout=0.2)
    assert rf.single_shot() == pytest.approx(42.0)
    assert rf.self_test is not None and rf.self_test.func == F.FUNC_SELF_TEST


def test_set_baud_sends_the_selector_and_reports_acceptance():
    t = FakeTransport([rx(F.BAUD_CODES[57600], 0x01)])
    rf = Rangefinder(t, timeout=0.2)
    assert rf.set_baud(57600) is True
    assert t.written[0][2] == F.BAUD_CODES[57600]


def test_set_baud_unsupported_rate_raises_before_transmitting():
    t = FakeTransport([])
    with pytest.raises(F.ProtocolError):
        Rangefinder(t).set_baud(12345)
    assert t.written == []


def test_ld_constant_on_is_fire_and_forget():
    """
    The manual's response row for this command is incomplete, so the driver must not invent a
    frame to wait for. It sends and returns.
    """
    t = FakeTransport([])
    rf = Rangefinder(t, timeout=0.05)
    rf.ld_constant_on(True)
    rf.ld_constant_on(False)
    assert t.written == [F.CMD_LD_ON, F.CMD_LD_OFF]


def test_context_manager_closes_the_transport():
    t = FakeTransport([])
    with Rangefinder(t):
        pass
    assert t.closed is True
