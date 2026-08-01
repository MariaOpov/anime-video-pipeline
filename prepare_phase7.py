"""Stage an immutable MMD bundle and write a Blender onboarding request."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.character_assets import safe_slug, stage_source_bundle  # noqa: E402
from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.io_utils import atomic_write_json  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--character", required=True)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--creator", default="Unknown")
    parser.add_argument("--source", default="Unknown")
    parser.add_argument("--license-name", default="Unknown")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    project = args.project.resolve()
    config = load_config(project, ROOT / "schemas", None)
    if args.character not in config.data.get("characters", {}):
        raise ValueError(f"Unknown project character: {args.character}")
    settings = config.data.get("phase7", {})
    if not settings.get("enabled", False):
        raise ValueError("Phase 7 is disabled in project.yaml")
    slug = safe_slug(args.character)
    asset_root = (project / settings.get("local_asset_dir", "local_assets/characters") / slug).resolve()
    try:
        asset_root.relative_to(project)
    except ValueError as exc:
        raise ValueError("Phase 7 local asset directory must stay inside the project") from exc
    staged_model, inspection = stage_source_bundle(args.model, asset_root)
    cache_dir = (project / settings.get("cache_dir", "blender_cache/characters")).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    profile_path = asset_root / "character.profile.json"
    cache_path = cache_dir / f"{slug}.blend"
    request = {
        "schema_version": 1,
        "project": str(project),
        "character": args.character,
        "source_model": str(staged_model),
        "source_model_relative": staged_model.relative_to(project).as_posix(),
        "model_format": inspection["format"],
        "model_sha256": inspection["model_sha256"],
        "discovered_texture_count": inspection["discovered_texture_count"],
        "profile_path": str(profile_path),
        "profile_relative": profile_path.relative_to(project).as_posix(),
        "cache_path": str(cache_path),
        "cache_relative": cache_path.relative_to(project).as_posix(),
        "cache_collection": f"PIPE_CHARACTER_{slug.upper().replace('-', '_')}",
        "target_height_meters": float(settings.get("target_height_meters", 1.72)),
        "rotation_z_degrees": float(settings.get("rotation_z_degrees", 0.0)),
        "license": {
            "name": args.license_name.strip(),
            "creator": args.creator.strip(),
            "source": args.source.strip(),
        },
    }
    request_path = args.request.resolve()
    try:
        request_path.relative_to(project)
    except ValueError as exc:
        raise ValueError("Phase 7 request must stay inside the project") from exc
    atomic_write_json(request_path, request)
    print(
        f"PHASE 7 REQUEST READY — {args.character}, {inspection['format'].upper()}, "
        f"{inspection['discovered_texture_count']} discovered texture(s). Request: {request_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
