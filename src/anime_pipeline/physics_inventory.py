"""Pure-Python helpers for Phase 8.1 physics inventory reports."""

from __future__ import annotations

from typing import Any, Iterable


CHARACTER_COUNT_FIELDS = (
    "object_count",
    "mesh_count",
    "visible_mesh_count",
    "hidden_render_mesh_count",
    "rigid_body_count",
    "mmd_rigid_body_count",
    "blender_rigid_body_count",
    "unbuilt_rigid_body_count",
    "active_rigid_body_count",
    "passive_rigid_body_count",
    "kinematic_rigid_body_count",
    "joint_count",
    "mmd_joint_count",
    "blender_constraint_count",
    "broken_joint_reference_count",
    "cloth_modifier_count",
    "collision_modifier_count",
    "physics_object_count",
    "hidden_physics_object_count",
    "physics_collection_count",
    "collision_group_count",
)


def actual_output_dimensions(width: int, height: int, percentage: int) -> tuple[int, int]:
    """Return Blender's effective pixel dimensions for a percentage render."""
    if width <= 0 or height <= 0:
        raise ValueError("render width and height must be positive")
    if not 1 <= percentage <= 100:
        raise ValueError("resolution percentage must be between 1 and 100")
    return (
        max(1, int(width * percentage / 100)),
        max(1, int(height * percentage / 100)),
    )


def aggregate_character_inventories(
    characters: Iterable[dict[str, Any]],
    *,
    issue_count: int = 0,
    warning_count: int = 0,
) -> dict[str, int]:
    """Aggregate stable count fields without depending on Blender."""
    items = list(characters)
    summary = {"character_count": len(items)}
    for field in CHARACTER_COUNT_FIELDS:
        summary[field] = sum(int(item.get(field, 0)) for item in items)
    summary["issue_count"] = int(issue_count)
    summary["warning_count"] = int(warning_count)
    return summary


def inventory_consistency_issues(report: dict[str, Any]) -> list[str]:
    """Return logical inconsistencies not expressible conveniently in JSON Schema."""
    issues: list[str] = []
    characters = report.get("characters", [])
    summary = report.get("summary", {})
    scene = report.get("scene", {})

    expected_summary = aggregate_character_inventories(
        characters,
        issue_count=len(report.get("issues", [])),
        warning_count=len(report.get("warnings", [])),
    )
    for field, expected in expected_summary.items():
        actual = summary.get(field)
        if actual != expected:
            issues.append(f"summary.{field} expected {expected}, found {actual}")

    try:
        expected_width, expected_height = actual_output_dimensions(
            int(scene["render_width"]),
            int(scene["render_height"]),
            int(scene["resolution_percentage"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(f"invalid render dimensions: {exc}")
    else:
        if scene.get("actual_output_width") != expected_width:
            issues.append(
                "scene.actual_output_width does not match render width and percentage"
            )
        if scene.get("actual_output_height") != expected_height:
            issues.append(
                "scene.actual_output_height does not match render height and percentage"
            )

    for item in characters:
        name = item.get("character", "<unknown>")
        rigid_body_count = int(item.get("rigid_body_count", 0))
        mmd_count = int(item.get("mmd_rigid_body_count", 0))
        blender_count = int(item.get("blender_rigid_body_count", 0))
        if rigid_body_count < max(mmd_count, blender_count):
            issues.append(f"{name}: rigid_body_count is smaller than a source count")
        expected_unbuilt = sum(
            detail.get("mmd_type") == "RIGID_BODY"
            and not detail.get("blender_rigid_body_present", False)
            for detail in item.get("rigid_bodies", [])
        )
        if int(item.get("unbuilt_rigid_body_count", 0)) != expected_unbuilt:
            issues.append(f"{name}: unbuilt_rigid_body_count is inconsistent")
        if (
            int(item.get("active_rigid_body_count", 0))
            + int(item.get("passive_rigid_body_count", 0))
            != blender_count
        ):
            issues.append(f"{name}: active/passive rigid-body counts are inconsistent")

    return issues
