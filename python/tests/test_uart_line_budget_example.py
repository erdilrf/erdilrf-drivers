"""Synthetic counterexamples; never opens serial ports or network sockets."""

import copy
import json
import importlib.util
import unittest
from pathlib import Path



ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "python/examples/uart_line_budget.py"
FIXTURE = ROOT / "python/examples/fixtures/uart-line-budget.examples.json"
EXPECTED = ROOT / "python/examples/fixtures/uart-line-budget.expected.json"
SPEC = importlib.util.spec_from_file_location("uart_line_budget_example", EXAMPLE)
BUDGET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUDGET)
CASES = json.loads(FIXTURE.read_text())["cases"]


class Counterexamples(unittest.TestCase):
    def test_duplex_changes_the_transport_bound(self):
        # Independently counted: 800 * (1+8+1) = 8000 bits on each wire.
        self.assertEqual(BUDGET.evaluate(FIXTURE.read_bytes()), json.loads(EXPECTED.read_text()))
        full, half = BUDGET.budget(CASES[0]), BUDGET.budget(CASES[1])
        self.assertEqual(full["tx_interval_ratio"], "5/6")
        self.assertEqual(full["rx_interval_ratio"], "5/6")
        self.assertEqual(full["required_interval_ratio_lower_bound"], "5/6")
        self.assertFalse(full["wire_time_strictly_exceeds_interval"])
        self.assertEqual(half["required_interval_ratio_lower_bound"], "5/3")
        self.assertTrue(half["wire_time_strictly_exceeds_interval"])

    def test_8E2_consumes_all_wire_time_not_a_sensor_rate_promise(self):
        # 800 * (1+8+1+2) = 9600 bits: exactly one second per direction.
        result = BUDGET.budget(CASES[2])
        self.assertEqual(result["bits_per_character"], 12)
        self.assertEqual(result["required_interval_ratio_lower_bound"], "1/1")
        self.assertFalse(result["wire_time_strictly_exceeds_interval"])
        self.assertEqual(result["device_timing_and_operational_feasibility"], "not_evaluated")

    def test_invalid_inputs_do_not_become_a_successful_budget(self):
        for field, value in (("baud", 0), ("baud", True), ("tx_bytes", -1),
                             ("rx_bytes", 1.5), ("data_bits", 7),
                             ("stop_bits", True), ("parity", "mark"),
                             ("duplex", "automatic"), ("interval_ms", 0)):
            case = copy.deepcopy(CASES[0])
            case[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                BUDGET.budget(case)
        for raw in (b'{"schema_version":1,"schema_version":1,"cases":[]}',
                    b'{"schema_version":1,"cases":[],"unknown":true}',
                    b"{" * 65537):
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError):
                BUDGET.evaluate(raw)


if __name__ == "__main__":
    unittest.main()
