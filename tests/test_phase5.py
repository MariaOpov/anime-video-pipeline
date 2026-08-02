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
            self.assertEqual(report["summary"]["quality_gate_count"], 34)
            self.assertEqual(report["summary"]["mouth_cue_count"], 2)
            self.assertTrue(output.is_file())
            self.assertIn("final_video", [item["name"] for item in report["artifacts"]])

    def test_procedural_performance_requires_pose_keys_and_resolved_bones(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            manifest_path = project / "generated" / "phase3_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["performance"]["source"] = "rules"
            manifest["performance"]["clips"] = [{
                "scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                "character": "Aiko", "role": "speaker",
                "start_frame": 1, "end_frame": 48,
                "action": "idle_talking", "emotion": "neutral",
                "intensity": 0.2, "gestures": ["breathe"], "look_at": None,
                "beats": [],
            }]
            manifest["summary"]["performance_clip_count"] = 1
            manifest["summary"]["gesture_count"] = 1
            atomic_write_json(manifest_path, manifest)
            report_path = project / "generated" / "phase3_scene_report.json"
            scene_report = json.loads(report_path.read_text(encoding="utf-8"))
            scene_report.update({"performance_target_count": 1,
                                 "performance_clip_count": 1, "gesture_count": 1})
            atomic_write_json(report_path, scene_report)

            with self.assertRaisesRegex(QualityGateError, "procedural_gestures_applied"):
                Phase5Auditor(self._config(project), self.schemas).run(
                    tool_versions=self.tool_versions
                )

            scene_report["pose_keyframe_count"] = 6
            atomic_write_json(report_path, scene_report)
            report, _ = Phase5Auditor(self._config(project), self.schemas).run(
                tool_versions=self.tool_versions
            )
            gate = next(item for item in report["quality_gates"]
                        if item["name"] == "procedural_gestures_applied")
            self.assertEqual(gate["status"], "passed")

    def test_performance_direction_requires_gaze_and_blink_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            manifest_path = project / "generated" / "phase3_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["performance"].update({
                "source": "rules",
                "clips": [{
                    "scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                    "character": "Aiko", "role": "speaker", "start_frame": 1,
                    "end_frame": 48, "action": "idle_talking", "emotion": "neutral",
                    "intensity": 0.2, "gestures": ["breathe"], "look_at": "Ren",
                    "beats": [{"type": "speech", "gesture": None, "start_frame": 1,
                               "peak_frame": 12, "end_frame": 25}],
                }],
                "gaze_events": [{"scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                                 "character": "Aiko", "target": "Ren",
                                 "start_frame": 1, "end_frame": 48}],
                "blink_events": [{"character": "Aiko", "close_frame": 20,
                                  "open_frame": 23}],
                "dialogue_beat_count": 1, "listener_reaction_count": 0,
                "performance_conflict_count": 0,
            })
            manifest["summary"].update({
                "performance_clip_count": 1, "gesture_count": 1,
                "dialogue_beat_count": 1, "gaze_target_count": 1,
                "blink_event_count": 1, "listener_reaction_count": 0,
                "performance_conflict_count": 0,
            })
            atomic_write_json(manifest_path, manifest)
            scene_path = project / "generated" / "phase3_scene_report.json"
            scene_report = json.loads(scene_path.read_text(encoding="utf-8"))
            scene_report.update({
                "performance_target_count": 1, "performance_clip_count": 1,
                "gesture_count": 1, "pose_keyframe_count": 6,
                "dialogue_beat_count": 1, "gaze_target_count": 1,
                "gaze_keyframe_count": 0, "blink_target_count": 1,
                "blink_event_count": 1, "blink_keyframe_count": 0,
                "listener_reaction_count": 0, "performance_conflict_count": 0,
            })
            atomic_write_json(scene_path, scene_report)

            with self.assertRaisesRegex(QualityGateError, "performance_direction_applied"):
                Phase5Auditor(self._config(project), self.schemas).run(
                    tool_versions=self.tool_versions
                )

            scene_report.update({"gaze_keyframe_count": 4, "blink_keyframe_count": 3})
            atomic_write_json(scene_path, scene_report)
            report, _ = Phase5Auditor(self._config(project), self.schemas).run(
                tool_versions=self.tool_versions
            )
            gate = next(item for item in report["quality_gates"]
                        if item["name"] == "performance_direction_applied")
            self.assertEqual(gate["status"], "passed")

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

    def test_cinematic_blocking_requires_placements_camera_keys_and_zero_risks(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            manifest_path = project / "generated" / "phase3_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["blocking"] = {
                "enabled": True,
                "shots": [{
                    "scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                    "start_frame": 1, "end_frame": 48, "composition": "single",
                    "subject": "Aiko", "listener": None,
                    "placements": [{"character": "Aiko", "position": [0, 0, 0],
                                    "facing_target": None, "body_yaw_degrees": 0}],
                    "camera": {"movement": "slow_dolly_in", "lens_mm": 56,
                               "start_location": [0, -6, 1.7],
                               "end_location": [0, -5.8, 1.7],
                               "start_target": [0, 0, 1.6],
                               "end_target": [0, 0, 1.6]},
                    "framing_risk_count": 0, "camera_collision_risk_count": 0,
                    "continuity_violation_count": 0, "blocking_conflict_count": 0,
                }],
                "placement_count": 1, "body_facing_count": 0,
                "camera_motion_count": 1, "framing_risk_count": 0,
                "camera_collision_risk_count": 0, "continuity_violation_count": 0,
                "blocking_conflict_count": 0,
            }
            manifest["summary"].update({
                "blocking_shot_count": 1, "character_placement_count": 1,
                "body_facing_count": 0, "camera_motion_count": 1,
                "framing_risk_count": 0, "camera_collision_risk_count": 0,
                "continuity_violation_count": 0, "blocking_conflict_count": 0,
            })
            atomic_write_json(manifest_path, manifest)
            scene_path = project / "generated" / "phase3_scene_report.json"
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
            scene.update({"blocking_shot_count": 1, "character_placement_count": 1,
                          "body_facing_count": 0, "camera_motion_count": 1,
                          "framing_risk_count": 0, "camera_collision_risk_count": 0,
                          "continuity_violation_count": 0, "blocking_conflict_count": 0})
            atomic_write_json(scene_path, scene)
            with self.assertRaisesRegex(QualityGateError, "cinematic_blocking_applied"):
                Phase5Auditor(self._config(project), self.schemas).run(
                    tool_versions=self.tool_versions
                )
            scene.update({"placement_keyframe_count": 4, "camera_keyframe_count": 4})
            atomic_write_json(scene_path, scene)
            report, _ = Phase5Auditor(self._config(project), self.schemas).run(
                tool_versions=self.tool_versions
            )
            gate = next(item for item in report["quality_gates"]
                        if item["name"] == "cinematic_blocking_applied")
            self.assertEqual(gate["status"], "passed")

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

    def test_production_character_gate_requires_cached_model_to_be_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            manifest_path = project / "generated" / "phase3_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            character = {
                "character": "Aiko", "profile": "local_assets/aiko.json",
                "cache_blend": "blender_cache/aiko.blend",
                "cache_collection": "PIPE_CHARACTER_AIKO",
                "armature_object": "PIPE_Aiko_Armature", "model_sha256": "a" * 64,
                "bone_mapping": {"spine": "上半身"},
                "morph_mapping": {"A": "あ"},
                "required_bone_count": 6, "resolved_bone_count": 6,
                "bone_coverage": 1.0, "required_mouth_morph_count": 5,
                "resolved_mouth_morph_count": 5, "mouth_morph_coverage": 1.0,
                "blink_morph_resolved": True, "texture_count": 4,
                "missing_texture_count": 0, "license_name": "Unknown",
                "license_warning": True, "warnings": [], "ready": True,
            }
            manifest["character_assets"] = {
                "enabled": True, "characters": [character], "configured_count": 1,
                "ready_count": 1, "missing_texture_count": 0,
                "warning_count": 0, "license_warning_count": 1,
            }
            manifest["summary"].update({
                "production_character_count": 1, "character_asset_ready_count": 1,
                "character_texture_missing_count": 0,
                "character_asset_warning_count": 0,
                "character_license_warning_count": 1,
            })
            atomic_write_json(manifest_path, manifest)
            with self.assertRaisesRegex(QualityGateError, "production_character_assets_ready"):
                Phase5Auditor(self._config(project), self.schemas).run(
                    tool_versions=self.tool_versions
                )
            scene_path = project / "generated" / "phase3_scene_report.json"
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
            scene.update({
                "production_character_count": 1,
                "production_character_loaded_count": 1,
                "resolved_character_bone_alias_count": 6,
                "resolved_character_mouth_morph_count": 5,
                "character_texture_missing_count": 0,
                "character_license_warning_count": 1,
            })
            atomic_write_json(scene_path, scene)
            report, _ = Phase5Auditor(self._config(project), self.schemas).run(
                tool_versions=self.tool_versions
            )
            gate = next(item for item in report["quality_gates"]
                        if item["name"] == "production_character_assets_ready")
            self.assertEqual(gate["status"], "passed")

    def test_phase8_gate_blocks_non_grounded_character(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._write_fixture(project)
            manifest_path = project / "generated" / "phase3_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["harmonization"].update({
                "enabled": True,
                "characters": [{
                    "character": "Aiko", "source": "base_scene",
                    "source_height_meters": 1.72, "target_height_meters": 1.68,
                    "planned_scale_factor": 0.976744,
                    "source_dimensions": [0.62, 0.38, 1.72],
                    "target_dimensions": [0.60558, 0.37116, 1.68],
                    "head_height_meters": 1.5456,
                    "canonical_controls": {"root": "__PIPE_ROOT__"},
                    "required_control_count": 10, "resolved_control_count": 10,
                    "fallback_control_count": 3, "runtime_probe_required": True,
                    "ready": True,
                }],
                "configured_count": 1, "ready_count": 1,
            })
            manifest["summary"].update({
                "harmonization_character_count": 1,
                "harmonization_ready_count": 1,
                "adaptive_camera_shot_count": 1,
            })
            atomic_write_json(manifest_path, manifest)
            scene_path = project / "generated" / "phase3_scene_report.json"
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
            scene.update({
                "harmonization_enabled": True, "harmonization_character_count": 1,
                "harmonization_ready_count": 1, "neutral_pose_character_count": 1,
                "grounded_character_count": 0, "bone_axes_verified_count": 1,
                "adaptive_camera_shot_count": 1, "adaptive_camera_pass_count": 1,
                "phase8_issue_count": 1,
            })
            atomic_write_json(scene_path, scene)
            report_path = project / "generated" / "phase8_harmonization_report.json"
            phase8 = {
                "schema_version": 1, "phase": 8, "status": "failed", "enabled": True,
                "project_name": "Phase 5 Test", "frame_start": 1, "frame_end": 48,
                "pose": "neutral_dialogue",
                "characters": [{
                    "character": "Aiko", "root_object": "PIPE_Aiko_ROOT",
                    "target_height_meters": 1.68, "measured_height_meters": 1.68,
                    "height_error_ratio": 0.0, "scale_factor": 0.976744,
                    "world_bounds_min": [-0.3, -0.2, 0.04],
                    "world_bounds_max": [0.3, 0.2, 1.72],
                    "neutral_pose": "neutral_dialogue", "arm_deviation_degrees": 0.1,
                    "neutral_pose_passed": True, "ground_plane_z": 0.0,
                    "ground_error_meters": 0.04, "grounding_passed": False,
                    "foot_lock_mode": "root_grounded", "bone_axes_verified": True,
                    "required_control_count": 10, "resolved_control_count": 10,
                    "ready": False,
                }],
                "shots": [{
                    "scene_id": "scene_001", "shot_id": "scene_001_shot_001",
                    "composition": "single", "subject": "Aiko",
                    "required_characters": ["Aiko"], "required_region": "full_body",
                    "world_bounds_min": [-0.3, -0.2, -0.06],
                    "world_bounds_max": [0.3, 0.2, 1.78], "lens_mm": 56,
                    "frame_margin_fraction": 0.06, "measured_minimum_margin": 0.061,
                    "head_visible": True, "feet_required": True, "feet_visible": True,
                    "framing_passed": True,
                }],
                "summary": {
                    "character_count": 1, "ready_character_count": 0,
                    "neutral_pose_character_count": 1, "scaled_character_count": 1,
                    "grounded_character_count": 0, "bone_axes_verified_count": 1,
                    "source_ik_character_count": 0, "root_grounded_character_count": 1,
                    "adaptive_camera_shot_count": 1, "framing_passed_shot_count": 1,
                    "issue_count": 1,
                },
            }
            atomic_write_json(report_path, phase8)
            with self.assertRaisesRegex(QualityGateError, "character_harmonization_ready"):
                Phase5Auditor(self._config(project), self.schemas).run(
                    tool_versions=self.tool_versions
                )

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
            "version": 6, "project_name": "Phase 5 Test", "fps": 24, "frame_start": 1, "frame_end": 48,
            "base_scene": "blender_scenes/base.blend", "output_scene": "blender_scenes/assembled.blend",
            "preview_video": "renders/preview.mp4",
            "render": {"engine": "BLENDER_EEVEE", "width": 1280, "height": 720, "resolution_percentage": 50},
            "camera": {},
            "performance": {"enabled": True, "source": None,
                            "amplitude_scale": 1.0, "clips": [],
                            "gaze_events": [], "blink_events": [],
                            "dialogue_beat_count": 0, "listener_reaction_count": 0,
                            "performance_conflict_count": 0},
            "blocking": {"enabled": False, "shots": [], "placement_count": 0,
                         "body_facing_count": 0, "camera_motion_count": 0,
                         "framing_risk_count": 0, "camera_collision_risk_count": 0,
                         "continuity_violation_count": 0, "blocking_conflict_count": 0},
            "character_assets": {"enabled": False, "characters": [],
                                 "configured_count": 0, "ready_count": 0,
                                 "missing_texture_count": 0, "warning_count": 0,
                                 "license_warning_count": 0},
            "harmonization": {
                "version": 1, "enabled": False,
                "report": "generated/phase8_harmonization_report.json",
                "pose": "neutral_dialogue",
                "floor_z": 0.0, "default_target_height_meters": 1.72,
                "height_tolerance_ratio": 0.02, "ground_tolerance_meters": 0.015,
                "rest_pose_max_degrees": 18.0, "neutral_arm_degrees": 12.0,
                "safe_frame_fraction": 0.88, "headroom_fraction": 0.06,
                "footroom_fraction": 0.04, "characters": [],
                "configured_count": 0, "ready_count": 0,
            },
            "shots": [{"scene_id": "scene_001", "shot_id": "scene_001_shot_001", "start_frame": 1,
                       "end_frame": 48, "shot_type": "medium", "movement": "static", "target": "Aiko"}],
            "dialogue": [{"line_id": "line_001", "shot_id": "scene_001_shot_001", "character": "Aiko",
                          "audio_path": "dialogue/line_001.wav", "start_frame": 1, "end_frame": 25,
                          "start_seconds": 0.0, "duration_seconds": 1.0, "mouth_cues": cues}],
            "summary": {"shot_count": 1, "dialogue_count": 1, "mouth_cue_count": 2,
                        "performance_clip_count": 0, "gesture_count": 0,
                        "dialogue_beat_count": 0, "gaze_target_count": 0,
                        "blink_event_count": 0, "listener_reaction_count": 0,
                        "performance_conflict_count": 0,
                        "blocking_shot_count": 0, "character_placement_count": 0,
                        "body_facing_count": 0, "camera_motion_count": 0,
                        "framing_risk_count": 0, "camera_collision_risk_count": 0,
                        "continuity_violation_count": 0, "blocking_conflict_count": 0,
                        "production_character_count": 0,
                        "character_asset_ready_count": 0,
                        "character_texture_missing_count": 0,
                        "character_asset_warning_count": 0,
                        "character_license_warning_count": 0,
                        "harmonization_character_count": 0,
                        "harmonization_ready_count": 0,
                        "adaptive_camera_shot_count": 0},
        }
        atomic_write_json(project / "generated" / "phase3_manifest.json", manifest)
        (project / "blender_scenes" / "assembled.blend").write_bytes(b"BLENDER" * 32)
        (project / "renders" / "preview.mp4").write_bytes(b"PREVIEW" * 32)
        atomic_write_json(project / "generated" / "phase3_scene_report.json", {
            "phase": 3, "status": "complete", "fps": 24, "frame_start": 1, "frame_end": 48,
            "camera_count": 1, "audio_strip_count": 1, "mouth_target_count": 1,
            "mouth_cue_count": 2, "performance_target_count": 0,
            "performance_clip_count": 0, "gesture_count": 0, "pose_keyframe_count": 0,
            "skipped_bone_alias_count": 0, "scene_file": "blender_scenes/assembled.blend",
            "dialogue_beat_count": 0, "gaze_target_count": 0,
            "gaze_keyframe_count": 0, "blink_target_count": 0,
            "blink_event_count": 0, "blink_keyframe_count": 0,
            "listener_reaction_count": 0, "performance_conflict_count": 0,
            "blocking_shot_count": 0, "character_placement_count": 0,
            "body_facing_count": 0, "placement_keyframe_count": 0,
            "camera_motion_count": 0, "camera_keyframe_count": 0,
            "framing_risk_count": 0, "camera_collision_risk_count": 0,
            "continuity_violation_count": 0, "blocking_conflict_count": 0,
            "production_character_count": 0,
            "production_character_loaded_count": 0,
            "resolved_character_bone_alias_count": 0,
            "resolved_character_mouth_morph_count": 0,
            "character_texture_missing_count": 0,
            "character_license_warning_count": 0,
            "harmonization_enabled": False,
            "harmonization_character_count": 0,
            "harmonization_ready_count": 0,
            "neutral_pose_character_count": 0,
            "grounded_character_count": 0,
            "bone_axes_verified_count": 0,
            "adaptive_camera_shot_count": 0,
            "adaptive_camera_pass_count": 0,
            "phase8_issue_count": 0,
            "phase8_report": "generated/phase8_harmonization_report.json",
            "preview_video": "renders/preview.mp4",
        })
        atomic_write_json(project / "generated" / "phase8_harmonization_report.json", {
            "schema_version": 1, "phase": 8, "status": "skipped", "enabled": False,
            "project_name": "Phase 5 Test", "frame_start": 1, "frame_end": 48,
            "pose": "neutral_dialogue", "characters": [], "shots": [],
            "summary": {
                "character_count": 0, "ready_character_count": 0,
                "neutral_pose_character_count": 0, "scaled_character_count": 0,
                "grounded_character_count": 0, "bone_axes_verified_count": 0,
                "source_ik_character_count": 0, "root_grounded_character_count": 0,
                "adaptive_camera_shot_count": 0, "framing_passed_shot_count": 0,
                "issue_count": 0,
            },
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
