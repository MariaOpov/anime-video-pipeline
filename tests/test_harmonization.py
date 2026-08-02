import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.cinematography import direct_cinematography
from anime_pipeline.harmonization import (
    build_harmonization_contract,
    camera_fit_distance,
)
from anime_pipeline.io_utils import validate
from anime_pipeline.rig_contract import (
    BONE_ALIASES,
    PHASE8_REQUIRED_CONTROLS,
    match_aliases,
)


class HarmonizationTests(unittest.TestCase):
    def test_canonical_aliases_accept_japanese_chinese_and_blender_suffixes(self):
        mapping = match_aliases([
            "全ての親.001", "上半身2", "头", "左腕.001", "右腕.002",
            "左腿", "右腿", "双目", "左足ＩＫ", "右腿IK",
        ], BONE_ALIASES)
        for alias in PHASE8_REQUIRED_CONTROLS:
            self.assertIsNotNone(mapping[alias], alias)

    def test_contract_normalizes_mixed_character_sources_and_proportions(self):
        assets = {
            "characters": [{
                "character": "Aiko", "ready": True,
                "dimensions": [0.64, 0.38, 1.72],
                "bone_mapping": {
                    "spine": "上半身2", "head": "頭", "arm.L": "左腕",
                    "arm.R": "右腕", "leg.L": "左足", "leg.R": "右足",
                    "eyes": "両目",
                },
            }],
        }
        contract = build_harmonization_contract(
            assets, {"Aiko": {}, "Ren": {}},
            {"enabled": True, "character_heights": {"Aiko": 1.68, "Ren": 1.78}},
        )
        self.assertEqual(contract["configured_count"], 2)
        self.assertEqual(contract["ready_count"], 2)
        by_name = {item["character"]: item for item in contract["characters"]}
        self.assertEqual(by_name["Aiko"]["source"], "phase7_cache")
        self.assertEqual(by_name["Ren"]["source"], "base_scene")
        self.assertEqual(by_name["Ren"]["target_height_meters"], 1.78)
        self.assertEqual(by_name["Aiko"]["resolved_control_count"], 10)
        self.assertGreater(by_name["Aiko"]["fallback_control_count"], 0)

    def test_camera_fit_responds_to_world_size_and_lens(self):
        base = camera_fit_distance(1.0, 1.8, 52.0, 16 / 9, 0.88)
        taller = camera_fit_distance(1.0, 2.4, 52.0, 16 / 9, 0.88)
        telephoto = camera_fit_distance(1.0, 1.8, 85.0, 16 / 9, 0.88)
        self.assertGreater(taller, base)
        self.assertGreater(telephoto, base)

    def test_cinematography_uses_harmonized_geometry(self):
        harmony = build_harmonization_contract(
            {}, {"Aiko": {}},
            {"enabled": True, "character_heights": {"Aiko": 2.0}},
        )
        result = direct_cinematography(
            [{"scene_id": "scene", "shot_id": "shot", "start_frame": 1,
              "end_frame": 48, "shot_type": "close_up", "target": "Aiko"}],
            {"clips": [{"shot_id": "shot", "character": "Aiko",
                         "role": "speaker", "look_at": None}]},
            {"aspect_ratio": 16 / 9},
            harmonization=harmony,
        )
        camera = result["shots"][0]["camera"]
        self.assertTrue(camera["adaptive"])
        self.assertEqual(camera["required_region"], "face")
        self.assertEqual(camera["subject_height_meters"], 2.0)

    def test_phase8_report_schema_accepts_a_complete_runtime_audit(self):
        report = {
            "schema_version": 1, "phase": 8, "status": "complete", "enabled": True,
            "project_name": "Demo", "frame_start": 1, "frame_end": 48,
            "pose": "neutral_dialogue",
            "characters": [{
                "character": "Aiko", "root_object": "PIPE_Aiko_ROOT",
                "target_height_meters": 1.68, "measured_height_meters": 1.68,
                "height_error_ratio": 0.0, "scale_factor": 0.976744,
                "world_bounds_min": [-0.3, -0.2, 0.0],
                "world_bounds_max": [0.3, 0.2, 1.68],
                "neutral_pose": "neutral_dialogue", "arm_deviation_degrees": 0.1,
                "neutral_pose_passed": True, "ground_plane_z": 0.0,
                "ground_error_meters": 0.0, "grounding_passed": True,
                "foot_lock_mode": "root_grounded", "bone_axes_verified": True,
                "required_control_count": 10, "resolved_control_count": 10,
                "ready": True,
            }],
            "shots": [{
                "scene_id": "scene", "shot_id": "shot", "composition": "single",
                "subject": "Aiko", "required_characters": ["Aiko"],
                "required_region": "full_body",
                "world_bounds_min": [-0.3, -0.2, -0.06],
                "world_bounds_max": [0.3, 0.2, 1.78], "lens_mm": 56,
                "frame_margin_fraction": 0.06, "measured_minimum_margin": 0.061,
                "head_visible": True, "feet_required": True, "feet_visible": True,
                "framing_passed": True,
            }],
            "summary": {
                "character_count": 1, "ready_character_count": 1,
                "neutral_pose_character_count": 1, "scaled_character_count": 1,
                "grounded_character_count": 1, "bone_axes_verified_count": 1,
                "source_ik_character_count": 0, "root_grounded_character_count": 1,
                "adaptive_camera_shot_count": 1, "framing_passed_shot_count": 1,
                "issue_count": 0,
            },
        }
        root = Path(__file__).resolve().parents[1]
        validate(report, root / "schemas" / "phase8_harmonization_report.schema.json",
                 "Phase 8 report")


if __name__ == "__main__":
    unittest.main()
