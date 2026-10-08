# Arduino / C++ driver

`ERDILRF_LRF.h` is a header-only driver for the ERDI 905 nm rangefinder UART protocol, plus one
example sketch in [`examples/BasicRanging/`](examples/BasicRanging/BasicRanging.ino).

## ⚠️ Verification status — read this before trusting it

| Checked | How |
|---|---|
| Function codes, header bytes, frame length | ✅ Cross-checked against the tested Python implementation by `python/tests/test_arduino_parity.py` |
| Transmit frames reproduce the manufacturer's printed bytes | ✅ Same test — the C++ checksum arithmetic is re-implemented and compared with all four published frames |
| Both checksum rules present and distinct | ✅ Same test |
| **The C++ compiles** | ❌ **Not verified.** The machine where this repository was authored has **no C++ toolchain** — no `g++`, `gcc`, `clang++`, `cl`, or `cmake` on `PATH`, and no Visual Studio install. |
| **The receive state machine behaves on hardware** | ❌ **Not verified.** No module and no board. |

The Python side of this repository carries 50 passing tests. The C++ side carries a constant-level
parity check and nothing more. Stating that plainly is the point: an unqualified "tested" badge on
code nobody compiled would be worth less than no badge at all.

**If you compile it and it fails, that is a bug report this project wants.** Please include the
compiler, version, board, and the exact error.

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
