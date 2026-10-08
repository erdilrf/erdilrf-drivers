# Checksum verification

The manual prints the checksum for six TX frames. Printing them is not proof, so every one was
recomputed from the stated rule before this library was published. This file records that work so
a reviewer can repeat it.

## The rule, as stated in the manual

> The checksum is the least significant 8 bits of the sum of the specified bytes.

* Host → module frame: `SUM[3:7]` — the function code plus the four data bytes.
* Module → host frame: `SUM[1:7]` — both header bytes, the function code, and the four data bytes.

The manual's own note 1 adds: *"Command and response frames use different checksum ranges. Use the
range specified for each frame."*

## Re-derivation of all six published TX frames

`FUNC` is byte 2; D1..D4 are bytes 3..6.

| Command | FUNC | D1 D2 D3 D4 | sum | `& 0xFF` | printed | match |
|---|---|---|---|---|---|---|
| Single-shot ranging | `0x88` | `FF FF FF FF` | 136 + 1020 = 1156 | **`0x84`** | `0x84` | ✅ |
| Continuous ranging | `0x89` | `FF FF FF FF` | 137 + 1020 = 1157 | **`0x85`** | `0x85` | ✅ |
| Stop ranging | `0x8E` | `FF FF FF FF` | 142 + 1020 = 1162 | **`0x8A`** | `0x8A` | ✅ |
| Angle measurement | `0x8A` | `FF FF FF FF` | 138 + 1020 = 1158 | **`0x86`** | `0x86` | ✅ |
| LD constant-on — enable | `0x86` | `FF FF FF 01` | 134 + 765 + 1 = 900 | **`0x84`** | `0x84` | ✅ |
| LD constant-on — disable | `0x86` | `FF FF FF 00` | 134 + 765 + 0 = 899 | **`0x83`** | `0x83` | ✅ |

Six of six reproduce. The manual is internally consistent, which is not something this project
assumed — it was checked.

Automated equivalents live in `python/tests/test_vectors.py`:
`test_tx_frames_match_the_manual` and `test_manual_send_checksums_recompute_independently`.

## Response frames are a different range — demonstrated

Take the ranging response `55 AA 88 01 FF 27 10` (STA=1 success, distance 1000.0 m):

```
bytes: 0x55 0xAA 0x88 0x01 0xFF 0x27 0x10
       85 + 170 + 136 + 1 + 255 + 39 + 16 = 702 = 0x2BE

response rule  SUM[1:7] = 0x2BE & 0xFF = 0xBE
command  rule  SUM[3:7] =       136 + 1 + 255 + 39 + 16 = 447 = 0x1BF & 0xFF = 0xBF
```

`0xBE != 0xBF`. Using one rule where the other belongs rejects every frame. That is exactly the
bug this library shipped in its first draft — `FrameReader` validated transmitted frames with the
response rule and rejected all of them. It was caught by
`test_reader_reassembles_a_frame_split_at_every_offset`, not by review, and the fix was to make
frame direction explicit rather than implied.

> An earlier revision of this file printed the intermediate sum as `0x24E`. That was an arithmetic
> slip (the true sum is `702 = 0x2BE`) and it was caught by running the CLI's `decode` against the
> same bytes rather than by re-reading the prose. The conclusion `0xBE != 0xBF` is unchanged; the
> intermediate value was wrong. Recorded here rather than quietly deleted, because a verification
> document that silently corrects itself is worth less than one that shows its own correction.

## What was *not* verified, and why

| Item | Status |
|---|---|
| Parity / stop bits | **Not stated in the manual.** The library assumes 8N1 and labels it an assumption. |
| Cable wire colours | **Not in the manual.** The manual documents pin numbers only. |
| LD constant-on response frame | **Incomplete in the manual.** Section 8 prints only `55` for that row; the rest is absent. Not guessed. |
| UART pin voltage tolerance | Only the 3.3–5 V supply figure is given. Logic-level tolerance is not specified. |
| `SPD*` / `LR*` / `LRF*` family equivalence | The manual covers LR1000E2. Other families share the `55 AA` framing where documented, but function codes are **not** assumed identical. |

A contradicting capture from real hardware outranks every row above. Open an issue with the raw
bytes.
