#!/usr/bin/env python3
"""Audit all production outputs and write the Phase 5 release report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.phase5 import Phase5Auditor, QualityGateError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--run-record", type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.project.resolve(), ROOT / "schemas", None)
        report, output = Phase5Auditor(config, ROOT / "schemas").run(
            blender=args.blender.resolve() if args.blender else None,
            run_record=args.run_record.resolve() if args.run_record else None,
        )
    except (OSError, ValueError, KeyError, RuntimeError, QualityGateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(
        f"PHASE 5 COMPLETE — {summary['passed_gate_count']}/{summary['quality_gate_count']} "
        f"quality gates passed, final video {summary['duration_seconds']:.3f}s, "
        f"estimated cost {summary['estimated_cost']}. Report: {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
