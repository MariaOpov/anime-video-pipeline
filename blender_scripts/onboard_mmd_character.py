"""Import, inspect, normalize, tag, pack, and cache one PMX/PMD character."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.rig_contract import (  # noqa: E402
    BONE_ALIASES,
    MORPH_ALIASES,
    match_aliases,
)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def import_model(path: Path):
    operator = bpy.ops.mmd_tools.import_model
    properties = {item.identifier for item in operator.get_rna_type().properties}
    kwargs = {"filepath": str(path)}
    if "scale" in properties:
        kwargs["scale"] = 0.08
    before = set(bpy.data.objects)
    result = operator(**kwargs)
    if "FINISHED" not in result:
        raise RuntimeError(f"mmd_tools import failed: {sorted(result)}")
    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not imported:
        raise RuntimeError("mmd_tools reported success but created no objects")
    return imported


def bounds(objects):
    points = [obj.matrix_world @ Vector(corner)
              for obj in objects if obj.type == "MESH" for corner in obj.bound_box]
    if not points:
        raise RuntimeError("Imported model has no mesh bounds")
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return minimum, maximum


def normalize(imported, collection, target_height, rotation_z):
    root = bpy.data.objects.new(f"{collection.name}_ROOT", None)
    collection.objects.link(root)
    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            matrix = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = matrix
    root.rotation_euler.z = math.radians(rotation_z)
    bpy.context.view_layer.update()
    minimum, maximum = bounds(imported)
    height = maximum.z - minimum.z
    if height <= 1e-6:
        raise RuntimeError("Imported model height is zero")
    scale = target_height / height
    root.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    minimum, maximum = bounds(imported)
    center = (minimum + maximum) * 0.5
    root.location += Vector((-center.x, -center.y, -minimum.z))
    bpy.context.view_layer.update()
    minimum, maximum = bounds(imported)
    dimensions = maximum - minimum
    return root, [round(dimensions.x, 5), round(dimensions.y, 5), round(dimensions.z, 5)]


def move_to_collection(objects, collection):
    for obj in objects:
        if collection not in obj.users_collection:
            collection.objects.link(obj)
        for current in list(obj.users_collection):
            if current != collection:
                current.objects.unlink(obj)


def texture_status():
    count = 0
    missing = 0
    warnings = []
    for image in bpy.data.images:
        if image.source not in {"FILE", "SEQUENCE", "MOVIE"}:
            continue
        count += 1
        path = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
        available = bool(image.packed_file) or bool(path and path.is_file())
        if not available:
            missing += 1
            warnings.append(f"Missing texture: {image.filepath or image.name}")
            continue
        if not image.packed_file:
            try:
                image.pack()
            except RuntimeError as exc:
                warnings.append(f"Could not pack texture {image.name}: {exc}")
    return count, missing, warnings


def bone_axes(armature, mapping):
    """Record rest-space directions for quaternion/left-right correction."""
    result = {}
    for alias, name in mapping.items():
        bone = armature.data.bones.get(name) if name else None
        if not bone:
            continue
        direction = bone.tail_local - bone.head_local
        if direction.length <= 1e-8:
            continue
        direction.normalize()
        result[alias] = [round(direction.x, 6), round(direction.y, 6), round(direction.z, 6)]
    return result


def main():
    args = arguments()
    request = load_json(args.request.resolve())
    source_model = Path(request["source_model"]).resolve()
    if not source_model.is_file():
        raise RuntimeError(f"Source model not found: {source_model}")
    if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
        raise RuntimeError("MMD Tools import operator is not available")
    imported = import_model(source_model)
    armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("Imported model contains no armature")
    armature = max(armatures, key=lambda obj: len(obj.data.bones))
    collection = bpy.data.collections.new(request["cache_collection"])
    bpy.context.scene.collection.children.link(collection)
    move_to_collection(imported, collection)
    root, dimensions = normalize(
        imported, collection, float(request["target_height_meters"]),
        float(request.get("rotation_z_degrees", 0.0)),
    )
    character = request["character"]
    armature.name = f"PIPE_{character}_Armature"
    armature["pipeline_character"] = character
    root["pipeline_character_root"] = character
    bone_names = [bone.name for bone in armature.data.bones]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    morph_names = sorted({block.name for obj in meshes
                          if obj.data.shape_keys for block in obj.data.shape_keys.key_blocks
                          if block.name.casefold() not in {"basis", "base"}})
    bone_mapping = match_aliases(bone_names, BONE_ALIASES)
    morph_mapping = match_aliases(morph_names, MORPH_ALIASES)
    for alias, name in bone_mapping.items():
        if name:
            armature[f"pipeline_bone_{alias.replace('.', '_')}"] = name
    for alias, name in morph_mapping.items():
        if name:
            armature[f"pipeline_morph_{alias}"] = name
    texture_count, missing_textures, warnings = texture_status()
    materials = {material.name for obj in meshes for material in obj.data.materials if material}
    cache_path = Path(request["cache_path"]).resolve()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene["pipeline_phase"] = 7
    bpy.context.scene["pipeline_character"] = character
    bpy.ops.wm.save_as_mainfile(filepath=str(cache_path))
    profile = {
        "schema_version": 1,
        "character": character,
        "source_model": request["source_model_relative"],
        "model_format": request["model_format"],
        "model_sha256": request["model_sha256"],
        "cache_blend": request["cache_relative"],
        "cache_collection": request["cache_collection"],
        "armature_object": armature.name,
        "target_height_meters": float(request["target_height_meters"]),
        "dimensions": dimensions,
        "object_count": len(imported) + 1,
        "mesh_count": len(meshes),
        "material_count": len(materials),
        "bone_count": len(bone_names),
        "morph_count": len(morph_names),
        "texture_count": texture_count,
        "missing_texture_count": missing_textures,
        "bone_mapping": bone_mapping,
        "bone_axes": bone_axes(armature, bone_mapping),
        "morph_mapping": morph_mapping,
        "license": request["license"],
        "warnings": warnings,
    }
    profile_path = Path(request["profile_path"]).resolve()
    atomic_write_json(profile_path, profile)
    print(
        f"PHASE 7 BLENDER PROFILE: {character}, {len(meshes)} mesh(es), "
        f"{len(bone_names)} bones, {len(morph_names)} morphs, "
        f"{texture_count} textures/{missing_textures} missing, cache={cache_path}"
    )


if __name__ == "__main__":
    main()
