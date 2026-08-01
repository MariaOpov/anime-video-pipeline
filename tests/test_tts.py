import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.tts import PiperTTS, PiperVoice


class PiperTests(unittest.TestCase):
    def test_builds_documented_cli_command(self):
        voice = PiperVoice("vi_VN-vais1000-medium", Path("voices"), length_scale=1.12)
        command = PiperTTS().build_command("Xin chào", voice, Path("line.wav"))
        self.assertEqual(command[1:3], ["-m", "piper"])
        self.assertIn("vi_VN-vais1000-medium", command)
        self.assertIn("--data-dir", command)
        self.assertEqual(command[-2:], ["--", "Xin chào"])


if __name__ == "__main__":
    unittest.main()

