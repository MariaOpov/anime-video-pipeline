"""Pure-Python Phase 8.1 runtime physics planning helpers."""

from __future__ import annotations

from typing import Any


def _normalise_collider_overrides(values: Any) -> dict[str, list[dict[str, Any]]]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("phase8_1.collider_overrides must be an object")

    normalised: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()

    for raw_character, raw_entries in values.items():
        character = str(raw_character).strip()
        if not character:
            raise ValueError(
                "phase8_1.collider_overrides character names must not be empty"
            )
        if not isinstance(raw_entries, list):
            raise ValueError(
                f"phase8_1.collider_overrides.{character} must be an array"
            )

        entries: list[dict[str, Any]] = []
        for index, raw_entry in enumerate(raw_entries):
            if not isinstance(raw_entry, dict):
                raise ValueError(
                    f"phase8_1.collider_overrides.{character}[{index}] "
                    "must be an object"
                )

            object_name = str(raw_entry.get("object", "")).strip()
            if not object_name:
                raise ValueError(
                    f"phase8_1.collider_overrides.{character}[{index}].object "
                    "must not be empty"
                )

            radial_scale = float(raw_entry.get("radial_scale", 1.0))
            length_scale = float(raw_entry.get("length_scale", 1.0))
            if not 1.0 <= radial_scale <= 2.0:
                raise ValueError(
                    f"phase8_1.collider_overrides.{character}[{index}]."
                    "radial_scale must be between 1.0 and 2.0"
                )
            if not 1.0 <= length_scale <= 2.0:
                raise ValueError(
                    f"phase8_1.collider_overrides.{character}[{index}]."
                    "length_scale must be between 1.0 and 2.0"
                )

            identity = (character.casefold(), object_name)
            if identity in seen:
                raise ValueError(
                    f"duplicate Phase 8.1 collider override for "
                    f"{character}/{object_name}"
                )
            seen.add(identity)

            entries.append({
                "object": object_name,
                "radial_scale": radial_scale,
                "length_scale": length_scale,
            })

        normalised[character] = entries

    return normalised


def build_physics_contract(
    settings: dict[str, Any] | None,
    *,
    frame_start: int,
    frame_end: int,
) -> dict[str, Any]:
    """Build and validate the Blender runtime-physics manifest contract."""
    if frame_start < 1 or frame_end < frame_start:
        raise ValueError("invalid render frame range for Phase 8.1 physics")

    values = settings or {}
    warmup_frames = int(values.get("warmup_frames", 36))
    if not 0 <= warmup_frames <= 240:
        raise ValueError("phase8_1.warmup_frames must be between 0 and 240")

    substeps = int(values.get("substeps_per_frame", 10))
    if not 1 <= substeps <= 100:
        raise ValueError("phase8_1.substeps_per_frame must be between 1 and 100")

    solver_iterations = int(values.get("solver_iterations", 10))
    if not 1 <= solver_iterations <= 1000:
        raise ValueError("phase8_1.solver_iterations must be between 1 and 1000")

    report = str(values.get("report", "generated/phase8_1_physics_report.json"))
    body_collection = str(
        values.get("rigid_body_collection", "PIPE_Phase8_1_RigidBodies")
    )
    constraint_collection = str(
        values.get("constraint_collection", "PIPE_Phase8_1_Constraints")
    )
    for label, value in (
        ("report", report),
        ("rigid_body_collection", body_collection),
        ("constraint_collection", constraint_collection),
    ):
        if not value.strip():
            raise ValueError(f"phase8_1.{label} must not be empty")

    collider_overrides = _normalise_collider_overrides(
        values.get("collider_overrides", {})
    )

    return {
        "version": 1,
        "enabled": bool(values.get("enabled", False)),
        "report": report,
        "render_frame_start": int(frame_start),
        "render_frame_end": int(frame_end),
        "warmup_frames": warmup_frames,
        "simulation_frame_start": int(frame_start) - warmup_frames,
        "simulation_frame_end": int(frame_end),
        "rigid_body_collection": body_collection,
        "constraint_collection": constraint_collection,
        "substeps_per_frame": substeps,
        "solver_iterations": solver_iterations,
        "collider_overrides": collider_overrides,
    }
