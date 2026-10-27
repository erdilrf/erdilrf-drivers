"""Incomplete command writes are software errors, not missing device replies."""

import unittest
from unittest import mock

from erdilrf_lrf.device import Rangefinder


class PartialWriteLink:
    def __init__(self, accepted):
        self.accepted = accepted
        self.written = []
        self.reads_after_write = 0

    def write(self, data):
        self.written.append(bytes(data))
        return self.accepted

    def read(self, size):
        if self.written:
            self.reads_after_write += 1
        return b""


class CommandWriteTests(unittest.TestCase):
    def test_incomplete_exchange_write_does_not_wait_for_a_reply_or_resend(self):
        for accepted in (0, 3, 7):
            with self.subTest(accepted=accepted):
                link = PartialWriteLink(accepted)
                device = Rangefinder(link)
                # A fake clock makes the old reply-timeout path deterministic.
                with mock.patch("erdilrf_lrf.device.time.monotonic", side_effect=[0, 2]):
                    with self.assertRaisesRegex(OSError, "complete command write"):
                        device.single_shot()
                self.assertEqual(len(link.written), 1)
                self.assertEqual(link.reads_after_write, 0)

    def test_fire_and_forget_commands_also_reject_incomplete_writes(self):
        operations = (
            ("continuous", lambda device: device.start_continuous()),
            ("constant_on", lambda device: device.ld_constant_on(True)),
            ("constant_off", lambda device: device.ld_constant_on(False)),
        )
        for name, operation in operations:
            with self.subTest(command=name):
                link = PartialWriteLink(3)
                with self.assertRaisesRegex(OSError, "complete command write"):
                    operation(Rangefinder(link))
                self.assertEqual(len(link.written), 1)
                self.assertEqual(link.reads_after_write, 0)


if __name__ == "__main__":
    unittest.main()
