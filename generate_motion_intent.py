#!/usr/bin/env python3
"""Generate a validated Phase 6 motion-intent plan without opening Studio."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.studio import ProjectStudio  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--mode", choices=("rules", "ollama"), default="rules")
    args = parser.parse_args()
    try:
        config = load_config(args.project.resolve(), ROOT / "schemas", None)
        plan, warnings = ProjectStudio(ROOT, config, ROOT / "schemas").generate_motion_intent(
            use_ai=args.mode == "ollama"
        )
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(
        f"MOTION INTENT READY — {len(plan['shots'])} shot(s), source={plan['source']}, "
        f"warnings={len(warnings)}. Output: {config.generated_dir / 'motion_intent_plan.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
