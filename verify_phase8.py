#!/usr/bin/env python3
"""Validate the Phase 8 runtime report without requiring a Phase 4 delivery."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.io_utils import load_json, validate  # noqa: E402


def verify(project: Path, schemas: Path) -> dict:
    project = project.resolve()
    manifest = load_json(project / "generated" / "phase3_manifest.json")
    validate(manifest, schemas / "phase3_manifest.schema.json", "Phase 3 manifest")
    relative = manifest["harmonization"]["report"]
    report_path = (project / relative).resolve()
    try:
        report_path.relative_to(project)
    except ValueError as exc:
        raise ValueError("Phase 8 report path escaped the project directory") from exc
    report = load_json(report_path)
    validate(
        report, schemas / "phase8_harmonization_report.schema.json",
        "Phase 8 harmonization report",
    )
    if report["project_name"] != manifest["project_name"]:
        raise ValueError("Phase 8 project identity does not match the manifest")
    if report["frame_start"] != manifest["frame_start"] or report["frame_end"] != manifest["frame_end"]:
        raise ValueError("Phase 8 frame range does not match the manifest")
    summary = report["summary"]
    if report["status"] != "complete" or int(summary["issue_count"]) != 0:
        raise ValueError(
            f"Phase 8 is not production-ready: {summary['issue_count']} issue(s)"
        )
    if int(summary["ready_character_count"]) != int(summary["character_count"]):
        raise ValueError("Phase 8 did not harmonize every configured character")
    if int(summary["framing_passed_shot_count"]) != int(summary["adaptive_camera_shot_count"]):
        raise ValueError("Phase 8 did not frame every shot safely")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.project, ROOT / "schemas")
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(
        f"PHASE 8 VERIFIED — {summary['ready_character_count']}/"
        f"{summary['character_count']} character(s), "
        f"{summary['framing_passed_shot_count']}/"
        f"{summary['adaptive_camera_shot_count']} shot(s) framed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
