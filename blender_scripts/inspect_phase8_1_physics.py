"""Read-only Blender inventory for Phase 8.1 character physics.

The script writes JSON diagnostics only. It does not build/clean MMD physics,
change frames, bake caches, save the current .blend, or render.

Example:
    blender --background ren.blend --python blender_scripts/inspect_phase8_1_physics.py -- \
        --project projects/demo --source-kind character_cache --character Ren \
        --output generated/phase8_1_ren_cache_inventory.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.physics_inventory import (  # noqa: E402
    actual_output_dimensions,
    aggregate_character_inventories,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument(
        "--source-kind",
        required=True,
        choices=("character_cache", "assembled_scene"),
    )
    parser.add_argument("--character", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def safe_attr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name)
    except (AttributeError, ReferenceError, RuntimeError):
        return default


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        return list(value)
    except (TypeError, ValueError):
        return str(value)


def mmd_type(obj: Any) -> str | None:
    value = safe_attr(obj, "mmd_type")
    if value:
        return str(value)
    try:
        value = obj.get("mmd_type")
    except (AttributeError, ReferenceError, RuntimeError):
        value = None
    return str(value) if value else None


def collection_objects(collection: Any) -> set[Any]:
    objects = set(collection.objects)
    for child in collection.children:
        objects.update(collection_objects(child))
    return objects


def descendants(root: Any) -> set[Any]:
    result = {root}
    pending = list(root.children)
    while pending:
        child = pending.pop()
        if child in result:
            continue
        result.add(child)
        pending.extend(child.children)
    return result


def profile_contracts(project: Path, requested: list[str]) -> list[dict[str, Any]]:
    registry_path = project / "local_assets" / "character_registry.json"
    registry = load_json(registry_path)
    configured = registry.get("characters", {})
    names = requested or [
        name for name, item in configured.items() if item.get("enabled", False)
    ]
    contracts = []
    for name in names:
        item = configured.get(name)
        if not item or not item.get("enabled", False):
            raise RuntimeError(f"Character is not enabled in registry: {name}")
        profile_path = (project / item["profile"]).resolve()
        try:
            profile_path.relative_to(project)
        except ValueError as exc:
            raise RuntimeError(f"Character profile escaped project: {name}") from exc
        profile = load_json(profile_path)
        if profile.get("character") != name:
            raise RuntimeError(f"Character profile identity mismatch: {name}")
        contracts.append(profile)
    return contracts


def character_objects(profile: dict[str, Any], source_kind: str) -> tuple[set[Any], str | None]:
    collection_name = str(profile["cache_collection"])
    collection = bpy.data.collections.get(collection_name)
    if collection:
        return collection_objects(collection), collection_name

    armature = bpy.data.objects.get(str(profile["armature_object"]))
    if not armature:
        armature = next(
            (
                obj
                for obj in bpy.data.objects
                if obj.type == "ARMATURE"
                and obj.get("pipeline_character") == profile["character"]
            ),
            None,
        )
    if armature:
        owned = descendants(armature)
        for obj in bpy.data.objects:
            if obj.type == "MESH" and any(
                modifier.type == "ARMATURE" and modifier.object == armature
                for modifier in obj.modifiers
            ):
                owned.add(obj)
        return owned, None

    if source_kind == "character_cache":
        return set(bpy.data.objects), None
    return set(), None


def point_cache_payload(cache: Any) -> dict[str, Any] | None:
    if cache is None:
        return None
    return {
        "frame_start": safe_attr(cache, "frame_start"),
        "frame_end": safe_attr(cache, "frame_end"),
        "frame_step": safe_attr(cache, "frame_step"),
        "is_baked": safe_attr(cache, "is_baked"),
        "is_baking": safe_attr(cache, "is_baking"),
        "is_outdated": safe_attr(cache, "is_outdated"),
        "use_disk_cache": safe_attr(cache, "use_disk_cache"),
        "use_library_path": safe_attr(cache, "use_library_path"),
        "compression": json_value(safe_attr(cache, "compression")),
        "name": safe_attr(cache, "name"),
        "index": safe_attr(cache, "index"),
    }


def rigid_body_world_payload(scene: Any) -> dict[str, Any]:
    world = safe_attr(scene, "rigidbody_world")
    if world is None:
        return {
            "present": False,
            "enabled": None,
            "collection": None,
            "constraint_collection": None,
            "substeps_per_frame": None,
            "solver_iterations": None,
            "time_scale": None,
            "use_split_impulse": None,
            "point_cache": None,
        }
    collection = safe_attr(world, "collection")
    constraints = safe_attr(world, "constraints")
    return {
        "present": True,
        "enabled": safe_attr(world, "enabled"),
        "collection": safe_attr(collection, "name"),
        "constraint_collection": safe_attr(constraints, "name"),
        "substeps_per_frame": safe_attr(world, "substeps_per_frame"),
        "solver_iterations": safe_attr(world, "solver_iterations"),
        "time_scale": safe_attr(world, "time_scale"),
        "use_split_impulse": safe_attr(world, "use_split_impulse"),
        "point_cache": point_cache_payload(safe_attr(world, "point_cache")),
    }


def mmd_rigid_payload(obj: Any) -> dict[str, Any]:
    data = safe_attr(obj, "mmd_rigid")
    if data is None:
        return {
            "type": None,
            "shape": None,
            "bone": None,
            "collision_group_number": None,
            "collision_group_mask": None,
        }
    return {
        "type": json_value(safe_attr(data, "type")),
        "shape": json_value(safe_attr(data, "shape")),
        "bone": safe_attr(data, "bone"),
        "collision_group_number": safe_attr(data, "collision_group_number"),
        "collision_group_mask": json_value(safe_attr(data, "collision_group_mask")),
    }


def rigid_body_payload(obj: Any) -> dict[str, Any]:
    body = safe_attr(obj, "rigid_body")
    mmd = mmd_rigid_payload(obj)
    return {
        "object": obj.name,
        "mmd_type": mmd_type(obj),
        "hide_render": bool(obj.hide_render),
        "hide_viewport": bool(obj.hide_viewport),
        "blender_rigid_body_present": body is not None,
        "blender_type": json_value(safe_attr(body, "type")),
        "kinematic": safe_attr(body, "kinematic"),
        "collision_shape": json_value(safe_attr(body, "collision_shape")),
        "collision_margin": safe_attr(body, "collision_margin"),
        "use_margin": safe_attr(body, "use_margin"),
        "collision_collections": json_value(safe_attr(body, "collision_collections")),
        "mass": safe_attr(body, "mass"),
        "friction": safe_attr(body, "friction"),
        "restitution": safe_attr(body, "restitution"),
        "linear_damping": safe_attr(body, "linear_damping"),
        "angular_damping": safe_attr(body, "angular_damping"),
        "use_deactivation": safe_attr(body, "use_deactivation"),
        "use_start_deactivated": safe_attr(body, "use_start_deactivated"),
        "mmd_rigid_type": mmd["type"],
        "mmd_shape": mmd["shape"],
        "mmd_bone": mmd["bone"],
        "mmd_collision_group_number": mmd["collision_group_number"],
        "mmd_collision_group_mask": mmd["collision_group_mask"],
        "collections": sorted(collection.name for collection in obj.users_collection),
    }


def joint_payload(obj: Any) -> dict[str, Any]:
    constraint = safe_attr(obj, "rigid_body_constraint")
    object1 = safe_attr(constraint, "object1")
    object2 = safe_attr(constraint, "object2")
    return {
        "object": obj.name,
        "mmd_type": mmd_type(obj),
        "hide_render": bool(obj.hide_render),
        "blender_constraint_present": constraint is not None,
        "constraint_type": json_value(safe_attr(constraint, "type")),
        "enabled": safe_attr(constraint, "enabled"),
        "disable_collisions": safe_attr(constraint, "disable_collisions"),
        "object1": safe_attr(object1, "name"),
        "object2": safe_attr(object2, "name"),
        "use_breaking": safe_attr(constraint, "use_breaking"),
        "breaking_threshold": safe_attr(constraint, "breaking_threshold"),
        "solver_iterations": safe_attr(constraint, "solver_iterations"),
        "collections": sorted(collection.name for collection in obj.users_collection),
    }


def modifier_payload(obj: Any, modifier: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "object": obj.name,
        "modifier": modifier.name,
        "type": modifier.type,
        "show_viewport": bool(modifier.show_viewport),
        "show_render": bool(modifier.show_render),
        "point_cache": None,
        "settings": {},
    }
    if modifier.type == "CLOTH":
        settings = safe_attr(modifier, "settings")
        collision = safe_attr(modifier, "collision_settings")
        payload["point_cache"] = point_cache_payload(safe_attr(modifier, "point_cache"))
        payload["settings"] = {
            "quality": safe_attr(settings, "quality"),
            "time_scale": safe_attr(settings, "time_scale"),
            "mass": safe_attr(settings, "mass"),
            "air_damping": safe_attr(settings, "air_damping"),
            "use_collision": safe_attr(collision, "use_collision"),
            "collision_quality": safe_attr(collision, "collision_quality"),
            "distance_min": safe_attr(collision, "distance_min"),
            "use_self_collision": safe_attr(collision, "use_self_collision"),
            "self_distance_min": safe_attr(collision, "self_distance_min"),
            "self_friction": safe_attr(collision, "self_friction"),
        }
    elif modifier.type == "COLLISION":
        settings = safe_attr(modifier, "settings")
        payload["settings"] = {
            "damping": safe_attr(settings, "damping"),
            "friction_factor": safe_attr(settings, "friction_factor"),
            "thickness_inner": safe_attr(settings, "thickness_inner"),
            "thickness_outer": safe_attr(settings, "thickness_outer"),
            "use_culling": safe_attr(settings, "use_culling"),
            "use_normal": safe_attr(settings, "use_normal"),
        }
    return payload


def collision_group_keys(rigid_bodies: Iterable[dict[str, Any]]) -> set[str]:
    groups: set[str] = set()
    for item in rigid_bodies:
        number = item.get("mmd_collision_group_number")
        if number is not None:
            groups.add(f"mmd:{number}")
        collections = item.get("collision_collections")
        if isinstance(collections, list):
            for index, enabled in enumerate(collections):
                if enabled:
                    groups.add(f"blender:{index}")
    return groups


def inspect_character(
    profile: dict[str, Any], source_kind: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    objects, resolved_collection = character_objects(profile, source_kind)
    warnings: list[str] = []
    issues: list[str] = []
    if resolved_collection is None:
        warnings.append(
            f"{profile['character']}: cache collection was not found; fallback ownership was used"
        )
    if not objects:
        issues.append(f"{profile['character']}: no owned objects were found")

    rigid_objects = sorted(
        (
            obj
            for obj in objects
            if safe_attr(obj, "rigid_body") is not None or mmd_type(obj) == "RIGID_BODY"
        ),
        key=lambda obj: obj.name.casefold(),
    )
    joint_objects = sorted(
        (
            obj
            for obj in objects
            if safe_attr(obj, "rigid_body_constraint") is not None
            or mmd_type(obj) == "JOINT"
        ),
        key=lambda obj: obj.name.casefold(),
    )
    rigid_bodies = [rigid_body_payload(obj) for obj in rigid_objects]
    joints = [joint_payload(obj) for obj in joint_objects]
    modifiers = [
        modifier_payload(obj, modifier)
        for obj in sorted(objects, key=lambda item: item.name.casefold())
        for modifier in obj.modifiers
        if modifier.type in {"CLOTH", "COLLISION"}
    ]

    mmd_rigid_count = sum(item["mmd_type"] == "RIGID_BODY" for item in rigid_bodies)
    blender_rigid_count = sum(item["blender_rigid_body_present"] for item in rigid_bodies)
    active_count = sum(item["blender_type"] == "ACTIVE" for item in rigid_bodies)
    passive_count = sum(item["blender_type"] == "PASSIVE" for item in rigid_bodies)
    mmd_joint_count = sum(item["mmd_type"] == "JOINT" for item in joints)
    blender_constraint_count = sum(item["blender_constraint_present"] for item in joints)
    broken_joint_count = sum(
        item["blender_constraint_present"]
        and (item["object1"] is None or item["object2"] is None)
        for item in joints
    )
    if broken_joint_count:
        issues.append(
            f"{profile['character']}: {broken_joint_count} built joint(s) have missing references"
        )

    modifier_objects = {
        obj
        for item in modifiers
        if (obj := bpy.data.objects.get(item["object"])) is not None
    }
    physics_objects = set(rigid_objects) | set(joint_objects) | modifier_objects
    physics_collections = sorted(
        {
            collection.name
            for obj in physics_objects
            for collection in obj.users_collection
        }
    )
    meshes = [obj for obj in objects if obj.type == "MESH"]
    hidden_meshes = [obj for obj in meshes if obj.hide_render]
    groups = collision_group_keys(rigid_bodies)
    result = {
        "character": profile["character"],
        "profile_cache_collection": str(profile["cache_collection"]),
        "resolved_collection": resolved_collection,
        "armature_object": str(profile["armature_object"]),
        "object_count": len(objects),
        "mesh_count": len(meshes),
        "visible_mesh_count": len(meshes) - len(hidden_meshes),
        "hidden_render_mesh_count": len(hidden_meshes),
        "rigid_body_count": len(rigid_objects),
        "mmd_rigid_body_count": mmd_rigid_count,
        "blender_rigid_body_count": blender_rigid_count,
        "unbuilt_rigid_body_count": sum(
            item["mmd_type"] == "RIGID_BODY"
            and not item["blender_rigid_body_present"]
            for item in rigid_bodies
        ),
        "active_rigid_body_count": active_count,
        "passive_rigid_body_count": passive_count,
        "kinematic_rigid_body_count": sum(
            item.get("kinematic") is True for item in rigid_bodies
        ),
        "joint_count": len(joint_objects),
        "mmd_joint_count": mmd_joint_count,
        "blender_constraint_count": blender_constraint_count,
        "broken_joint_reference_count": broken_joint_count,
        "cloth_modifier_count": sum(item["type"] == "CLOTH" for item in modifiers),
        "collision_modifier_count": sum(item["type"] == "COLLISION" for item in modifiers),
        "physics_object_count": len(physics_objects),
        "hidden_physics_object_count": sum(obj.hide_render for obj in physics_objects),
        "physics_collection_count": len(physics_collections),
        "collision_group_count": len(groups),
        "physics_built": blender_rigid_count > 0 or blender_constraint_count > 0,
        "rigid_bodies": rigid_bodies,
        "joints": joints,
        "modifiers": modifiers,
        "physics_collections": physics_collections,
        "collision_groups": sorted(groups),
    }
    return result, issues, warnings


def relative_or_absolute(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def main() -> None:
    args = arguments()
    project = args.project.resolve()
    output = args.output if args.output.is_absolute() else project / args.output
    output = output.resolve()
    try:
        output.relative_to(project)
    except ValueError as exc:
        raise RuntimeError("Phase 8.1 diagnostic output must stay inside the project") from exc

    profiles = profile_contracts(project, args.character)
    scene = bpy.context.scene
    render = scene.render
    actual_width, actual_height = actual_output_dimensions(
        int(render.resolution_x),
        int(render.resolution_y),
        int(render.resolution_percentage),
    )
    character_results = []
    issues: list[str] = []
    warnings: list[str] = []
    for profile in profiles:
        result, character_issues, character_warnings = inspect_character(
            profile, args.source_kind
        )
        character_results.append(result)
        issues.extend(character_issues)
        warnings.extend(character_warnings)

    world = rigid_body_world_payload(scene)
    total_built = sum(item["blender_rigid_body_count"] for item in character_results)
    if total_built and not world["present"]:
        issues.append("Blender rigid bodies exist but the scene has no Rigid Body World")
    elif total_built and world["enabled"] is False:
        issues.append("Blender rigid bodies exist but the Rigid Body World is disabled")

    payload = {
        "schema_version": 1,
        "phase": "8.1",
        "status": "complete",
        "source_kind": args.source_kind,
        "source_file": relative_or_absolute(Path(bpy.data.filepath), project),
        "blender_version": bpy.app.version_string,
        "scene": {
            "name": scene.name,
            "frame_start": int(scene.frame_start),
            "frame_end": int(scene.frame_end),
            "frame_current": int(scene.frame_current),
            "render_engine": str(render.engine),
            "render_width": int(render.resolution_x),
            "render_height": int(render.resolution_y),
            "resolution_percentage": int(render.resolution_percentage),
            "actual_output_width": actual_width,
            "actual_output_height": actual_height,
        },
        "rigid_body_world": world,
        "characters": character_results,
        "issues": issues,
        "warnings": warnings,
        "summary": aggregate_character_inventories(
            character_results,
            issue_count=len(issues),
            warning_count=len(warnings),
        ),
    }
    atomic_write_json(output, payload)
    print(
        "PHASE 8.1 PHYSICS INVENTORY COMPLETE: "
        f"source={args.source_kind}, characters={len(character_results)}, "
        f"rigid_bodies={payload['summary']['rigid_body_count']} "
        f"(built={payload['summary']['blender_rigid_body_count']}, "
        f"unbuilt={payload['summary']['unbuilt_rigid_body_count']}), "
        f"joints={payload['summary']['joint_count']}, "
        f"cloth={payload['summary']['cloth_modifier_count']}, "
        f"collision={payload['summary']['collision_modifier_count']}, "
        f"issues={len(issues)}, warnings={len(warnings)}, output={output}"
    )


if __name__ == "__main__":
    main()
