import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.screenplay import RuleBasedAnalyzer


class ScreenplayTests(unittest.TestCase):
    def test_dialogue_becomes_valid_structure(self):
        result = RuleBasedAnalyzer(24, 30).analyze("Demo", "[Roof]\nAiko: I am sad.\nRen: Hello.")
        self.assertEqual(result["fps"], 24)
        self.assertEqual(len(result["scenes"]), 1)
        self.assertEqual(len(result["scenes"][0]["shots"]), 2)
        self.assertEqual(result["scenes"][0]["shots"][0]["dialogue"][0]["character"], "Aiko")

    def test_duration_is_capped(self):
        script = "\n".join(f"Aiko: This is dialogue line number {i}." for i in range(30))
        result = RuleBasedAnalyzer(24, 10).analyze("Demo", script)
        duration = sum(s["duration_seconds"] for scene in result["scenes"] for s in scene["shots"])
        self.assertLessEqual(duration, 10)


if __name__ == "__main__":
    unittest.main()

