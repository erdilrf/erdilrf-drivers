# Turn UART chunks into a reproducible offline parser report

Keep the original input file and identify the decoder before interpreting a log.
The example in [`replay_jsonl.py`](../python/examples/replay_jsonl.py) records the
input SHA-256, reviewed source hashes, chunk count, accepted raw frames and parser
errors. It reads a file and prints JSON; it does not open a serial port or send
any of the command bytes in the file.

**Disclosure:** this example and document were prepared with AI assistance for
ERDILRF / ERDI LASER. The maintainers are affiliated with the referenced module
manufacturer, ERDI TECH LTD. All supplied fixture bytes are synthetic; no hardware
capture or measurement is presented.

## Use the exact framing source

This example uses `erdilrf_lrf.frames.FrameReader` from package version `0.2.0`,
with the eight-byte `55 AA` framing documented for the LR1000E2 protocol family.
The reference source is commit
`904025b3c38302aea510ba97c370ed17c4844e6e`:

| File | SHA-256 |
|---|---|
| `python/src/erdilrf_lrf/frames.py` | `3d8cd26c5d3aad0267093f8ba4c4ef82173b3bb603c55e342ed706ac9a96147f` |
| `protocol/PROTOCOL.md` | `52fd09b319484980bc65eb0f87a479a8d66df48dd3a9f44848b474f6f93ba995` |
| `python/pyproject.toml` | `600a1484ed057057e0ec33d2d2707284a248affda24377617683fbf7c146f87a` |

The script refuses changed source pins or a different package version. These
checks identify the three reviewed files; they do not assert that the entire
checkout is unchanged. Review a new decoder revision before updating its pins.

The existing library's public calls are `FrameReader(direction=...)` and
`reader.feed(chunk)`. Direction is `command` for host-to-module bytes and
`response` for module-to-host bytes. Each reader retains its own partial input.
The two directions need independent reader instances because their bytes and
checksum ranges differ. One call to `feed` can return several frames.

## Input: one supplied chunk per line

The JSONL schema has exactly three fields:

```json
{"origin":"synthetic","direction":"command","hex":"55 AA 88"}
{"origin":"synthetic","direction":"response","hex":"55 AA 88 01"}
{"origin":"synthetic","direction":"command","hex":"FF FF FF FF 84"}
{"origin":"synthetic","direction":"response","hex":"FF 27 10 BE"}
```

`hex` contains byte pairs separated by one ASCII space. Keep every chunk boundary
and its direction. `origin` must be `synthetic` or `captured`, consistently within
one file. That value is a supplied label; the tool cannot establish where bytes
came from. A captured label does not turn an unverified file into hardware proof.

The example rejects unknown fields, duplicate JSON keys, malformed hex, missing
directions, mixed origin labels and blank rows. Limits are 1 MiB per input file,
4096 rows and 4096 bytes per chunk. It validates every row before printing a
report, so malformed trailing input does not produce a partial success report.

Keep an original capture private. If a report must be shared, review an exported
copy for credentials, personal information and customer traffic. Retain its
relationship to the private original; an exported copy has its own hash.

## Run without installing dependencies

From a source checkout with Python 3.9 or later:

```sh
PYTHONPATH=python/src python3 -B python/examples/replay_jsonl.py python/examples/fixtures/uart-synthetic.jsonl
```

In PowerShell, set `$env:PYTHONPATH = "python/src"` first, then run the same
command with `python -B`. The script requires this checkout's framing module,
not a different copy found on the interpreter's import path.

The complete expected stdout is checked in as
[`uart-synthetic.expected.json`](../python/examples/fixtures/uart-synthetic.expected.json).
It is deterministic: it contains no local paths, timestamps or random values.

The eight synthetic rows exercise these cases:

| Input | Expected framing result |
|---|---|
| Rows 1-4: interleaved partial TX and RX chunks | One command frame completes at row 3; one response frame at row 4 |
| Row 5: two command frames in one chunk | Two command frames |
| Row 6: two response frames in one chunk | Two response frames |
| Row 7: response ending in `BF` | One checksum error; no accepted frame |
| Row 8: response ending in `BE` | One accepted response frame |

The result therefore has seven accepted raw frames and one parser error. Error
entries are collected only when newly appended to `reader.errors`; a later feed
does not repeat an earlier error. Row numbers identify where a frame completed
or an error was observed, not the original byte offset or capture time.

Run the focused standard-library controls with:

```sh
PYTHONPATH=python/src python3 -B -m unittest discover -s python/tests -p test_replay_example.py -v
```

## What the report establishes

An accepted frame passed this parser's header, length and direction-specific
checksum checks. That result does not establish valid function semantics, status,
physical units, device behaviour or an electrical connection. The report retains
raw frame bytes and does not print synthetic values as measured distances.

This is byte-sequence replay. It does not replay timing, host scheduling, serial
settings, read deadlines, power state or firmware. The library exposes no public
flush or incomplete-tail query here. A final partial header can yield no frame
and no error; an empty result is not a completeness or transport-health verdict.
The error list is the parser's observations, not an exhaustive account of every
discarded byte. Preserve the input file even when no frame is emitted.

The LR1000E2 source gives this example a specific 905 nm integration context.
Other 905 nm families, 1535 nm modules and other real series need their own exact
manual and framing implementation. Wavelength, a shared connector or a matching
header does not establish protocol compatibility. A laser-source product without
this serial protocol is outside this parser's scope.

For a real investigation, separately record the actual package version or source
commit, exact model and manual revision, firmware and supplied configuration when
known. Mark missing evidence unknown. The reproducible software report is one
part of that record, not a hardware acceptance result.
