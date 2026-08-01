#!/usr/bin/env python3
"""CLI entry point for the anime video production pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.pipeline import Pipeline, PipelineError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an anime project from local assets.")
    parser.add_argument("--project", required=True, type=Path, help="Project directory")
    parser.add_argument("--preset", choices=("preview", "balanced", "final"))
    parser.add_argument("--phase", type=int, choices=(1, 2), default=1,
                        help="Highest pipeline phase to execute (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan only")
    parser.add_argument("--resume", action="store_true", help="Skip completed valid stages")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = Pipeline(
            project_dir=args.project.resolve(),
            preset_override=args.preset,
            dry_run=args.dry_run,
            resume=args.resume,
            verbose=args.verbose,
            phase=args.phase,
        ).run()
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
