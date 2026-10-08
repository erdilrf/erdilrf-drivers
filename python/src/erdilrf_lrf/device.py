"""
erdilrf_lrf.device — high-level host access to an ERDI 905 nm rangefinder module.

The module deliberately depends on nothing but the standard library. Serial I/O is injected as a
small duck-typed transport, which means:

* the whole device layer is testable without hardware (see `tests/test_device.py`);
* you can bring your own link — pyserial, a socket, an MCU bridge, a recorded capture.

`SerialTransport` is provided for the common case and imports pyserial lazily, so importing this
module never requires it.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Iterable, Protocol, runtime_checkable

from . import frames as F

__all__ = ["Transport", "SerialTransport", "Rangefinder", "DeviceTimeout"]


class DeviceTimeout(TimeoutError):
    """No matching frame arrived within the timeout."""


@runtime_checkable
class Transport(Protocol):
    """Minimal link the driver needs. Implement these two methods and nothing else."""

    def write(self, data: bytes) -> int:
        """Send bytes to the module. Return the number accepted."""

    def read(self, size: int) -> bytes:
        """Return up to `size` bytes, blocking only as long as your own timeout allows."""


class SerialTransport:
    """
    pyserial-backed transport.

    Defaults are 115200 8N1 — the manual documents 115200 and 8 data bits but is silent on parity
    and stop bits, so 8N1 is an assumption recorded in PROTOCOL.md, not a documented fact. If a
    module stays silent, try `parity="E"` or `parity="O"` before assuming a wiring fault.
    """

    def __init__(self, port: str, baudrate: int = 115200, *, parity: str = "N",
                 stopbits: float = 1, read_timeout: float = 0.2) -> None:
        try:
            import serial  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "pyserial is required to open a serial port. "
                "Install it with:  pip install pyserial"
            ) from exc
        self._serial_mod = serial
        self.port = port
        self.baudrate = baudrate
        self._ser = serial.Serial(
            port=port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
            parity={"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                    "O": serial.PARITY_ODD}[parity.upper()],
            stopbits={1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE,
                      2: serial.STOPBITS_TWO}[float(stopbits)],
            timeout=read_timeout,
        )

    def write(self, data: bytes) -> int:
        return self._ser.write(data)

    def read(self, size: int) -> bytes:
        return self._ser.read(size)

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:  # noqa: BLE001 - closing must never mask the real error
            pass

    def __enter__(self) -> "SerialTransport":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def list_ports() -> list[str]:
        try:
            from serial.tools import list_ports  # type: ignore
        except ImportError:
            return []
        return [p.device for p in list_ports.comports()]


class Rangefinder:
    """
    Blocking, single-threaded host driver.

    Every call reads from the transport until it sees the frame it is waiting for or the deadline
    passes. Unrelated and self-test frames are recorded in `self.unsolicited` rather than
    discarded, because on a real module the power-on self-test arrives when it feels like it and
    swallowing it hides real faults.
    """

    def __init__(self, transport: Transport, *, timeout: float = 1.0, chunk: int = 64) -> None:
        self.transport = transport
        self.timeout = timeout
        self.chunk = chunk
        self.reader = F.FrameReader()
        self.unsolicited: list[F.Frame] = []
        self.self_test: F.Frame | None = None
        # Frames already parsed but not yet consumed. This queue is why the driver cannot lose a
        # response: an earlier draft flushed by *consuming* a frame and discarding the rest of the
        # parsed batch, which silently ate the answer to the very command it had just sent.
        self._pending: deque[F.Frame] = deque()

    # ---------------------------------------------------------------- plumbing

    def _fill(self, deadline: float) -> None:
        """Block until at least one frame is pending, or the deadline passes."""
        while not self._pending:
            chunk = self.transport.read(self.chunk)
            if chunk:
                self._pending.extend(self.reader.feed(chunk))
            if self._pending:
                return
            if time.monotonic() >= deadline:
                return

    def _flush(self) -> list[F.Frame]:
        """
        Drop everything already sitting in the link *before* a command is sent.

        On a real port a previous command's answer, or a burst of unrelated frames, can still be
        buffered. Accepting one of those as the answer to the next command yields a wrong distance
        with no error — the worst outcome this driver can produce. So they are discarded, and
        recorded in the returned list for anyone who wants to see them.
        """
        dropped: list[F.Frame] = list(self._pending)
        self._pending.clear()
        while True:
            chunk = self.transport.read(self.chunk)
            if not chunk:
                break
            dropped.extend(self.reader.feed(chunk))
        return dropped

    def _pump(self, deadline: float, want: Iterable[int] | None) -> F.Frame | None:
        wanted = set(want) if want is not None else None
        while True:
            self._fill(deadline)
            if not self._pending:
                return None
            f = self._pending.popleft()
            if f.is_self_test:
                self.self_test = f
                if wanted is None or F.FUNC_SELF_TEST in wanted:
                    return f
                self.unsolicited.append(f)
                continue
            if wanted is None or f.func in wanted:
                return f
            # a frame for some other command: keep it visible, do not return it
            self.unsolicited.append(f)
            if time.monotonic() >= deadline:
                return None

    def _exchange(self, command: bytes, expect: Iterable[int], timeout: float | None = None) -> F.Frame:
        budget = self.timeout if timeout is None else timeout
        self._flush()
        self.transport.write(command)
        frame = self._pump(time.monotonic() + budget, expect)
        if frame is None:
            raise DeviceTimeout(
                f"no response to {command.hex(' ').upper()} within {budget}s "
                f"(wanted func {[hex(x) for x in expect]})")
        return frame

    # ---------------------------------------------------------------- measurements

    def single_shot(self) -> float | None:
        """
        Trigger one measurement and return metres.

        Returns None when the module answers but reports a failed measurement (STA != 1), which is
        a normal outcome against a poor target. Raises DeviceTimeout when it does not answer at all.
        """
        frame = self._exchange(F.CMD_SINGLE_SHOT, (F.FUNC_SINGLE_SHOT,))
        return F.decode_distance_or_none(frame)

    def start_continuous(self) -> None:
        self.transport.write(F.CMD_CONTINUOUS)

    def stop_continuous(self, *, timeout: float | None = None) -> bool:
        frame = self._exchange(F.CMD_STOP, (F.FUNC_STOP,), timeout)
        return frame.sta == F.STA_SUCCESS

    def stream(self, count: int | None = None, *, settle: float = 0.05) -> Iterable[float | None]:
        """
        Start continuous ranging and yield distances in metres.

        Yields `count` samples (or forever when count is None). Stops continuous mode on exit.
        Frames arriving before the first valid range are yielded as None rather than dropped, so a
        caller can see how long the module took to lock on.
        """
        self.start_continuous()
        time.sleep(settle)
        produced = 0
        try:
            while count is None or produced < count:
                frame = self._pump(time.monotonic() + self.timeout, (F.FUNC_CONTINUOUS,))
                if frame is None:
                    raise DeviceTimeout("continuous ranging went quiet")
                yield F.decode_distance_or_none(frame)
                produced += 1
        finally:
            try:
                self.stop_continuous(timeout=0.5)
            except (DeviceTimeout, F.ProtocolError):
                pass

    def angle(self) -> float | None:
        """
        Angle in degrees. Only available on modules fitted with an angle sensor — the manual says so
        explicitly. On a rangefinder-only module expect a timeout, not a wrong number.
        """
        frame = self._exchange(F.CMD_ANGLE, (F.FUNC_ANGLE,))
        if frame.sta != F.STA_SUCCESS:
            return None
        return F.decode_angle(frame)

    def read_self_test(self, timeout: float | None = None) -> F.Frame | None:
        """
        Wait for the unsolicited power-on self-test frame.

        Best called immediately after opening the port, *before* anything else: the frame is emitted
        once at power-on, so if you have already sent other commands you have probably missed it and
        will get None. That is not a fault.
        """
        return self._pump(time.monotonic() + (self.timeout if timeout is None else timeout),
                          (F.FUNC_SELF_TEST,))

    # ---------------------------------------------------------------- configuration

    def set_baud(self, baud: int, *, timeout: float | None = None) -> bool:
        """
        Request a new baud rate. Returns True when the module accepted it.

        The change takes effect only after the module is restarted. This method does **not**
        reconfigure the transport — do that yourself after the restart, otherwise the accepted
        setting and the open port will disagree.
        """
        frame = self._exchange(F.set_baud_command(baud), (F.BAUD_CODES[baud],), timeout)
        return frame.sta == F.STA_SUCCESS

    def ld_constant_on(self, enable: bool) -> None:
        """
        Turn the laser diode constant-on mode on or off.

        Fire-and-forget: the manual's response row for this command is incomplete (it prints only
        `55`), so this library does not invent a frame layout to validate against. See
        PROTOCOL.md section 3.6. The manufacturer warns against leaving it enabled for long periods.
        """
        self.transport.write(F.CMD_LD_ON if enable else F.CMD_LD_OFF)

    def __enter__(self) -> "Rangefinder":
        return self

    def __exit__(self, *exc) -> None:
        close = getattr(self.transport, "close", None)
        if callable(close):
            close()
