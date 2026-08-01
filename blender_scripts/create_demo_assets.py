"""Create original CC0-style mannequin assets for pipeline integration tests.

Run with Blender, not system Python:
    blender --background --python blender_scripts/create_demo_assets.py -- --project projects/demo
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.armatures, bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.65):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def add_uv_sphere(name: str, location, scale, mat, parent=None, bone=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if parent:
        world_matrix = obj.matrix_world.copy()
        obj.parent = parent
        if bone:
            obj.parent_type = "BONE"
            obj.parent_bone = bone
        obj.matrix_world = world_matrix
    return obj


def add_cylinder(name: str, a: Vector, b: Vector, radius: float, mat, parent=None, bone=None):
    midpoint = (a + b) * 0.5
    delta = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=radius, depth=delta.length, location=midpoint)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(delta.normalized())
    obj.data.materials.append(mat)
    if parent:
        world_matrix = obj.matrix_world.copy()
        obj.parent = parent
        if bone:
            obj.parent_type = "BONE"
            obj.parent_bone = bone
        obj.matrix_world = world_matrix
    return obj


def create_armature(name: str, x: float):
    arm_data = bpy.data.armatures.new(f"{name}_ArmatureData")
    arm = bpy.data.objects.new(f"{name}_Armature", arm_data)
    bpy.context.collection.objects.link(arm)
    arm.location.x = x
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = {
        "root": ((0, 0, 0), (0, 0, 0.9), None),
        "spine": ((0, 0, 0.9), (0, 0, 1.7), "root"),
        "head": ((0, 0, 1.7), (0, 0, 2.25), "spine"),
        "arm.L": ((0, 0, 1.55), (0.75, 0, 1.25), "spine"),
        "arm.R": ((0, 0, 1.55), (-0.75, 0, 1.25), "spine"),
        "leg.L": ((0.18, 0, 0.9), (0.18, 0, 0.05), "root"),
        "leg.R": ((-0.18, 0, 0.9), (-0.18, 0, 0.05), "root"),
    }
    edit_bones = {}
    for bone_name, (head, tail, parent_name) in bones.items():
        bone = arm_data.edit_bones.new(bone_name)
        bone.head, bone.tail = head, tail
        if parent_name:
            bone.parent = edit_bones[parent_name]
        edit_bones[bone_name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.select_set(False)
    return arm


def create_character(name: str, x: float, body_color, accent_color):
    skin = material(f"{name}_Skin", (1.0, 0.72, 0.58, 1.0))
    body = material(f"{name}_Body", body_color)
    accent = material(f"{name}_Accent", accent_color)
    dark = material(f"{name}_Eyes", (0.025, 0.035, 0.055, 1.0), 0.35)
    arm = create_armature(name, x)
    add_uv_sphere(f"{name}_Head", (x, 0, 2.18), (0.34, 0.30, 0.38), skin, arm, "head")
    add_uv_sphere(f"{name}_Torso", (x, 0, 1.30), (0.43, 0.28, 0.65), body, arm, "spine")
    add_uv_sphere(f"{name}_Hip", (x, 0, 0.86), (0.36, 0.25, 0.25), accent, arm, "root")
    for side, sign in (("L", 1), ("R", -1)):
        add_cylinder(f"{name}_Arm.{side}", Vector((x, 0, 1.52)), Vector((x + 0.75 * sign, 0, 1.22)),
                     0.12, body, arm, f"arm.{side}")
        add_cylinder(f"{name}_Leg.{side}", Vector((x + 0.18 * sign, 0, 0.82)),
                     Vector((x + 0.18 * sign, 0, 0.08)), 0.14, accent, arm, f"leg.{side}")
    for sign in (-1, 1):
        add_uv_sphere(f"{name}_Eye_{sign}", (x + 0.105 * sign, -0.278, 2.25), (0.045, 0.025, 0.065), dark, arm, "head")
    arm["pipeline_character"] = name
    return arm


def keyframe_pose(arm, frame: int, values: dict[str, tuple[float, float, float]]) -> None:
    for bone_name, rotation in values.items():
        bone = arm.pose.bones[bone_name]
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = rotation
        bone.keyframe_insert("rotation_euler", frame=frame, group=bone_name)


def animate(arm, fps: int) -> None:
    # Four-second loop: subtle breathing plus restrained talking gesture.
    for frame, tilt, gesture in ((1, 0.0, 0.0), (25, 0.025, 0.14), (49, 0.0, -0.10),
                                 (73, -0.02, 0.10), (97, 0.0, 0.0)):
        keyframe_pose(arm, frame, {
            "spine": (tilt, 0, 0), "head": (-tilt * 0.5, 0, 0),
            "arm.L": (0, gesture, gesture * 0.35), "arm.R": (0, -gesture, -gesture * 0.35),
        })
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action.name = f"{arm['pipeline_character']}_IdleTalking"
        for curve in arm.animation_data.action.fcurves:
            for modifier in list(curve.modifiers):
                curve.modifiers.remove(modifier)
            curve.modifiers.new("CYCLES")


def environment():
    concrete = material("RooftopConcrete", (0.18, 0.21, 0.26, 1.0))
    rail = material("Railing", (0.04, 0.055, 0.08, 1.0), 0.4)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, -0.12), scale=(6, 4, 0.12))
    bpy.context.object.name = "Rooftop"
    bpy.context.object.data.materials.append(concrete)
    for x in (-5.6, 5.6):
        add_cylinder("RailingPost", Vector((x, 3.7, 0)), Vector((x, 3.7, 1.2)), 0.06, rail)
    add_cylinder("RailingTop", Vector((-5.6, 3.7, 1.2)), Vector((5.6, 3.7, 1.2)), 0.055, rail)


def camera_and_lights():
    bpy.ops.object.camera_add(location=(0, -8.5, 2.2), rotation=(math.radians(82), 0, 0))
    camera = bpy.context.object
    camera.name = "DemoCamera"
    bpy.context.scene.camera = camera
    direction = Vector((0, 0, 1.35)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 52
    bpy.ops.object.light_add(type="AREA", location=(-3, -3, 6))
    key = bpy.context.object
    key.name, key.data.energy, key.data.shape, key.data.size = "SunsetKey", 900, "DISK", 5.0
    key.data.color = (1.0, 0.48, 0.24)
    key.rotation_euler = (math.radians(25), 0, math.radians(-35))
    bpy.ops.object.light_add(type="AREA", location=(3, 1, 4))
    fill = bpy.context.object
    fill.name, fill.data.energy, fill.data.size = "SkyFill", 650, 4.0
    fill.data.color = (0.28, 0.42, 1.0)
    fill.rotation_euler = (math.radians(15), 0, math.radians(145))


def configure_scene(fps: int = 24):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
    scene.render.fps, scene.frame_start, scene.frame_end = fps, 1, 97
    scene.world.color = (0.035, 0.045, 0.08)


def main() -> None:
    args = arguments()
    project = args.project.resolve()
    characters_dir = project / "assets" / "characters"
    motions_dir = project / "assets" / "motions"
    scene_dir = project / "blender_scenes"
    for directory in (characters_dir, motions_dir, scene_dir):
        directory.mkdir(parents=True, exist_ok=True)
    clear_scene()
    environment()
    aiko = create_character("Aiko", -1.1, (0.12, 0.34, 0.72, 1), (0.09, 0.16, 0.32, 1))
    ren = create_character("Ren", 1.1, (0.48, 0.12, 0.18, 1), (0.12, 0.06, 0.08, 1))
    animate(aiko, 24)
    animate(ren, 24)
    camera_and_lights()
    configure_scene()
    scene_file = scene_dir / "demo_mannequins.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_file))
    # Separate physical files make the Phase 1 asset availability contract explicit.
    bpy.ops.wm.save_as_mainfile(filepath=str(characters_dir / "demo_characters.blend"), copy=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(motions_dir / "demo_motions.blend"), copy=True)
    print(f"DEMO ASSETS CREATED: {scene_file}")


if __name__ == "__main__":
    main()


