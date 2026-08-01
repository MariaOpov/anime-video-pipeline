import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.audio import normalize_and_pad_wav, wav_duration


class AudioTests(unittest.TestCase):
    def test_normalize_and_pad_pcm_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            output = Path(directory) / "output.wav"
            samples = array("h", [1000, -1000] * 400)
            with wave.open(str(source), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(8000)
                wav_file.writeframes(samples.tobytes())
            duration = normalize_and_pad_wav(source, output, pad_before=0.1, pad_after=0.2,
                                             target_peak=0.5)
            self.assertAlmostEqual(duration, 0.4, places=3)
            self.assertAlmostEqual(wav_duration(output), 0.4, places=3)
            with wave.open(str(output), "rb") as wav_file:
                rendered = array("h")
                rendered.frombytes(wav_file.readframes(wav_file.getnframes()))
            self.assertGreaterEqual(max(abs(sample) for sample in rendered), 16380)

    def test_rejects_negative_padding(self):
        with self.assertRaises(ValueError):
            normalize_and_pad_wav(Path("missing.wav"), Path("out.wav"), pad_before=-1)


if __name__ == "__main__":
    unittest.main()

