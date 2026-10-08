"""
erdilrf_lrf — host-side driver for ERDI 905 nm laser rangefinder modules.

Framing and protocol: [`frames`][erdilrf_lrf.frames].
High-level device access: [`device`][erdilrf_lrf.device].

The protocol implemented here is documented in `protocol/PROTOCOL.md` and was derived from
the manufacturer's LR1000E2 user manual v1.2, with every published frame recomputed from the
stated checksum rule before release.
"""

from __future__ import annotations

from .frames import (
    BAUD_BY_CODE,
    BAUD_CODES,
    CMD_ANGLE,
    CMD_CONTINUOUS,
    CMD_LD_OFF,
    CMD_LD_ON,
    CMD_SINGLE_SHOT,
    CMD_STOP,
    FRAME_LEN,
    Frame,
    FrameReader,
    ProtocolError,
    build_command,
    checksum_response,
    checksum_send,
    decode_angle,
    decode_distance,
    decode_distance_or_none,
    parse_frame,
    set_baud_command,
    summarise,
)

__version__ = "0.2.0"

__all__ = [
    "BAUD_BY_CODE",
    "BAUD_CODES",
    "CMD_ANGLE",
    "CMD_CONTINUOUS",
    "CMD_LD_OFF",
    "CMD_LD_ON",
    "CMD_SINGLE_SHOT",
    "CMD_STOP",
    "FRAME_LEN",
    "Frame",
    "FrameReader",
    "ProtocolError",
    "build_command",
    "checksum_response",
    "checksum_send",
    "decode_angle",
    "decode_distance",
    "decode_distance_or_none",
    "parse_frame",
    "set_baud_command",
    "summarise",
    "__version__",
]
