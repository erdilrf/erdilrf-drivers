/*
 * ERDILRF_LRF.h — header-only Arduino / C++ driver for ERDI 905 nm laser rangefinder modules.
 *
 * Implements the 8-byte UART protocol of the LR1000E2 family.
 * Reference: protocol/PROTOCOL.md in this repository.
 *
 * Frame:  0x55 0xAA FUNC D1 D2 D3 D4 SUM
 *   host -> module   SUM = (FUNC + D1 + D2 + D3 + D4) & 0xFF
 *   module -> host   SUM = (0x55 + 0xAA + FUNC + D1 + D2 + D3 + D4) & 0xFF
 *
 * The two checksum ranges differ. Getting this wrong rejects every frame.
 *
 * LICENSE: MIT. See LICENSE in the repository root.
 * NOTE: the manufacturer's manual states this product "must not be used for military
 * applications". Intended use is civilian industrial distance measurement.
 */

#ifndef ERDILRF_LRF_H
#define ERDILRF_LRF_H

#include <Arduino.h>

class ErdilrfLrf {
 public:
  static const uint8_t kFrameLen = 8;
  static const uint8_t kHeaderH = 0x55;
  static const uint8_t kHeaderL = 0xAA;

  // Function codes
  static const uint8_t kFuncSelfTest = 0x80;
  static const uint8_t kFuncLdConstantOn = 0x86;
  static const uint8_t kFuncSingleShot = 0x88;
  static const uint8_t kFuncContinuous = 0x89;
  static const uint8_t kFuncAngle = 0x8A;
  static const uint8_t kFuncStop = 0x8E;

  // STA is per-command, not global. See PROTOCOL.md section 6.
  static const uint8_t kStaSuccess = 0x01;

  struct Frame {
    uint8_t func;
    uint8_t d1, d2, d3, d4;
    uint8_t checksum;
    bool checksumOk;
    bool selfTest;   // true for an unsolicited 0x80 frame
  };

  explicit ErdilrfLrf(Stream &serial) : serial_(serial), haveSelfTest_(false) {}

  // ---------------------------------------------------------------- transmit

  // SUM[3:7] — function code plus the four data bytes.
  static uint8_t checksumSend(uint8_t func, uint8_t d1, uint8_t d2, uint8_t d3, uint8_t d4) {
    return (uint8_t)(func + d1 + d2 + d3 + d4);
  }

  // SUM[1:7] — both header bytes, function code and the four data bytes.
  static uint8_t checksumResponse(const uint8_t *f) {
    uint16_t sum = 0;
    for (uint8_t i = 0; i < 7; i++) sum += f[i];
    return (uint8_t)(sum & 0xFF);
  }

  void send(uint8_t func, uint8_t d1 = 0xFF, uint8_t d2 = 0xFF,
            uint8_t d3 = 0xFF, uint8_t d4 = 0xFF) {
    uint8_t f[kFrameLen] = {kHeaderH, kHeaderL, func, d1, d2, d3, d4,
                            checksumSend(func, d1, d2, d3, d4)};
    serial_.write(f, kFrameLen);
  }

  void requestSingleShot()  { send(kFuncSingleShot); }
  void requestContinuous()  { send(kFuncContinuous); }
  void requestStop()        { send(kFuncStop); }
  void requestAngle()       { send(kFuncAngle); }

  // The manual's response row for LD constant-on is incomplete, so this is fire-and-forget.
  void setLdConstantOn(bool on) { send(kFuncLdConstantOn, 0xFF, 0xFF, 0xFF, on ? 0x01 : 0x00); }

  // The new rate takes effect only after the module is restarted.
  void requestBaudRate(uint8_t typeCode) { send(typeCode); }

  // ---------------------------------------------------------------- receive

  // Resynchronises on 55 AA, so a corrupt frame costs at most one frame.
  bool readFrame(Frame &out, uint32_t timeoutMs = 200) {
    uint32_t start = millis();
    while ((uint32_t)(millis() - start) < timeoutMs) {
      while (serial_.available()) {
        uint8_t b = (uint8_t)serial_.read();
        if (index_ == 0 && b != kHeaderH) continue;
        if (index_ == 1 && b != kHeaderL) { index_ = (b == kHeaderH) ? 1 : 0; continue; }
        buf_[index_++] = b;
        if (index_ == kFrameLen) {
          index_ = 0;
          if (parse(buf_, out)) return true;
          // bad checksum: drop one byte and keep resynchronising
          for (uint8_t i = 1; i < kFrameLen; i++) buf_[i - 1] = buf_[i];
          index_ = kFrameLen - 1;
        }
      }
    }
    return false;
  }

  static bool parse(const uint8_t *f, Frame &out) {
    if (f[0] != kHeaderH || f[1] != kHeaderL) return false;
    out.func = f[2];
    out.d1 = f[3]; out.d2 = f[4]; out.d3 = f[5]; out.d4 = f[6];
    out.checksum = f[7];
    out.checksumOk = (f[7] == checksumResponse(f));
    out.selfTest = (out.func == kFuncSelfTest);
    return out.checksumOk;
  }

  // reported = measured x 10, so the 16-bit register holds tenths.
  static float decodeDistance(const Frame &f) {
    return (float)(((uint16_t)f.d3 << 8) | f.d4) / 10.0f;
  }

  static float decodeAngle(const Frame &f) {
    return (float)(((uint16_t)f.d3 << 8) | f.d4) / 10.0f;
  }

  // Returns -1 when the module answered but reported a failed measurement.
  // Distinguishing "failed" from "no answer" matters: they have different causes.
  float singleShot(uint32_t timeoutMs = 200) {
    while (serial_.available()) serial_.read();   // discard stale bytes before transmitting
    requestSingleShot();
    Frame f;
    if (!readFrame(f, timeoutMs)) return -2.0f;   // no answer at all
    if (f.func != kFuncSingleShot) return -2.0f;
    if (f.d1 != kStaSuccess) return -1.0f;        // answered, measurement failed
    return decodeDistance(f);
  }

  // The self-test frame is emitted once, at power-on, before anything is sent.
  bool readPowerOnSelfTest(Frame &out, uint32_t timeoutMs = 500) {
    if (haveSelfTest_) { out = selfTest_; return true; }
    if (!readFrame(out, timeoutMs)) return false;
    if (!out.selfTest) return false;
    selfTest_ = out;
    haveSelfTest_ = true;
    return true;
  }

 private:
  Stream &serial_;
  uint8_t buf_[kFrameLen] = {0};
  uint8_t index_ = 0;
  Frame selfTest_;
  bool haveSelfTest_;
};

#endif  // ERDILRF_LRF_H
