import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.phase4 import build_ffmpeg_command, build_srt, srt_timestamp


class Phase4Tests(unittest.TestCase):
    def test_formats_srt_timestamp(self):
        self.assertEqual(srt_timestamp(0), "00:00:00,000")
        self.assertEqual(srt_timestamp(3661.234), "01:01:01,234")

    def test_rejects_negative_srt_timestamp(self):
        with self.assertRaises(ValueError):
            srt_timestamp(-0.1)

    def test_builds_utf8_vietnamese_srt(self):
        timeline = {"lines": [{
            "line_id": "line_001", "character": "Aiko",
            "text": "Mình sẽ quay lại.", "start_seconds": 1.0, "end_seconds": 2.25,
        }]}
        result = build_srt(timeline, include_speaker_names=True)
        self.assertIn("00:00:01,000 --> 00:00:02,250", result)
        self.assertIn("Aiko: Mình sẽ quay lại.", result)

    def test_burn_command_reencodes_video_and_normalizes_audio(self):
        command = build_ffmpeg_command(
            "ffmpeg", input_video="renders/input.mp4", subtitle_file="subtitles/vi.srt",
            output_video="output/final.mp4", settings={}, subtitle_mode="burn",
        )
        self.assertIn("libx264", command)
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", command)
        self.assertTrue(any(value.startswith("subtitles=") for value in command))

    def test_soft_command_copies_video_and_adds_mov_text(self):
        command = build_ffmpeg_command(
            "ffmpeg", input_video="renders/input.mp4", subtitle_file="subtitles/vi.srt",
            output_video="output/final.mp4", settings={}, subtitle_mode="soft",
        )
        self.assertIn("copy", command)
        self.assertIn("mov_text", command)
        self.assertIn("language=vie", command)


if __name__ == "__main__":
    unittest.main()
