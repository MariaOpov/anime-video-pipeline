#!/usr/bin/env python3
"""Validate a Phase 8.1 read-only physics inventory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.io_utils import load_json, validate  # noqa: E402
from anime_pipeline.physics_inventory import inventory_consistency_issues  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    path = args.input.resolve()
    try:
        report = load_json(path)
        validate(
            report,
            ROOT / "schemas" / "phase8_1_physics_inventory.schema.json",
            "Phase 8.1 physics inventory",
        )
        issues = inventory_consistency_issues(report)
        if issues:
            raise ValueError("; ".join(issues))
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(
        "PHASE 8.1 INVENTORY VERIFIED — "
        f"{summary['character_count']} character(s), "
        f"{summary['rigid_body_count']} rigid body object(s), "
        f"{summary['blender_rigid_body_count']} built, "
        f"{summary['unbuilt_rigid_body_count']} unbuilt, "
        f"{summary['joint_count']} joint object(s), "
        f"{summary['cloth_modifier_count']} cloth modifier(s), "
        f"{summary['collision_modifier_count']} collision modifier(s), "
        f"{summary['issue_count']} issue(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
