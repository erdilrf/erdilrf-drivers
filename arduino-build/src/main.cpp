/*
 * Compile-verification sketch for ERDILRF_LRF.h.
 *
 * This file exists to prove the header compiles and that every public member is
 * actually usable from a sketch. It deliberately touches the whole API, including
 * the parts the BasicRanging example does not: the Frame struct fields, manual
 * checksum helpers, readFrame(), decodeDistance(), decodeAngle() and setLdConstantOn().
 *
 * It is not meant to run meaningfully without hardware; the point is compilation.
 * On target it will report the power-on self-test result over Serial.
 */

#include <Arduino.h>
#include <ERDILRF_LRF.h>

// A SoftwareSerial-free build: use the hardware UART so this compiles on boards
// without the SoftwareSerial library as well.
ErdilrfLrf lrf(Serial);

static uint8_t gFailures = 0;

// Exercise the static checksum helpers and compare against the values printed in the
// manufacturer's manual. This runs on-target and is a real self-check, not decoration.
static void verifyChecksums() {
  struct Case { uint8_t func; const char* name; uint8_t expected; };
  const Case cases[] = {
    {ErdilrfLrf::kFuncSingleShot, "single-shot", 0x84},
    {ErdilrfLrf::kFuncContinuous, "continuous", 0x85},
    {ErdilrfLrf::kFuncStop,       "stop",       0x8A},
    {ErdilrfLrf::kFuncAngle,      "angle",      0x86},
  };
  for (uint8_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
    uint8_t got = ErdilrfLrf::checksumSend(cases[i].func, 0xFF, 0xFF, 0xFF, 0xFF);
    Serial.print(F("checksum "));
    Serial.print(cases[i].name);
    Serial.print(F(": got 0x"));
    Serial.print(got, HEX);
    Serial.print(F(" expected 0x"));
    Serial.println(cases[i].expected, HEX);
    if (got != cases[i].expected) { gFailures++; }
  }
  // LD constant-on frames use a different D4.
  if (ErdilrfLrf::checksumSend(ErdilrfLrf::kFuncLdConstantOn, 0xFF, 0xFF, 0xFF, 0x01) != 0x84) { gFailures++; }
  if (ErdilrfLrf::checksumSend(ErdilrfLrf::kFuncLdConstantOn, 0xFF, 0xFF, 0xFF, 0x00) != 0x83) { gFailures++; }

  // Response-side rule, checked against the worked example: 55 AA 88 01 FF 27 10 -> 0xBE
  uint8_t resp[7] = {0x55, 0xAA, 0x88, 0x01, 0xFF, 0x27, 0x10};
  uint8_t r = ErdilrfLrf::checksumResponse(resp);
  Serial.print(F("response checksum: got 0x"));
  Serial.print(r, HEX);
  Serial.println(F(" expected 0xBE"));
  if (r != 0xBE) { gFailures++; }
}

// Exercise parse()/decodeDistance() with a synthetic frame.
static void verifyParseAndDecode() {
  // 55 AA 88 01 FF 27 10 BE  ->  STA=1, 0x2710 = 10000 -> 1000.0 m
  const uint8_t raw[8] = {0x55, 0xAA, 0x88, 0x01, 0xFF, 0x27, 0x10, 0xBE};
  ErdilrfLrf::Frame f;
  bool ok = ErdilrfLrf::parse(raw, f);
  Serial.print(F("parse ok="));
  Serial.print(ok ? 1 : 0);
  Serial.print(F(" func=0x"));
  Serial.print(f.func, HEX);
  Serial.print(F(" checksumOk="));
  Serial.print(f.checksumOk ? 1 : 0);
  Serial.print(F(" selfTest="));
  Serial.print(f.selfTest ? 1 : 0);
  float m = ErdilrfLrf::decodeDistance(f);
  Serial.print(F(" distance="));
  Serial.println(m, 1);
  if (!ok || !f.checksumOk || m < 999.0f || m > 1001.0f) { gFailures++; }

  // A corrupted checksum must be rejected.
  uint8_t bad[8] = {0x55, 0xAA, 0x88, 0x01, 0xFF, 0x27, 0x10, 0x00};
  ErdilrfLrf::Frame fb;
  if (ErdilrfLrf::parse(bad, fb)) { gFailures++; }
}

void setup() {
  Serial.begin(115200);

  Serial.println(F("ERDILRF_LRF compile-verification"));
  verifyChecksums();
  verifyParseAndDecode();

  ErdilrfLrf::Frame st;
  if (lrf.readPowerOnSelfTest(st)) {
    Serial.print(F("self-test STA=0x"));
    Serial.println(st.d1, HEX);
  }

  // Touch the remaining public surface so nothing is left uncompiled.
  lrf.requestSingleShot();
  lrf.requestContinuous();
  lrf.requestAngle();
  lrf.setLdConstantOn(false);
  lrf.requestBaudRate(0x07);
  float d = lrf.singleShot(100);
  Serial.print(F("singleShot() -> "));
  Serial.println(d, 1);

  Serial.print(F("FAILURES="));
  Serial.println(gFailures);
}

void loop() {
  ErdilrfLrf::Frame f;
  if (lrf.readFrame(f, 50)) {
    Serial.print(F("frame func=0x"));
    Serial.print(f.func, HEX);
    Serial.print(F(" d1=0x"));
    Serial.println(f.d1, HEX);
  }
  delay(1000);
}
