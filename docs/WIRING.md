# Wiring an ERDI 905 nm rangefinder module over UART

Most "the module does not respond" reports are one of two wiring mistakes. Both are in this file.

## Pinout

The manufacturer documents **pin numbers only**. There is no published mapping from pin number to
cable colour, so **do not trust a colour from a forum post** — buzz the cable out with a multimeter
and write the mapping on the connector.

| Pin | Signal | Direction from the module's point of view |
|---|---|---|
| 1 | GND | power return |
| 2 | VCC | 3.3–5 V |
| 3 | I/O | reserved for expansion |
| 4 | TXD | **module → host** |
| 5 | RXD | **host → module** |
| 6 | SW-SHOT | function enable (factory-set polarity) |

## Mistake 1 — TXD and RXD are named from the module's side

The names on the module describe what *the module* does, not what your MCU should do. Cross them:

```
module TXD (pin 4)  ──►  host RX
module RXD (pin 5)  ◄──  host TX
module GND (pin 1)  ──── host GND        (common ground is mandatory)
module VCC (pin 2)  ◄──  3.3–5 V
```

Straight-through TXD-to-TXD is the most common cause of a silent link. It looks correct on a
schematic and produces exactly nothing on the wire, because both ends are listening.

## Mistake 2 — assuming the enable pin's polarity

Pin 6 (SW-SHOT) enables normal operation. The manual describes it as "function enable (active
high)" **and**, in the same row, "compatible with active-low control requirements" — meaning the
factory configuration decides which you receive.

Do not design around an assumed polarity. Tie it to the level that makes your specific unit
measure, confirm with the power-on self-test frame, and record it in your BOM notes.

## Logic levels

The supply is 3.3–5 V. The manual does **not** publish a logic-level tolerance for TXD/RXD.

* If your MCU is **3.3 V**: safe on the RX side in the common case, but verify before trusting it
  with a 5 V module.
* If your MCU is **5 V** and the module's UART is 3.3 V: level-shift the line into the module, or at
  minimum use a series resistor with a divider on the module's RX. Driving a 3.3 V input from a 5 V
  push-pull output is outside the documented specification.
* If in doubt, measure the idle level of pin 4 with the module powered. Idle-high at ~3.3 V means a
  3.3 V UART.

## Power

| Parameter | Value |
|---|---|
| Supply | 3.3–5 V |
| Inrush current | < 350 mA |
| Operating power | ≤ 1 W |
| Sleep power | < 1 mW |
| Standby power | < 0.3 W |

The inrush figure matters: a small LDO sized for the 1 W operating power, with no bulk capacitance,
will brown out at power-on and the module will reset mid-measurement. Put **≥ 100 µF** of bulk
capacitance at the module's VCC pin, not back at the regulator.

Keep the supply and ground returns separate from motor or servo currents. A ranging module sharing a
ground return with a drive motor will produce intermittent bad shots, and it will look like a
protocol problem.

## First bring-up sequence

1. **Nothing but power and ground.** Confirm the module powers up and draws standby current.
2. **Read the power-on self-test before sending anything.** It is emitted **once, at power-on**. If
   you have already sent other commands you have missed it — power-cycle and retry.
   Check `STA`: `0x01` is initialisation success.
3. **Send one command and read the bytes.** `erdilrf measure --port COM3 --count 1` or the byte
   string `55 AA 88 FF FF FF FF 84`.
4. **If silence:** swap TXD/RXD, then try `--parity E`. If parity is wrong you see nothing at all,
   which is why the driver defaults to 8N1 and labels it an assumption.
5. **If you get frames but the checksum fails:** you are probably validating with the wrong rule.
   Transmitted and received frames use different checksum ranges — see
   [`../protocol/PROTOCOL.md`](../protocol/PROTOCOL.md) section 2.

## Optical window, if you are building one

Only relevant for custom enclosures; the module ships with its own optics.

| Recommendation | Value |
|---|---|
| Window material | H-K9L optical glass or fused silica |
| AR coating | 855–955 nm, transmittance ≥ 99.5 % |
| Window thickness | 2–4 mm |
| Wedge angle tolerance | ≤ 3′ |
| Air gap, window to module | < 0.5 mm |
| Transmitter axis | parallel to the window surface normal |

Window edge margins: outer dimension minus clear aperture **≥ 2 mm**, and projected clear aperture
minus optical-assembly outer dimension **≥ 1.5 mm**.
