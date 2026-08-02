import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.physics_runtime import build_physics_contract


class Phase81ColliderOverrideContractTests(unittest.TestCase):
    def test_normalises_ren_wrist_overrides(self):
        contract = build_physics_contract(
            {
                "enabled": True,
                "collider_overrides": {
                    "Ren": [
                        {
                            "object": "017_右手首",
                            "radial_scale": 1.15,
                            "length_scale": 1.05,
                        },
                        {
                            "object": "021_左手首",
                            "radial_scale": 1.15,
                            "length_scale": 1.05,
                        },
                    ]
                },
            },
            frame_start=1,
            frame_end=366,
        )
        self.assertEqual(
            contract["collider_overrides"]["Ren"][0]["object"],
            "017_右手首",
        )
        self.assertEqual(
            contract["collider_overrides"]["Ren"][1]["object"],
            "021_左手首",
        )
        self.assertAlmostEqual(
            contract["collider_overrides"]["Ren"][0]["radial_scale"],
            1.15,
        )
        self.assertAlmostEqual(
            contract["collider_overrides"]["Ren"][0]["length_scale"],
            1.05,
        )

    def test_rejects_duplicate_character_object_override(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_physics_contract(
                {
                    "collider_overrides": {
                        "Ren": [
                            {
                                "object": "017_右手首",
                                "radial_scale": 1.15,
                                "length_scale": 1.05,
                            },
                            {
                                "object": "017_右手首",
                                "radial_scale": 1.10,
                                "length_scale": 1.02,
                            },
                        ]
                    }
                },
                frame_start=1,
                frame_end=48,
            )

    def test_rejects_unsafe_scale_range(self):
        with self.assertRaisesRegex(ValueError, "radial_scale"):
            build_physics_contract(
                {
                    "collider_overrides": {
                        "Ren": [
                            {
                                "object": "017_右手首",
                                "radial_scale": 2.5,
                                "length_scale": 1.05,
                            }
                        ]
                    }
                },
                frame_start=1,
                frame_end=48,
            )


if __name__ == "__main__":
    unittest.main()
