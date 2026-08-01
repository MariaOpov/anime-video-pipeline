import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.direction import (
    deterministic_blinks,
    direct_performance,
    performance_conflicts,
)
from anime_pipeline.motion_ai import RuleMotionPlanner


class PerformanceDirectorTests(unittest.TestCase):
    def setUp(self):
        self.screenplay = {
            "title": "Direction Test", "fps": 24,
            "scenes": [{
                "scene_id": "scene_001", "location": "roof",
                "time_of_day": "sunset", "mood": "neutral",
                "shots": [
                    {
                        "shot_id": "shot_001", "duration_seconds": 2.0,
                        "camera": {"shot_type": "medium", "movement": "static", "target": "Aiko"},
                        "characters": [{"name": "Aiko", "position": [0, 0, 0],
                                        "action": "idle_talking", "emotion": "neutral",
                                        "look_at": None}],
                        "dialogue": [{"character": "Aiko", "text": "Thật chứ?",
                                      "emotion": "neutral"}],
                        "description": "Dialogue",
                    },
                    {
                        "shot_id": "shot_002", "duration_seconds": 2.0,
                        "camera": {"shot_type": "medium", "movement": "static", "target": "Ren"},
                        "characters": [{"name": "Ren", "position": [0, 0, 0],
                                        "action": "idle_talking", "emotion": "neutral",
                                        "look_at": None}],
                        "dialogue": [{"character": "Ren", "text": "Thật.",
                                      "emotion": "neutral"}],
                        "description": "Dialogue",
                    },
                ],
            }],
        }
        self.timeline = {
            "lines": [
                {"shot_id": "shot_001", "character": "Aiko",
                 "start_frame": 1, "end_frame": 37},
                {"shot_id": "shot_002", "character": "Ren",
                 "start_frame": 49, "end_frame": 85},
            ]
        }
        self.frames = {
            ("scene_001", "shot_001"): (1, 48),
            ("scene_001", "shot_002"): (49, 96),
        }

    def test_rules_infer_the_other_scene_character_as_look_target(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        self.assertEqual(plan["shots"][0]["characters"][0]["look_at"], "Ren")
        self.assertEqual(plan["shots"][1]["characters"][0]["look_at"], "Aiko")

    def test_director_adds_speakers_listeners_beats_gaze_and_blinks(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        result = direct_performance(
            self.screenplay, plan, self.frames, self.timeline, "Demo", 24
        )
        self.assertEqual(len(result["clips"]), 4)
        self.assertEqual(result["dialogue_beat_count"], 2)
        self.assertEqual(result["listener_reaction_count"], 2)
        self.assertEqual(len(result["gaze_events"]), 4)
        self.assertGreater(len(result["blink_events"]), 0)
        self.assertEqual(result["performance_conflict_count"], 0)

    def test_question_and_affirmation_beats_land_at_different_times(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        result = direct_performance(
            self.screenplay, plan, self.frames, self.timeline, "Demo", 24
        )
        speakers = [clip for clip in result["clips"] if clip["role"] == "speaker"]
        tilt = next(beat for beat in speakers[0]["beats"] if beat["gesture"] == "head_tilt")
        nod = next(beat for beat in speakers[1]["beats"] if beat["gesture"] == "nod")
        tilt_progress = (tilt["peak_frame"] - 1) / 36
        nod_progress = (nod["peak_frame"] - 49) / 36
        self.assertGreater(tilt_progress, nod_progress)

    def test_blinks_are_reproducible_and_overlaps_are_detected(self):
        first = deterministic_blinks("Demo", ["Aiko", "Ren"], fps=24,
                                     frame_start=1, frame_end=240)
        second = deterministic_blinks("Demo", ["Ren", "Aiko"], fps=24,
                                      frame_start=1, frame_end=240)
        self.assertEqual(first, second)
        self.assertEqual(performance_conflicts([
            {"character": "Aiko", "start_frame": 1, "end_frame": 20},
            {"character": "Aiko", "start_frame": 15, "end_frame": 30},
        ]), 1)


if __name__ == "__main__":
    unittest.main()
