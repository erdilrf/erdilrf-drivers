# What a 905 nm rangefinder datasheet does not tell you

Four gaps I found while verifying the UART protocol of an LR1000E2-class 905 nm laser rangefinder
module — and how to work around each one.

This is not a complaint about the manual. It is what the manual says, what it deliberately leaves
out, and what that costs you at bring-up. Every claim below is reproducible from the published
document, which is cited at the end so you can check me.

---

## 0. Context: the frame format is 8 bytes, and the checksum is direction-dependent

```text
offset   0     1     2      3    4    5     6      7
        0x55  0xAA  FUNC   D1   D2   D3    D4     SUM

host  -> module   SUM = (FUNC + D1 + D2 + D3 + D4) & 0xFF
module -> host    SUM = (0x55 + 0xAA + FUNC + D1 + D2 + D3 + D4) & 0xFF
```

Two different ranges. The manual states this in its own notes, and it is the single most common way
an integration stalls: if you build one checksum helper and use it for both directions, **every
transmitted frame you validate looks corrupt, or every received frame does.** You get a link that
appears dead while the bytes on the wire are perfectly fine.

A worked example with the ranging response `55 AA 88 01 FF 27 10` (1000.0 m):

```text
bytes:  0x55 0xAA 0x88 0x01 0xFF 0x27 0x10   ->  85+170+136+1+255+39+16 = 702 = 0x2BE

response rule  SUM[1:7] = 0x2BE & 0xFF              = 0xBE   <- correct
command  rule  SUM[3:7] = 136+1+255+39+16 = 0x1BF & 0xFF = 0xBF   <- wrong, silently rejects
```

Verify it yourself before trusting me:

```bash
erdilrf decode "55 AA 88 01 FF 27 10 BE"
# checksum : 0xBE  (recomputed 0xBE) OK
# STA      : 0x01  measurement successful
# detail   : 1000.0 m
```

Distance decoding is `((DIS_H << 8) | DIS_L) / 10` — the register holds **tenths of a metre**, so the
16-bit field tops out at 6553.5 m and 1000 m arrives as `0x2710`.

Now the four gaps.

---

## Gap 1 — One response frame is printed incomplete, and it is the one that controls the laser

The manual documents the LD constant-on command, including both complete transmit frames:

```text
55 AA 86 FF FF FF 01 84     enable LD constant-on
55 AA 86 FF FF FF 00 83     disable
```

The response row prints only:

```text
55
```

That is one byte of an eight-byte frame. The remaining seven bytes are **not in the published
document**, as far as I can determine.

**Why this matters more than it looks.** LD constant-on is the command that turns the laser diode on
continuously. It is the one command where a failed write has a physical consequence rather than just
a wrong number — and it is the only command in the manual whose acknowledgment you cannot parse.

**What to do.** Do not invent the missing bytes. Send it fire-and-forget, and confirm the result
observably, not by reading a reply:

1. Issue the enable frame and do **not** block waiting for a well-formed acknowledgment.
2. Confirm from the physical side — the module draws measurably more current, and the emitter is
   live.
3. Prefer `singleShot()` / `continuous` for anything automated. Turn LD constant-on on only for
   alignment work, and turn it off when you are done. The manufacturer warns against leaving it
   enabled for extended periods, which is consistent with it being a service mode rather than an
   operating mode.

---

## Gap 2 — Parity and stop bits are unstated

The manual gives you two of the four serial parameters:

| Parameter | Documented? | Value |
|---|---|---|
| Baud rate | ✅ yes | 115200 default, plus nine selectable rates |
| Data bits | ✅ yes | 8 |
| Frame length | ✅ yes | 8 bytes, fixed |
| **Parity** | ❌ **not stated** | — |
| **Stop bits** | ❌ **not stated** | — |

**Why this matters.** Wrong parity does not produce garbled data — it produces **silence**. The UART
never frames a valid byte, so you see nothing at all. That symptom is indistinguishable from a
wiring fault, a dead module, or a power problem, and it sends people hunting through hardware when
the actual fix is one configuration byte.

**How to narrow it down without a scope.** Parity errors are not probabilistic; they are total. So:

* **Complete silence** + correct TXD/RXD crossover + confirmed power → try `8E1`, then `8O1`.
  A parity mismatch is the single best explanation for *absolutely nothing* on the wire.
* **Occasional valid frames among garbage** → parity is probably fine; suspect grounding or a noisy
  supply instead.
* **Frames arrive but the checksum fails** → the link is fine. You are almost certainly validating
  with the wrong rule (see section 0).

