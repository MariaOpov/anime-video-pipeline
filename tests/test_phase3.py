import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.config import ProjectConfig
from anime_pipeline.io_utils import atomic_write_json
from anime_pipeline.phase3 import Phase3Planner, seconds_to_frame


class Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.schemas = Path(__file__).resolve().parents[1] / "schemas"

    def test_seconds_to_frame_uses_blender_one_based_timeline(self):
        self.assertEqual(seconds_to_frame(0, 24), 1)
        self.assertEqual(seconds_to_frame(4.55, 24), 110)

    def test_builds_valid_blender_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            manifest = Phase3Planner(self._config(project), self.schemas).build()
            self.assertEqual(manifest["frame_end"], 48)
            self.assertEqual(manifest["summary"], {
                "shot_count": 1, "dialogue_count": 1, "mouth_cue_count": 2,
            })
            self.assertEqual(manifest["dialogue"][0]["mouth_cues"][1]["mouth_shape"], "A")

    def test_rejects_lip_sync_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project, lip_character="Ren")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                Phase3Planner(self._config(project), self.schemas).build()

    def _config(self, project: Path) -> ProjectConfig:
        return ProjectConfig(project, {
            "project_name": "Phase 3 Test", "render_engine": "BLENDER_EEVEE",
            "output": {"width": 1280, "height": 720, "fps": 24},
            "phase3": {
                "enabled": True, "base_scene": "blender_scenes/base.blend",
                "output_scene": "blender_scenes/output.blend",
                "preview_video": "renders/preview.mp4",
            },
        })

    def _write_fixture(self, project: Path, lip_character: str = "Aiko") -> None:
        (project / "generated").mkdir(parents=True)
        (project / "blender_scenes").mkdir()
        (project / "blender_scenes" / "base.blend").touch()
        (project / "dialogue").mkdir()
        (project / "dialogue" / "line_001.wav").touch()
        (project / "lip_sync").mkdir()
        atomic_write_json(project / "generated" / "shot_list.json", {
            "fps": 24, "total_duration_seconds": 2.0,
            "shots": [{
                "scene_id": "scene_001", "shot_id": "shot_001",
                "start_seconds": 0.0, "end_seconds": 2.0, "duration_seconds": 2.0,
                "camera": {"shot_type": "medium", "movement": "static", "target": "Aiko"},
            }],
        })
        atomic_write_json(project / "generated" / "dialogue_timeline.json", {
            "fps": 24, "total_duration_seconds": 1.0, "warnings": [],
            "lines": [{
                "line_id": "line_001", "scene_id": "scene_001", "shot_id": "shot_001",
                "character": "Aiko", "text": "Xin chào", "emotion": "neutral",
                "voice_id": "demo", "audio_path": "dialogue/line_001.wav",
                "start_seconds": 0.0, "end_seconds": 1.0, "duration_seconds": 1.0,
                "start_frame": 1, "end_frame": 25, "recorded_override": False,
            }],
        })
        atomic_write_json(project / "lip_sync" / "line_001.json", {
            "line_id": "line_001", "character": lip_character,
            "audio_path": "dialogue/line_001.wav", "duration_seconds": 1.0,
            "mouth_cues": [
                {"start": 0.0, "end": 0.2, "source_shape": "X", "mouth_shape": "closed"},
                {"start": 0.2, "end": 0.8, "source_shape": "D", "mouth_shape": "A"},
            ],
        })


if __name__ == "__main__":
    unittest.main()
