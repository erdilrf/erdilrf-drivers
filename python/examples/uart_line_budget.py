"""Offline UART wire-time arithmetic; no serial, networking, or device control."""

import json
import sys
from fractions import Fraction
from pathlib import Path


FIELDS = {"name", "baud", "data_bits", "parity", "stop_bits", "duplex",
          "interval_ms", "tx_bytes", "rx_bytes"}


def integer(value, name, minimum):
    if type(value) is not int or not minimum <= value <= 10**12:
        raise ValueError(name + " must be a bounded integer >= " + str(minimum))
    return value


def ratio(value):
    return str(value.numerator) + "/" + str(value.denominator)


def budget(case):
    if not isinstance(case, dict) or set(case) != FIELDS:
        raise ValueError("case fields must exactly match the documented schema")
    if not isinstance(case["name"], str) or not case["name"].isascii() or not 1 <= len(case["name"]) <= 80:
        raise ValueError("name must be 1..80 ASCII characters")
    baud = integer(case["baud"], "baud", 1)
    if type(case["data_bits"]) is not int or case["data_bits"] != 8:
        raise ValueError("this byte-count example supports 8 data bits only")
    if case["parity"] not in ("none", "even", "odd"):
        raise ValueError("parity must be none, even, or odd")
    if type(case["stop_bits"]) is not int or case["stop_bits"] not in (1, 2):
        raise ValueError("stop_bits must be 1 or 2")
    if case["duplex"] not in ("full", "half"):
        raise ValueError("duplex must be full or half")
    interval = Fraction(integer(case["interval_ms"], "interval_ms", 1), 1000)
    tx = integer(case["tx_bytes"], "tx_bytes", 0)
    rx = integer(case["rx_bytes"], "rx_bytes", 0)
    bits = 1 + 8 + (case["parity"] != "none") + case["stop_bits"]
    tx_time, rx_time = Fraction(tx * bits, baud), Fraction(rx * bits, baud)
    # Separate UART directions can overlap; a shared half-duplex wire cannot.
    lower_bound = max(tx_time, rx_time) if case["duplex"] == "full" else tx_time + rx_time
    return {
        "name": case["name"],
        "bits_per_character": bits,
        "tx_wire_seconds": ratio(tx_time),
        "rx_wire_seconds": ratio(rx_time),
        "tx_interval_ratio": ratio(tx_time / interval),
        "rx_interval_ratio": ratio(rx_time / interval),
        "required_wire_seconds_lower_bound": ratio(lower_bound),
        "required_interval_ratio_lower_bound": ratio(lower_bound / interval),
        "wire_time_strictly_exceeds_interval": lower_bound > interval,
        "device_timing_and_operational_feasibility": "not_evaluated",
    }


def reject_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field: " + key)
        result[key] = value
    return result


def evaluate(raw):
    if len(raw) > 65536:
        raise ValueError("input exceeds 64 KiB")
    doc = json.loads(raw, object_pairs_hook=reject_duplicate_fields)
    if not isinstance(doc, dict) or set(doc) != {"schema_version", "cases"}:
        raise ValueError("expected schema_version and cases")
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if not isinstance(doc["cases"], list) or not 1 <= len(doc["cases"]) <= 20:
        raise ValueError("cases must contain 1..20 items")
    return {"schema_version": 1, "results": [budget(case) for case in doc["cases"]]}


def main(argv):
    if len(argv) != 1:
        print("usage: python3 uart_line_budget.py INPUT.json", file=sys.stderr)
        return 2
    try:
        with Path(argv[0]).open("rb") as stream:
            raw = stream.read(65537)
        output = evaluate(raw)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print("invalid input: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
