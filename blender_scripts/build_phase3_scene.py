"""Assemble cameras, dialogue audio, and mouth animation in Blender.

Run with Blender, not system Python:
    blender --background base.blend --python blender_scripts/build_phase3_scene.py -- \
        --project projects/demo [--render]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


MOUTH_SHAPES = {
    "closed": (1.00, 0.16), "neutral": (1.00, 0.35),
    "A": (0.80, 1.45), "I": (1.55, 0.42), "U": (0.62, 0.92),
    "E": (1.30, 0.68), "O": (0.72, 1.22),
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--render", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


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


def create_mouth(character: str):
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


def insert_mouth_pose(mouth, frame: int, active_shape: str) -> None:
    keys = mouth.data.shape_keys.key_blocks
    if active_shape not in keys:
        active_shape = "neutral" if "neutral" in keys else "closed"
    for name in MOUTH_SHAPES:
        if name not in keys:
            continue
        key = keys[name]
        key.value = 1.0 if name == active_shape else 0.0
        key.keyframe_insert(data_path="value", frame=frame, group="PIPE_Mouth")


def animate_dialogue(manifest: dict) -> tuple[int, int]:
    fps = manifest["fps"]
    targets = {}
    applied_cues = 0
    for line in manifest["dialogue"]:
        character = line["character"]
        mouth = targets.setdefault(character, create_mouth(character))
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
            insert_mouth_pose(mouth, frame, shape)
    return len(targets), applied_cues


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
    return armature.matrix_world @ Vector((0, 0, 1.65))


def create_camera(shot: dict, settings: dict):
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
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera["pipeline_shot_id"] = shot["shot_id"]
    return camera


def assemble_cameras(manifest: dict) -> int:
    scene = bpy.context.scene
    for marker in list(scene.timeline_markers):
        if marker.name.startswith("PIPE_"):
            scene.timeline_markers.remove(marker)
    first = None
    for shot in manifest["shots"]:
        camera = create_camera(shot, manifest.get("camera", {}))
        marker = scene.timeline_markers.new(f"PIPE_{shot['shot_id']}", frame=shot["start_frame"])
        marker.camera = camera
        first = first or camera
    if first:
        scene.camera = first
    return len(manifest["shots"])


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
                 mouth_targets: int, mouth_cues: int, rendered: bool) -> Path:
    output_scene = (project / manifest["output_scene"]).resolve()
    preview = (project / manifest["preview_video"]).resolve()
    report = {
        "phase": 3, "status": "complete", "fps": manifest["fps"],
        "frame_start": manifest["frame_start"], "frame_end": manifest["frame_end"],
        "camera_count": camera_count, "audio_strip_count": audio_count,
        "mouth_target_count": mouth_targets, "mouth_cue_count": mouth_cues,
        "scene_file": output_scene.relative_to(project).as_posix(),
        "preview_video": preview.relative_to(project).as_posix() if rendered else None,
    }
    report_path = project / "generated" / "phase3_scene_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return report_path


def main() -> None:
    args = arguments()
    project = args.project.resolve()
    manifest = load_json(project / "generated" / "phase3_manifest.json")
    preview = configure_scene(project, manifest)
    camera_count = assemble_cameras(manifest)
    audio_count = assemble_audio(project, manifest)
    mouth_targets, mouth_cues = animate_dialogue(manifest)

    output_scene = (project / manifest["output_scene"]).resolve()
    output_scene.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.frame_set(manifest["frame_start"])
    bpy.ops.wm.save_as_mainfile(filepath=str(output_scene))
    if args.render:
        bpy.ops.render.render(animation=True)
    report = write_report(
        project, manifest, camera_count=camera_count, audio_count=audio_count,
        mouth_targets=mouth_targets, mouth_cues=mouth_cues, rendered=args.render,
    )
    print(
        f"PHASE 3 BLENDER COMPLETE: {camera_count} cameras, {audio_count} audio strips, "
        f"{mouth_cues} mouth cues, scene={output_scene}, "
        f"preview={preview if args.render else 'not rendered'}, report={report}"
    )


if __name__ == "__main__":
    main()
