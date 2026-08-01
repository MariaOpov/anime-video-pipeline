"""Phase 3 manifest preparation for deterministic Blender scene assembly."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .io_utils import atomic_write_json, load_json, validate


def seconds_to_frame(seconds: float, fps: int) -> int:
    """Convert absolute seconds to Blender's one-based timeline frame."""
    if seconds < 0 or fps <= 0:
        raise ValueError("seconds must be non-negative and fps must be positive")
    return round(seconds * fps) + 1


class Phase3Planner:
    def __init__(self, config: ProjectConfig, schemas: Path):
        self.config = config
        self.schemas = schemas
        self.settings = config.data.get("phase3", {})

    def build(self) -> dict[str, Any]:
        if not self.settings.get("enabled", False):
            raise ValueError("Phase 3 is disabled in project.yaml")

        generated = self.config.generated_dir
        shot_list = self._validated_json(
            generated / "shot_list.json", None, "Phase 1 shot list"
        )
        timeline = self._validated_json(
            generated / "dialogue_timeline.json",
            self.schemas / "dialogue_timeline.schema.json",
            "Phase 2 dialogue timeline",
        )
        if int(shot_list.get("fps", 0)) != self.config.fps or int(timeline["fps"]) != self.config.fps:
            raise ValueError("Phase 1, Phase 2, and project FPS values do not match")

        base_scene = self._project_path("base_scene", "blender_scenes/demo_mannequins.blend")
        if not base_scene.is_file():
            raise ValueError(f"Phase 3 base scene not found: {base_scene}. Run run_step2.ps1")
        output_scene = self._project_path("output_scene", "blender_scenes/phase3_assembled.blend")
        preview_video = self._project_path("preview_video", "renders/phase3_preview.mp4")

        shots = []
        known_shots: set[str] = set()
        for shot in shot_list.get("shots", []):
            shot_id = shot["shot_id"]
            if shot_id in known_shots:
                raise ValueError(f"Duplicate shot in shot_list.json: {shot_id}")
            known_shots.add(shot_id)
            start = float(shot["start_seconds"])
            end = float(shot["end_seconds"])
            if end <= start:
                raise ValueError(f"Invalid timing for shot: {shot_id}")
            camera = shot.get("camera", {})
            shots.append({
                "scene_id": shot["scene_id"], "shot_id": shot_id,
                "start_frame": seconds_to_frame(start, self.config.fps),
                "end_frame": max(seconds_to_frame(start, self.config.fps),
                                 round(end * self.config.fps)),
                "shot_type": camera.get("shot_type", "medium"),
                "movement": camera.get("movement", "static"),
                "target": camera.get("target"),
            })

        dialogue = []
        cue_total = 0
        for line in timeline["lines"]:
            if line["shot_id"] not in known_shots:
                raise ValueError(f"Dialogue references unknown shot: {line['shot_id']}")
            audio_path = (self.config.project_dir / line["audio_path"]).resolve()
            if not audio_path.is_file():
                raise ValueError(f"Dialogue WAV not found: {audio_path}. Run Phase 2")
            lip_path = self.config.project_dir / "lip_sync" / f"{line['line_id']}.json"
            lip_sync = self._validated_json(
                lip_path, self.schemas / "lip_sync.schema.json",
                f"lip sync {line['line_id']}",
            )
            if lip_sync["line_id"] != line["line_id"] or lip_sync["character"] != line["character"]:
                raise ValueError(f"Lip-sync identity mismatch for {line['line_id']}")
            duration = float(line["duration_seconds"])
            for cue in lip_sync["mouth_cues"]:
                if float(cue["end"]) > duration + 0.1:
                    raise ValueError(f"Mouth cue exceeds dialogue duration: {line['line_id']}")
            cue_total += len(lip_sync["mouth_cues"])
            dialogue.append({
                "line_id": line["line_id"], "shot_id": line["shot_id"],
                "character": line["character"], "audio_path": line["audio_path"],
                "start_frame": int(line["start_frame"]), "end_frame": int(line["end_frame"]),
                "start_seconds": float(line["start_seconds"]),
                "duration_seconds": duration, "mouth_cues": lip_sync["mouth_cues"],
            })

        total_seconds = max(float(shot_list.get("total_duration_seconds", 0)),
                            float(timeline.get("total_duration_seconds", 0)))
        output = self.config.data["output"]
        manifest = {
            "version": 1, "project_name": self.config.data["project_name"],
            "fps": self.config.fps, "frame_start": 1,
            "frame_end": max(1, math.ceil(total_seconds * self.config.fps)),
            "base_scene": base_scene.relative_to(self.config.project_dir).as_posix(),
            "output_scene": output_scene.relative_to(self.config.project_dir).as_posix(),
            "preview_video": preview_video.relative_to(self.config.project_dir).as_posix(),
            "render": {
                "engine": self.config.data.get("render_engine", "BLENDER_EEVEE"),
                "width": int(output["width"]), "height": int(output["height"]),
                "resolution_percentage": int(self.settings.get("resolution_percentage", 100)),
            },
            "camera": self.settings.get("camera", {}),
            "shots": shots, "dialogue": dialogue,
            "summary": {"shot_count": len(shots), "dialogue_count": len(dialogue),
                        "mouth_cue_count": cue_total},
        }
        validate(manifest, self.schemas / "phase3_manifest.schema.json", "Phase 3 manifest")
        return manifest

    def write(self, manifest: dict[str, Any] | None = None) -> Path:
        manifest = manifest or self.build()
        output = self.config.generated_dir / "phase3_manifest.json"
        atomic_write_json(output, manifest)
        return output

    def _project_path(self, key: str, default: str) -> Path:
        path = (self.config.project_dir / self.settings.get(key, default)).resolve()
        try:
            path.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"phase3.{key} must stay inside the project directory") from exc
        return path

    def _validated_json(self, path: Path, schema: Path | None, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError(f"Missing {label}: {path}")
        payload = load_json(path)
        if schema:
            validate(payload, schema, label)
        return payload
