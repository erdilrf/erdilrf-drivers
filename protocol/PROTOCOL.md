# ERDI 905 nm Laser Rangefinder — UART Protocol Reference

Status: **verified against a primary source**
Primary source: `LR1000E2 USER MANUAL v1.2 | 2025.10 | ERDI TECH LTD`, section 8 "Host Communication Protocol"
Document SHA-256: `ab396d61a08d1d4d3e89ced7f77156096250697dc296d6fefffce16b010701a9`

Every frame in this document was recomputed from the manufacturer's stated checksum rule
before publication. See [`verification.md`](verification.md) for the arithmetic.

---

## 1. Physical layer

| Property | Value |
|---|---|
| Interface | UART-TTL |
| Default baud rate | 115200 bps |
| Data bits | 8 |
| Frame length | **8 bytes**, fixed |
| Supply voltage | 3.3–5 V |

The manual states `8 data bits` and an 8-byte frame. **It does not state parity or stop bits.**
We therefore drive the port as **8N1** in this library, which is the near-universal default, and we
label that as an assumption rather than a documented fact. If a module does not answer, try
`8E1` / `8O1` first.

## 2. Frame layout

All 8 bytes, fixed positions:

```
offset  0     1     2       3    4    5    6     7
        +-----+-----+-------+----+----+----+----+-------+
        | 0x55| 0xAA| FUNC  | D1 | D2 | D3 | D4 | SUM   |
        +-----+-----+-------+----+----+----+----+-------+
          header H  header L   ---- payload ----   checksum
```

* Header is **`0x55 0xAA`**.
* Checksum is **the least significant 8 bits** of a byte sum.
* **Host→module and module→host frames use different checksum ranges.** This is the single most
  common integration mistake, and the manual calls it out explicitly in its own notes.

```python
send_checksum     = (FUNC + D1 + D2 + D3 + D4) & 0xFF
response_checksum = (0x55 + 0xAA + FUNC + D1 + D2 + D3 + D4) & 0xFF
```

## 3. Commands — host to module

### 3.1 Single-shot ranging

```
TX  55 AA 88 FF FF FF FF 84
RX  55 AA 88 STA FF DIS_H DIS_L SUM
```

### 3.2 Continuous ranging

```
TX  55 AA 89 FF FF FF FF 85
RX  55 AA 89 STA FF DIS_H DIS_L SUM
```

The module then emits frames at an adaptive rate of **3–10 Hz** until stopped.

### 3.3 Stop ranging

```
TX  55 AA 8E FF FF FF FF 8A
RX  55 AA 8E STA FF FF FF SUM
```

`STA = 1` — continuous ranging stopped. `STA = 0` — failed to stop.

### 3.4 Angle measurement

```
TX  55 AA 8A FF FF FF FF 86
RX  55 AA 8A STA FF ANG_H ANG_L SUM
```

> **Availability:** the manual states this command is *"available only on modules equipped with an
> angle sensor"*. Do not assume a rangefinder-only module implements it.

### 3.5 Set baud rate

```
TX  55 AA TYPE FF FF FF FF SUM
RX  55 AA TYPE STA FF FF FF SUM
```

| TYPE | Baud rate | TYPE | Baud rate |
|---|---|---|---|
| `0x01` | 9600 | `0x06` | 57600 |
| `0x02` | 14400 | `0x07` | 115200 |
| `0x03` | 19200 | `0x08` | 128000 |
| `0x04` | 38400 | `0x09` | 230400 |
| `0x05` | 56000 | | |

> **The new baud rate takes effect only after the module is restarted.** `STA = 1` means the setting
> was accepted, *not* that the link has already changed speed.

### 3.6 LD constant-on mode

```
TX (enable)   55 AA 86 FF FF FF 01 84
TX (disable)  55 AA 86 FF FF FF 00 83
RX            -- see known gap below --
```

