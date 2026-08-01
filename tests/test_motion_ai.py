import copy
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.config import ProjectConfig
from anime_pipeline.io_utils import atomic_write_json
from anime_pipeline.motion_ai import (
    OllamaMotionPlanner,
    RuleMotionPlanner,
    apply_motion_intent,
    motion_intent_warnings,
    validate_motion_intent,
)
from anime_pipeline.studio import ProjectStudio, StudioJobManager, build_job_command


class FakeResponse:
    ok = True

    def __init__(self, payload=None):
        self.payload = payload or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, generated):
        self.generated = generated
        self.request = None

    def get(self, *_args, **_kwargs):
        return FakeResponse()

    def post(self, url, json, timeout):
        self.request = {"url": url, "json": json, "timeout": timeout}
        import json as json_module
        return FakeResponse({"response": json_module.dumps(self.generated)})


class MotionAITests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.schema = self.root / "schemas" / "motion_intent.schema.json"
        self.screenplay = {
            "title": "Motion Test", "fps": 24,
            "scenes": [{
                "scene_id": "scene_001", "location": "roof", "time_of_day": "sunset",
                "mood": "sad", "shots": [{
                    "shot_id": "scene_001_shot_001", "duration_seconds": 2.0,
                    "camera": {"shot_type": "close_up", "movement": "static", "target": "Aiko"},
                    "characters": [{"name": "Aiko", "position": [0, 0, 0],
                                    "action": "sad_talking", "emotion": "sad", "look_at": "Ren"}],
                    "dialogue": [{"character": "Aiko", "text": "Xin lỗi", "emotion": "sad"}],
                    "description": "Aiko looks down",
                }],
            }],
        }

    def test_rule_plan_matches_screenplay_and_validates(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        validate_motion_intent(plan, self.screenplay, self.schema)
        intent = plan["shots"][0]["characters"][0]
        self.assertEqual(intent["action"], "sad_talking")
        self.assertIn("look_down", intent["gestures"])
        self.assertEqual(plan["source"], "rules")

    def test_rejects_stale_plan(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        changed = copy.deepcopy(self.screenplay)
        changed["scenes"][0]["shots"][0]["dialogue"][0]["text"] = "Đã thay đổi"
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_motion_intent(plan, changed, self.schema)

    def test_rejects_character_identity_change(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        plan["shots"][0]["characters"][0]["name"] = "Unknown"
        with self.assertRaisesRegex(ValueError, "character identity"):
            validate_motion_intent(plan, self.screenplay, self.schema)

    def test_applies_validated_motion_and_camera(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        plan["shots"][0]["characters"][0]["action"] = "idle_talking"
        plan["shots"][0]["camera_suggestion"] = "medium"
        validate_motion_intent(plan, self.screenplay, self.schema)
        updated = apply_motion_intent(self.screenplay, plan)
        self.assertEqual(updated["scenes"][0]["shots"][0]["characters"][0]["action"], "idle_talking")
        self.assertEqual(updated["scenes"][0]["shots"][0]["camera"]["shot_type"], "medium")
        self.assertEqual(self.screenplay["scenes"][0]["shots"][0]["camera"]["shot_type"], "close_up")

    def test_ollama_request_uses_json_schema_and_no_streaming(self):
        generated = RuleMotionPlanner().build("Demo", self.screenplay)
        generated.pop("version")
        generated.pop("source")
        generated.pop("project_name")
        generated.pop("fps")
        generated.pop("screenplay_sha256")
        session = FakeSession(generated)
        planner = OllamaMotionPlanner("http://127.0.0.1:11434", "demo", self.schema,
                                      session=session)
        plan = planner.generate("Demo", self.screenplay, ["idle", "sad_talking"])
        validate_motion_intent(plan, self.screenplay, self.schema)
        self.assertFalse(session.request["json"]["stream"])
        self.assertEqual(session.request["json"]["format"]["$schema"],
                         "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(session.request["json"]["options"]["temperature"], 0.2)

    def test_warns_when_ai_requests_unavailable_motion(self):
        plan = RuleMotionPlanner().build("Demo", self.screenplay)
        plan["shots"][0]["characters"][0]["action"] = "dramatic_spin"
        warnings = motion_intent_warnings(plan, ["idle", "sad_talking"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("dramatic_spin", warnings[0])

    def test_rules_add_dialogue_and_environment_gestures(self):
        screenplay = copy.deepcopy(self.screenplay)
        shot = screenplay["scenes"][0]["shots"][0]
        shot["characters"][0]["emotion"] = "neutral"
        shot["characters"][0]["action"] = "idle_talking"
        shot["dialogue"][0]["text"] = "Thật chứ?"
        shot["description"] = "A gentle wind crosses the rooftop"
        gestures = RuleMotionPlanner().build("Demo", screenplay)["shots"][0]["characters"][0]["gestures"]
        self.assertEqual(gestures, ["breathe", "head_tilt", "wind_sway"])

        shot["dialogue"][0]["text"] = "Thật. Chúng ta về nhà thôi."
        shot["description"] = "Dialogue"
        gestures = RuleMotionPlanner().build("Demo", screenplay)["shots"][0]["characters"][0]["gestures"]
        self.assertEqual(gestures, ["breathe", "nod"])

    def test_job_commands_are_allowlisted(self):
        command = build_job_command(self.root, self.root / "projects" / "demo",
                                    "all", "preview", False, r"D:\Blender\blender.exe")
        self.assertEqual(command[0], "powershell.exe")
        self.assertIn("-Render", command)
        self.assertNotIn("-Fresh", command)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            build_job_command(self.root, self.root, "arbitrary", "preview", False, "blender")

    def test_job_manager_captures_output(self):
        manager = StudioJobManager()
        manager.start("test", [sys.executable, "-c", "print('studio-ok')"], self.root)
        deadline = time.time() + 5
        while time.time() < deadline and manager.snapshot()["status"] == "running":
            time.sleep(0.01)
        snapshot = manager.snapshot()
        self.assertEqual(snapshot["status"], "complete")
        self.assertIn("studio-ok", snapshot["lines"])

    def test_project_studio_writes_utf8_script_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project.mkdir(exist_ok=True)
            (project / "script.txt").write_text("Old", encoding="utf-8")
            config = ProjectConfig(project, {
                "project_name": "Studio", "script": "script.txt",
                "output": {"width": 640, "height": 360, "fps": 24},
                "phase6": {"enabled": True, "max_script_characters": 100},
            })
            studio = ProjectStudio(self.root, config, self.root / "schemas")
            studio.write_script("Aiko: Xin chào\r\nRen: Chào cậu")
            self.assertEqual(studio.read_script(), "Aiko: Xin chào\nRen: Chào cậu")
            with self.assertRaisesRegex(ValueError, "empty"):
                studio.write_script("  ")


if __name__ == "__main__":
    unittest.main()
