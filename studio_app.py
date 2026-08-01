#!/usr/bin/env python3
"""FastAPI entry point for the local Anime Pipeline Studio."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from anime_pipeline import __version__  # noqa: E402
from anime_pipeline.config import load_config  # noqa: E402
from anime_pipeline.studio import (  # noqa: E402
    ProjectStudio,
    StudioJobManager,
    build_job_command,
)


PROJECT = Path(os.environ.get("ANIME_PIPELINE_PROJECT", ROOT / "projects" / "demo")).resolve()
BLENDER = os.environ.get("ANIME_PIPELINE_BLENDER", r"D:\Blender_5.1\blender.exe")
CONFIG = load_config(PROJECT, ROOT / "schemas", None)
STUDIO = ProjectStudio(ROOT, CONFIG, ROOT / "schemas")
JOBS = StudioJobManager()

app = FastAPI(title="Anime Pipeline Studio", version=__version__, docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=ROOT / "studio_static"), name="static")


class ScriptUpdate(BaseModel):
    text: str


class MotionGenerateRequest(BaseModel):
    use_ai: bool = True


class MotionSaveRequest(BaseModel):
    plan: dict[str, Any]


class JobRequest(BaseModel):
    mode: Literal["phase1", "phase2", "all"] = "all"
    preset: Literal["preview", "balanced", "final"] = "preview"
    fresh: bool = False


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "studio_static" / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    try:
        return STUDIO.status(JOBS)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/script")
def get_script() -> dict[str, str]:
    return {"text": STUDIO.read_script()}


@app.put("/api/script")
def put_script(update: ScriptUpdate) -> dict[str, Any]:
    try:
        STUDIO.write_script(update.text)
        return {"saved": True, "characters": len(update.text)}
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/documents/{name}")
def document(name: str) -> dict[str, Any]:
    try:
        payload = STUDIO.read_document(name)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if payload is None:
        raise HTTPException(404, f"Document is not available: {name}")
    return payload


@app.post("/api/motion-intent/generate")
def generate_motion_intent(request: MotionGenerateRequest) -> dict[str, Any]:
    try:
        plan, warnings = STUDIO.generate_motion_intent(request.use_ai)
        return {"plan": plan, "warnings": warnings}
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/motion-intent")
def save_motion_intent(request: MotionSaveRequest) -> dict[str, Any]:
    try:
        plan, warnings = STUDIO.save_motion_intent(request.plan)
        return {"plan": plan, "warnings": warnings}
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs")
def start_job(request: JobRequest) -> dict[str, Any]:
    try:
        command = build_job_command(
            ROOT, CONFIG.project_dir, request.mode, request.preset, request.fresh, BLENDER
        )
        return JOBS.start(request.mode, command, ROOT)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/jobs/current")
def current_job(offset: int = Query(0, ge=0)) -> dict[str, Any] | None:
    return JOBS.snapshot(offset)


@app.get("/api/artifacts/{name}")
def artifact(name: str) -> FileResponse:
    try:
        path = STUDIO.artifact_path(name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    media_type = "video/mp4" if path.suffix.lower() == ".mp4" else "text/plain"
    return FileResponse(path, media_type=media_type, filename=None)
