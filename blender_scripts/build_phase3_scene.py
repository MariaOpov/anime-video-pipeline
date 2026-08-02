"""Assemble cameras, dialogue audio, and mouth animation in Blender.

Run with Blender, not system Python:
    blender --background base.blend --python blender_scripts/build_phase3_scene.py -- \
        --project projects/demo [--render]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Euler, Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline.gestures import build_pose_keyframes  # noqa: E402
from anime_pipeline.harmonization import camera_fit_distance  # noqa: E402
from anime_pipeline.rig_contract import (  # noqa: E402
    BONE_ALIASES,
    PHASE8_REQUIRED_CONTROLS,
    match_aliases,
)


MOUTH_SHAPES = {
    "closed": (1.00, 0.16), "neutral": (1.00, 0.35),
    "A": (0.80, 1.45), "I": (1.55, 0.42), "U": (0.62, 0.92),
    "E": (1.30, 0.68), "O": (0.72, 1.22),
}

POSE_BONE_ALIASES = BONE_ALIASES

BLINK_SHAPE_ALIASES = {"blink", "eye_blink", "eyeblink", "まばたき"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--render", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def load_json(path: Path) -> dict:
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


def armature_for(character: str):
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE" and obj.get("pipeline_character") == character:
            return obj
    candidates = (f"{character}_Armature", character)
    for name in candidates:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == "ARMATURE":
            return obj
    raise RuntimeError(f"No armature found for character: {character}")


def pose_bone_for(armature, alias: str):
    mapped = armature.get(f"pipeline_bone_{alias.replace('.', '_')}")
    if mapped:
        bone = armature.pose.bones.get(str(mapped))
        if bone:
            return bone
    candidates = POSE_BONE_ALIASES.get(alias, (alias,))
    for name in candidates:
        bone = armature.pose.bones.get(name)
        if bone:
            return bone
    lowered = {bone.name.casefold(): bone for bone in armature.pose.bones}
    for name in candidates:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    resolved = match_aliases(
        [bone.name for bone in armature.pose.bones], {alias: tuple(candidates)}
    ).get(alias)
    if resolved:
        return armature.pose.bones.get(resolved)
    return None


def _neutral_quaternion(bone):
    stored = bone.get("pipeline_neutral_quaternion")
    if stored and len(stored) == 4:
        from mathutils import Quaternion
        return Quaternion(tuple(float(value) for value in stored))
    return bone.rotation_quaternion.copy() if bone.rotation_mode == "QUATERNION" else Euler(
        bone.rotation_euler, bone.rotation_mode
    ).to_quaternion()


def _semantic_delta_quaternion(bone, rotation):
    """Convert canonical armature-space XYZ intent into this bone's local axes."""
    rest = bone.bone.matrix_local.to_quaternion()
    semantic = Euler(rotation, "XYZ").to_quaternion()
    return rest.inverted() @ semantic @ rest


def look_direction(armature, target_name: str | None) -> float:
    if not target_name:
        return 0.0
    try:
        target = armature_for(target_name)
    except RuntimeError:
        return 0.0
    delta = target.matrix_world.translation.x - armature.matrix_world.translation.x
    if abs(delta) < 0.001:
        return 0.0
    return 1.0 if delta > 0 else -1.0


def animate_performances(manifest: dict) -> tuple[int, int, int, int, int]:
    settings = manifest.get("performance", {})
    clips = settings.get("clips", []) if settings.get("enabled", False) else []
    if not clips:
        return 0, 0, 0, 0, 0
    amplitude = float(settings.get("amplitude_scale", 1.0))
    characters = sorted({clip["character"] for clip in clips})
    armatures = {character: armature_for(character) for character in characters}
    actions = {}
    for character, armature in armatures.items():
        armature.animation_data_create()
        action = bpy.data.actions.new(f"PIPE_{character}_ProceduralPerformance")
        armature.animation_data.action = action
        actions[character] = action

    inserted = 0
    skipped_bones: set[tuple[str, str]] = set()
    for clip in clips:
        character = clip["character"]
        armature = armatures[character]
        direction = look_direction(armature, clip.get("look_at"))
        for keyframe in build_pose_keyframes(
            clip, look_direction=direction, amplitude_scale=amplitude
        ):
            for alias, rotation in keyframe["rotations"].items():
                bone = pose_bone_for(armature, alias)
                if not bone:
                    skipped_bones.add((character, alias))
                    continue
                neutral = _neutral_quaternion(bone)
                bone.rotation_mode = "QUATERNION"
                bone.rotation_quaternion = neutral @ _semantic_delta_quaternion(bone, rotation)
                bone.keyframe_insert(
                    data_path="rotation_quaternion", frame=keyframe["frame"],
                    group=f"PIPE_{alias}",
                )
                inserted += 1

    for action in actions.values():
        for curve in getattr(action, "fcurves", []):
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"
    gesture_count = sum(len(clip.get("gestures", [])) for clip in clips)
    return len(armatures), len(clips), gesture_count, inserted, len(skipped_bones)


def eye_objects_for(character: str):
    prefix = f"{character}_Eye_".casefold()
    return [obj for obj in bpy.data.objects
            if obj.type == "MESH" and obj.name.casefold().startswith(prefix)]


def blink_shape_targets(character: str):
    armature = armature_for(character)
    mapped_blink = armature.get("pipeline_morph_blink")
    targets = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.shape_keys:
            continue
        belongs = obj.name.casefold().startswith(character.casefold())
        belongs = belongs or obj.parent == armature
        belongs = belongs or any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in obj.modifiers
        )
        if not belongs:
            continue
        for block in obj.data.shape_keys.key_blocks:
            if (mapped_blink and block.name == mapped_blink) or block.name.casefold() in BLINK_SHAPE_ALIASES:
                targets.append(block)
    return targets


def animate_blinks(manifest: dict) -> tuple[int, int, int]:
    events = manifest.get("performance", {}).get("blink_events", [])
    targets_by_character = {}
    target_ids = set()
    inserted = 0
    applied_events = 0
    for event in events:
        character = event["character"]
        if character not in targets_by_character:
            shapes = blink_shape_targets(character)
            eyes = [] if shapes else eye_objects_for(character)
            targets_by_character[character] = (shapes, eyes)
            target_ids.update(("shape", id(target)) for target in shapes)
            target_ids.update(("eye", target.name) for target in eyes)
        shapes, eyes = targets_by_character[character]
        close = int(event["close_frame"])
        opened = int(event["open_frame"])
        if shapes:
            for target in shapes:
                for frame, value in ((max(1, close - 1), 0.0), (close, 1.0), (opened, 0.0)):
                    target.value = value
                    target.keyframe_insert(data_path="value", frame=frame, group="PIPE_Blink")
                    inserted += 1
            applied_events += 1
        elif eyes:
            for eye in eyes:
                baseline = float(eye.scale.z)
                for frame, value in ((max(1, close - 1), baseline),
                                     (close, baseline * 0.08), (opened, baseline)):
                    eye.scale.z = value
                    eye.keyframe_insert(data_path="scale", index=2, frame=frame,
                                        group="PIPE_Blink")
                    inserted += 1
            applied_events += 1
    return len(target_ids), applied_events, inserted


