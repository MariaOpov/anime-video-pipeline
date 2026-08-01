import logging
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.config import ProjectConfig
from anime_pipeline.phase2 import Phase2Runner


def write_test_wav(path: Path, seconds: float = 0.2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * round(8000 * seconds))


class Phase2IntegrationTests(unittest.TestCase):
    def test_generates_timeline_and_lip_sync_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "generated").mkdir()
            (project / "tools" / "rhubarb").mkdir(parents=True)
            (project / "tools" / "rhubarb" / "rhubarb.exe").touch()
            (project / "tools" / "rhubarb" / "res").mkdir()
            voices = project / "tools" / "voices"
            voices.mkdir(parents=True)
            (voices / "demo.onnx").touch()
            config = ProjectConfig(project, {
                "output": {"fps": 24},
                "characters": {"Aiko": {"voice_id": "demo_voice"}},
                "phase2": {
                    "enabled": True,
                    "piper_data_dir": "tools/voices",
                    "rhubarb_executable": "tools/rhubarb/rhubarb.exe",
                    "rhubarb_recognizer": "phonetic",
                    "voices": {"demo_voice": {"model": "demo"}},
                },
            })
            screenplay = {"scenes": [{
                "scene_id": "scene_001",
                "shots": [{"shot_id": "scene_001_shot_001", "dialogue": [{
                    "character": "Aiko", "text": "Xin chào", "emotion": "happy"
                }]}],
            }]}
            shot_list = {"shots": [{
                "shot_id": "scene_001_shot_001", "start_seconds": 0.0, "end_seconds": 2.0
            }]}

            def fake_synthesize(_self, _text, _voice, output):
                write_test_wav(output)

            fake_lips = {"duration": 0.4, "mouth_cues": [
                {"start": 0.0, "end": 0.2, "source_shape": "X", "mouth_shape": "neutral"},
                {"start": 0.2, "end": 0.4, "source_shape": "D", "mouth_shape": "A"},
            ]}
            with patch("anime_pipeline.phase2.piper_available", return_value=True), \
                 patch("anime_pipeline.phase2.PiperTTS.synthesize", new=fake_synthesize), \
                 patch("anime_pipeline.phase2.RhubarbLipSync.analyze", return_value=fake_lips):
                summary = Phase2Runner(
                    config, Path(__file__).resolve().parents[1] / "schemas",
                    logging.getLogger("phase2-test"), dry_run=False, resume=False,
                ).run(screenplay, shot_list)

            self.assertIn("1 WAV file", summary)
            self.assertTrue((project / "dialogue" / "scene_001_shot_001_line_001.wav").is_file())
            self.assertTrue((project / "generated" / "dialogue_timeline.json").is_file())
            self.assertTrue((project / "lip_sync" / "scene_001_shot_001_line_001.json").is_file())


if __name__ == "__main__":
    unittest.main()
