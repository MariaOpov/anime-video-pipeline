import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.io_utils import validate
from anime_pipeline.physics_runtime import build_physics_contract


class PhysicsRuntimeTests(unittest.TestCase):
    def test_builds_negative_warmup_without_moving_render_timing(self):
        contract = build_physics_contract(
            {"enabled": True, "warmup_frames": 36},
            frame_start=1,
            frame_end=366,
        )
        self.assertTrue(contract["enabled"])
        self.assertEqual(contract["render_frame_start"], 1)
        self.assertEqual(contract["render_frame_end"], 366)
        self.assertEqual(contract["simulation_frame_start"], -35)
        self.assertEqual(contract["simulation_frame_end"], 366)

    def test_rejects_invalid_runtime_settings(self):
        with self.assertRaises(ValueError):
            build_physics_contract(
                {"enabled": True, "warmup_frames": -1},
                frame_start=1,
                frame_end=48,
            )
        with self.assertRaises(ValueError):
            build_physics_contract(
                {"enabled": True, "substeps_per_frame": 0},
                frame_start=1,
                frame_end=48,
            )

    def test_runtime_report_schema_accepts_complete_evidence(self):
        report = {
            "schema_version": 1,
            "phase": "8.1",
            "status": "complete",
            "enabled": True,
            "project_name": "Demo",
            "render_frame_start": 1,
            "render_frame_end": 366,
            "simulation_frame_start": -35,
            "simulation_frame_end": 366,
            "warmup_frames": 36,
            "warmup_evaluated_frame_count": 37,
            "render_timing_preserved": True,
            "rigid_body_world_present": True,
            "rigid_body_world_enabled": True,
            "rigid_body_collection": "PIPE_Phase8_1_RigidBodies",
            "constraint_collection": "PIPE_Phase8_1_Constraints",
            "rigid_body_count": 581,
            "constraint_count": 860,
            "hidden_render_rigid_body_count": 581,
            "substeps_per_frame": 10,
            "solver_iterations": 10,
            "cache_frame_start": -35,
            "cache_frame_end": 366,
            "cache_is_baked": False,
            "cache_is_outdated": False,
            "issues": [],
        }
        root = Path(__file__).resolve().parents[1]
        validate(
            report,
            root / "schemas" / "phase8_1_physics_report.schema.json",
            "Phase 8.1 runtime physics report",
        )


if __name__ == "__main__":
    unittest.main()
