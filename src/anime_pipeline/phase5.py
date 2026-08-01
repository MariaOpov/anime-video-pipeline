"""Phase 5 production audit and release report generation."""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import ProjectConfig
from .io_utils import atomic_write_json, load_json, validate


class QualityGateError(RuntimeError):
    """Raised after a production report records one or more failed gates."""


class Phase5Auditor:
    def __init__(self, config: ProjectConfig, schemas: Path):
        self.config = config
        self.schemas = schemas
        self.settings = config.data.get("phase5", {})
        self.gates: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] = {
            "scene_count": 0, "shot_count": 0, "unresolved_motion_count": 0,
            "dialogue_count": 0, "mouth_cue_count": 0, "timing_warning_count": 0,
            "performance_clip_count": 0, "gesture_count": 0,
            "pose_keyframe_count": 0, "skipped_bone_alias_count": 0,
            "dialogue_beat_count": 0, "gaze_target_count": 0,
            "gaze_keyframe_count": 0, "blink_event_count": 0,
            "blink_keyframe_count": 0, "listener_reaction_count": 0,
            "performance_conflict_count": 0,
            "duration_seconds": 0, "output_size_bytes": 0, "output_width": 0,
            "output_height": 0, "estimated_cost": 0,
        }
        self.artifacts: list[dict[str, Any]] = []

    def run(self, *, blender: Path | None = None, run_record: Path | None = None,
            tool_versions: dict[str, str | None] | None = None) -> tuple[dict[str, Any], Path]:
        if not self.settings.get("enabled", False):
            raise ValueError("Phase 5 is disabled in project.yaml")

        self._audit_phase1()
        timeline = self._audit_phase2()
        manifest = self._audit_phase3(timeline)
        self._audit_phase4(timeline, manifest)

        failed = sum(gate["status"] == "failed" for gate in self.gates)
        run = self._read_run_record(run_record)
        report = {
            "schema_version": 1,
            "phase": 5,
            "status": "complete" if failed == 0 else "failed",
            "project_name": self.config.data["project_name"],
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pipeline_version": __version__,
            "tool_versions": tool_versions or self._tool_versions(blender),
            "run": run,
            "summary": {
                "quality_gate_count": len(self.gates),
                "passed_gate_count": len(self.gates) - failed,
                "failed_gate_count": failed,
                **self.metrics,
            },
            "quality_gates": self.gates,
            "artifacts": self.artifacts,
        }
        validate(report, self.schemas / "production_report.schema.json", "Phase 5 report")
        output = self._project_path("report", "generated/production_report.json")
        atomic_write_json(output, report)
        if failed:
            names = ", ".join(gate["name"] for gate in self.gates if gate["status"] == "failed")
            raise QualityGateError(f"{failed} Phase 5 quality gate(s) failed: {names}")
        return report, output

    def _audit_phase1(self) -> None:
        generated = self.config.generated_dir
        screenplay = self._json_gate(
            1, "screenplay_schema", generated / "screenplay.json",
            self.schemas / "screenplay.schema.json",
        )
        shot_list = self._json_gate(1, "shot_list_exists", generated / "shot_list.json")
        assets = self._json_gate(1, "asset_index_exists", generated / "asset_index.json")
        motions = self._json_gate(1, "motion_plan_exists", generated / "motion_plan.json")
        self._json_gate(1, "pipeline_state_exists", generated / "pipeline_state.json")

        screenplay_shots = sum(len(scene.get("shots", [])) for scene in screenplay.get("scenes", [])) if screenplay else 0
        flat_shots = len(shot_list.get("shots", [])) if shot_list else 0
        self._gate(1, "shot_count_matches", screenplay is not None and shot_list is not None and screenplay_shots == flat_shots,
                   screenplay_shots, flat_shots, "Screenplay and flattened shot list must agree")

        unresolved = 0
        if motions:
            unresolved = sum(
                assignment.get("motion_id") is None
                for shot in motions.get("shots", [])
                for assignment in shot.get("assignments", [])
            )
        maximum_unresolved = int(self.settings.get("max_unresolved_motion_assignments", 0))
        self._gate(1, "motion_assignments_resolved", motions is not None and unresolved <= maximum_unresolved,
                   f"<= {maximum_unresolved}", unresolved)

        warning_count = len(assets.get("warnings", [])) if assets else 0
        maximum_warnings = int(self.settings.get("max_asset_warnings", 0))
        self._gate(1, "asset_warnings_within_limit", assets is not None and warning_count <= maximum_warnings,
                   f"<= {maximum_warnings}", warning_count)
        self.metrics.update({"scene_count": len(screenplay.get("scenes", [])) if screenplay else 0,
                             "shot_count": flat_shots, "unresolved_motion_count": unresolved})

    def _audit_phase2(self) -> dict[str, Any] | None:
        timeline = self._json_gate(
            2, "dialogue_timeline_schema", self.config.generated_dir / "dialogue_timeline.json",
            self.schemas / "dialogue_timeline.schema.json",
        )
        if not timeline:
            self._gate(2, "dialogue_files_complete", False, "all WAV and lip-sync files", "timeline unavailable")
            return None

        warning_count = len(timeline.get("warnings", []))
        maximum_warnings = int(self.settings.get("max_timing_warnings", 0))
        self._gate(2, "timing_warnings_within_limit", warning_count <= maximum_warnings,
                   f"<= {maximum_warnings}", warning_count)

        complete = True
        cue_count = 0
        for line in timeline.get("lines", []):
            audio = self._resolve_project_relative(line.get("audio_path", ""))
            if not audio.is_file() or audio.stat().st_size <= 44:
                complete = False
            lip_path = self.config.project_dir / "lip_sync" / f"{line['line_id']}.json"
            try:
                lip = load_json(lip_path)
                validate(lip, self.schemas / "lip_sync.schema.json", f"lip sync {line['line_id']}")
                if lip.get("line_id") != line.get("line_id") or lip.get("character") != line.get("character"):
                    complete = False
                cue_count += len(lip.get("mouth_cues", []))
            except (OSError, ValueError, KeyError):
                complete = False
        line_count = len(timeline.get("lines", []))
        self._gate(2, "dialogue_files_complete", complete and line_count > 0,
                   f"{line_count} valid WAV/lip-sync pair(s)", f"{line_count if complete else 'incomplete'}")
        self._gate(2, "mouth_cues_generated", cue_count > 0, "> 0", cue_count)
        self.metrics.update({"dialogue_count": line_count, "mouth_cue_count": cue_count,
                             "timing_warning_count": warning_count})
        return timeline

    def _audit_phase3(self, timeline: dict[str, Any] | None) -> dict[str, Any] | None:
        generated = self.config.generated_dir
        manifest = self._json_gate(
            3, "phase3_manifest_schema", generated / "phase3_manifest.json",
            self.schemas / "phase3_manifest.schema.json",
        )
        scene_report = self._json_gate(3, "phase3_scene_report_exists", generated / "phase3_scene_report.json")
        if not manifest or not scene_report:
            self._gate(3, "blender_assembly_counts_match", False, "manifest counts", "report unavailable")
            self._gate(3, "phase3_artifacts_exist", False, "assembled scene and preview", "missing")
            return manifest

        summary = manifest["summary"]
        counts_match = (
            scene_report.get("status") == "complete"
            and int(scene_report.get("camera_count", -1)) == int(summary["shot_count"])
            and int(scene_report.get("audio_strip_count", -1)) == int(summary["dialogue_count"])
            and int(scene_report.get("mouth_cue_count", -1)) == int(summary["mouth_cue_count"])
            and int(scene_report.get("performance_clip_count", -1)) == int(summary["performance_clip_count"])
            and int(scene_report.get("gesture_count", -1)) == int(summary["gesture_count"])
            and int(scene_report.get("dialogue_beat_count", -1)) == int(summary["dialogue_beat_count"])
            and int(scene_report.get("gaze_target_count", -1)) == int(summary["gaze_target_count"])
            and int(scene_report.get("blink_event_count", -1)) == int(summary["blink_event_count"])
            and int(scene_report.get("listener_reaction_count", -1)) == int(summary["listener_reaction_count"])
            and int(scene_report.get("performance_conflict_count", -1)) == int(summary["performance_conflict_count"])
        )
        self._gate(3, "blender_assembly_counts_match", counts_match, summary, {
            "shot_count": scene_report.get("camera_count"),
            "dialogue_count": scene_report.get("audio_strip_count"),
            "mouth_cue_count": scene_report.get("mouth_cue_count"),
            "performance_clip_count": scene_report.get("performance_clip_count"),
            "gesture_count": scene_report.get("gesture_count"),
            "dialogue_beat_count": scene_report.get("dialogue_beat_count"),
            "gaze_target_count": scene_report.get("gaze_target_count"),
            "blink_event_count": scene_report.get("blink_event_count"),
            "listener_reaction_count": scene_report.get("listener_reaction_count"),
            "performance_conflict_count": scene_report.get("performance_conflict_count"),
        })
        expected_clips = int(summary["performance_clip_count"])
        pose_keyframes = int(scene_report.get("pose_keyframe_count", 0))
        skipped_bones = int(scene_report.get("skipped_bone_alias_count", 0))
        performance_ok = expected_clips == 0 or (
            int(scene_report.get("performance_clip_count", -1)) == expected_clips
            and pose_keyframes > 0 and skipped_bones == 0
        )
        self._gate(3, "procedural_gestures_applied", performance_ok,
                   "all performance clips keyed with 0 skipped bone aliases", {
                       "performance_clips": scene_report.get("performance_clip_count"),
                       "pose_keyframes": pose_keyframes, "skipped_bone_aliases": skipped_bones,
                   })
        expected_gaze = int(summary["gaze_target_count"])
        expected_blinks = int(summary["blink_event_count"])
        gaze_keys = int(scene_report.get("gaze_keyframe_count", 0))
        blink_keys = int(scene_report.get("blink_keyframe_count", 0))
        conflicts = int(scene_report.get("performance_conflict_count", -1))
        direction_ok = (
            int(scene_report.get("dialogue_beat_count", -1)) == int(summary["dialogue_beat_count"])
            and int(scene_report.get("listener_reaction_count", -1)) == int(summary["listener_reaction_count"])
            and conflicts == 0 and int(summary["performance_conflict_count"]) == 0
            and (expected_gaze == 0 or (
                int(scene_report.get("gaze_target_count", -1)) == expected_gaze and gaze_keys > 0
            ))
            and (expected_blinks == 0 or (
                int(scene_report.get("blink_event_count", -1)) == expected_blinks and blink_keys > 0
            ))
        )
        self._gate(3, "performance_direction_applied", direction_ok,
                   "all dialogue beats, gaze, blinks, and listener reactions applied with 0 conflicts", {
                       "dialogue_beats": scene_report.get("dialogue_beat_count"),
                       "gaze_targets": scene_report.get("gaze_target_count"),
                       "gaze_keyframes": gaze_keys,
                       "blink_events": scene_report.get("blink_event_count"),
                       "blink_keyframes": blink_keys,
                       "listener_reactions": scene_report.get("listener_reaction_count"),
                       "conflicts": conflicts,
                   })
        scene_path = self._resolve_project_relative(scene_report.get("scene_file", ""))
        preview_path = self._resolve_project_relative(scene_report.get("preview_video", ""))
        artifacts_exist = scene_path.is_file() and preview_path.is_file() and preview_path.stat().st_size > 0
        self._gate(3, "phase3_artifacts_exist", artifacts_exist, "assembled scene and non-empty preview",
                   {"scene": scene_path.is_file(), "preview": preview_path.is_file()})
        if scene_path.is_file():
            self._artifact("phase3_scene", scene_path)
        if preview_path.is_file():
            self._artifact("phase3_preview", preview_path)
        if timeline:
            self._gate(3, "timeline_dialogue_count_matches", len(timeline["lines"]) == summary["dialogue_count"],
                       len(timeline["lines"]), summary["dialogue_count"])
        self.metrics.update({
            "performance_clip_count": expected_clips,
            "gesture_count": int(summary["gesture_count"]),
            "pose_keyframe_count": pose_keyframes,
            "skipped_bone_alias_count": skipped_bones,
            "dialogue_beat_count": int(summary["dialogue_beat_count"]),
            "gaze_target_count": expected_gaze, "gaze_keyframe_count": gaze_keys,
            "blink_event_count": expected_blinks, "blink_keyframe_count": blink_keys,
            "listener_reaction_count": int(summary["listener_reaction_count"]),
            "performance_conflict_count": conflicts,
        })
        return manifest

    def _audit_phase4(self, timeline: dict[str, Any] | None,
                      manifest: dict[str, Any] | None) -> None:
        report = self._json_gate(4, "phase4_report_exists", self.config.generated_dir / "phase4_report.json")
        if not report:
            self._gate(4, "final_video_exists", False, "verified final MP4", "report unavailable")
            return

        self._gate(4, "phase4_status_complete", report.get("status") == "complete",
                   "complete", report.get("status"))

        output = self._resolve_project_relative(report.get("output_video", ""))
        subtitle = self._resolve_project_relative(report.get("subtitle_file", ""))
        minimum_size = int(self.settings.get("min_output_size_bytes", 1024))
        output_size = output.stat().st_size if output.is_file() else 0
        self._gate(4, "final_video_exists", output.is_file() and output_size >= minimum_size,
                   f">= {minimum_size} bytes", output_size)
        self._gate(4, "reported_output_size_matches", report.get("output_size_bytes") == output_size,
                   output_size, report.get("output_size_bytes"))
        self._gate(4, "subtitles_exist", subtitle.is_file() and subtitle.stat().st_size > 0,
                   "non-empty UTF-8 subtitle file", subtitle.is_file())
        expected_subtitles = len(timeline.get("lines", [])) if timeline else 0
        self._gate(4, "subtitle_count_matches", timeline is not None and report.get("subtitle_count") == expected_subtitles,
                   expected_subtitles, report.get("subtitle_count"))
        self._gate(4, "audio_normalized", report.get("audio_normalized") is True, True,
                   report.get("audio_normalized"))

        percentage = int(self.config.data.get("phase3", {}).get("resolution_percentage", 100))
        expected_width = round(int(self.config.data["output"]["width"]) * percentage / 100)
        expected_height = round(int(self.config.data["output"]["height"]) * percentage / 100)
        actual_size = [report.get("width"), report.get("height")]
        self._gate(4, "delivery_dimensions_match", actual_size == [expected_width, expected_height],
                   [expected_width, expected_height], actual_size)

        duration = float(report.get("duration_seconds", 0))
        expected_duration = float(manifest["frame_end"]) / float(manifest["fps"]) if manifest else 0
        tolerance = float(self.settings.get("duration_tolerance_seconds", 0.25))
        duration_ok = duration > 0 and expected_duration > 0 and abs(duration - expected_duration) <= tolerance
        self._gate(4, "delivery_duration_matches", duration_ok,
                   f"{expected_duration:.3f}s ± {tolerance:.3f}s", duration)
        self._gate(4, "maximum_duration_respected", duration <= float(self.config.data["maximum_video_duration"]),
                   f"<= {self.config.data['maximum_video_duration']}s", duration)
        if output.is_file():
            self._artifact("final_video", output)
        if subtitle.is_file():
            self._artifact("subtitles", subtitle)
        self.metrics.update({"duration_seconds": duration, "output_size_bytes": output_size,
                             "output_width": report.get("width", 0), "output_height": report.get("height", 0),
                             "estimated_cost": 0})

    def _json_gate(self, phase: int, name: str, path: Path,
                   schema: Path | None = None) -> dict[str, Any] | None:
        try:
            payload = load_json(path)
            if schema:
                validate(payload, schema, name)
        except (OSError, ValueError, KeyError) as exc:
            self._gate(phase, name, False, "valid JSON output", str(exc))
            return None
        self._gate(phase, name, True, "valid JSON output", path.relative_to(self.config.project_dir).as_posix())
        return payload

    def _gate(self, phase: int, name: str, passed: bool, expected: Any, actual: Any,
              detail: str | None = None) -> None:
        gate = {"phase": phase, "name": name, "status": "passed" if passed else "failed",
                "expected": expected, "actual": actual}
        if detail:
            gate["detail"] = detail
        self.gates.append(gate)

    def _artifact(self, name: str, path: Path) -> None:
        self.artifacts.append({"name": name, "path": path.relative_to(self.config.project_dir).as_posix(),
                               "size_bytes": path.stat().st_size})

    def _project_path(self, key: str, default: str) -> Path:
        return self._resolve_project_relative(self.settings.get(key, default))

    def _resolve_project_relative(self, value: str) -> Path:
        path = (self.config.project_dir / value).resolve()
        try:
            path.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError("Phase 5 artifact paths must stay inside the project directory") from exc
        return path

    def _read_run_record(self, path: Path | None) -> dict[str, Any]:
        if path and path.is_file():
            return load_json(path)
        return {"status": "audit_only", "stages": []}

    def _tool_versions(self, blender: Path | None) -> dict[str, str | None]:
        versions: dict[str, str | None] = {
            "python": platform.python_version(), "pipeline": __version__,
            "blender": self._command_version(blender, ["--version"]) if blender else None,
            "piper_tts": self._package_version("piper-tts"),
            "rhubarb": None,
            "ffmpeg": None,
        }
        raw_rhubarb = self.config.data.get("phase2", {}).get("rhubarb_executable")
        if raw_rhubarb:
            rhubarb = (self.config.project_dir / raw_rhubarb).resolve()
            versions["rhubarb"] = self._command_version(rhubarb, ["--version"])
        phase4_report = self.config.generated_dir / "phase4_report.json"
        if phase4_report.is_file():
            versions["ffmpeg"] = str(load_json(phase4_report).get("ffmpeg_version") or "unknown")
        return versions

    @staticmethod
    def _package_version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None

    @staticmethod
    def _command_version(executable: Path, arguments: list[str]) -> str | None:
        if not executable.is_file():
            return None
        try:
            result = subprocess.run([str(executable), *arguments], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", check=False, timeout=20)
        except OSError:
            return None
        output = result.stdout.strip() or result.stderr.strip()
        return output.splitlines()[0].strip() if result.returncode == 0 and output else None
