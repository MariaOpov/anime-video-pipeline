import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.motions import MotionSelector


class MotionSelectorTests(unittest.TestCase):
    def setUp(self):
        self.assets = [
            {"asset_id": "talk", "type": "motion", "available": True,
             "action": "idle_talking", "character_type": "humanoid", "compatible_skeleton": "mmd_standard"},
            {"asset_id": "idle", "type": "motion", "available": True,
             "action": "idle", "character_type": "humanoid", "compatible_skeleton": "any"},
        ]

    def test_exact_match(self):
        selected = MotionSelector(self.assets).select("idle_talking", skeleton="mmd_standard")
        self.assertEqual(selected.motion_id, "talk")
        self.assertEqual(selected.fallback_level, 0)

    def test_fallback_match(self):
        selected = MotionSelector(self.assets).select("sad_talking", skeleton="mmd_standard")
        self.assertEqual(selected.motion_id, "talk")
        self.assertEqual(selected.selected_action, "idle_talking")
        self.assertGreater(selected.fallback_level, 0)

    def test_missing_motion_is_safe(self):
        selected = MotionSelector([]).select("sword_attack")
        self.assertIsNone(selected.motion_id)
        self.assertIn("no compatible", selected.reason)


if __name__ == "__main__":
    unittest.main()

