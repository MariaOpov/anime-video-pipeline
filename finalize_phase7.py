"""Validate a Blender-created character profile and activate it locally."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.character_assets import profile_coverage, update_registry  # noqa: E402
from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.io_utils import load_json, validate  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    project = args.project.resolve()
    config = load_config(project, ROOT / "schemas", None)
    settings = config.data.get("phase7", {})
    request_path = args.request.resolve()
    try:
        request_path.relative_to(project)
    except ValueError as exc:
        raise ValueError("Phase 7 request must stay inside the project") from exc
    request = load_json(request_path)
    profile_path = Path(request["profile_path"]).resolve()
    try:
        profile_path.relative_to(project)
    except ValueError as exc:
        raise ValueError("Phase 7 profile must stay inside the project") from exc
    profile = load_json(profile_path)
    validate(profile, ROOT / "schemas" / "character_profile.schema.json", "Phase 7 character profile")
    if profile["character"] != request["character"]:
        raise ValueError("Phase 7 character identity mismatch")
    if profile["model_sha256"] != request["model_sha256"]:
        raise ValueError("Phase 7 source-model digest mismatch")
    cache = (project / profile["cache_blend"]).resolve()
    try:
        cache.relative_to(project)
    except ValueError as exc:
        raise ValueError("Phase 7 cache must stay inside the project") from exc
    if not cache.is_file() or cache.stat().st_size < 1024:
        raise ValueError(f"Phase 7 cache blend is missing or empty: {cache}")
    coverage = profile_coverage(profile)
    minimum_bones = float(settings.get("minimum_bone_alias_coverage", 1.0))
    minimum_mouth = float(settings.get("minimum_mouth_morph_coverage", 1.0))
    if float(coverage["bone_coverage"]) < minimum_bones:
        raise ValueError(
            f"Bone alias coverage {coverage['bone_coverage']:.0%} is below {minimum_bones:.0%}"
        )
    if float(coverage["mouth_morph_coverage"]) < minimum_mouth:
        raise ValueError(
            f"Mouth morph coverage {coverage['mouth_morph_coverage']:.0%} is below {minimum_mouth:.0%}"
        )
    if settings.get("require_blink_morph", True) and not coverage["blink_morph_resolved"]:
        raise ValueError("Required blink morph was not resolved")
    if settings.get("require_complete_textures", True) and profile["missing_texture_count"]:
        raise ValueError(f"Model has {profile['missing_texture_count']} missing texture(s)")
    if settings.get("require_license_metadata", False) and profile["license"]["name"].casefold() in {"", "unknown"}:
        raise ValueError("Model license metadata is required")
    registry_relative = settings.get("registry", "local_assets/character_registry.json")
    registry = update_registry(
        project, registry_relative, profile["character"],
        profile_path.relative_to(project).as_posix(),
    )
    print(
        f"PHASE 7 CHARACTER READY — {profile['character']}, "
        f"{coverage['resolved_bone_count']}/{coverage['required_bone_count']} required bones, "
        f"{coverage['resolved_mouth_morph_count']}/{coverage['required_mouth_morph_count']} mouth morphs, "
        f"blink={'yes' if coverage['blink_morph_resolved'] else 'no'}, "
        f"missing textures={profile['missing_texture_count']}. Registry: {registry}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
