# Ordered-unit interface intake record

Use one record for one supplied module configuration. Leave unknowns explicit; this blank record sends no bytes and establishes no hardware compatibility.

This repository documents the **LR1000E2 UART-TTL protocol family**. Its [protocol reference](../protocol/PROTOCOL.md) identifies *LR1000E2 User Manual v1.2, 2025.10*, section 8, with document SHA-256 `ab396d61a08d1d4d3e89ced7f77156096250697dc296d6fefffce16b010701a9`. That reference does not identify the configuration of your ordered unit.

Other 905 nm families, 1535 nm modules and laser-source products need their own exact source and driver-scope review. A catalogue entry, wavelength, shared housing, connector or matching frame header does not establish support.

## 1. Bind the ordered configuration to its evidence

Record ID: __________  Date: __________  Review status: **UNRESOLVED**

| Item | Actual value | Evidence reference and unresolved differences |
| --- | --- | --- |
| Full ordered model/SKU, option suffixes and supplied configuration | __________ | __________ |
| Hardware and firmware revision, when supplied | __________ | __________ |
| Unit-specific manual/protocol title, revision, date and section | __________ | __________ |
| Protocol source file SHA-256 | __________ | __________ |
| Driver checkout commit and Python/Arduino package version | __________ | __________ |

Keep order documents, device serial numbers and customer information private. Put sanitized evidence references in a shared issue; do not paste credentials, addresses or unrelated capture content.

## 2. Record the physical interface and native UART profile

Use evidence for the supplied configuration, not a family-level default. Keep device settings and host settings separate.

| Item | Supplied device / evidence | Host or adapter configuration / evidence |
| --- | --- | --- |
| Electrical interface as supplied | __________ | __________ |
| Connector revision, pin mapping and signal directions | __________ | __________ |
| Documented signal levels/tolerance and any required interface conversion | __________ | __________ |
| Baud rate and data bits | __________ | __________ |
| Parity and stop bits | __________ | __________ |
| Flow control or other required link settings, if specified | __________ | __________ |

The reference manual states 115200 baud and eight data bits; parity and stop bits are unstated. The library's 8N1 default is an **assumption**, not evidence of an ordered unit's native profile. See [PROTOCOL](../protocol/PROTOCOL.md#1-physical-layer), [WIRING](WIRING.md) and the [CLI options](../python/src/erdilrf_lrf/cli.py). This record does not authorize live commands or connection based on unconfirmed settings.

## 3. Compare this protocol with this driver

| Required comparison | Source evidence / driver reference / unresolved difference |
| --- | --- |
| Frame layout, function and status meanings, checksum direction and units | __________ |
| Optional functions and configuration-dependent behaviour | __________ |
| Existing permitted native capture: private reference, SHA-256 and TX/RX direction, if available | __________ |
| Actual native profile associated with that capture | __________ |
| Differences requiring a separate decoder or interface review | __________ |

For an already-authorized capture, the [offline replay guide](replaying-uart-logs.md) and [replay_jsonl.py](../python/examples/replay_jsonl.py) identify parser observations without sending commands. It cannot establish device settings or compatibility. The [UART wire budget](uart-wire-budget.md) uses supplied assumptions and does not establish device timing.

Disposition: **UNRESOLVED** / outside documented driver scope / documentation comparison recorded; hardware unverified.

Reviewer and evidence references: __________

Retain unresolved differences before selecting a driver profile. A filled sheet is not a bench test, a protocol implementation for another model, a receiver mapping or a successful measurement.

AI-assisted preparation for ERDILRF / ERDI LASER, affiliated with module manufacturer ERDI TECH LTD. This is a blank engineering record; no hardware test was performed.
