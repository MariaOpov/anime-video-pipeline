import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.gestures import PITCH, ROLL, YAW, build_pose_keyframes


class GestureExecutorTests(unittest.TestCase):
    def performance(self, **overrides):
        payload = {
            "start_frame": 1, "end_frame": 49, "action": "idle_talking",
            "intensity": 0.4, "gestures": ["breathe"],
        }
        payload.update(overrides)
        return payload

    def test_talking_and_breathing_generate_smooth_bounded_pose_keys(self):
        keys = build_pose_keyframes(self.performance())
        self.assertEqual(keys[0]["frame"], 1)
        self.assertEqual(keys[-1]["frame"], 49)
        self.assertIn("spine", keys[2]["rotations"])
        self.assertIn("arm.L", keys[2]["rotations"])
        self.assertEqual(keys[0]["rotations"]["spine"], [0.0, 0.0, 0.0])
        self.assertEqual(keys[-1]["rotations"]["arm.R"], [0.0, 0.0, 0.0])
        self.assertLessEqual(
            max(abs(value) for key in keys for rotation in key["rotations"].values()
                for value in rotation), 0.65,
        )

    def test_look_down_and_nod_create_visible_head_pitch(self):
        keys = build_pose_keyframes(self.performance(gestures=["look_down", "nod"]))
        self.assertGreater(max(key["rotations"]["head"][PITCH] for key in keys), 0.2)

    def test_look_target_controls_yaw_without_creating_mirrored_roll(self):
        neutral = build_pose_keyframes(self.performance(), look_direction=0.0)
        right = build_pose_keyframes(self.performance(), look_direction=1.0)
        left = build_pose_keyframes(self.performance(), look_direction=-1.0)
        self.assertGreater(right[2]["rotations"]["head"][YAW],
                           neutral[2]["rotations"]["head"][YAW])
        self.assertLess(left[2]["rotations"]["head"][YAW],
                        neutral[2]["rotations"]["head"][YAW])
        self.assertEqual(right[2]["rotations"]["head"][ROLL],
                         neutral[2]["rotations"]["head"][ROLL])
        self.assertEqual(left[2]["rotations"]["head"][ROLL],
                         neutral[2]["rotations"]["head"][ROLL])

    def test_head_tilt_uses_roll_not_look_yaw(self):
        neutral = build_pose_keyframes(self.performance(gestures=[]))
        tilted = build_pose_keyframes(self.performance(gestures=["head_tilt"]))
        self.assertGreater(tilted[2]["rotations"]["head"][ROLL],
                           neutral[2]["rotations"]["head"][ROLL])
        self.assertEqual(tilted[2]["rotations"]["head"][YAW],
                         neutral[2]["rotations"]["head"][YAW])

    def test_wind_sway_moves_spine_more_than_baseline(self):
        baseline = build_pose_keyframes(self.performance(gestures=[]))
        windy = build_pose_keyframes(self.performance(gestures=["wind_sway"]))
        self.assertGreater(abs(windy[1]["rotations"]["spine"][ROLL]),
                           abs(baseline[1]["rotations"]["spine"][ROLL]))

    def test_rejects_unknown_gesture_and_invalid_frames(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            build_pose_keyframes(self.performance(gestures=["execute_code"]))
        with self.assertRaisesRegex(ValueError, "ordered"):
            build_pose_keyframes(self.performance(start_frame=10, end_frame=5))

    def test_dialogue_beat_adds_keyframes_and_times_nod_to_peak(self):
        performance = self.performance(
            gestures=["nod"],
            beats=[{
                "type": "gesture", "gesture": "nod",
                "start_frame": 8, "peak_frame": 14, "end_frame": 22,
            }],
        )
        keys = build_pose_keyframes(performance)
        by_frame = {key["frame"]: key for key in keys}
        self.assertIn(14, by_frame)
        self.assertGreater(by_frame[14]["rotations"]["head"][0],
                           by_frame[8]["rotations"]["head"][0])

    def test_listener_reaction_is_subtle_and_bounded(self):
        performance = self.performance(
            action="idle", gestures=["breathe"], role="listener",
            beats=[{
                "type": "listener_reaction", "gesture": None,
                "start_frame": 20, "peak_frame": 27, "end_frame": 35,
            }],
        )
        keys = build_pose_keyframes(performance)
        peak = next(key for key in keys if key["frame"] == 27)
        self.assertGreater(peak["rotations"]["head"][0], 0)
        self.assertLess(peak["rotations"]["head"][0], 0.1)

    def test_sad_emotion_changes_resting_head_and_spine_posture(self):
        neutral = build_pose_keyframes(self.performance(emotion="neutral"))
        sad = build_pose_keyframes(self.performance(emotion="sad"))
        self.assertGreater(sad[2]["rotations"]["head"][0],
                           neutral[2]["rotations"]["head"][0])
        self.assertGreater(sad[2]["rotations"]["spine"][0],
                           neutral[2]["rotations"]["spine"][0])


if __name__ == "__main__":
    unittest.main()
