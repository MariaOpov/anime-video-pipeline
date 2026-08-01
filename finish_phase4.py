#!/usr/bin/env python3
"""Create subtitles, normalize audio, and export the final Phase 4 MP4."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.phase4 import Phase4Runner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.project.resolve(), ROOT / "schemas", None)
        summary = Phase4Runner(config, ROOT / "schemas").run(dry_run=args.dry_run)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    prefix = "DRY RUN PHASE 4 OK" if args.dry_run else "PHASE 4 COMPLETE"
    print(f"{prefix} — {summary} Outputs: {config.project_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
