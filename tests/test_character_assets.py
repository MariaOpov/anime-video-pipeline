import sys
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anime_pipeline.character_assets import (
    BONE_ALIASES,
    build_character_contract,
    inspect_source_bundle,
    match_aliases,
    profile_coverage,
    safe_slug,
    stage_source_bundle,
    update_registry,
)
from anime_pipeline.io_utils import atomic_write_json


class CharacterAssetTests(unittest.TestCase):
    def setUp(self):
        self.schemas = Path(__file__).resolve().parents[1] / "schemas"

    def test_inspects_and_stages_complete_unicode_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            model = source / "芙拉薇娅.pmx"
            model.write_bytes(b"PMX fixture")
            (source / "1.png").write_bytes(b"texture")
            (source / "metal.spa").write_bytes(b"sphere texture")
            inspection = inspect_source_bundle(model)
            self.assertEqual(inspection["format"], "pmx")
            self.assertEqual(inspection["discovered_texture_count"], 2)
            staged, staged_inspection = stage_source_bundle(model, root / "local")
            self.assertTrue(staged.is_file())
            self.assertTrue((staged.parent / "1.png").is_file())
            self.assertEqual(staged_inspection["model_sha256"], inspection["model_sha256"])
            staged_texture = staged.parent / "1.png"
            staged_texture.chmod(stat.S_IREAD)
            try:
                with patch(
                    "anime_pipeline.character_assets.shutil.copy2",
                    side_effect=AssertionError("identical staged files must not be overwritten"),
                ):
                    staged_again, _ = stage_source_bundle(model, root / "local")
                self.assertEqual(staged_again, staged)
            finally:
                staged_texture.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_alias_mapping_and_coverage_accept_mmd_suffix_side_names(self):
        bones = match_aliases(
            ["上半身2", "頭", "腕.L", "腕.R", "足.L", "足.R", "両目"],
            BONE_ALIASES,
        )
        coverage = profile_coverage({
            "bone_mapping": bones,
            "morph_mapping": {"A": "あ", "I": "い", "U": "う", "E": "え",
                              "O": "お", "blink": "まばたき"},
        })
        self.assertEqual(coverage["bone_coverage"], 1.0)
        self.assertEqual(coverage["mouth_morph_coverage"], 1.0)
        self.assertTrue(coverage["blink_morph_resolved"])

    def test_unicode_character_name_gets_stable_safe_slug(self):
        self.assertEqual(safe_slug("Aiko Demo"), "aiko-demo")
        self.assertEqual(safe_slug("芙拉薇娅"), safe_slug("芙拉薇娅"))
        self.assertTrue(safe_slug("芙拉薇娅").startswith("character-"))

    def test_valid_profile_becomes_ready_manifest_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            profile_path = project / "local_assets" / "characters" / "aiko" / "character.profile.json"
            cache_path = project / "blender_cache" / "characters" / "aiko.blend"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_bytes(b"BLENDER" * 200)
            profile = self._profile()
            atomic_write_json(profile_path, profile)
            update_registry(project, "local_assets/character_registry.json", "Aiko",
                            profile_path.relative_to(project).as_posix())
            contract = build_character_contract(project, {
                "enabled": True, "registry": "local_assets/character_registry.json",
                "minimum_bone_alias_coverage": 1.0,
                "minimum_mouth_morph_coverage": 1.0,
                "require_blink_morph": True, "require_complete_textures": True,
                "require_license_metadata": False,
            }, self.schemas)
            self.assertEqual(contract["configured_count"], 1)
            self.assertEqual(contract["ready_count"], 1)
            self.assertTrue(contract["characters"][0]["ready"])
            self.assertEqual(contract["characters"][0]["resolved_bone_count"], 6)

    @staticmethod
    def _profile():
        return {
            "schema_version": 1, "character": "Aiko",
            "source_model": "local_assets/characters/aiko/bundles/abc/model.pmx",
            "model_format": "pmx", "model_sha256": "a" * 64,
            "cache_blend": "blender_cache/characters/aiko.blend",
            "cache_collection": "PIPE_CHARACTER_AIKO",
            "armature_object": "PIPE_Aiko_Armature", "target_height_meters": 1.72,
            "dimensions": [0.6, 0.4, 1.72], "object_count": 4, "mesh_count": 2,
            "material_count": 3, "bone_count": 30, "morph_count": 12,
            "texture_count": 3, "missing_texture_count": 0,
            "bone_mapping": {"spine": "上半身", "head": "頭", "arm.L": "左腕",
                             "arm.R": "右腕", "leg.L": "左足", "leg.R": "右足",
                             "eyes": "両目"},
            "morph_mapping": {"A": "あ", "I": "い", "U": "う", "E": "え",
                              "O": "お", "blink": "まばたき"},
            "license": {"name": "Unknown", "creator": "Unknown", "source": "Unknown"},
            "warnings": [],
        }


if __name__ == "__main__":
    unittest.main()
