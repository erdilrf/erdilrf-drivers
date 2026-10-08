/*
 * BasicRanging — minimal ERDI 905 nm rangefinder example.
 *
 * Wiring (the module's TXD/RXD are named from the module's side — cross them):
 *   module pin 1 GND ──── board GND
 *   module pin 2 VCC ──── 3.3 V or 5 V   (plus >= 100 uF bulk capacitance at the module)
 *   module pin 4 TXD ───► board RX
 *   module pin 5 RXD ◄─── board TX
 *   module pin 6 SW-SHOT ─ tie to the level that enables your unit's factory configuration
 *
 * On a classic Uno/Nano, `Serial` is the USB port, so use a software serial on other pins for the
 * module. On a board with spare hardware UARTs (ESP32, Teensy, STM32, RP2040), use one of those.
 *
 * Default link: 115200 bps, 8 data bits, 8-byte frame. The manufacturer documents 115200 and 8 data
 * bits but is SILENT on parity and stop bits; 8N1 is an assumption, not a documented fact.
 */

#include "ERDILRF_LRF.h"

#if defined(ARDUINO_ARCH_AVR)
  #include <SoftwareSerial.h>
  SoftwareSerial moduleSerial(10, 11);   // RX, TX
#else
  #define moduleSerial Serial1
#endif

ErdilrfLrf lrf(moduleSerial);

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { /* wait for USB CDC, but never forever */ }
  moduleSerial.begin(115200);

  Serial.println(F("ERDI 905 nm rangefinder - basic ranging"));
  Serial.println(F("Protocol: 8-byte frames, 55 AA header, checksums differ per direction."));
  Serial.println();

  // The power-on self-test is emitted ONCE, at power-on, before anything is sent.
  // Reading it here is the cheapest health check there is.
  ErdilrfLrf::Frame st;
  if (lrf.readPowerOnSelfTest(st)) {
    Serial.print(F("power-on self-test: "));
    if (st.d1 == ErdilrfLrf::kStaSuccess) {
      Serial.println(F("initialisation OK"));
    } else {
      Serial.print(F("initialisation FAILED, ErrCode=0x"));
      Serial.println(st.d4, HEX);
    }
  } else {
    Serial.println(F("no self-test frame (already powered past it? power-cycle to retry)"));
  }
}

void loop() {
  float d = lrf.singleShot();

  if (d >= 0.0f) {
    Serial.print(d, 1);
    Serial.println(F(" m"));
  } else if (d > -1.5f) {
    // The module answered, but reported a failed measurement (STA != 1).
    // Normal against a poor or non-reflective target. Not a comms fault.
    Serial.println(F("no return (shot failed - poor target?)"));
  } else {
    // No valid frame at all: check TXD/RXD crossover, enable pin, parity, and grounding.
    Serial.println(F("no answer - check TXD/RXD crossover, pin 6, parity, common ground"));
  }

  delay(1000);
}
