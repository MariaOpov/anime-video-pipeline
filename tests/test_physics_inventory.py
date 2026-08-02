import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.io_utils import validate
from anime_pipeline.physics_inventory import (
    actual_output_dimensions,
    aggregate_character_inventories,
    inventory_consistency_issues,
)


class PhysicsInventoryTests(unittest.TestCase):
    def test_actual_output_dimensions_apply_percentage(self):
        self.assertEqual(actual_output_dimensions(1280, 720, 50), (640, 360))
        self.assertEqual(actual_output_dimensions(1280, 720, 100), (1280, 720))

    def test_actual_output_dimensions_reject_invalid_values(self):
        with self.assertRaises(ValueError):
            actual_output_dimensions(0, 720, 100)
        with self.assertRaises(ValueError):
            actual_output_dimensions(1280, 720, 0)

    def test_aggregate_character_inventories_sums_stable_counts(self):
        summary = aggregate_character_inventories([
            {"rigid_body_count": 3, "joint_count": 2, "object_count": 10},
            {"rigid_body_count": 4, "joint_count": 1, "object_count": 20},
        ], issue_count=1, warning_count=2)
        self.assertEqual(summary["character_count"], 2)
        self.assertEqual(summary["rigid_body_count"], 7)
        self.assertEqual(summary["joint_count"], 3)
        self.assertEqual(summary["object_count"], 30)
        self.assertEqual(summary["issue_count"], 1)
        self.assertEqual(summary["warning_count"], 2)

    def test_inventory_schema_and_consistency_accept_complete_report(self):
        character = {
            "character": "Ren",
            "profile_cache_collection": "PIPE_CHARACTER_REN",
            "resolved_collection": "PIPE_CHARACTER_REN",
            "armature_object": "PIPE_Ren_Armature",
            "object_count": 3,
            "mesh_count": 2,
            "visible_mesh_count": 1,
            "hidden_render_mesh_count": 1,
            "rigid_body_count": 1,
            "mmd_rigid_body_count": 1,
            "blender_rigid_body_count": 1,
            "unbuilt_rigid_body_count": 0,
            "active_rigid_body_count": 1,
            "passive_rigid_body_count": 0,
            "kinematic_rigid_body_count": 0,
            "joint_count": 0,
            "mmd_joint_count": 0,
            "blender_constraint_count": 0,
            "broken_joint_reference_count": 0,
            "cloth_modifier_count": 0,
            "collision_modifier_count": 0,
            "physics_object_count": 1,
            "hidden_physics_object_count": 1,
            "physics_collection_count": 1,
            "collision_group_count": 1,
            "physics_built": True,
            "rigid_bodies": [{
                "object": "Rigid",
                "mmd_type": "RIGID_BODY",
                "hide_render": True,
                "hide_viewport": False,
                "blender_rigid_body_present": True,
                "blender_type": "ACTIVE",
                "kinematic": False,
                "collision_shape": "CAPSULE",
                "collision_margin": 0.0,
                "use_margin": True,
                "collision_collections": [True, False],
                "mass": 1.0,
                "friction": 0.5,
                "restitution": 0.0,
                "linear_damping": 0.04,
                "angular_damping": 0.1,
                "use_deactivation": False,
                "use_start_deactivated": False,
                "mmd_rigid_type": "1",
                "mmd_shape": "CAPSULE",
                "mmd_bone": "腕.L",
                "mmd_collision_group_number": 1,
                "mmd_collision_group_mask": [False, True],
                "collections": ["RigidBodies"]
            }],
            "joints": [],
            "modifiers": [],
            "physics_collections": ["RigidBodies"],
            "collision_groups": ["blender:0", "mmd:1"]
        }
        report = {
            "schema_version": 1,
            "phase": "8.1",
            "status": "complete",
            "source_kind": "character_cache",
            "source_file": "blender_cache/characters/ren.blend",
            "blender_version": "5.1.2",
            "scene": {
                "name": "Scene",
                "frame_start": 1,
                "frame_end": 366,
                "frame_current": 1,
                "render_engine": "BLENDER_EEVEE",
                "render_width": 1280,
                "render_height": 720,
                "resolution_percentage": 50,
                "actual_output_width": 640,
                "actual_output_height": 360
            },
            "rigid_body_world": {
                "present": True,
                "enabled": True,
                "collection": "RigidBodyWorld",
                "constraint_collection": "RigidBodyConstraints",
                "substeps_per_frame": 10,
                "solver_iterations": 10,
                "time_scale": 1.0,
                "use_split_impulse": False,
                "point_cache": {
                    "frame_start": 1,
                    "frame_end": 366,
                    "frame_step": 1,
                    "is_baked": False,
                    "is_baking": False,
                    "is_outdated": False,
                    "use_disk_cache": False,
                    "use_library_path": False,
                    "compression": "NO",
                    "name": "Cache",
                    "index": 0
                }
            },
            "characters": [character],
            "issues": [],
            "warnings": [],
            "summary": aggregate_character_inventories([character])
        }
        root = Path(__file__).resolve().parents[1]
        validate(
            report,
            root / "schemas" / "phase8_1_physics_inventory.schema.json",
            "Phase 8.1 physics inventory",
        )
        self.assertEqual(inventory_consistency_issues(report), [])


if __name__ == "__main__":
    unittest.main()
