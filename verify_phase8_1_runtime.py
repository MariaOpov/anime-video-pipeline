#!/usr/bin/env python3
"""Validate the Phase 8.1 runtime-physics report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.io_utils import validate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.input.resolve().open("r", encoding="utf-8-sig") as handle:
            report = json.load(handle)
        validate(
            report,
            ROOT / "schemas" / "phase8_1_physics_report.schema.json",
            "Phase 8.1 runtime physics report",
        )
        if report["enabled"]:
            if report["status"] != "complete":
                raise ValueError("enabled Phase 8.1 physics did not complete")
            if report["issues"]:
                raise ValueError("Phase 8.1 runtime report contains issues")
            if not report["render_timing_preserved"]:
                raise ValueError("render timing was not preserved")
            if not report["rigid_body_world_present"]:
                raise ValueError("Rigid Body World is missing")
            if not report["rigid_body_world_enabled"]:
                raise ValueError("Rigid Body World is disabled")
            if report["rigid_body_count"] <= 0 or report["constraint_count"] <= 0:
                raise ValueError("physics objects are missing")
            expected = report["warmup_frames"] + 1
            if report["warmup_evaluated_frame_count"] != expected:
                raise ValueError(
                    "warm-up evaluation count does not include the render start frame"
                )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        "PHASE 8.1 RUNTIME VERIFIED — "
        f"world={report['rigid_body_world_present']}/{report['rigid_body_world_enabled']}, "
        f"bodies={report['rigid_body_count']}, constraints={report['constraint_count']}, "
        f"warmup={report['simulation_frame_start']}..{report['render_frame_start']}, "
        f"render={report['render_frame_start']}..{report['render_frame_end']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
