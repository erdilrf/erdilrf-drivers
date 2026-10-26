# Calculate a UART byte budget before choosing a measurement schedule

**Disclosure:** this example and document were prepared with AI assistance for ERDILRF / ERDI LASER. The maintainers are affiliated with the referenced module manufacturer, ERDI TECH LTD. All traffic counts and serial settings below are hypothetical; no hardware measurement is presented. The example reads a local JSON file and prints arithmetic. It opens no serial port or network connection.

A decoder can be correct while a proposed traffic schedule cannot fit on the wire. Start with bytes and serial framing, then keep device timing as a separate unknown.

The pinned `erdilrf/erdilrf-drivers` main source at `904025b3c38302aea510ba97c370ed17c4844e6e` declares `FRAME_LEN = 8` in [`python/src/erdilrf_lrf/frames.py`](https://github.com/erdilrf/erdilrf-drivers/blob/904025b3c38302aea510ba97c370ed17c4844e6e/python/src/erdilrf_lrf/frames.py#L31), SHA-256 `3d8cd26c5d3aad0267093f8ba4c4ef82173b3bb603c55e342ed706ac9a96147f`. That is the source anchor for an eight-byte example. This tutorial does not infer the settings or capabilities of a physical LR1000E2 unit. It does not extend that framing to other models, the separate ErdiLRF Arduino library, NMEA sonar, Wiseome, MAVLink, ROS, or PX4.

For one eight-bit UART character, count one start bit, eight data bits, an optional parity bit, and the configured stop bits. Thus an assumed 8N1 character takes 10 bits; an assumed 8E2 character takes 12. Divide the total bits by the assumed baud rate to obtain ideal serialization time.

From the repository root, run the included standard-library example with Python 3.9 or later. No package installation is needed:

```sh
python3 -B python/examples/uart_line_budget.py python/examples/fixtures/uart-line-budget.examples.json
python3 -B -m unittest discover -s python/tests -p test_uart_line_budget_example.py -v
```

The [input fixture](../python/examples/fixtures/uart-line-budget.examples.json) and [complete expected stdout](../python/examples/fixtures/uart-line-budget.expected.json) are deterministic.

The three cases all assume 800 transmitted bytes and 800 received bytes in one second, at 9600 baud. Think of each direction as 100 hypothetical eight-byte packets. These counts are invented test inputs, not an observed or supported ERDILRF measurement rate. There is no claim that one command produces one response on this schedule.

| Assumed transport | Ideal time per direction | Required interval lower bound |
| --- | --- | --- |
| Full duplex, 8N1 | 5/6 second | 5/6 second; directions may overlap |
| Shared half duplex, 8N1 | 5/6 second | 5/3 seconds; exceeds one second |
| Full duplex, 8E2 | 1 second | 1 second; no ideal wire headroom |

The half-duplex case is a contrasting transport calculation, not a declaration that the documented module has a half-duplex interface. Full duplex gives separate directional budgets. It does not mean a command and its dependent response can overlap: their actual sequencing can impose a larger lower bound.

An output below or equal to one interval is **not an operational pass**. Interbyte gaps, sensor acquisition, command processing, request/response dependencies, turnaround, host scheduling, USB buffering, retries, and application deadlines are excluded. The tool reports `not_evaluated` for device timing and operational feasibility in every case. Obtain those facts from the exact unit's documentation and measured captures before selecting a real schedule. Baud alone cannot establish measurement Hz or end-to-end latency.

The JSON input requires every setting explicitly, accepts eight data bits with none/even/odd parity and one/two stop bits, and rejects zero baud, fractional byte counts, booleans as integers, unknown fields, and duplicate JSON keys. Output uses exact fractions, avoiding a rounded boundary decision.

This asset adds transport arithmetic. The [offline replay tutorial](replaying-uart-logs.md) reassembles supplied TX/RX chunks and preserves checksum errors; it does not calculate wire occupancy. Use that separate tool to inspect byte-sequence evidence; this calculator does not parse frames or replay timing. Neither asset demonstrates hardware performance, protocol compatibility beyond its stated source, safety suitability, certification, or buyer demand. The LR1000E2 source provides the specific 905 nm context. Other 905 nm families, 1535 nm modules and other real series require their own frame size, exact interface and settings; wavelength or a matching header does not establish compatibility. A laser-source product without this serial interface is outside the example.

The calculation is independent of the framing library: it neither imports that library nor sends commands. The eight-byte source pin explains one packet-size example; changing models requires new inputs and a separate source review.