> ⚠️ **Known documentation gap — response frame is incomplete in the primary source.**
> Section 8 of the manual prints only `55` for this response row; the remaining bytes are missing
> from the published document. We have **not** guessed them. This library therefore sends the
> command and does not attempt to validate a response frame for it.
> Do not leave LD constant-on mode enabled for extended periods (manufacturer's warning).

## 4. Unsolicited frame — power-on self-test

```
RX  55 AA 80 STA 00 00 ErrCode SUM
```

`STA = 1` power-on initialisation succeeded. `STA = 0` failed, with `ErrCode` populated.

## 5. Decoding measurements

The manual states: **reported value = measured value × 10** — i.e. the register holds tenths.

```python
raw_units = (DIS_H << 8) | DIS_L
meters    = raw_units / 10.0     # same scaling for ANG: degrees = raw_units / 10.0
```

| Target | DIS_H | DIS_L | raw | result |
|---|---|---|---|---|
| 1.0 m | `0x00` | `0x0A` | 10 | 1.0 m |
| 10.0 m | `0x00` | `0x64` | 100 | 10.0 m |
| 100.0 m | `0x03` | `0xE8` | 1000 | 100.0 m |
| 1000.0 m | `0x27` | `0x10` | 10000 | 1000.0 m |

## 6. `STA` semantics, collected

Different commands use `STA` differently — read the row, not a blanket rule.

| Frame | `STA = 1` | `STA = 0` | other |
|---|---|---|---|
| Single-shot / continuous ranging | measurement successful | measurement failed | failed |
| Stop ranging | stop succeeded | stop failed | failed |
| Angle measurement | measurement successful | measurement failed | failed |
| Set baud rate | setting successful | setting failed | failed |
| Power-on self-test | init succeeded | init failed | failed |
| LD constant-on | *(no meaning — see gap)* | | |

## 7. Electrical interface

| Pin | Signal | Description |
|---|---|---|
| 1 | GND | Power supply negative |
| 2 | VCC | Power supply positive |
| 3 | I/O | Reserved for expansion |
| 4 | TXD | Transmit data: **module → host** |
| 5 | RXD | Receive data: **host → module** |
| 6 | SW-SHOT | Function enable, `active high` |

> **TXD/RXD are named from the module's point of view.** Wiring module TXD to host TXD is the second
> most common integration mistake. Cross them: module TXD → host RX.
>
> The manual adds that SW-SHOT is *"compatible with active-low control requirements"*, meaning the
> factory configuration determines the polarity you receive. **Confirm the polarity of your specific
> unit before designing around it.**

The manual does **not** document wire colours for the supplied cable, or the logic-level tolerance of
the UART pins beyond the 3.3–5 V supply figure. Treat those as unknown until confirmed per unit.

## 8. Applicable module families

The documented register format above is what ERDI publishes for the LR1000E2. Other families in the
905 nm line share the `55 AA` framing and, where they publish protocol tables, the same
`SUM[3:7]` / `SUM[1:7]` checksum split. **Verify per model** — do not assume identical `FUNC` codes
across families.

## 9. Compliance note

This protocol describes a **civilian industrial optical distance-measurement sensor module**.
The manufacturer's own manual restricts the product to civilian applications and states it must not
be used for defence purposes. Intended integration targets are civilian equipment: UAVs, outdoor
observation devices, surveying and mapping systems, industrial robotics and automation.

The module is **IEC 60825-1 Class 1** and operates at 905 ± 5 nm.

## 10. Sources and how to challenge this document

* Primary: LR1000E2 User Manual v1.2, 2025.10, ERDI TECH LTD — section 8.
* Checksum arithmetic re-derived independently — [`verification.md`](verification.md).
* Where the manual is silent (parity, wire colours, LD response frame), this document says so
  instead of filling the gap.

If you have a module that contradicts any row here, open an issue with the raw bytes you observed.
A contradicting capture outranks this document.
