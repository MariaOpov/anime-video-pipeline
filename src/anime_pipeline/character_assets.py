"""Production character registry, rig aliases, and profile validation helpers."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_json, load_json, validate


MODEL_EXTENSIONS = {".pmx", ".pmd"}
TEXTURE_EXTENSIONS = {
    ".png", ".bmp", ".jpg", ".jpeg", ".tga", ".webp", ".dds", ".spa", ".sph",
}

BONE_ALIASES: dict[str, tuple[str, ...]] = {
    "spine": ("上半身2", "上半身", "spine", "upper_body", "upper body"),
    "head": ("頭", "head"),
    "arm.L": ("左腕", "腕.L", "arm.L", "upper_arm.L", "left arm"),
    "arm.R": ("右腕", "腕.R", "arm.R", "upper_arm.R", "right arm"),
    "leg.L": ("左足", "足.L", "leg.L", "thigh.L", "left leg"),
    "leg.R": ("右足", "足.R", "leg.R", "thigh.R", "right leg"),
    "eyes": ("両目", "目", "eyes", "eye"),
}
REQUIRED_BONE_ALIASES = ("spine", "head", "arm.L", "arm.R", "leg.L", "leg.R")

MORPH_ALIASES: dict[str, tuple[str, ...]] = {
    "A": ("あ", "a", "mouth_a", "aa"),
    "I": ("い", "i", "mouth_i", "ih"),
    "U": ("う", "u", "mouth_u", "ou"),
    "E": ("え", "e", "mouth_e", "eh"),
    "O": ("お", "o", "mouth_o", "oh"),
    "blink": ("まばたき", "blink", "eye_blink", "eyeblink"),
}
REQUIRED_MOUTH_MORPHS = ("A", "I", "U", "E", "O")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        slug = f"character-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:10]}"
    return slug


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fold(value: str) -> str:
    return re.sub(r"[\s_.-]+", "", value.casefold())


def match_aliases(names: list[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, str | None]:
    """Resolve application-owned aliases using exact, then normalized matches."""
    exact = {name.casefold(): name for name in names}
    folded = {_fold(name): name for name in names}
    result: dict[str, str | None] = {}
    for alias, candidates in aliases.items():
        match = next((exact[candidate.casefold()] for candidate in candidates
                      if candidate.casefold() in exact), None)
        if match is None:
            match = next((folded[_fold(candidate)] for candidate in candidates
                          if _fold(candidate) in folded), None)
        result[alias] = match
    return result


def inspect_source_bundle(model: Path) -> dict[str, Any]:
    model = model.resolve()
    if not model.is_file() or model.suffix.casefold() not in MODEL_EXTENSIONS:
        raise ValueError("model must be an existing .pmx or .pmd file")
    bundle = model.parent
    textures = sorted(
        path for path in bundle.rglob("*")
        if path.is_file() and path.suffix.casefold() in TEXTURE_EXTENSIONS
    )
    return {
        "model": model,
        "bundle": bundle,
        "format": model.suffix.casefold().lstrip("."),
        "model_sha256": file_sha256(model),
        "discovered_texture_count": len(textures),
        "discovered_textures": [path.relative_to(bundle).as_posix() for path in textures],
    }


def _same_file_contents(source: Path, destination: Path) -> bool:
    if not destination.is_file() or source.stat().st_size != destination.stat().st_size:
        return False
    return file_sha256(source) == file_sha256(destination)


def _copy_bundle_file(source: str, destination: str) -> str:
    """Copy one bundle file while leaving an identical staged file untouched."""
    source_path = Path(source)
    destination_path = Path(destination)
    if _same_file_contents(source_path, destination_path):
        return str(destination_path)
    if destination_path.exists():
        destination_path.chmod(destination_path.stat().st_mode | 0o200)
    return shutil.copy2(source_path, destination_path)


def stage_source_bundle(model: Path, destination_root: Path) -> tuple[Path, dict[str, Any]]:
    """Copy an entire immutable PMX bundle into a content-addressed local directory."""
    inspection = inspect_source_bundle(model)
    bundle_id = inspection["model_sha256"][:12]
    destination = destination_root / "bundles" / bundle_id
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        inspection["bundle"], destination, dirs_exist_ok=True,
        copy_function=_copy_bundle_file,
    )
    staged_model = destination / model.resolve().relative_to(inspection["bundle"])
    if not staged_model.is_file():
        raise ValueError(f"staged model is missing: {staged_model}")
    return staged_model, inspection


def profile_coverage(profile: dict[str, Any]) -> dict[str, float | int | bool]:
    bone_mapping = profile.get("bone_mapping", {})
    morph_mapping = profile.get("morph_mapping", {})
    resolved_bones = sum(bool(bone_mapping.get(alias)) for alias in REQUIRED_BONE_ALIASES)
    resolved_mouth = sum(bool(morph_mapping.get(alias)) for alias in REQUIRED_MOUTH_MORPHS)
    return {
        "required_bone_count": len(REQUIRED_BONE_ALIASES),
        "resolved_bone_count": resolved_bones,
        "bone_coverage": round(resolved_bones / len(REQUIRED_BONE_ALIASES), 4),
        "required_mouth_morph_count": len(REQUIRED_MOUTH_MORPHS),
        "resolved_mouth_morph_count": resolved_mouth,
        "mouth_morph_coverage": round(resolved_mouth / len(REQUIRED_MOUTH_MORPHS), 4),
        "blink_morph_resolved": bool(morph_mapping.get("blink")),
    }


def load_registry(project: Path, relative: str) -> dict[str, Any]:
    path = (project / relative).resolve()
    try:
        path.relative_to(project.resolve())
    except ValueError as exc:
        raise ValueError("Phase 7 registry must stay inside the project directory") from exc
    if not path.is_file():
        return {"schema_version": 1, "characters": {}}
    registry = load_json(path)
    if registry.get("schema_version") != 1 or not isinstance(registry.get("characters"), dict):
        raise ValueError("invalid Phase 7 character registry")
    return registry


def update_registry(project: Path, relative: str, character: str, profile_relative: str) -> Path:
    registry = load_registry(project, relative)
    registry["characters"][character] = {"enabled": True, "profile": profile_relative}
    path = (project / relative).resolve()
    atomic_write_json(path, registry)
    return path


def build_character_contract(project: Path, settings: dict[str, Any], schemas: Path) -> dict[str, Any]:
    enabled = bool(settings.get("enabled", False))
    result: dict[str, Any] = {
        "enabled": enabled, "characters": [], "configured_count": 0,
        "ready_count": 0, "missing_texture_count": 0,
        "warning_count": 0, "license_warning_count": 0,
    }
    if not enabled:
        return result
    registry = load_registry(project, settings.get("registry", "local_assets/character_registry.json"))
    minimum_bones = float(settings.get("minimum_bone_alias_coverage", 1.0))
    minimum_mouth = float(settings.get("minimum_mouth_morph_coverage", 1.0))
    require_blink = bool(settings.get("require_blink_morph", True))
    require_textures = bool(settings.get("require_complete_textures", True))
    require_license = bool(settings.get("require_license_metadata", False))
    for character, entry in registry["characters"].items():
        if not entry.get("enabled", True):
            continue
        result["configured_count"] += 1
        profile_path = (project / entry["profile"]).resolve()
        try:
            profile_path.relative_to(project.resolve())
        except ValueError as exc:
            raise ValueError("Phase 7 profile must stay inside the project directory") from exc
        profile = load_json(profile_path)
        validate(profile, schemas / "character_profile.schema.json", f"character profile {character}")
        if profile["character"] != character:
            raise ValueError(f"character profile identity mismatch: {character}")
        coverage = profile_coverage(profile)
        cache = (project / profile["cache_blend"]).resolve()
        try:
            cache.relative_to(project.resolve())
        except ValueError as exc:
            raise ValueError("Phase 7 cache must stay inside the project directory") from exc
        missing_textures = int(profile["missing_texture_count"])
        license_unknown = profile["license"]["name"].casefold() in {"", "unknown"}
        ready = (
            cache.is_file()
            and float(coverage["bone_coverage"]) >= minimum_bones
            and float(coverage["mouth_morph_coverage"]) >= minimum_mouth
            and (not require_blink or bool(coverage["blink_morph_resolved"]))
            and (not require_textures or missing_textures == 0)
            and (not require_license or not license_unknown)
        )
        warnings = list(profile.get("warnings", []))
        result["characters"].append({
            "character": character, "profile": entry["profile"],
            "cache_blend": profile["cache_blend"],
            "cache_collection": profile["cache_collection"],
            "armature_object": profile["armature_object"],
            "model_sha256": profile["model_sha256"],
            "bone_mapping": profile["bone_mapping"],
            "morph_mapping": profile["morph_mapping"],
            **coverage, "texture_count": int(profile["texture_count"]),
            "missing_texture_count": missing_textures,
            "license_name": profile["license"]["name"],
            "license_warning": license_unknown, "warnings": warnings,
            "ready": ready,
        })
        result["ready_count"] += ready
        result["missing_texture_count"] += missing_textures
        result["warning_count"] += len(warnings)
        result["license_warning_count"] += license_unknown
    return result
