# erdilrf-drivers

Open-source host drivers and a verified protocol reference for **ERDI 905 nm laser rangefinder
modules** — the LR1000E2 UART protocol family.

[![tests](https://img.shields.io/badge/tests-50%20passing-brightgreen)](#tests)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](python/)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![dependencies](https://img.shields.io/badge/core%20dependencies-none-brightgreen)](python/pyproject.toml)

If you are integrating a 905 nm single-point DToF ranging module over UART and you have the
datasheet but not the byte layout, this repository is the byte layout.

```text
TX  55 AA 88 FF FF FF FF 84     single-shot ranging
RX  55 AA 88 01 FF 27 10 BE     STA=1, 0x2710 = 10000 -> 1000.0 m
```

---

## What is in here

| Path | What it is |
|---|---|
| [`protocol/PROTOCOL.md`](protocol/PROTOCOL.md) | Full 8-byte UART frame reference: every documented command, both checksum ranges, distance and angle decoding |
| [`protocol/verification.md`](protocol/verification.md) | The checksum arithmetic, re-derived independently of the manufacturer's printed values |
| [`docs/what-the-datasheet-does-not-say.md`](docs/what-the-datasheet-does-not-say.md) | Four gaps in the published datasheet — parity, wire colours, enable polarity, an incomplete response frame — and how to work around each |
| [`docs/open-source-laser-ranging-projects.md`](docs/open-source-laser-ranging-projects.md) | Categorised open-source projects for ranging and LiDAR integration. Every link verified before publication |
| [`python/`](python/) | Host driver. **Zero core dependencies** — pure standard library. `pyserial` is optional |
| [`arduino/`](arduino/) | Arduino library (header-only) + `library.properties` / `library.json` metadata, plus a minimal `.ino` example |
| [`arduino-build/`](arduino-build/) | PlatformIO project that **proves the Arduino driver compiles** on AVR. `cd arduino-build && pio run` |
| [`docs/WIRING.md`](docs/WIRING.md) | Pinout, level shifting, and the two wiring mistakes that account for most "it does not work" reports |

## Quick start (Python)

```bash
pip install -e python/            # no dependencies beyond the standard library
pip install pyserial              # only needed to actually open a port
```

```bash
erdilrf frames                     # print the whole command table — no hardware needed
erdilrf decode "55 AA 88 01 FF 27 10 BE"   # decode a captured frame — no hardware needed
erdilrf ports
erdilrf measure --port COM3 --count 5
erdilrf stream  --port COM3
erdilrf selftest --port COM3       # run immediately after power-on
```

```python
from erdilrf_lrf import Rangefinder, SerialTransport

with Rangefinder(SerialTransport("COM3")) as rf:
    print(rf.single_shot())                 # 123.4 metres, or None if the shot failed
    for distance in rf.stream(count=10):    # 3-10 Hz adaptive continuous ranging
        print(distance)
```

## The protocol in one table

Fixed 8-byte frames. Checksum is the low byte of a sum — and **the two directions use different
ranges**, which is the single most common integration mistake.

```text
offset   0     1     2      3    4    5     6      7
        0x55  0xAA  FUNC   D1   D2   D3    D4     SUM

host  -> module   SUM = (FUNC + D1 + D2 + D3 + D4) & 0xFF
module -> host    SUM = (0x55 + 0xAA + FUNC + D1 + D2 + D3 + D4) & 0xFF
```

| Command | Transmit | Response |
|---|---|---|
| Single-shot ranging | `55 AA 88 FF FF FF FF 84` | `55 AA 88 STA FF DIS_H DIS_L SUM` |
| Continuous ranging | `55 AA 89 FF FF FF FF 85` | `55 AA 89 STA FF DIS_H DIS_L SUM` |
| Stop ranging | `55 AA 8E FF FF FF FF 8A` | `55 AA 8E STA FF FF FF SUM` |
| Angle measurement † | `55 AA 8A FF FF FF FF 86` | `55 AA 8A STA FF ANG_H ANG_L SUM` |
| LD constant-on on / off | `55 AA 86 FF FF FF 01 84` / `… 00 83` | see known gap below |
| Set baud rate | `55 AA TYPE FF FF FF FF SUM` | `55 AA TYPE STA FF FF FF SUM` |

Distance and angle are both scaled by 10 — the 16-bit register holds tenths, so
`((DIS_H << 8) | DIS_L) / 10` gives metres.

† The manual states angle measurement is available **only on modules fitted with an angle sensor**.

Default link: **115200 bps, 8 data bits, 8-byte frame**. The manufacturer documents 115200 and 8
data bits; it is **silent on parity and stop bits**, so this driver assumes 8N1 and says so. If a
module stays silent, try `--parity E` or `--parity O` before assuming a wiring fault.

## Known gaps we did not paper over

Good protocol documentation says what it does not know. These are the places the primary source is
incomplete, and this project deliberately does **not** fill them in:

* **The LD constant-on response frame is incomplete in the published manual** — section 8 prints
  only `55` for that row. This driver therefore sends the command and does not validate a reply.
  It does not guess the missing bytes.
* **Cable wire colours are not documented.** The manual gives pin numbers only:
  1 GND, 2 VCC, 3 I/O (reserved), 4 TXD, 5 RXD, 6 SW-SHOT.
* **SW-SHOT polarity is configuration-dependent.** The manual says "function enable (active high)"
  and in the same row "compatible with active-low control requirements". Confirm per unit.
* **UART logic-level tolerance is not specified.** Only the 3.3–5 V supply figure is given.
* The manual covers the **LR1000E2**. Other families in the 905 nm line share the `55 AA` framing
  where they publish protocol tables, but function codes are **not** assumed identical.

A capture from real hardware outranks every row above. If your module disagrees, open an issue with
the raw bytes.

## Tests

50 tests, no hardware and no serial port required — serial I/O is injected as a two-method
transport, so the whole driver runs against a scripted fake link.

```bash
cd python && python -m pytest -q
```

```text
50 passed
```

The suite is not decoration; it has already caught real defects in this repository:

* `FrameReader` validated *transmitted* frames with the *response* checksum rule and rejected every
  one of them. Found by `test_reader_reassembles_a_frame_split_at_every_offset`.
* A pre-command flush consumed a frame and discarded the rest of the parsed batch, silently eating
  the answer to the command it had just sent. That is a wrong distance with no error — the worst
  failure this driver can produce. Found by the device-layer tests.
* The fake transport itself had to be rebuilt: a static response buffer cannot express "the answer
  arrives *after* the command", which is exactly the ordering under test.

Golden vectors assert that all six transmit frames printed in the manufacturer's manual are
reproduced byte for byte, and that each printed checksum is reproducible from the stated rule.

### What the tests do *not* cover

The **Arduino/C++ driver is compile-verified but has never run against a physical module.**
`arduino-build/` is a PlatformIO project that builds the header for `uno` and `nanoatmega328`
(ATmega328P — 16-bit `int`, 2 KB RAM, no FPU) with `-Wall -Wextra` and **zero warnings from this
driver**; the example sketch compiles as well. Its constants are also cross-checked against the Python
implementation by `python/tests/test_arduino_parity.py`.

What remains unverified is **behaviour on real hardware** — no test in this repository has ever run
against a real module. The framing is verified against the manual and against itself, not against
silicon. See [`arduino/README.md`](arduino/README.md) for the exact numbers and how to reproduce them.

## Who this is for

Engineers integrating a **civilian industrial optical distance-measurement sensor module**: UAV and
drone payloads, mobile robots and AGVs, surveying and mapping instruments, industrial safety and
automation, and handheld optical devices.

The module is **IEC 60825-1 Class 1** and operates at **905 ± 5 nm**. The manufacturer's own manual
restricts the product to **civilian applications** and excludes defence use.

## Hardware reference

| Parameter | Value |
|---|---|
| Wavelength | 905 ± 5 nm |
| Measurement range | 4–1000 m (LR1000E2) |
| Accuracy | ±1 m (d ≤ 400 m); ±(1 m + 0.001d) (d > 400 m) |
| Measurement rate | 3–10 Hz adaptive |
| Interface | UART-TTL, default 115200 bps, 8-byte frame |
| Supply | 3.3–5 V |
| Laser safety | IEC 60825-1 Class 1 |

Full parameter tables, and the families this protocol applies to, are in
[`protocol/PROTOCOL.md`](protocol/PROTOCOL.md).

## Contributing

The most useful contribution is a **contradicting capture**: raw bytes from a module that disagrees
with a row in `PROTOCOL.md`. Test coverage for a new module family is welcome. Please do not send
captures containing customer site names, coordinates, or serial numbers.

## License

MIT. `LICENSE`.

---

<sub>Maintained alongside the ERDI 905 nm laser rangefinder module line. Protocol reference derived
from the LR1000E2 user manual v1.2 (2025.10, ERDI TECH LTD), section 8.</sub>
