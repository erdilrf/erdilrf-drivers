# Arduino / C++ driver

`ERDILRF_LRF.h` is a header-only driver for the ERDI 905 nm rangefinder UART protocol, plus one
example sketch in [`examples/BasicRanging/`](examples/BasicRanging/BasicRanging.ino).

## 📦 Installable from the Arduino Library Manager

This library is published in a **dedicated repository** so it can be indexed:

**→ [github.com/erdilrf/erdilrf-lrf-arduino](https://github.com/erdilrf/erdilrf-lrf-arduino)**

Search for `ERDILRF_LRF` in **Tools → Manage Libraries…**, or with PlatformIO:

```ini
lib_deps = erdilrf/ERDILRF_LRF
```

**Why a separate repository?** The Arduino Library Manager requires `library.properties` to be at the
**root of the repository**. This combined repository is a monorepo, so that is impossible here —
putting `library.properties` at this repository's root would also make the build-verification sketch
under `arduino-build/src/` get compiled as library source.

**Which copy is authoritative?** The files under `arduino/` here are the **development copy**; the
dedicated repository is the **distribution artifact**. They are kept identical by hand at release
time, which is a known drift risk — run the check to detect divergence:

```bash
python tools/check_arduino_sync.py
```

It compares the SHA-256 of `arduino/src/ERDILRF_LRF.h` here against the copy fetched from the
distribution repository, and fails loudly on divergence rather than letting the two quietly differ.


## Verification status — read this before trusting it

| Checked | How |
|---|---|
| Function codes, header bytes, frame length | ✅ Cross-checked against the tested Python implementation by `python/tests/test_arduino_parity.py` |
| Transmit frames reproduce the manufacturer's printed bytes | ✅ Same test — the C++ checksum arithmetic is re-implemented and compared with all four published frames |
| Both checksum rules present and distinct | ✅ Same test |
| **The C++ compiles** | ✅ **Verified on AVR — see below** |
| **The receive state machine behaves on hardware** | ❌ **Not verified.** No module and no board. |

### Compilation evidence

`arduino-build/` is a PlatformIO project whose only job is to prove this header compiles. Reproduce it:

```bash
cd arduino-build && pio run
```

Last verified run (PlatformIO Core 6.2.0, `framework-arduino-avr` 5.4.0, `toolchain-atmelavr`
1.70300):

```text
uno            SUCCESS    RAM 14.3% (293/2048 B)   Flash 16.5% (5312/32256 B)
nanoatmega328  SUCCESS    RAM 14.3% (293/2048 B)   Flash 17.3% (5312/30720 B)
2 succeeded
```

The example sketch compiles too (it pulls in `SoftwareSerial` on AVR):

```text
pio ci --board=uno --lib=arduino arduino/examples/BasicRanging/BasicRanging.ino
uno  SUCCESS   RAM 16.5% (337/2048 B)   Flash 18.8% (6076/32256 B)
```

**AVR was chosen deliberately**: 16-bit `int`, 2 KB of RAM, no FPU. If it builds there it is very
unlikely to break on a 32-bit MCU. `build_flags = -Wall -Wextra` is on, and the build reports
**zero warnings originating from this driver** — the 8 warnings that appear all come from the Arduino
core's own `new.cpp` (`unused parameter 'tag'`).

`arduino-build/src/main.cpp` additionally calls every public member and re-checks the six published
checksums **on-target at runtime**, printing `FAILURES=0` on a healthy build. That is a real self-test,
not decoration.

The Python side of this repository carries 50 passing tests. The C++ side now carries compilation
proof plus constant-level parity. **Neither has ever run against a physical module** — the framing is
verified against the manual and against itself, not against hardware. Stating that plainly is the
point.

**If you compile it and it fails on your toolchain, that is a bug report this project wants.** Please
include the compiler, version, board, and the exact error.

## What was mechanically verified

`checksumSend()` implements `(FUNC + D1 + D2 + D3 + D4) & 0xFF` and `checksumResponse()` sums the
first seven bytes. Feeding the four documented function codes through the C++ arithmetic reproduces
`55 AA 88 FF FF FF FF 84`, `55 AA 89 FF FF FF FF 85`, `55 AA 8E FF FF FF FF 8A` and
`55 AA 8A FF FF FF FF 86` exactly. The test fails if any constant in the header drifts from the
Python implementation.

## Usage

```cpp
#include "ERDILRF_LRF.h"

ErdilrfLrf lrf(Serial1);     // any Stream: hardware UART, SoftwareSerial, ...

void setup() {
  Serial1.begin(115200);

  ErdilrfLrf::Frame st;
  if (lrf.readPowerOnSelfTest(st)) {
    // STA 0x01 = initialisation OK
  }
}

void loop() {
  float d = lrf.singleShot();
  if (d >= 0.0f)        Serial.println(d);
  else if (d > -1.5f)   Serial.println("shot failed (poor target)");   // module answered
  else                  Serial.println("no answer - check wiring");    // nothing came back
  delay(500);
}
```

`singleShot()` deliberately returns three distinguishable outcomes:

| Return | Meaning |
|---|---|
| `>= 0` | distance in metres |
| `-1.0` | the module answered and reported `STA != 1` — the shot failed |
| `-2.0` | no valid frame arrived at all |

Collapsing the last two into a single "error" hides the difference between *a bad target* and *a bad
cable*, which are the two things an integrator actually needs to tell apart.

## Notes and limits

* Default link is **115200 8N1**. The manufacturer documents 115200 and 8 data bits but is **silent
  on parity and stop bits** — 8N1 is an assumption, not a documented fact. If the module is silent,
  try `SERIAL_8E1` before suspecting the wiring.
* `readFrame()` resynchronises on the `55 AA` header, so one corrupt frame costs one frame.
* `setLdConstantOn()` is fire-and-forget: the manual's response row for that command is incomplete,
  and this driver does not invent a layout to wait for.
* `requestBaudRate()` takes the raw `TYPE` selector and occupies the **function** byte, matching the
  manual's `55 AA TYPE FF FF FF FF SUM` frame. The change applies only after a restart.
* Angle measurement is only present on modules fitted with an angle sensor.
* `SoftwareSerial` at 115200 bps is unreliable on 16 MHz AVR boards. Prefer a hardware UART on
  ESP32 / STM32 / RP2040 / Teensy, or drop the module to 57600 bps first.
