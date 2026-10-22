"""The documented package-level quick start works without a serial dependency or hardware."""
import subprocess
import sys
import unittest
from pathlib import Path


class PublicQuickStartTest(unittest.TestCase):
    def test_readme_import_and_injected_ranging_without_pyserial(self):
        source = Path(__file__).resolve().parents[1] / "src"
        example = r'''import sys
sys.path.insert(0, sys.argv[1])
from erdilrf_lrf import Rangefinder, SerialTransport
assert "serial" not in sys.modules
class CapturedReply:
    def __init__(self):
        self.pending = b""
        self.closed = False
    def read(self, size):
        chunk, self.pending = self.pending[:size], self.pending[size:]
        return chunk
    def write(self, command):
        assert command == bytes.fromhex("55 AA 88 FF FF FF FF 84")
        self.pending = bytes.fromhex("55 AA 88 01 FF 27 10 BE")
        return len(command)
    def close(self):
        self.closed = True
link = CapturedReply()
with Rangefinder(link) as rf:
    assert rf.single_shot() == 1000.0
assert link.closed
assert "serial" not in sys.modules
'''
        result = subprocess.run([sys.executable, "-I", "-B", "-c", example, str(source)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
