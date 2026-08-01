"""Project configuration loading and path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import load_yaml, validate


@dataclass(frozen=True)
class ProjectConfig:
    project_dir: Path
    data: dict[str, Any]

    @property
    def generated_dir(self) -> Path:
        return self.project_dir / "generated"

    @property
    def script_path(self) -> Path:
        return self.project_dir / self.data.get("script", "script.txt")

    @property
    def fps(self) -> int:
        return int(self.data["output"]["fps"])

    @property
    def asset_paths(self) -> list[Path]:
        raw_paths = self.data.get("asset_library_paths", ["assets"])
        return [(self.project_dir / value).resolve() for value in raw_paths]


def load_config(project_dir: Path, schema_dir: Path, preset_override: str | None) -> ProjectConfig:
    config_path = project_dir / "project.yaml"
    if not config_path.is_file():
        raise ValueError(f"Missing project configuration: {config_path}")
    data = load_yaml(config_path)
    if preset_override:
        data["preset"] = preset_override
    validate(data, schema_dir / "project.schema.json", "project.yaml")
    script_path = project_dir / data.get("script", "script.txt")
    if not script_path.is_file():
        raise ValueError(f"Missing script: {script_path}")
    return ProjectConfig(project_dir=project_dir, data=data)

