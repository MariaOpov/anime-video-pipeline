import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.config import ProjectConfig
from anime_pipeline.io_utils import atomic_write_json
from anime_pipeline.phase5 import Phase5Auditor, QualityGateError


class Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.schemas = Path(__file__).resolve().parents[1] / "schemas"
        self.tool_versions = {
            "python": "3.12.0", "pipeline": "0.5.0", "blender": "Blender 5.1.2",
            "piper_tts": "1.6.0", "rhubarb": "Rhubarb Lip Sync 1.14.0",
            "ffmpeg": "7.1",
        }

    def test_all_quality_gates_pass_and_report_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            report, output = Phase5Auditor(self._config(project), self.schemas).run(
                tool_versions=self.tool_versions
            )
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["summary"]["failed_gate_count"], 0)
            self.assertEqual(report["summary"]["mouth_cue_count"], 2)
            self.assertTrue(output.is_file())
            self.assertIn("final_video", [item["name"] for item in report["artifacts"]])

    def test_missing_final_video_fails_gate_and_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            (project / "output" / "final.mp4").unlink()
            with self.assertRaisesRegex(QualityGateError, "final_video_exists"):
                Phase5Auditor(self._config(project), self.schemas).run(
                    tool_versions=self.tool_versions
                )
            report = json.loads((project / "generated" / "production_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertGreater(report["summary"]["failed_gate_count"], 0)

    def test_timing_warnings_obey_configured_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            timeline_path = project / "generated" / "dialogue_timeline.json"
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            timeline["warnings"] = ["line exceeds shot"]
            atomic_write_json(timeline_path, timeline)
            config = self._config(project)
            config.data["phase5"]["max_timing_warnings"] = 1
            report, _ = Phase5Auditor(config, self.schemas).run(tool_versions=self.tool_versions)
            gate = next(item for item in report["quality_gates"] if item["name"] == "timing_warnings_within_limit")
            self.assertEqual(gate["status"], "passed")

    def test_embeds_stage_run_record(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            run_record = project / "generated" / "phase5_run_record.json"
            atomic_write_json(run_record, {"status": "complete", "stages": [
                {"name": "phase3_blender", "phase": 3, "status": "complete", "duration_seconds": 4.2}
            ]})
            report, _ = Phase5Auditor(self._config(project), self.schemas).run(
                run_record=run_record, tool_versions=self.tool_versions
            )
            self.assertEqual(report["run"]["stages"][0]["duration_seconds"], 4.2)

    def _config(self, project: Path) -> ProjectConfig:
        return ProjectConfig(project, {
            "project_name": "Phase 5 Test", "maximum_video_duration": 30,
            "output": {"width": 1280, "height": 720, "fps": 24},
            "phase2": {"rhubarb_executable": "tools/rhubarb/rhubarb.exe"},
            "phase3": {"resolution_percentage": 50},
            "phase5": {
                "enabled": True, "report": "generated/production_report.json",
                "max_asset_warnings": 0, "max_unresolved_motion_assignments": 0,
                "max_timing_warnings": 0, "min_output_size_bytes": 100,
                "duration_tolerance_seconds": 0.1,
            },
        })

    def _write_fixture(self, project: Path) -> None:
        for directory in ("generated", "dialogue", "lip_sync", "blender_scenes", "renders", "subtitles", "output"):
            (project / directory).mkdir(parents=True, exist_ok=True)
        screenplay = {
            "title": "Test", "fps": 24,
            "scenes": [{
                "scene_id": "scene_001", "location": "roof", "time_of_day": "sunset", "mood": "calm",
                "shots": [{
                    "shot_id": "scene_001_shot_001", "duration_seconds": 2.0,
                    "camera": {"shot_type": "medium", "movement": "static", "target": "Aiko"},
                    "characters": [{"name": "Aiko", "position": [0, 0, 0], "action": "talking",
                                    "emotion": "neutral", "look_at": None}],
                    "dialogue": [{"character": "Aiko", "text": "Xin chào", "emotion": "neutral"}],
                    "description": "Dialogue",
                }],
            }],
        }
        atomic_write_json(project / "generated" / "screenplay.json", screenplay)
        atomic_write_json(project / "generated" / "shot_list.json", {
            "fps": 24, "total_duration_seconds": 2.0,
            "shots": [{"scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                       "start_seconds": 0.0, "end_seconds": 2.0, "duration_seconds": 2.0,
                       "camera": {"shot_type": "medium", "movement": "static", "target": "Aiko"}}],
        })
        atomic_write_json(project / "generated" / "asset_index.json", {"assets": [], "warnings": []})
        atomic_write_json(project / "generated" / "motion_plan.json", {
            "shots": [{"assignments": [{"character": "Aiko", "motion_id": "idle"}]}]
        })
        atomic_write_json(project / "generated" / "pipeline_state.json", {"version": 1, "stages": {}})
        timeline = {
            "fps": 24, "total_duration_seconds": 1.0, "warnings": [],
            "lines": [{
                "line_id": "line_001", "scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                "character": "Aiko", "text": "Xin chào", "emotion": "neutral", "voice_id": "voice",
                "audio_path": "dialogue/line_001.wav", "start_seconds": 0.0, "end_seconds": 1.0,
                "duration_seconds": 1.0, "start_frame": 1, "end_frame": 25,
                "recorded_override": False,
            }],
        }
        atomic_write_json(project / "generated" / "dialogue_timeline.json", timeline)
        (project / "dialogue" / "line_001.wav").write_bytes(b"R" * 128)
        cues = [
            {"start": 0.0, "end": 0.3, "source_shape": "X", "mouth_shape": "closed"},
            {"start": 0.3, "end": 0.8, "source_shape": "D", "mouth_shape": "A"},
        ]
        atomic_write_json(project / "lip_sync" / "line_001.json", {
            "line_id": "line_001", "character": "Aiko", "audio_path": "dialogue/line_001.wav",
            "duration_seconds": 1.0, "mouth_cues": cues,
        })
        manifest = {
            "version": 1, "project_name": "Phase 5 Test", "fps": 24, "frame_start": 1, "frame_end": 48,
            "base_scene": "blender_scenes/base.blend", "output_scene": "blender_scenes/assembled.blend",
            "preview_video": "renders/preview.mp4",
            "render": {"engine": "BLENDER_EEVEE", "width": 1280, "height": 720, "resolution_percentage": 50},
            "camera": {},
            "shots": [{"scene_id": "scene_001", "shot_id": "scene_001_shot_001", "start_frame": 1,
                       "end_frame": 48, "shot_type": "medium", "movement": "static", "target": "Aiko"}],
            "dialogue": [{"line_id": "line_001", "shot_id": "scene_001_shot_001", "character": "Aiko",
                          "audio_path": "dialogue/line_001.wav", "start_frame": 1, "end_frame": 25,
                          "start_seconds": 0.0, "duration_seconds": 1.0, "mouth_cues": cues}],
            "summary": {"shot_count": 1, "dialogue_count": 1, "mouth_cue_count": 2},
        }
        atomic_write_json(project / "generated" / "phase3_manifest.json", manifest)
        (project / "blender_scenes" / "assembled.blend").write_bytes(b"BLENDER" * 32)
        (project / "renders" / "preview.mp4").write_bytes(b"PREVIEW" * 32)
        atomic_write_json(project / "generated" / "phase3_scene_report.json", {
            "phase": 3, "status": "complete", "fps": 24, "frame_start": 1, "frame_end": 48,
            "camera_count": 1, "audio_strip_count": 1, "mouth_target_count": 1,
            "mouth_cue_count": 2, "scene_file": "blender_scenes/assembled.blend",
            "preview_video": "renders/preview.mp4",
        })
        (project / "subtitles" / "dialogue.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")
        (project / "output" / "final.mp4").write_bytes(b"FINAL" * 64)
        atomic_write_json(project / "generated" / "phase4_report.json", {
            "phase": 4, "status": "complete", "ffmpeg_version": "7.1",
            "input_video": "renders/preview.mp4", "subtitle_file": "subtitles/dialogue.srt",
            "subtitle_count": 1, "subtitle_mode": "burn", "audio_normalized": True,
            "output_video": "output/final.mp4", "duration_seconds": 2.0,
            "width": 640, "height": 360, "output_size_bytes": 320,
        })


if __name__ == "__main__":
    unittest.main()
