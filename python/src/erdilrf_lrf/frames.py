"""
erdilrf_lrf.frames — ERDI 905 nm laser rangefinder UART framing.

Pure standard library. No serial dependency, so this module is testable anywhere.

Frame layout (8 bytes, fixed):

    offset   0     1     2      3    4    5    6      7
            0x55  0xAA  FUNC   D1   D2   D3   D4    SUM

Checksum — and this is the part people get wrong:

    host -> module   SUM = (FUNC + D1 + D2 + D3 + D4) & 0xFF
    module -> host   SUM = (0x55 + 0xAA + FUNC + D1 + D2 + D3 + D4) & 0xFF

The two directions use different ranges. The manufacturer's manual states this in its own
notes; this module encodes it as two separate functions so it cannot be confused.

Source: LR1000E2 User Manual v1.2 (2025.10, ERDI TECH LTD) section 8.
See protocol/PROTOCOL.md for the full reference and protocol/verification.md for the
checksum arithmetic re-derived independently of the manual's printed values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

HEADER_H = 0x55
HEADER_L = 0xAA
FRAME_LEN = 8
PAD = 0xFF

# ---------------------------------------------------------------- function codes

FUNC_SELF_TEST = 0x80          # module -> host, unsolicited, at power-on
FUNC_LD_CONSTANT_ON = 0x86     # host -> module, D4 selects enable/disable
FUNC_SINGLE_SHOT = 0x88
FUNC_CONTINUOUS = 0x89
FUNC_ANGLE = 0x8A
FUNC_STOP = 0x8E
# NOTE: set-baud has no separate function code. The manual's `TYPE` selector occupies the
# FUNCTION position itself (frame is `55 AA TYPE FF FF FF FF SUM`), so its "func" byte is
# one of BAUD_BY_CODE's keys. Do not invent a distinct constant for it.

#: Baud-rate selector codes, from the manual's TYPE table.
BAUD_CODES: dict[int, int] = {
    9600: 0x01,
    14400: 0x02,
    19200: 0x03,
    38400: 0x04,
    56000: 0x05,
    57600: 0x06,
    115200: 0x07,
    128000: 0x08,
    230400: 0x09,
}
BAUD_BY_CODE: dict[int, int] = {v: k for k, v in BAUD_CODES.items()}

#: LD constant-on selector (goes in D4).
LD_ON = 0x01
LD_OFF = 0x00

#: STA values are per-command, not global. See PROTOCOL.md section 6.
STA_SUCCESS = 0x01
STA_FAILURE = 0x00


class ProtocolError(ValueError):
    """Raised when bytes cannot be interpreted as a valid ERDI frame."""


# ---------------------------------------------------------------- checksums


def checksum_send(func: int, d1: int = PAD, d2: int = PAD, d3: int = PAD, d4: int = PAD) -> int:
    """Checksum for a host -> module frame: low byte of FUNC + D1 + D2 + D3 + D4."""
    return (func + d1 + d2 + d3 + d4) & 0xFF


def checksum_response(frame: bytes) -> int:
    """
    Checksum for a module -> host frame: low byte of
    HEADER_H + HEADER_L + FUNC + D1 + D2 + D3 + D4.

    Accepts the first 7 bytes, or a full 8-byte frame (byte 7 is ignored).
    """
    if len(frame) < 7:
        raise ProtocolError(f"need at least 7 bytes to checksum a response, got {len(frame)}")
    return sum(frame[:7]) & 0xFF


# ---------------------------------------------------------------- building


def build_command(func: int, d1: int = PAD, d2: int = PAD, d3: int = PAD, d4: int = PAD) -> bytes:
    """Build an 8-byte host -> module frame with the correct send-side checksum."""
    for name, val in (("func", func), ("d1", d1), ("d2", d2), ("d3", d3), ("d4", d4)):
        if not 0 <= val <= 0xFF:
            raise ProtocolError(f"{name}=0x{val:X} does not fit in one byte")
    return bytes([HEADER_H, HEADER_L, func, d1, d2, d3, d4,
                  checksum_send(func, d1, d2, d3, d4)])


# ---------------------------------------------------------------- the command set

CMD_SINGLE_SHOT = build_command(FUNC_SINGLE_SHOT)   # 55 AA 88 FF FF FF FF 84
CMD_CONTINUOUS = build_command(FUNC_CONTINUOUS)     # 55 AA 89 FF FF FF FF 85
CMD_STOP = build_command(FUNC_STOP)                 # 55 AA 8E FF FF FF FF 8A
CMD_ANGLE = build_command(FUNC_ANGLE)               # 55 AA 8A FF FF FF FF 86
CMD_LD_ON = build_command(FUNC_LD_CONSTANT_ON, PAD, PAD, PAD, LD_ON)    # ... FF FF FF 01 84
CMD_LD_OFF = build_command(FUNC_LD_CONSTANT_ON, PAD, PAD, PAD, LD_OFF)  # ... FF FF FF 00 83


def set_baud_command(baud: int) -> bytes:
    """
    Build the set-baud frame. The selector is carried in D1 (the manual calls this field TYPE).

    Reminder: the new rate applies only after the module is restarted.
    """
    if baud not in BAUD_CODES:
        raise ProtocolError(
            f"unsupported baud {baud}; supported: {sorted(BAUD_CODES)}")
    return build_command(BAUD_CODES[baud])


# ---------------------------------------------------------------- parsing


class Frame(NamedTuple):
    func: int
    d1: int
    d2: int
    d3: int
    d4: int
    checksum: int
    raw: bytes
    #: which checksum rule this frame is subject to: "response" (module -> host) or
    #: "command" (host -> module). The two rules genuinely differ, so a frame that does not
    #: record its direction cannot be validated. This field exists because omitting it was a
    #: real bug: FrameReader validated TX frames with the RX rule and rejected every one.
    direction: str = "response"

    @property
    def expected_checksum(self) -> int:
        if self.direction == "command":
            return checksum_send(self.func, self.d1, self.d2, self.d3, self.d4)
        return checksum_response(self.raw)

    @property
    def checksum_ok(self) -> bool:
        return self.checksum == self.expected_checksum

    @property
    def sta(self) -> int:
        return self.d1

    @property
    def is_self_test(self) -> bool:
        return self.func == FUNC_SELF_TEST

    @property
    def error_code(self) -> int | None:
        """Self-test error code, present in D4 of a `55 AA 80` frame."""
        return self.d4 if self.is_self_test else None


DIRECTIONS = ("response", "command")


def parse_frame(data: bytes, *, direction: str = "response", verify_checksum: bool = True) -> Frame:
    """
    Parse exactly 8 bytes into a Frame.

    `direction` selects the checksum rule: "response" for module -> host frames (the default,
    matching what a host reads from the port) or "command" for host -> module frames.

    Raises ProtocolError on wrong length, wrong header, or (unless disabled) a bad checksum.
    """
    if direction not in DIRECTIONS:
        raise ProtocolError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    if len(data) != FRAME_LEN:
        raise ProtocolError(f"expected {FRAME_LEN} bytes, got {len(data)}: {data.hex(' ')}")
    if data[0] != HEADER_H or data[1] != HEADER_L:
        raise ProtocolError(f"bad header {data[0]:02X} {data[1]:02X}, expected 55 AA")
    f = Frame(data[2], data[3], data[4], data[5], data[6], data[7], bytes(data), direction)
    if verify_checksum and not f.checksum_ok:
        raise ProtocolError(
            f"checksum mismatch: frame says 0x{f.checksum:02X}, "
            f"{'SUM[3:7]' if direction == 'command' else 'SUM[1:7]'} sums to "
            f"0x{f.expected_checksum:02X}")
    return f


class FrameReader:
    """
    Byte-stream reassembler.

    Feed it arbitrary chunks from a serial port; it yields complete, checksum-valid Frame
    objects. Resynchronises on the 55 AA header, so a truncated or corrupted frame costs at
    most one frame and never poisons the stream.

    Use the default `direction="response"` for bytes read from the module. Switch to
    "command" only when replaying frames you transmitted.
    """

    def __init__(self, *, direction: str = "response", verify_checksum: bool = True,
                 collect_errors: bool = True) -> None:
        if direction not in DIRECTIONS:
            raise ProtocolError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
        self._buf = bytearray()
        self._direction = direction
        self._verify = verify_checksum
        self._collect_errors = collect_errors
        self.errors: list[str] = []

    def feed(self, chunk: bytes) -> list[Frame]:
        if chunk:
            self._buf.extend(chunk)
        return list(self._drain())

    def _drain(self):
        while True:
            # drop leading bytes until the header aligns
            i = self._buf.find(bytes([HEADER_H, HEADER_L]))
            if i < 0:
                # keep only a possible half-header at the tail
                if self._buf[-1:] == bytes([HEADER_H]):
                    del self._buf[:-1]
                else:
                    self._buf.clear()
                return
            if i:
                if self._collect_errors:
                    self.errors.append(f"discarded {i} non-header byte(s): {bytes(self._buf[:i]).hex(' ')}")
                del self._buf[:i]
            if len(self._buf) < FRAME_LEN:
                return
            candidate = bytes(self._buf[:FRAME_LEN])
            try:
                yield parse_frame(candidate, direction=self._direction,
                                  verify_checksum=self._verify)
            except ProtocolError as exc:
                if self._collect_errors:
                    self.errors.append(str(exc))
                # a bad frame can still hide the real header one byte in; step forward by 1
                del self._buf[:1]
                continue
            del self._buf[:FRAME_LEN]


# ---------------------------------------------------------------- decoding


def decode_distance(frame: Frame) -> float:
    """
    Measured distance in **metres**.

    The manual states: reported value = measured value x 10, so the 16-bit register holds
    tenths of a metre. DIS_H is D3, DIS_L is D4.
    """
    if frame.d2 != PAD:
        raise ProtocolError(
            f"expected 0xFF in D2 of a ranging response, got 0x{frame.d2:02X}")
    if frame.sta != STA_SUCCESS:
        raise ProtocolError(f"measurement failed (STA=0x{frame.sta:02X})")
    raw = (frame.d3 << 8) | frame.d4
    return raw / 10.0


def decode_angle(frame: Frame) -> float:
    """Measured angle in degrees, same x10 scaling. Only on modules with an angle sensor."""
    if frame.sta != STA_SUCCESS:
        raise ProtocolError(f"angle measurement failed (STA=0x{frame.sta:02X})")
    raw = (frame.d3 << 8) | frame.d4
    return raw / 10.0


def decode_distance_or_none(frame: Frame) -> float | None:
    """Convenience for polling loops: metres, or None when STA reports a failed measurement."""
    try:
        return decode_distance(frame)
    except ProtocolError:
        return None


# ---------------------------------------------------------------- human-readable helpers


@dataclass(frozen=True)
class FrameSummary:
    func: int
    name: str
    sta: int
    sta_meaning: str
    detail: str


_NAMES = {
    FUNC_SELF_TEST: "power-on self-test",
    FUNC_LD_CONSTANT_ON: "LD constant-on mode",
    FUNC_SINGLE_SHOT: "single-shot ranging",
    FUNC_CONTINUOUS: "continuous ranging",
    FUNC_ANGLE: "angle measurement",
    FUNC_STOP: "stop ranging",
}


def summarise(frame: Frame) -> FrameSummary:
    name = _NAMES.get(frame.func, f"unknown function 0x{frame.func:02X}")
    sta, meaning, detail = frame.sta, "", ""

    if frame.direction == "command":
        # A transmitted frame's D1 is a parameter, not a status byte. Reporting "measurement
        # failed" here would invent a fault out of a field that has no such meaning.
        return FrameSummary(frame.func, name, sta,
                            "n/a (transmitted frame — D1 is a parameter, not STA)", "")

    if frame.func in BAUD_BY_CODE:
        name = f"set baud to {BAUD_BY_CODE[frame.func]} bps"
        meaning = "setting successful" if sta == STA_SUCCESS else "setting failed"
        detail = "takes effect after restart"
    elif frame.func in (FUNC_SINGLE_SHOT, FUNC_CONTINUOUS):
        meaning = "measurement successful" if sta == STA_SUCCESS else "measurement failed"
        if sta == STA_SUCCESS:
            detail = f"{(frame.d3 << 8 | frame.d4) / 10.0:.1f} m"
    elif frame.func == FUNC_STOP:
        meaning = "stopped" if sta == STA_SUCCESS else "failed to stop"
    elif frame.func == FUNC_ANGLE:
        meaning = "measurement successful" if sta == STA_SUCCESS else "measurement failed"
        if sta == STA_SUCCESS:
            detail = f"{(frame.d3 << 8 | frame.d4) / 10.0:.1f} deg"
    elif frame.func == FUNC_SELF_TEST:
        meaning = "init succeeded" if sta == STA_SUCCESS else "init FAILED"
        if sta != STA_SUCCESS:
            detail = f"ErrCode=0x{frame.d4:02X}"
    else:
        meaning = "n/a"

    return FrameSummary(frame.func, name, sta, meaning, detail)
