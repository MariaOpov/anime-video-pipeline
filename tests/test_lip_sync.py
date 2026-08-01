import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.lip_sync import RhubarbLipSync, map_rhubarb_payload


class LipSyncTests(unittest.TestCase):
    def test_maps_rhubarb_shapes_to_mmd_mouths(self):
        payload = {"mouthCues": [
            {"start": 0.0, "end": 0.1, "value": "X"},
            {"start": 0.1, "end": 0.3, "value": "D"},
            {"start": 0.3, "end": 0.5, "value": "F"},
        ]}
        result = map_rhubarb_payload(payload)
        self.assertEqual([cue["mouth_shape"] for cue in result], ["neutral", "A", "U"])

    def test_custom_mapping_overrides_default(self):
        payload = {"mouthCues": [{"start": 0.0, "end": 0.1, "value": "D"}]}
        self.assertEqual(map_rhubarb_payload(payload, {"D": "あ"})[0]["mouth_shape"], "あ")

    def test_rejects_invalid_timing(self):
        with self.assertRaises(ValueError):
            map_rhubarb_payload({"mouthCues": [{"start": 1.0, "end": 0.5, "value": "A"}]})

    def test_installation_requires_resource_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "rhubarb.exe"
            executable.touch()
            rhubarb = RhubarbLipSync(executable)
            self.assertFalse(rhubarb.available())
            (Path(directory) / "res").mkdir()
            self.assertTrue(rhubarb.available())


if __name__ == "__main__":
    unittest.main()