```bash
erdilrf measure --port COM3 --parity E --count 1
erdilrf measure --port COM3 --parity O --count 1
```

The driver defaults to 8N1 because that is the near-universal default, and labels it an assumption in
`PROTOCOL.md` rather than a fact. An assumption that announces itself is worth more than a guess that
does not.

---

## Gap 3 — TXD and RXD are named from the module's point of view

The pinout is documented clearly:

| Pin | Signal | Description as printed |
|---|---|---|
| 1 | GND | power supply negative |
| 2 | VCC | power supply positive |
| 3 | I/O | reserved for expansion |
| 4 | TXD | transmit data: **module → host** |
| 5 | RXD | receive data: **host → module** |
| 6 | SW-SHOT | function enable |

Those parenthetical directions are the whole story, and they are easy to read past. `TXD` on the
module means *the module transmits* — so it must land on your **RX**. A straight-through TXD-to-TXD
cable is the most common cause of a silent link, and it looks correct on a schematic.

**What the manual does not give you:** there is **no mapping from pin number to cable colour**.
Forum posts supply colour mappings confidently and inconsistently. Buzz the cable out with a
multimeter and write the mapping on the connector. This is five minutes against an afternoon.

---

## Gap 4 — The enable pin's polarity is configuration-dependent

Pin 6, SW-SHOT, is described as:

> Function enable (active high)

and, in the same table cell:

> Compatible with active-low control requirements

Both statements are true, and together they mean **the polarity you receive is decided by the
factory configuration, not by the datasheet.** The manual does not tell you which unit you have.

**What to do.** Do not design around an assumed polarity. Tie pin 6 to the level that makes your
*actual unit* measure, confirm it against the power-on self-test frame, and record the finding in
your own BOM notes. If you are building a product around this module, get the polarity confirmed in
writing with your order.

Also worth knowing: the module emits a **power-on self-test frame once, at power-on** —
`55 AA 80 STA 00 00 ErrCode SUM`. `STA = 0x01` means initialisation succeeded; `STA = 0x00` means it
failed and `ErrCode` carries the reason. It is free diagnostics, and it is only available if you read
the port *before* sending anything else. Miss it and you have to power-cycle.

---

## The general lesson, which is not specific to this module

Every one of these four gaps is invisible in a specification table and expensive at bring-up. Three
of them (parity, wire colours, enable polarity) fail as **silence**, and silence has a dozen possible
causes. Only one of them (the checksum split) fails as **garbage**, which at least points at the
protocol.

So when a link is dead, order your diagnosis by *what the symptom can distinguish*, not by what is
easiest to check:

| Symptom | Most likely cause | Next |
|---|---|---|
| Nothing at all | parity unstated (gap 2), TXD/RXD crossed (gap 3), enable pin (gap 4) | try `8E1`, swap TX/RX, toggle pin 6 |
| Frames, checksum fails | wrong checksum range (section 0) | use the response rule for received bytes |
| Intermittent bad shots | supply sag, shared ground with motors | ≥ 100 µF bulk at the module; separate returns |
| Works, then resets | inrush current vs. undersized regulator | module draws < 350 mA inrush |

---

## Where this came from

The protocol in this article is implemented, tested and published here:

**[github.com/erdilrf/erdilrf-drivers](https://github.com/erdilrf/erdilrf-drivers)**

* [`protocol/PROTOCOL.md`](https://github.com/erdilrf/erdilrf-drivers/blob/main/protocol/PROTOCOL.md) — every documented command, both checksum ranges, `STA` semantics per command
* [`protocol/verification.md`](https://github.com/erdilrf/erdilrf-drivers/blob/main/protocol/verification.md) — the checksum arithmetic re-derived independently. All six transmit frames printed in the manual reproduce byte for byte, and that file also records an arithmetic slip I made and corrected rather than quietly fixing
* `python/` — zero-dependency host driver, 50 tests, no hardware required
* `arduino/` — header-only C++ driver. **Not compiled**: no C++ toolchain was available where it was written, and `arduino/README.md` says so plainly instead of claiming otherwise

Primary source: **LR1000E2 User Manual v1.2, 2025.10, ERDI TECH LTD**, section 8
(SHA-256 `ab396d61a08d1d4d3e89ced7f77156096250697dc296d6fefffce16b010701a9`).

If your module disagrees with anything above, open an issue with the raw bytes. A capture from real
hardware outranks this article.

---

<sub>Scope note: this covers a civilian industrial optical distance-measurement sensor module
(IEC 60825-1 Class 1, 905 ± 5 nm). The manufacturer restricts the product to civilian applications
and excludes defence use.</sub>
