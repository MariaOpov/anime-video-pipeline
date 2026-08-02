#!/usr/bin/env python3
"""Validate Phase 1–2 outputs and prepare the Blender Phase 3 manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.phase3 import Phase3Planner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.project.resolve(), ROOT / "schemas", None)
        planner = Phase3Planner(config, ROOT / "schemas")
        manifest = planner.build()
        output = planner.write(manifest)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = manifest["summary"]
    print(
        f"PHASE 3 MANIFEST READY — {summary['shot_count']} shot(s), "
        f"{summary['dialogue_count']} dialogue strip(s), "
        f"{summary['mouth_cue_count']} mouth cue(s), "
        f"{summary['performance_clip_count']} performance clip(s), "
        f"{summary['gesture_count']} gesture(s), "
        f"{summary['dialogue_beat_count']} dialogue beat(s), "
        f"{summary['gaze_target_count']} gaze target(s), "
        f"{summary['blink_event_count']} blink(s), "
        f"{summary['listener_reaction_count']} listener reaction(s), "
        f"{summary['blocking_shot_count']} blocking shot(s), "
        f"{summary['character_placement_count']} placement(s), "
        f"{summary['camera_motion_count']} camera move(s), "
        f"{summary['framing_risk_count']} framing risk(s), "
        f"{summary['character_asset_ready_count']}/{summary['production_character_count']} "
        f"production character(s) ready. Output: {output}"
        f" Phase 8: {summary['harmonization_ready_count']}/"
        f"{summary['harmonization_character_count']} character(s) planned, "
        f"{summary['adaptive_camera_shot_count']} adaptive camera shot(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
