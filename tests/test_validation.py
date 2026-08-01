import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.io_utils import validate


class ValidationTests(unittest.TestCase):
    def test_malformed_screenplay_is_rejected(self):
        schema = Path(__file__).resolve().parents[1] / "schemas" / "screenplay.schema.json"
        with self.assertRaises(ValueError):
            validate({"title": "Broken", "fps": 24, "scenes": []}, schema, "test screenplay")


if __name__ == "__main__":
    unittest.main()