def animate_gaze(manifest: dict) -> tuple[int, int]:
    events = manifest.get("performance", {}).get("gaze_events", [])
    applied = 0
    inserted = 0
    for event in events:
        armature = armature_for(event["character"])
        direction = look_direction(armature, event["target"])
        if not direction:
            continue
        start, end = int(event["start_frame"]), int(event["end_frame"])
        transition = max(2, min(5, (end - start) // 5))
        eye_bone = pose_bone_for(armature, "eyes")
        if eye_bone:
            eye_bone.rotation_mode = "XYZ"
            for frame, value in ((start, 0.0), (min(end, start + transition), direction * 0.09),
                                 (max(start, end - transition), direction * 0.09), (end, 0.0)):
                eye_bone.rotation_euler.z = value
                eye_bone.keyframe_insert(data_path="rotation_euler", index=2, frame=frame,
                                         group="PIPE_Gaze")
                inserted += 1
            applied += 1
            continue
        eyes = eye_objects_for(event["character"])
        if not eyes:
            continue
        for eye in eyes:
            for frame, value in ((start, 0.0), (min(end, start + transition), direction * 0.018),
                                 (max(start, end - transition), direction * 0.018), (end, 0.0)):
                eye.delta_location.x = value
                eye.keyframe_insert(data_path="delta_location", index=0, frame=frame,
                                    group="PIPE_Gaze")
                inserted += 1
        applied += 1
    return applied, inserted


def mouth_material():
    material = bpy.data.materials.get("PIPE_MouthMaterial")
    if material:
        return material
    material = bpy.data.materials.new("PIPE_MouthMaterial")
    material.diffuse_color = (0.055, 0.012, 0.018, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = material.diffuse_color
        bsdf.inputs["Roughness"].default_value = 0.5
    return material


def create_fallback_mouth(character: str):
    existing = bpy.data.objects.get(f"{character}_Mouth")
    if existing and existing.type == "MESH" and existing.data.shape_keys:
        return existing

    armature = armature_for(character)
    width, depth, height = 0.10, 0.012, 0.035
    vertices = [
        (-width, -depth, -height), (width, -depth, -height),
        (width, depth, -height), (-width, depth, -height),
        (-width, -depth, height), (width, -depth, height),
        (width, depth, height), (-width, depth, height),
    ]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7)]
    mesh = bpy.data.meshes.new(f"{character}_MouthMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mouth_material())
    mouth = bpy.data.objects.new(f"{character}_Mouth", mesh)
    bpy.context.scene.collection.objects.link(mouth)

    local_position = Vector((0, -0.305, 2.08))
    world_position = armature.matrix_world @ local_position
    mouth.matrix_world = Matrix.Translation(world_position)
    world_matrix = mouth.matrix_world.copy()
    mouth.parent = armature
    if "head" in armature.pose.bones:
        mouth.parent_type = "BONE"
        mouth.parent_bone = "head"
    else:
        mouth.parent_type = "OBJECT"
    mouth.matrix_world = world_matrix
    mouth["pipeline_mouth_target"] = character

    basis = mouth.shape_key_add(name="Basis")
    for shape_name, (width_scale, height_scale) in MOUTH_SHAPES.items():
        shape = mouth.shape_key_add(name=shape_name)
        for index, point in enumerate(shape.data):
            source = basis.data[index].co
            point.co.x = source.x * width_scale
            point.co.y = source.y
            point.co.z = source.z * height_scale
        shape.value = 0.0
    return mouth


def mouth_targets_for(character: str):
    armature = armature_for(character)
    requested = {
        shape: armature.get(f"pipeline_morph_{shape}")
        for shape in ("A", "I", "U", "E", "O")
    }
    targets = []
    if any(requested.values()):
        for obj in bpy.data.objects:
            if obj.type != "MESH" or not obj.data.shape_keys:
                continue
            belongs = obj.parent == armature or obj.name.casefold().startswith(character.casefold())
            belongs = belongs or any(
                modifier.type == "ARMATURE" and modifier.object == armature
                for modifier in obj.modifiers
            )
            if not belongs:
                continue
            keys = obj.data.shape_keys.key_blocks
            mapping = {shape: name for shape, name in requested.items() if name and name in keys}
            if mapping:
                targets.append((obj, mapping))
    if targets:
        return targets
    fallback = create_fallback_mouth(character)
    return [(fallback, {shape: shape for shape in ("A", "I", "U", "E", "O")})]


def insert_mouth_pose(targets, frame: int, active_shape: str) -> None:
    for obj, mapping in targets:
        keys = obj.data.shape_keys.key_blocks
        for shape, name in mapping.items():
            key = keys.get(name)
            if not key:
                continue
            key.value = 1.0 if shape == active_shape else 0.0
            key.keyframe_insert(data_path="value", frame=frame, group="PIPE_Mouth")


def animate_dialogue(manifest: dict) -> tuple[int, int]:
    fps = manifest["fps"]
    targets = {}
    applied_cues = 0
    for line in manifest["dialogue"]:
        character = line["character"]
        mouths = targets.setdefault(character, mouth_targets_for(character))
        events = {int(line["start_frame"]): "closed", int(line["end_frame"]): "closed"}
        for cue in line["mouth_cues"]:
            start = int(line["start_frame"]) + round(float(cue["start"]) * fps)
            end = int(line["start_frame"]) + round(float(cue["end"]) * fps)
            line_start, line_end = int(line["start_frame"]), int(line["end_frame"])
            start = max(line_start, min(start, max(line_start, line_end - 1)))
            end = min(line_end, max(start + 1, end))
            events[start] = cue["mouth_shape"]
            events.setdefault(end, "closed")
            applied_cues += 1
        for frame, shape in sorted(events.items()):
            insert_mouth_pose(mouths, frame, shape)
    return sum(len(items) for items in targets.values()), applied_cues


def _character_objects(character: str):
    roots = [obj for obj in bpy.data.objects
             if obj.get("pipeline_character_root") == character]
    armatures = [obj for obj in bpy.data.objects
                 if obj.type == "ARMATURE" and obj.get("pipeline_character") == character]
    owned = set(roots + armatures)
    for obj in bpy.data.objects:
        parent = obj.parent
        while parent:
            if parent in roots or parent in armatures:
                owned.add(obj)
                break
            parent = parent.parent
        if obj.type == "MESH" and any(
            modifier.type == "ARMATURE" and modifier.object in armatures
            for modifier in obj.modifiers
        ):
            owned.add(obj)
        if obj.get("pipeline_mouth_target") == character:
            owned.add(obj)
    return owned


def load_character_assets(project: Path, manifest: dict) -> tuple[int, int, int, int, int]:
    contract = manifest.get("character_assets", {})
    characters = contract.get("characters", []) if contract.get("enabled", False) else []
    loaded = 0
    resolved_bones = 0
    resolved_mouth = 0
    missing_textures = 0
    license_warnings = 0
    for item in characters:
        if not item.get("ready", False):
            raise RuntimeError(f"Production character is not ready: {item['character']}")
        cache = (project / item["cache_blend"]).resolve()
        if not cache.is_file():
            raise RuntimeError(f"Production character cache is missing: {cache}")
        existing = sorted(
            _character_objects(item["character"]),
            key=_parent_depth, reverse=True,
        )
        for obj in existing:
            bpy.data.objects.remove(obj, do_unlink=True)
        with bpy.data.libraries.load(str(cache), link=False) as (data_from, data_to):
            if item["cache_collection"] not in data_from.collections:
                raise RuntimeError(
                    f"Character cache collection is missing: {item['cache_collection']}"
                )
            data_to.collections = [item["cache_collection"]]
        collection = data_to.collections[0]
        if not collection:
            raise RuntimeError(f"Failed to append character collection: {item['character']}")
        bpy.context.scene.collection.children.link(collection)
        armature = armature_for(item["character"])
        if armature.name != item["armature_object"]:
            raise RuntimeError(f"Character armature identity mismatch: {item['character']}")
        armature["pipeline_character"] = item["character"]
        for alias, name in item.get("bone_mapping", {}).items():
            if name and armature.pose.bones.get(name):
                armature[f"pipeline_bone_{alias.replace('.', '_')}"] = name
        for alias, name in item.get("morph_mapping", {}).items():
            if name:
                armature[f"pipeline_morph_{alias}"] = name
        loaded += 1
        resolved_bones += int(item["resolved_bone_count"])
        resolved_mouth += int(item["resolved_mouth_morph_count"])
        missing_textures += int(item["missing_texture_count"])
        license_warnings += int(item["license_warning"])
    bpy.context.view_layer.update()
    return loaded, resolved_bones, resolved_mouth, missing_textures, license_warnings


def _parent_depth(obj) -> int:
    depth = 0
    parent = obj.parent
    while parent:
        depth += 1
        parent = parent.parent
    return depth


def character_root_for(character: str, armature=None):
    for obj in bpy.data.objects:
        if obj.get("pipeline_character_root") == character:
            return obj
    armature = armature or armature_for(character)
    owned = _character_objects(character)
    root = bpy.data.objects.new(f"PIPE_{character}_ROOT", None)
    bpy.context.scene.collection.objects.link(root)
    root.matrix_world = Matrix.Translation(armature.matrix_world.translation)
    root["pipeline_character_root"] = character
    for obj in list(owned):
        if obj == root or obj.parent in owned:
            continue
        matrix = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = matrix
    return root


def character_meshes(character: str):
    # Hidden MMD rigid-body/helper meshes must not affect visible character
    # height, grounding, or adaptive camera framing.
    return [
        obj
        for obj in _character_objects(character)
        if obj.type == "MESH" and not obj.hide_render
    ]


def character_bounds(character: str) -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []

    for obj in character_meshes(character):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()

        try:
            points.extend(
                evaluated.matrix_world @ vertex.co
                for vertex in mesh.vertices
            )
        finally:
            evaluated.to_mesh_clear()

    if not points:
        raise RuntimeError(
            f"Character has no measurable visible mesh bounds: {character}"
        )

    minimum = Vector((
        min(point.x for point in points),
        min(point.y for point in points),
        min(point.z for point in points),
    ))
    maximum = Vector((
        max(point.x for point in points),
        max(point.y for point in points),
        max(point.z for point in points),
    ))
    return minimum, maximum


def _neutralize_arm(armature, alias: str, neutral_degrees: float) -> float:
    bone = pose_bone_for(armature, alias)
    if not bone:
        return 180.0
    rest = bone.bone.tail_local - bone.bone.head_local
    if rest.length <= 1e-8:
        return 180.0
    rest.normalize()
    side = 1.0 if rest.x >= 0.0 else -1.0
    angle = math.radians(neutral_degrees)
    target = Vector((side * math.sin(angle), 0.0, -math.cos(angle))).normalized()
    rest_rotation = bone.bone.matrix_local.to_quaternion()
    local_target = rest_rotation.inverted() @ target
    correction = Vector((0.0, 1.0, 0.0)).rotation_difference(local_target.normalized())
    bone.rotation_mode = "QUATERNION"
    bone.rotation_quaternion = correction
    bone["pipeline_neutral_quaternion"] = list(correction)
    bpy.context.view_layer.update()
    posed = bone.tail - bone.head
    if posed.length <= 1e-8:
        return 180.0
    return round(math.degrees(posed.normalized().angle(target)), 5)


def _tag_runtime_bones(armature) -> dict[str, str | None]:
    mapping = match_aliases([bone.name for bone in armature.pose.bones], BONE_ALIASES)
    for alias, name in mapping.items():
        if name:
            armature[f"pipeline_bone_{alias.replace('.', '_')}"] = name
    return mapping


def _ensure_foot_lock(character: str, root, alias: str, floor_z: float):
    side = "L" if alias.endswith(".L") else "R"
    name = f"PIPE_{character}_FootLock_{side}"
    control = bpy.data.objects.get(name)
    if not control:
        control = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(control)
    control["pipeline_foot_lock"] = f"{character}:{side}"
    control.empty_display_type = "PLAIN_AXES"
    control.empty_display_size = 0.12
    control.matrix_world = Matrix.Translation((root.matrix_world.translation.x,
                                               root.matrix_world.translation.y,
                                               floor_z))
    matrix = control.matrix_world.copy()
    control.parent = root
    control.matrix_world = matrix
    return control


def harmonize_characters(manifest: dict) -> list[dict]:
    contract = manifest.get("harmonization", {})
    if not contract.get("enabled", False):
        return []
    floor_z = float(contract["floor_z"])
    height_tolerance = float(contract["height_tolerance_ratio"])
    ground_tolerance = float(contract["ground_tolerance_meters"])
    neutral_limit = float(contract["rest_pose_max_degrees"])
    neutral_degrees = float(contract["neutral_arm_degrees"])
    results = []
    bpy.context.scene.frame_set(int(manifest["frame_start"]))
    for plan in contract.get("characters", []):
        character = plan["character"]
        armature = armature_for(character)
        mapping = _tag_runtime_bones(armature)
        root = character_root_for(character, armature)
        root["pipeline_character_root"] = character
        root["pipeline_base_yaw_radians"] = float(root.rotation_euler.z)

        left_deviation = _neutralize_arm(armature, "arm.L", neutral_degrees)
        right_deviation = _neutralize_arm(armature, "arm.R", neutral_degrees)
        for alias in ("spine", "head", "arm.L", "arm.R", "leg.L", "leg.R", "eyes"):
            bone = pose_bone_for(armature, alias)
            if bone and not bone.get("pipeline_neutral_quaternion"):
                bone.rotation_mode = "QUATERNION"
                bone["pipeline_neutral_quaternion"] = list(bone.rotation_quaternion)

        minimum, maximum = character_bounds(character)
        measured_height = maximum.z - minimum.z
        if measured_height <= 1e-6:
            raise RuntimeError(f"Character height is zero: {character}")
        target_height = float(plan["target_height_meters"])
        scale_factor = target_height / measured_height
        root.scale = tuple(float(component) * scale_factor for component in root.scale)
        bpy.context.view_layer.update()
        minimum, maximum = character_bounds(character)
        root.location.z += floor_z - minimum.z
        root["pipeline_ground_offset_z"] = float(root.location.z)
        root["pipeline_target_height_meters"] = target_height
        bpy.context.view_layer.update()
        minimum, maximum = character_bounds(character)
        dimensions = maximum - minimum
        center = (minimum + maximum) * 0.5
        root["pipeline_stage_offset_x"] = float(root.location.x - center.x)
        root["pipeline_stage_offset_y"] = float(root.location.y - center.y)
        measured_height = dimensions.z
        height_error = abs(measured_height - target_height) / target_height
        ground_error = abs(minimum.z - floor_z)

        left_rest = None
        right_rest = None
        if mapping.get("arm.L") and mapping.get("arm.R"):
            left_bone = armature.data.bones.get(mapping["arm.L"])
            right_bone = armature.data.bones.get(mapping["arm.R"])
            if left_bone and right_bone:
                left_rest = left_bone.tail_local - left_bone.head_local
                right_rest = right_bone.tail_local - right_bone.head_local
        axis_verified = bool(
            left_rest is not None and right_rest is not None
            and left_rest.length > 1e-8 and right_rest.length > 1e-8
            and left_rest.x * right_rest.x < 0.0
        )

        source_ik = 0
        for alias in ("leg_ik.L", "leg_ik.R"):
            ik_bone = pose_bone_for(armature, alias)
            if ik_bone:
                ik_bone.lock_location = (True, True, True)
                ik_bone["pipeline_foot_lock"] = True
                source_ik += 1
            else:
                _ensure_foot_lock(character, root, alias, floor_z)

        resolved_controls = 0
        for alias in PHASE8_REQUIRED_CONTROLS:
            if alias == "root":
                available = root is not None
            elif alias == "eyes":
                available = pose_bone_for(armature, "eyes") is not None or bool(
                    eye_objects_for(character)
                )
            elif alias in {"leg_ik.L", "leg_ik.R"}:
                available = True  # source IK or an application-owned grounded fallback
            else:
                available = pose_bone_for(armature, alias) is not None
            resolved_controls += int(available)

        neutral_deviation = max(left_deviation, right_deviation)
        neutral_passed = neutral_deviation <= neutral_limit
        height_passed = height_error <= height_tolerance
        grounding_passed = ground_error <= ground_tolerance
        controls_passed = resolved_controls == len(PHASE8_REQUIRED_CONTROLS)
        ready = neutral_passed and height_passed and grounding_passed and axis_verified and controls_passed
        results.append({
            "character": character,
            "root_object": root.name,
            "target_height_meters": round(target_height, 5),
            "measured_height_meters": round(measured_height, 5),
            "height_error_ratio": round(height_error, 6),
            "scale_factor": round(scale_factor, 6),
            "world_bounds_min": [round(value, 5) for value in minimum],
            "world_bounds_max": [round(value, 5) for value in maximum],
            "neutral_pose": "neutral_dialogue",
            "arm_deviation_degrees": round(neutral_deviation, 5),
            "neutral_pose_passed": neutral_passed,
            "ground_plane_z": round(floor_z, 5),
            "ground_error_meters": round(ground_error, 6),
            "grounding_passed": grounding_passed,
            "foot_lock_mode": "source_ik" if source_ik == 2 else "root_grounded",
            "bone_axes_verified": axis_verified,
            "required_control_count": len(PHASE8_REQUIRED_CONTROLS),
            "resolved_control_count": resolved_controls,
            "ready": ready,
        })
    return results


def camera_collection():
    collection = bpy.data.collections.get("PIPE_Phase3_Cameras")
    if not collection:
        collection = bpy.data.collections.new("PIPE_Phase3_Cameras")
        bpy.context.scene.collection.children.link(collection)
    return collection


def target_point(character: str | None) -> Vector:
    if not character:
        return Vector((0, 0, 1.5))
    armature = armature_for(character)
    head = pose_bone_for(armature, "head")
    if head:
        return armature.matrix_world @ ((head.head + head.tail) * 0.5)
    minimum, maximum = character_bounds(character)
    return Vector(((minimum.x + maximum.x) * 0.5,
                   (minimum.y + maximum.y) * 0.5,
                   minimum.z + (maximum.z - minimum.z) * 0.88))


def _camera_rotation(location: Vector, target: Vector):
    return (target - location).to_track_quat("-Z", "Y").to_euler()


def _union_bounds(characters: list[str]) -> tuple[Vector, Vector]:
    bounds = [character_bounds(character) for character in characters]
    minimum = Vector((min(item[0].x for item in bounds),
                      min(item[0].y for item in bounds),
                      min(item[0].z for item in bounds)))
    maximum = Vector((max(item[1].x for item in bounds),
                      max(item[1].y for item in bounds),
                      max(item[1].z for item in bounds)))
    return minimum, maximum


def _shot_region(shot: dict, blocking: dict, contract: dict):
    composition = blocking.get("composition", "single")
    subject = blocking.get("subject") or shot.get("target")
    if not subject:
        subject = next(
            (item.get("character") for item in contract.get("characters", [])
             if item.get("character")),
            None,
        )
    if not subject:
        raise RuntimeError(f"Adaptive camera has no subject: {shot['shot_id']}")
    placements = blocking.get("placements", [])
    cast = [item["character"] for item in placements]
    required = cast if composition == "two_shot" and cast else [subject]
    minimum, maximum = _union_bounds(required)
    height = maximum.z - minimum.z
    head = target_point(subject)
    region = "face" if composition == "close_up" else "full_body"
    if region == "face":
        subject_minimum, subject_maximum = character_bounds(subject)
        subject_height = subject_maximum.z - subject_minimum.z
        half_width = max(0.16, (subject_maximum.x - subject_minimum.x) * 0.36)
        minimum = Vector((head.x - half_width, subject_minimum.y,
                          max(subject_minimum.z, head.z - subject_height * 0.30)))
        maximum = Vector((head.x + half_width, subject_maximum.y,
                          subject_maximum.z + subject_height * float(contract["headroom_fraction"])))
    else:
        minimum.z -= height * float(contract["footroom_fraction"])
        maximum.z += height * float(contract["headroom_fraction"])
    return required, subject, region, head, minimum, maximum


def adaptive_camera_contract(manifest: dict, shot: dict, blocking: dict) -> tuple[dict, dict]:
    contract = manifest["harmonization"]
    required, subject, region, head, minimum, maximum = _shot_region(
        shot, blocking, contract
    )
    dimensions = maximum - minimum
    composition = blocking.get("composition", "single")
    fallback_lenses = {"close_up": 68.0, "over_shoulder": 58.0,
                       "two_shot": 52.0, "single": 56.0}
    original = blocking.get("camera", {})
    lens = float(original.get("lens_mm", fallback_lenses.get(composition, 56.0)))
    aspect = float(manifest["render"]["width"]) / float(manifest["render"]["height"])
    distance = camera_fit_distance(
        max(0.1, dimensions.x), max(0.1, dimensions.z), lens, aspect,
        float(contract["safe_frame_fraction"]),
    ) * 1.08 + max(0.0, dimensions.y) / 2.0
    movement = original.get("movement", "static")
    original_start = Vector(original.get("start_location", (0.0, 0.0, 0.0)))
    original_end = Vector(original.get("end_location", original_start))
    movement_delta = original_end - original_start
    # A dolly-in must still fit at the closest keyed position.
    distance += max(0.0, movement_delta.y)
    center = (minimum + maximum) * 0.5
    start_target = Vector((head.x, center.y, center.z)) if region == "face" else center
    start_location = Vector((center.x, minimum.y - distance, start_target.z))
    end_location = start_location + movement_delta
    target_delta = Vector(original.get("end_target", (0.0, 0.0, 0.0))) - Vector(
        original.get("start_target", (0.0, 0.0, 0.0))
    )
    end_target = start_target + target_delta
    margin = round((1.0 - float(contract["safe_frame_fraction"])) / 2.0, 4)
    plan = {
        "movement": movement,
        "lens_mm": lens,
        "start_location": [round(value, 5) for value in start_location],
        "end_location": [round(value, 5) for value in end_location],
        "start_target": [round(value, 5) for value in start_target],
        "end_target": [round(value, 5) for value in end_target],
        "adaptive": True,
        "required_region": region,
        "frame_margin_fraction": margin,
        "subject_height_meters": round(
            character_bounds(subject)[1].z - character_bounds(subject)[0].z, 5
        ),
    }
    basis = {
        "required_characters": required, "subject": subject, "required_region": region,
        "head": head, "minimum": minimum, "maximum": maximum, "margin": margin,
    }
    return plan, basis


def _box_corners(minimum: Vector, maximum: Vector) -> list[Vector]:
    return [Vector((x, y, z)) for x in (minimum.x, maximum.x)
            for y in (minimum.y, maximum.y) for z in (minimum.z, maximum.z)]


def audit_camera_framing(manifest: dict, shot: dict, blocking: dict, camera) -> dict:
    scene = bpy.context.scene
    frames = [int(shot["start_frame"]), int(shot["end_frame"])]
    all_inside = True
    head_visible = True
    feet_visible = True
    minimum_margin = 1.0
    final_minimum = final_maximum = None
    required_region = "full_body"
    required_characters = []
    subject = blocking.get("subject") or shot.get("target")
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        required_characters, subject, required_region, head, minimum, maximum = _shot_region(
            shot, blocking, manifest["harmonization"]
        )
        final_minimum, final_maximum = minimum, maximum
        margin = float(camera.get("pipeline_frame_margin", 0.04))
        projected = [world_to_camera_view(scene, camera, point)
                     for point in _box_corners(minimum, maximum)]
        inside = all(
            point.z > 0 and margin <= point.x <= 1.0 - margin
            and margin <= point.y <= 1.0 - margin
            for point in projected
        )
        all_inside = all_inside and inside
        for point in projected:
            minimum_margin = min(minimum_margin, point.x, 1.0 - point.x,
                                 point.y, 1.0 - point.y)
        head_projection = world_to_camera_view(scene, camera, head)
        head_visible = head_visible and (
            head_projection.z > 0 and margin <= head_projection.x <= 1.0 - margin
            and margin <= head_projection.y <= 1.0 - margin
        )
        if required_region == "full_body":
            foot_points = [Vector((x, y, minimum.z)) for x in (minimum.x, maximum.x)
                           for y in (minimum.y, maximum.y)]
            feet_visible = feet_visible and all(
                (projection := world_to_camera_view(scene, camera, point)).z > 0
                and margin <= projection.x <= 1.0 - margin
                and margin <= projection.y <= 1.0 - margin
                for point in foot_points
            )
    passed = all_inside and head_visible and feet_visible
    return {
        "scene_id": shot["scene_id"],
        "shot_id": shot["shot_id"],
        "composition": blocking.get("composition", "single"),
        "subject": subject,
        "required_characters": required_characters,
        "required_region": required_region,
        "world_bounds_min": [round(value, 5) for value in final_minimum],
        "world_bounds_max": [round(value, 5) for value in final_maximum],
        "lens_mm": round(float(camera.data.lens), 4),
        "frame_margin_fraction": round(float(camera.get("pipeline_frame_margin", 0.04)), 4),
        "measured_minimum_margin": round(minimum_margin, 6),
        "head_visible": head_visible,
        "feet_required": required_region == "full_body",
        "feet_visible": feet_visible,
        "framing_passed": passed,
    }


def create_camera(shot: dict, settings: dict, blocking: dict | None = None):
    if blocking:
        camera_plan = blocking["camera"]
        data = bpy.data.cameras.new(f"PIPE_{shot['shot_id']}_Data")
        data.lens = float(camera_plan["lens_mm"])
        camera = bpy.data.objects.new(f"PIPE_{shot['shot_id']}_Camera", data)
        camera_collection().objects.link(camera)
        start_location = Vector(camera_plan["start_location"])
        end_location = Vector(camera_plan["end_location"])
        start_target = Vector(camera_plan["start_target"])
        end_target = Vector(camera_plan["end_target"])
        camera.location = start_location
        camera.rotation_euler = _camera_rotation(start_location, start_target)
        inserted = 0
        movement = camera_plan["movement"]
        if movement != "static":
            for frame, location, target in (
                (int(shot["start_frame"]), start_location, start_target),
                (int(shot["end_frame"]), end_location, end_target),
            ):
                camera.location = location
                camera.rotation_euler = _camera_rotation(location, target)
                camera.keyframe_insert(data_path="location", frame=frame,
                                       group="PIPE_CameraMove")
                camera.keyframe_insert(data_path="rotation_euler", frame=frame,
                                       group="PIPE_CameraMove")
                inserted += 2
            if camera.animation_data and camera.animation_data.action:
                for curve in camera.animation_data.action.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "BEZIER"
                        point.handle_left_type = "AUTO_CLAMPED"
                        point.handle_right_type = "AUTO_CLAMPED"
        camera["pipeline_shot_id"] = shot["shot_id"]
        camera["pipeline_composition"] = blocking["composition"]
        camera["pipeline_camera_movement"] = movement
        camera["pipeline_adaptive"] = bool(camera_plan.get("adaptive", False))
        camera["pipeline_required_region"] = camera_plan.get("required_region", "full_body")
        camera["pipeline_frame_margin"] = float(
            camera_plan.get("frame_margin_fraction", 0.04)
        )
        return camera, int(movement != "static"), inserted

    target = target_point(shot.get("target"))
    shot_type = shot.get("shot_type", "medium")
    presets = {
        "close_up": (float(settings.get("close_up_distance", 4.2)), 72.0, 1.88),
        "medium": (float(settings.get("medium_distance", 6.4)), 58.0, 1.62),
        "wide": (float(settings.get("wide_distance", 8.6)), 48.0, 1.48),
        "long": (float(settings.get("wide_distance", 8.6)), 48.0, 1.48),
    }
    distance, lens, target_height = presets.get(shot_type, presets["medium"])
    if not shot.get("target") or shot_type in {"wide", "long"}:
        target = Vector((0, 0, target_height))
    else:
        target.z = target_height
    location = target + Vector((0, -distance, 0.15 if shot_type == "close_up" else 0.0))
    data = bpy.data.cameras.new(f"PIPE_{shot['shot_id']}_Data")
    data.lens = lens
    camera = bpy.data.objects.new(f"PIPE_{shot['shot_id']}_Camera", data)
    camera_collection().objects.link(camera)
    camera.location = location
    camera.rotation_euler = _camera_rotation(camera.location, target)
    camera["pipeline_shot_id"] = shot["shot_id"]
    return camera, 0, 0


def assemble_cameras(manifest: dict) -> tuple[int, int, int, list[dict]]:
    scene = bpy.context.scene
    for marker in list(scene.timeline_markers):
        if marker.name.startswith("PIPE_"):
            scene.timeline_markers.remove(marker)
    first = None
    camera_movements = 0
    camera_keyframes = 0
    audits = []
    blocking = {
        shot["shot_id"]: shot
        for shot in manifest.get("blocking", {}).get("shots", [])
    }
    adaptive = bool(manifest.get("harmonization", {}).get("enabled", False))
    for shot in manifest["shots"]:
        scene.frame_set(int(shot["start_frame"]))
        bpy.context.view_layer.update()
        shot_blocking = blocking.get(shot["shot_id"])
        if not shot_blocking:
            shot_type = shot.get("shot_type")
            composition = (
                "close_up" if shot_type == "close_up"
                else "two_shot" if shot_type in {"wide", "long"}
                else "single"
            )
            fallback_cast = [
                {"character": item["character"]}
                for item in manifest.get("harmonization", {}).get("characters", [])
            ] if composition == "two_shot" else []
            shot_blocking = {
                "composition": composition, "subject": shot.get("target"),
                "listener": None, "placements": fallback_cast,
                "camera": {"movement": "static"},
            }
        if adaptive:
            plan, _basis = adaptive_camera_contract(manifest, shot, shot_blocking)
            shot_blocking = dict(shot_blocking)
            shot_blocking["camera"] = plan
        camera, moved, inserted = create_camera(
            shot, manifest.get("camera", {}), shot_blocking
        )
        camera_movements += moved
        camera_keyframes += inserted
        marker = scene.timeline_markers.new(f"PIPE_{shot['shot_id']}", frame=shot["start_frame"])
        marker.camera = camera
        first = first or camera
        if adaptive:
            audits.append(audit_camera_framing(manifest, shot, shot_blocking, camera))
    if first:
        scene.camera = first
    return len(manifest["shots"]), camera_movements, camera_keyframes, audits


def animate_blocking(manifest: dict) -> tuple[int, int, int]:
    blocking = manifest.get("blocking", {})
    shots = blocking.get("shots", []) if blocking.get("enabled", False) else []
    placements = 0
    body_facings = 0
    inserted = 0
    touched = set()
    for shot in shots:
        start, end = int(shot["start_frame"]), int(shot["end_frame"])
        for placement in shot["placements"]:
            armature = armature_for(placement["character"])
            control = character_root_for(placement["character"], armature)
            control.rotation_mode = "XYZ"
            location = Vector(placement["position"])
            location.x += float(control.get("pipeline_stage_offset_x", 0.0))
            location.y += float(control.get("pipeline_stage_offset_y", 0.0))
            location.z += float(control.get("pipeline_ground_offset_z", control.location.z))
            yaw = math.radians(float(placement["body_yaw_degrees"]))
            base_yaw = float(control.get("pipeline_base_yaw_radians", 0.0))
            for frame in (start, end):
                control.location = location
                control.rotation_euler.z = base_yaw + yaw
                control.keyframe_insert(data_path="location", frame=frame,
                                        group="PIPE_Blocking")
                control.keyframe_insert(data_path="rotation_euler", index=2, frame=frame,
                                        group="PIPE_Blocking")
                inserted += 2
            placements += 1
            body_facings += placement.get("facing_target") is not None
            touched.add(control.name)
    for name in touched:
        armature = bpy.data.objects.get(name)
        action = armature.animation_data.action if armature and armature.animation_data else None
        if not action:
            continue
        for curve in action.fcurves:
            if curve.data_path not in {"location", "rotation_euler"}:
                continue
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"
    return placements, body_facings, inserted


def add_sound_strip(editor, *, name: str, filepath: str, channel: int, frame_start: int):
    strips = getattr(editor, "strips", None)
    if strips is None:
        strips = editor.sequences
    try:
        return strips.new_sound(name=name, filepath=filepath, channel=channel,
                                frame_start=frame_start, stream=False)
    except TypeError:
        return strips.new_sound(name=name, filepath=filepath, channel=channel,
                                frame_start=frame_start)


def assemble_audio(project: Path, manifest: dict) -> int:
    scene = bpy.context.scene
    editor = scene.sequence_editor_create()
    for channel, line in enumerate(manifest["dialogue"], start=1):
        audio = (project / line["audio_path"]).resolve()
        strip = add_sound_strip(
            editor, name=f"PIPE_AUDIO_{line['line_id']}", filepath=str(audio),
            channel=channel, frame_start=line["start_frame"],
        )
        strip.volume = 1.0
    return len(manifest["dialogue"])


def configure_scene(project: Path, manifest: dict) -> Path:
    scene = bpy.context.scene
    render = manifest["render"]
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.resolution_percentage = render["resolution_percentage"]
    scene.render.fps = manifest["fps"]
    scene.render.fps_base = 1.0
    scene.frame_start = manifest["frame_start"]
    scene.frame_end = manifest["frame_end"]
    scene.sync_mode = "AUDIO_SYNC"
    image_settings = scene.render.image_settings
    if hasattr(image_settings, "media_type"):
        # Blender 5.x separates media type from the image-only file formats.
        image_settings.media_type = "VIDEO"
    else:
        # Blender 4.x and older expose FFmpeg as a file format directly.
        image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.audio_codec = "AAC"
    scene.render.ffmpeg.audio_bitrate = 192
    preview = (project / manifest["preview_video"]).resolve()
    preview.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(preview)
    scene["pipeline_phase"] = 3
    scene["pipeline_project"] = manifest["project_name"]
    return preview


def write_report(project: Path, manifest: dict, *, camera_count: int, audio_count: int,
                 mouth_targets: int, mouth_cues: int, performance_targets: int,
                 performance_clips: int, gestures: int, pose_keyframes: int,
                 skipped_bones: int, dialogue_beats: int, gaze_targets: int,
                 gaze_keyframes: int, blink_targets: int, blink_events: int,
                 blink_keyframes: int, listener_reactions: int,
                 performance_conflicts: int, blocking_shots: int,
                 character_placements: int, body_facings: int,
                 placement_keyframes: int, camera_movements: int,
                 camera_keyframes: int, framing_risks: int,
                 camera_collision_risks: int, continuity_violations: int,
                 blocking_conflicts: int, production_characters: int,
                 production_characters_loaded: int, resolved_character_bones: int,
                 resolved_character_mouth_morphs: int, character_texture_missing: int,
                 character_license_warnings: int, harmonization_results: list[dict],
                 camera_audits: list[dict], rendered: bool) -> Path:
    output_scene = (project / manifest["output_scene"]).resolve()
    preview = (project / manifest["preview_video"]).resolve()
    harmonization_enabled = bool(manifest.get("harmonization", {}).get("enabled", False))
    harmonization_ready = sum(item["ready"] for item in harmonization_results)
    neutral_ready = sum(item["neutral_pose_passed"] for item in harmonization_results)
    grounded = sum(item["grounding_passed"] for item in harmonization_results)
    axes_verified = sum(item["bone_axes_verified"] for item in harmonization_results)
    adaptive_passed = sum(item["framing_passed"] for item in camera_audits)
    phase8_issues = (
        sum(not item["ready"] for item in harmonization_results)
        + sum(not item["framing_passed"] for item in camera_audits)
    )
    report = {
        "phase": 3, "status": "complete", "fps": manifest["fps"],
        "frame_start": manifest["frame_start"], "frame_end": manifest["frame_end"],
        "camera_count": camera_count, "audio_strip_count": audio_count,
        "mouth_target_count": mouth_targets, "mouth_cue_count": mouth_cues,
        "performance_target_count": performance_targets,
        "performance_clip_count": performance_clips,
        "gesture_count": gestures, "pose_keyframe_count": pose_keyframes,
        "skipped_bone_alias_count": skipped_bones,
        "dialogue_beat_count": dialogue_beats,
        "gaze_target_count": gaze_targets, "gaze_keyframe_count": gaze_keyframes,
        "blink_target_count": blink_targets, "blink_event_count": blink_events,
        "blink_keyframe_count": blink_keyframes,
        "listener_reaction_count": listener_reactions,
        "performance_conflict_count": performance_conflicts,
        "blocking_shot_count": blocking_shots,
        "character_placement_count": character_placements,
        "body_facing_count": body_facings,
        "placement_keyframe_count": placement_keyframes,
        "camera_motion_count": camera_movements,
        "camera_keyframe_count": camera_keyframes,
        "framing_risk_count": framing_risks,
        "camera_collision_risk_count": camera_collision_risks,
        "continuity_violation_count": continuity_violations,
        "blocking_conflict_count": blocking_conflicts,
        "production_character_count": production_characters,
        "production_character_loaded_count": production_characters_loaded,
        "resolved_character_bone_alias_count": resolved_character_bones,
        "resolved_character_mouth_morph_count": resolved_character_mouth_morphs,
        "character_texture_missing_count": character_texture_missing,
        "character_license_warning_count": character_license_warnings,
        "harmonization_enabled": harmonization_enabled,
        "harmonization_character_count": len(harmonization_results),
        "harmonization_ready_count": harmonization_ready,
        "neutral_pose_character_count": neutral_ready,
        "grounded_character_count": grounded,
        "bone_axes_verified_count": axes_verified,
        "adaptive_camera_shot_count": len(camera_audits),
        "adaptive_camera_pass_count": adaptive_passed,
        "phase8_issue_count": phase8_issues,
        "phase8_report": manifest.get("harmonization", {}).get(
            "report", "generated/phase8_harmonization_report.json"
        ),
        "scene_file": output_scene.relative_to(project).as_posix(),
        "preview_video": preview.relative_to(project).as_posix() if rendered else None,
    }
    report_path = project / "generated" / "phase3_scene_report.json"
    atomic_write_json(report_path, report)
    return report_path


def write_phase8_report(project: Path, manifest: dict, characters: list[dict],
                        shots: list[dict]) -> Path:
    contract = manifest.get("harmonization", {})
    enabled = bool(contract.get("enabled", False))
    ready = sum(item["ready"] for item in characters)
    neutral = sum(item["neutral_pose_passed"] for item in characters)
    scaled = sum(
        item["height_error_ratio"] <= float(contract.get("height_tolerance_ratio", 0.02))
        for item in characters
    )
    grounded = sum(item["grounding_passed"] for item in characters)
    axes = sum(item["bone_axes_verified"] for item in characters)
    source_ik = sum(item["foot_lock_mode"] == "source_ik" for item in characters)
    framed = sum(item["framing_passed"] for item in shots)
    issues = sum(not item["ready"] for item in characters) + sum(
        not item["framing_passed"] for item in shots
    )
    report = {
        "schema_version": 1,
        "phase": 8,
        "status": "skipped" if not enabled else "complete" if issues == 0 else "failed",
        "enabled": enabled,
        "project_name": manifest["project_name"],
        "frame_start": int(manifest["frame_start"]),
        "frame_end": int(manifest["frame_end"]),
        "pose": contract.get("pose", "neutral_dialogue"),
        "characters": characters,
        "shots": shots,
        "summary": {
            "character_count": len(characters),
            "ready_character_count": ready,
            "neutral_pose_character_count": neutral,
            "scaled_character_count": scaled,
            "grounded_character_count": grounded,
            "bone_axes_verified_count": axes,
            "source_ik_character_count": source_ik,
            "root_grounded_character_count": len(characters) - source_ik,
            "adaptive_camera_shot_count": len(shots),
            "framing_passed_shot_count": framed,
            "issue_count": issues,
        },
    }
    relative = contract.get("report", "generated/phase8_harmonization_report.json")
    report_path = (project / relative).resolve()
    try:
        report_path.relative_to(project.resolve())
    except ValueError as exc:
        raise RuntimeError("Phase 8 report path escaped the project directory") from exc
    atomic_write_json(report_path, report)
    return report_path


def main() -> None:
    args = arguments()
    project = args.project.resolve()
    manifest = load_json(project / "generated" / "phase3_manifest.json")
    preview = configure_scene(project, manifest)
    character_assets = manifest.get("character_assets", {})
    (production_characters_loaded, resolved_character_bones,
     resolved_character_mouth_morphs, character_texture_missing,
     character_license_warnings) = load_character_assets(project, manifest)
    harmonization_results = harmonize_characters(manifest)
    audio_count = assemble_audio(project, manifest)
    performance_targets, performance_clips, gestures, pose_keyframes, skipped_bones = (
        animate_performances(manifest)
    )
    character_placements, body_facings, placement_keyframes = animate_blocking(manifest)
    gaze_targets, gaze_keyframes = animate_gaze(manifest)
    blink_targets, blink_events, blink_keyframes = animate_blinks(manifest)
    mouth_targets, mouth_cues = animate_dialogue(manifest)
    camera_count, camera_movements, camera_keyframes, camera_audits = assemble_cameras(manifest)
    direction = manifest.get("performance", {})
    blocking = manifest.get("blocking", {})

    output_scene = (project / manifest["output_scene"]).resolve()
    output_scene.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.frame_set(manifest["frame_start"])
    bpy.ops.wm.save_as_mainfile(filepath=str(output_scene))
    phase8_report = write_phase8_report(
        project, manifest, harmonization_results, camera_audits
    )
    phase8_issues = (
        sum(not item["ready"] for item in harmonization_results)
        + sum(not item["framing_passed"] for item in camera_audits)
    )
    phase8_enabled = bool(manifest.get("harmonization", {}).get("enabled", False))
    render_allowed = not phase8_enabled or phase8_issues == 0
    if args.render and render_allowed:
        bpy.ops.render.render(animation=True)
    actual_framing_risks = (
        sum(not item["framing_passed"] for item in camera_audits)
        if phase8_enabled else int(blocking.get("framing_risk_count", 0))
    )
    report = write_report(
        project, manifest, camera_count=camera_count, audio_count=audio_count,
        mouth_targets=mouth_targets, mouth_cues=mouth_cues,
        rendered=args.render and render_allowed,
        performance_targets=performance_targets, performance_clips=performance_clips,
        gestures=gestures, pose_keyframes=pose_keyframes, skipped_bones=skipped_bones,
        dialogue_beats=int(direction.get("dialogue_beat_count", 0)),
        gaze_targets=gaze_targets, gaze_keyframes=gaze_keyframes,
        blink_targets=blink_targets, blink_events=blink_events,
        blink_keyframes=blink_keyframes,
        listener_reactions=int(direction.get("listener_reaction_count", 0)),
        performance_conflicts=int(direction.get("performance_conflict_count", 0)),
        blocking_shots=len(blocking.get("shots", [])),
        character_placements=character_placements, body_facings=body_facings,
        placement_keyframes=placement_keyframes,
        camera_movements=camera_movements, camera_keyframes=camera_keyframes,
        framing_risks=actual_framing_risks,
        camera_collision_risks=int(blocking.get("camera_collision_risk_count", 0)),
        continuity_violations=int(blocking.get("continuity_violation_count", 0)),
        blocking_conflicts=int(blocking.get("blocking_conflict_count", 0)),
        production_characters=int(character_assets.get("configured_count", 0)),
        production_characters_loaded=production_characters_loaded,
        resolved_character_bones=resolved_character_bones,
        resolved_character_mouth_morphs=resolved_character_mouth_morphs,
        character_texture_missing=character_texture_missing,
        character_license_warnings=character_license_warnings,
        harmonization_results=harmonization_results,
        camera_audits=camera_audits,
    )
    if phase8_enabled and not render_allowed:
        raise RuntimeError(
            f"Phase 8 blocked production with {phase8_issues} harmonization/framing issue(s); "
            f"see {phase8_report}"
        )
    print(
        f"PHASE 3 BLENDER COMPLETE: {camera_count} cameras, {audio_count} audio strips, "
        f"{mouth_cues} mouth cues, {performance_clips} performance clips, "
        f"{gestures} gestures, {pose_keyframes} pose keyframes, "
        f"{direction.get('dialogue_beat_count', 0)} dialogue beats, "
        f"{gaze_targets} gaze targets/{gaze_keyframes} gaze keys, "
        f"{blink_events} blinks/{blink_keyframes} blink keys, "
        f"{direction.get('listener_reaction_count', 0)} listener reactions, "
        f"{len(blocking.get('shots', []))} blocking shots/{character_placements} placements, "
        f"{camera_movements} camera moves/{camera_keyframes} camera keys, "
        f"{production_characters_loaded} production character(s), "
        f"{resolved_character_bones} resolved bones/{resolved_character_mouth_morphs} mouth morphs, "
        f"{character_texture_missing} missing character textures, "
        f"{len(harmonization_results)} harmonized character(s)/{phase8_issues} Phase 8 issues, "
        f"{actual_framing_risks} framing risks, "
        f"{blocking.get('camera_collision_risk_count', 0)} camera collision risks, "
        f"{skipped_bones} skipped aliases, scene={output_scene}, "
        f"preview={preview if args.render else 'not rendered'}, "
        f"phase8_report={phase8_report}, report={report}"
    )


if __name__ == "__main__":
    main()
