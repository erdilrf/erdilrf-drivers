"""
erdilrf_lrf.cli — command-line access to an ERDI 905 nm rangefinder module.

Two of these commands need no hardware at all, which is deliberate:

    erdilrf frames            print the documented command table
    erdilrf decode <hex>      decode one captured frame

Support engineers spend a lot of time asking customers "paste me the bytes you saw". `decode`
answers that without a module, a driver install, or a working serial port.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from . import frames as F
from .device import DeviceTimeout, Rangefinder, SerialTransport


def _hex(b: bytes) -> str:
    return b.hex(" ").upper()


# ---------------------------------------------------------------- offline commands


def cmd_frames(_args: argparse.Namespace) -> int:
    rows = [
        ("single-shot ranging", F.CMD_SINGLE_SHOT, "55 AA 88 STA FF DIS_H DIS_L SUM"),
        ("continuous ranging", F.CMD_CONTINUOUS, "55 AA 89 STA FF DIS_H DIS_L SUM"),
        ("stop ranging", F.CMD_STOP, "55 AA 8E STA FF FF FF SUM"),
        ("angle measurement", F.CMD_ANGLE, "55 AA 8A STA FF ANG_H ANG_L SUM"),
        ("LD constant-on: enable", F.CMD_LD_ON, "(response frame not published)"),
        ("LD constant-on: disable", F.CMD_LD_OFF, "(response frame not published)"),
    ]
    print(f"ERDI 905 nm rangefinder protocol - erdilrf-lrf {__version__}\n")
    print(f"{'command':26s} {'transmit (8 bytes)':26s} response")
    print("-" * 92)
    for name, tx, rx in rows:
        print(f"{name:26s} {_hex(tx):26s} {rx}")
    print()
    print("checksum, host -> module : (FUNC + D1 + D2 + D3 + D4) & 0xFF")
    print("checksum, module -> host : (55 + AA + FUNC + D1 + D2 + D3 + D4) & 0xFF")
    print("distance                 : ((DIS_H << 8) | DIS_L) / 10 metres")
    print()
    print("set baud rate            : 55 AA TYPE FF FF FF FF SUM")
    print("  " + "  ".join(f"{c:02X}={b}" for b, c in sorted(F.BAUD_CODES.items(), key=lambda kv: kv[1])))
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    text = " ".join(args.hex).replace(",", " ").replace("0x", " ").replace("0X", " ")
    try:
        data = bytes(int(tok, 16) for tok in text.split())
    except ValueError as exc:
        print(f"error: could not read hex bytes: {exc}", file=sys.stderr)
        return 2
    direction = args.direction
    try:
        frame = F.parse_frame(data, direction=direction, verify_checksum=not args.no_checksum)
    except F.ProtocolError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        if len(data) == F.FRAME_LEN and not args.no_checksum:
            alt = "command" if direction == "response" else "response"
            try:
                F.parse_frame(data, direction=alt)
            except F.ProtocolError:
                pass
            else:
                print(f"hint: this frame is valid as a {alt} frame. "
                      f"Re-run with --direction {alt}.", file=sys.stderr)
        return 1

    s = F.summarise(frame)
    print(f"raw        : {_hex(frame.raw)}")
    print(f"direction  : {frame.direction}")
    print(f"func       : 0x{frame.func:02X}  ({s.name})")
    print(f"D1..D4     : {frame.d1:02X} {frame.d2:02X} {frame.d3:02X} {frame.d4:02X}")
    print(f"checksum   : 0x{frame.checksum:02X}  (recomputed 0x{frame.expected_checksum:02X}) "
          f"{'OK' if frame.checksum_ok else 'MISMATCH'}")
    print(f"STA        : 0x{s.sta:02X}  {s.sta_meaning}")
    if s.detail:
        print(f"detail     : {s.detail}")
    if frame.is_self_test and frame.sta != F.STA_SUCCESS:
        print(f"error code : 0x{frame.error_code:02X}")
    return 0


# ---------------------------------------------------------------- hardware commands


def _open(args: argparse.Namespace) -> Rangefinder:
    return Rangefinder(SerialTransport(args.port, args.baud, parity=args.parity,
                                       stopbits=args.stopbits),
                       timeout=args.timeout)


def cmd_ports(_args: argparse.Namespace) -> int:
    ports = SerialTransport.list_ports()
    if not ports:
        print("no serial ports found (or pyserial is not installed: pip install pyserial)")
        return 1
    for p in ports:
        print(p)
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    with _open(args) as rf:
        for i in range(args.count):
            try:
                d = rf.single_shot()
            except DeviceTimeout as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print("no return (shot failed)" if d is None else f"{d:.1f} m")
            if i + 1 < args.count:
                import time
                time.sleep(args.interval)
    return 0


def cmd_stream(args: argparse.Namespace) -> int:
    with _open(args) as rf:
        try:
            for d in rf.stream(count=args.count):
                print("--" if d is None else f"{d:.1f} m")
        except (DeviceTimeout, KeyboardInterrupt):
            print("\nstopped")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """
    Read the unsolicited power-on self-test.

    It is emitted once, at power-on, so this is only meaningful on a freshly powered module. If it
    returns nothing, power-cycle the module and run this again — that is the documented cause, not
    a defect in the tool.
    """
    with _open(args) as rf:
        frame = rf.read_self_test()
        if frame is None:
            print("no self-test frame seen. It is sent once at power-on: "
                  "power-cycle the module and retry immediately.", file=sys.stderr)
            return 1
        s = F.summarise(frame)
        print(f"{s.name}: {s.sta_meaning} {s.detail}".rstrip())
        return 0 if frame.sta == F.STA_SUCCESS else 1


# ---------------------------------------------------------------- wiring


def _add_serial_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port", required=True, help="serial port, e.g. COM3 or /dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--parity", default="N", choices=["N", "E", "O"],
                   help="the manual does not state parity; 8N1 is an assumption")
    p.add_argument("--stopbits", type=float, default=1, choices=[1, 1.5, 2])
    p.add_argument("--timeout", type=float, default=1.0)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="erdilrf",
        description="Host driver for ERDI 905 nm laser rangefinder modules.")
    ap.add_argument("--version", action="version", version=f"erdilrf-lrf {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("frames", help="print the documented command table (no hardware)") \
        .set_defaults(func=cmd_frames)

    d = sub.add_parser("decode", help="decode captured hex bytes (no hardware)")
    d.add_argument("hex", nargs="+", help="8 hex bytes, e.g. '55 AA 88 01 FF 00 64 8A'")
    d.add_argument("--direction", default="response", choices=list(F.DIRECTIONS))
    d.add_argument("--no-checksum", action="store_true", help="decode even if the checksum is bad")
    d.set_defaults(func=cmd_decode)

    sub.add_parser("ports", help="list serial ports").set_defaults(func=cmd_ports)

    m = sub.add_parser("measure", help="trigger single-shot measurements")
    _add_serial_opts(m)
    m.add_argument("--count", type=int, default=1)
    m.add_argument("--interval", type=float, default=0.3)
    m.set_defaults(func=cmd_measure)

    s = sub.add_parser("stream", help="continuous ranging until stopped")
    _add_serial_opts(s)
    s.add_argument("--count", type=int, default=None)
    s.set_defaults(func=cmd_stream)

    t = sub.add_parser("selftest", help="read the power-on self-test frame")
    _add_serial_opts(t)
    t.set_defaults(func=cmd_selftest)

    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
