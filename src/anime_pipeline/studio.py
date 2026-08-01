"""Local Studio services: safe project editing, motion planning, and job execution."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import ProjectConfig
from .io_utils import atomic_write_json, load_json
from .motion_ai import (
    OllamaMotionPlanner,
    RuleMotionPlanner,
    available_motion_actions,
    motion_intent_warnings,
    validate_motion_intent,
    write_motion_intent,
)


DOCUMENTS = {
    "screenplay": "generated/screenplay.json",
    "motion_intent": "generated/motion_intent_plan.json",
    "motion_plan": "generated/motion_plan.json",
    "production_report": "generated/production_report.json",
}
ARTIFACTS = {
    "final_video": "output/final_video.mp4",
    "phase3_preview": "renders/phase3_preview.mp4",
    "subtitles": "subtitles/dialogue_vi.srt",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProjectStudio:
    def __init__(self, root: Path, config: ProjectConfig, schemas: Path):
        self.root = root.resolve()
        self.config = config
        self.schemas = schemas.resolve()
        self.settings = config.data.get("phase6", {})
        if not self.settings.get("enabled", False):
            raise ValueError("Phase 6 is disabled in project.yaml")

    @property
    def motion_intent_path(self) -> Path:
        return self.config.generated_dir / "motion_intent_plan.json"

    def read_script(self) -> str:
        return self.config.script_path.read_text(encoding="utf-8-sig")

    def write_script(self, text: str) -> None:
        maximum = int(self.settings.get("max_script_characters", 100_000))
        if not text.strip():
            raise ValueError("Script cannot be empty")
        if len(text) > maximum:
            raise ValueError(f"Script exceeds the {maximum} character limit")
        target = self.config.script_path
        temporary = target.with_name(f".{target.name}.studio.tmp")
        temporary.write_text(text.replace("\r\n", "\n").replace("\r", "\n"),
                             encoding="utf-8", newline="\n")
        os.replace(temporary, target)

    def read_document(self, name: str) -> dict[str, Any] | None:
        relative = DOCUMENTS.get(name)
        if not relative:
            raise ValueError(f"Unknown Studio document: {name}")
        path = self._project_path(relative)
        return load_json(path) if path.is_file() else None

    def artifact_path(self, name: str) -> Path:
        relative = ARTIFACTS.get(name)
        if not relative:
            raise ValueError(f"Unknown Studio artifact: {name}")
        path = self._project_path(relative)
        if not path.is_file():
            raise ValueError(f"Artifact is not available: {name}")
        return path

    def screenplay_for_motion(self) -> dict[str, Any]:
        screenplay_path = self.config.generated_dir / "screenplay.json"
        if not screenplay_path.is_file():
            raise ValueError("screenplay.json is missing. Run Phase 1 first")
        if self.config.script_path.stat().st_mtime_ns > screenplay_path.stat().st_mtime_ns:
            raise ValueError("script.txt is newer than screenplay.json. Run Phase 1 first")
        return load_json(screenplay_path)

    def generate_motion_intent(self, use_ai: bool) -> tuple[dict[str, Any], list[str]]:
        screenplay = self.screenplay_for_motion()
        raw_asset_index = self.config.generated_dir / "asset_index.json"
        assets = load_json(raw_asset_index) if raw_asset_index.is_file() else None
        actions = available_motion_actions(assets)
        settings = self.settings.get("ollama", {})
        if use_ai:
            planner = OllamaMotionPlanner(
                settings.get("endpoint", "http://127.0.0.1:11434"),
                settings.get("model", "qwen2.5:3b"),
                self.schemas / "motion_intent.schema.json",
                int(settings.get("timeout_seconds", 180)),
            )
            if not planner.available():
                raise ValueError("Ollama is not reachable. Start Ollama or use Rules mode")
            plan = planner.generate(self.config.data["project_name"], screenplay, actions)
        else:
            plan = RuleMotionPlanner().build(self.config.data["project_name"], screenplay)
        validate_motion_intent(plan, screenplay, self.schemas / "motion_intent.schema.json")
        write_motion_intent(
            self.motion_intent_path, plan, screenplay, self.schemas / "motion_intent.schema.json"
        )
        return plan, motion_intent_warnings(plan, actions)

    def save_motion_intent(self, plan: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        screenplay = self.screenplay_for_motion()
        plan = dict(plan)
        plan["source"] = "manual"
        write_motion_intent(
            self.motion_intent_path, plan, screenplay, self.schemas / "motion_intent.schema.json"
        )
        asset_path = self.config.generated_dir / "asset_index.json"
        assets = load_json(asset_path) if asset_path.is_file() else None
        return plan, motion_intent_warnings(plan, available_motion_actions(assets))

    def status(self, jobs: "StudioJobManager") -> dict[str, Any]:
        intent = self.read_document("motion_intent")
        report = self.read_document("production_report")
        ollama = self.settings.get("ollama", {})
        planner = OllamaMotionPlanner(
            ollama.get("endpoint", "http://127.0.0.1:11434"),
            ollama.get("model", "qwen2.5:3b"),
            self.schemas / "motion_intent.schema.json",
            5,
        )
        return {
            "project_name": self.config.data["project_name"],
            "project_path": str(self.config.project_dir),
            "pipeline_version": __version__,
            "ollama": {"available": planner.available(), "model": planner.model},
            "documents": {name: self._project_path(path).is_file() for name, path in DOCUMENTS.items()},
            "artifacts": {name: self._project_path(path).is_file() for name, path in ARTIFACTS.items()},
            "motion_source": intent.get("source") if intent else None,
            "quality_summary": report.get("summary") if report else None,
            "job": jobs.snapshot(),
        }

    def _project_path(self, relative: str) -> Path:
        path = (self.config.project_dir / relative).resolve()
        try:
            path.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError("Studio paths must stay inside the project directory") from exc
        return path


def build_job_command(root: Path, project: Path, mode: str, preset: str,
                      fresh: bool, blender: str) -> list[str]:
    if preset not in {"preview", "balanced", "final"}:
        raise ValueError("Invalid pipeline preset")
    if mode == "phase1":
        return [sys.executable, str(root / "run_pipeline.py"), "--project", str(project),
                "--preset", preset]
    if mode == "phase2":
        command = [sys.executable, str(root / "run_pipeline.py"), "--project", str(project),
                   "--phase", "2", "--preset", preset]
        if not fresh:
            command.append("--resume")
        return command
    if mode == "all":
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(root / "run_all.ps1"), "-Render", "-Project", str(project),
                   "-Preset", preset, "-Blender", blender]
        if fresh:
            command.append("-Fresh")
        return command
    raise ValueError(f"Unsupported Studio job mode: {mode}")


@dataclass
class StudioJob:
    job_id: str
    mode: str
    command: list[str]
    status: str = "running"
    started_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    return_code: int | None = None
    lines: list[str] = field(default_factory=list)


class StudioJobManager:
    def __init__(self, maximum_lines: int = 10_000):
        self.maximum_lines = maximum_lines
        self._job: StudioJob | None = None
        self._lock = threading.Lock()

    def start(self, mode: str, command: list[str], cwd: Path) -> dict[str, Any]:
        with self._lock:
            if self._job and self._job.status == "running":
                raise ValueError("A pipeline job is already running")
            job = StudioJob(uuid.uuid4().hex, mode, command)
            self._job = job
        thread = threading.Thread(target=self._run, args=(job, cwd), daemon=True)
        thread.start()
        return self.snapshot()

    def _run(self, job: StudioJob, cwd: Path) -> None:
        try:
            process = subprocess.Popen(
                job.command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", shell=False,
            )
            assert process.stdout is not None
            with process.stdout:
                for line in process.stdout:
                    with self._lock:
                        job.lines.append(line.rstrip("\r\n"))
                        if len(job.lines) > self.maximum_lines:
                            del job.lines[:len(job.lines) - self.maximum_lines]
            return_code = process.wait()
            with self._lock:
                job.return_code = return_code
                job.status = "complete" if return_code == 0 else "failed"
        except OSError as exc:
            with self._lock:
                job.lines.append(f"ERROR: {exc}")
                job.return_code = -1
                job.status = "failed"
        finally:
            with self._lock:
                job.completed_at = utc_now()

    def snapshot(self, offset: int = 0) -> dict[str, Any] | None:
        with self._lock:
            if not self._job:
                return None
            safe_offset = max(0, min(offset, len(self._job.lines)))
            return {
                "job_id": self._job.job_id, "mode": self._job.mode,
                "status": self._job.status, "started_at": self._job.started_at,
                "completed_at": self._job.completed_at, "return_code": self._job.return_code,
                "lines": self._job.lines[safe_offset:], "next_offset": len(self._job.lines),
            }
