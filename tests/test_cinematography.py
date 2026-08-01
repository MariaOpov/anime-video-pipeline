import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.cinematography import direct_cinematography


class CinematographyTests(unittest.TestCase):
    def shots(self):
        return [
            {"scene_id": "scene_001", "shot_id": "shot_001", "start_frame": 1,
             "end_frame": 48, "shot_type": "medium", "movement": "static",
             "target": "Aiko"},
            {"scene_id": "scene_001", "shot_id": "shot_002", "start_frame": 49,
             "end_frame": 96, "shot_type": "close_up", "movement": "static",
             "target": "Ren"},
            {"scene_id": "scene_001", "shot_id": "shot_003", "start_frame": 97,
             "end_frame": 144, "shot_type": "medium", "movement": "static",
             "target": "Aiko"},
            {"scene_id": "scene_001", "shot_id": "shot_004", "start_frame": 145,
             "end_frame": 192, "shot_type": "medium", "movement": "static",
             "target": "Ren"},
        ]

    def performance(self):
        clips = []
        for shot, speaker, listener in zip(
            self.shots(), ("Aiko", "Ren", "Aiko", "Ren"),
            ("Ren", "Aiko", "Ren", "Aiko"),
        ):
            clips.extend([
                {"shot_id": shot["shot_id"], "character": speaker,
                 "role": "speaker", "look_at": listener},
                {"shot_id": shot["shot_id"], "character": listener,
                 "role": "listener", "look_at": speaker},
            ])
        return {"clips": clips}

    def test_director_builds_stable_blocking_and_camera_moves(self):
        result = direct_cinematography(
            self.shots(), self.performance(),
            {"close_up_distance": 4.2, "medium_distance": 6.4, "wide_distance": 8.6},
        )
        self.assertEqual(len(result["shots"]), 4)
        self.assertEqual(result["placement_count"], 8)
        self.assertEqual(result["body_facing_count"], 8)
        self.assertEqual(result["camera_motion_count"], 3)
        self.assertEqual(result["shots"][0]["composition"], "two_shot")
        self.assertEqual(result["shots"][1]["composition"], "close_up")
        self.assertEqual(result["shots"][2]["composition"], "over_shoulder")
        self.assertEqual(result["shots"][3]["camera"]["movement"], "slow_dolly_out")
        self.assertEqual(result["framing_risk_count"], 0)
        self.assertEqual(result["camera_collision_risk_count"], 0)
        self.assertEqual(result["continuity_violation_count"], 0)
        self.assertEqual(result["blocking_conflict_count"], 0)

    def test_characters_keep_screen_side_and_face_each_other(self):
        result = direct_cinematography(self.shots(), self.performance(), {})
        for shot in result["shots"]:
            placements = {item["character"]: item for item in shot["placements"]}
            self.assertLess(placements["Aiko"]["position"][0],
                            placements["Ren"]["position"][0])
            self.assertGreater(placements["Aiko"]["body_yaw_degrees"], 0)
            self.assertLess(placements["Ren"]["body_yaw_degrees"], 0)

    def test_invalid_safety_settings_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "spacing"):
            direct_cinematography(
                self.shots(), self.performance(), {}, {"character_spacing": 0.2}
            )
        with self.assertRaisesRegex(ValueError, "motion strength"):
            direct_cinematography(
                self.shots(), self.performance(), {}, {"camera_motion_strength": 2.0}
            )

    def test_disabled_director_is_an_empty_safe_contract(self):
        result = direct_cinematography(
            self.shots(), self.performance(), {}, {"enabled": False}
        )
        self.assertFalse(result["enabled"])
        self.assertEqual(result["shots"], [])
        self.assertEqual(result["blocking_conflict_count"], 0)


if __name__ == "__main__":
    unittest.main()
