"""Phase 2: offline dialogue audio, exact timing, and lip-sync cues."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .audio import normalize_and_pad_wav, wav_duration
from .config import ProjectConfig
from .io_utils import atomic_write_json, validate
from .lip_sync import RhubarbLipSync
from .state import PipelineState
from .tts import PiperTTS, PiperVoice, piper_available


class Phase2Runner:
    def __init__(self, config: ProjectConfig, schemas: Path, logger: Any,
                 dry_run: bool, resume: bool):
        self.config = config
        self.schemas = schemas
        self.logger = logger
        self.dry_run = dry_run
        self.resume = resume
        self.settings = config.data.get("phase2", {})
        self.state = PipelineState(config.generated_dir / "pipeline_state.json")

    def run(self, screenplay: dict[str, Any], shot_list: dict[str, Any]) -> str:
        if not self.settings.get("enabled", False):
            raise ValueError("Phase 2 is disabled in project.yaml")
        jobs = self._collect_jobs(screenplay, shot_list)
        if not jobs:
            raise ValueError("The screenplay contains no dialogue for Phase 2")
        rhubarb = self._rhubarb()
        self._validate_dependencies(jobs, rhubarb)
        if self.dry_run:
            overrides = sum(job["recorded_override"].is_file() for job in jobs)
            return f"{len(jobs)} dialogue line(s), {overrides} recorded override(s), Piper ready, Rhubarb ready."

        dialogue_dir = self.config.project_dir / "dialogue"
        lip_dir = self.config.project_dir / "lip_sync"
        work_dir = dialogue_dir / ".work"
        for directory in (dialogue_dir, lip_dir, work_dir, dialogue_dir / "recorded"):
            directory.mkdir(parents=True, exist_ok=True)

        self._generate_audio(jobs, work_dir)
        timeline, warnings = self._build_timeline(jobs)
        validate(timeline, self.schemas / "dialogue_timeline.schema.json", "dialogue timeline")
        timeline_path = self.config.generated_dir / "dialogue_timeline.json"
        atomic_write_json(timeline_path, timeline)
        self.state.complete("dialogue_timeline", [timeline_path])
        cue_count = self._generate_lip_sync(jobs, rhubarb, lip_dir)
        shutil.rmtree(work_dir, ignore_errors=True)
        for warning in warnings:
            self.logger.warning(warning)
        return (f"{len(jobs)} WAV file(s), {cue_count} mouth cue(s), "
                f"{len(warnings)} timing warning(s).")

    def _collect_jobs(self, screenplay: dict[str, Any], shot_list: dict[str, Any]) -> list[dict[str, Any]]:
        timings = {shot["shot_id"]: shot for shot in shot_list["shots"]}
        character_config = self.config.data.get("characters", {})
        jobs = []
        for scene in screenplay["scenes"]:
            for shot in scene["shots"]:
                shot_timing = timings[shot["shot_id"]]
                for index, line in enumerate(shot["dialogue"], start=1):
                    line_id = f"{shot['shot_id']}_line_{index:03d}"
                    character = line["character"]
                    voice_id = character_config.get(character, {}).get(
                        "voice_id", self.settings.get("default_voice")
                    )
                    voice_data = self.settings.get("voices", {}).get(voice_id)
                    if not voice_id or not voice_data:
                        raise ValueError(f"No Phase 2 voice configuration for character '{character}'")
                    jobs.append({
                        "line_id": line_id, "scene_id": scene["scene_id"],
                        "shot_id": shot["shot_id"], "character": character,
                        "text": line["text"], "emotion": line.get("emotion", "neutral"),
                        "voice_id": voice_id, "voice_data": voice_data,
                        "shot_start": float(shot_timing["start_seconds"]),
                        "shot_end": float(shot_timing["end_seconds"]),
                        "audio_path": self.config.project_dir / "dialogue" / f"{line_id}.wav",
                        "transcript_path": self.config.project_dir / "dialogue" / f"{line_id}.txt",
                        "recorded_override": self.config.project_dir / "dialogue" / "recorded" / f"{line_id}.wav",
                    })
        return jobs

    def _rhubarb(self) -> RhubarbLipSync:
        raw_executable = self.settings.get("rhubarb_executable", "../../tools/rhubarb/rhubarb.exe")
        executable = (self.config.project_dir / raw_executable).resolve()
        return RhubarbLipSync(
            executable, self.settings.get("rhubarb_recognizer", "phonetic"),
            self.settings.get("mouth_morph_mapping"),
        )

    def _validate_dependencies(self, jobs: list[dict[str, Any]], rhubarb: RhubarbLipSync) -> None:
        if not rhubarb.available():
            raise ValueError(f"Rhubarb is not installed: {rhubarb.executable}. Run setup_phase2.ps1")
        needs_piper = any(not job["recorded_override"].is_file() for job in jobs)
        if needs_piper and not piper_available():
            raise ValueError("Piper is not installed in .venv. Run setup_phase2.ps1")
        default_data_dir = self.settings.get("piper_data_dir")
        checked: set[tuple[str, str | None]] = set()
        for job in jobs:
            if job["recorded_override"].is_file():
                continue
            voice = PiperVoice.from_config(job["voice_data"], self.config.project_dir, default_data_dir)
            key = (voice.model, str(voice.data_dir) if voice.data_dir else None)
            if key in checked:
                continue
            checked.add(key)
            model_path = Path(voice.model)
            if model_path.suffix == ".onnx":
                resolved = model_path if model_path.is_absolute() else (self.config.project_dir / model_path).resolve()
            elif voice.data_dir:
                resolved = voice.data_dir / f"{voice.model}.onnx"
            else:
                resolved = Path(voice.model + ".onnx")
            if not resolved.is_file():
                raise ValueError(f"Piper voice model not found: {resolved}. Run setup_phase2.ps1")

    def _generate_audio(self, jobs: list[dict[str, Any]], work_dir: Path) -> None:
        tts = PiperTTS()
        default_data_dir = self.settings.get("piper_data_dir")
        before = float(self.settings.get("silence_before_seconds", 0.08))
        after = float(self.settings.get("silence_after_seconds", 0.12))
        peak = float(self.settings.get("normalization_peak", 0.92))
        for job in jobs:
            stage = f"tts_{job['line_id']}"
            outputs = [job["audio_path"], job["transcript_path"]]
            if self.resume and self.state.can_resume(stage):
                self.logger.info("Resume: skipped %s", stage)
                continue
            job["transcript_path"].write_text(job["text"] + "\n", encoding="utf-8")
            raw_wav = work_dir / f"{job['line_id']}.wav"
            if job["recorded_override"].is_file():
                source = job["recorded_override"]
            else:
                voice = PiperVoice.from_config(job["voice_data"], self.config.project_dir, default_data_dir)
                tts.synthesize(job["text"], voice, raw_wav)
                source = raw_wav
            normalize_and_pad_wav(source, job["audio_path"], pad_before=before, pad_after=after,
                                  target_peak=peak)
            self.state.complete(stage, outputs)

    def _build_timeline(self, jobs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
        gap = float(self.settings.get("dialogue_gap_seconds", 0.08))
        cursors: dict[str, float] = {}
        warnings = []
        lines = []
        for job in jobs:
            duration = wav_duration(job["audio_path"])
            start = max(job["shot_start"], cursors.get(job["shot_id"], job["shot_start"]))
            end = start + duration
            cursors[job["shot_id"]] = end + gap
            if end > job["shot_end"] + 0.001:
                warnings.append(
                    f"{job['line_id']} exceeds {job['shot_id']} by {end - job['shot_end']:.3f}s"
                )
            fps = self.config.fps
            lines.append({
                "line_id": job["line_id"], "scene_id": job["scene_id"], "shot_id": job["shot_id"],
                "character": job["character"], "text": job["text"], "emotion": job["emotion"],
                "voice_id": job["voice_id"],
                "audio_path": job["audio_path"].relative_to(self.config.project_dir).as_posix(),
                "start_seconds": round(start, 6), "end_seconds": round(end, 6),
                "duration_seconds": round(duration, 6),
                "start_frame": round(start * fps) + 1, "end_frame": round(end * fps) + 1,
                "recorded_override": job["recorded_override"].is_file(),
            })
        total = max((line["end_seconds"] for line in lines), default=0.0)
        return {"fps": self.config.fps, "total_duration_seconds": round(total, 6),
                "lines": lines, "warnings": warnings}, warnings

    def _generate_lip_sync(self, jobs: list[dict[str, Any]], rhubarb: RhubarbLipSync,
                           lip_dir: Path) -> int:
        total_cues = 0
        for job in jobs:
            output = lip_dir / f"{job['line_id']}.json"
            stage = f"lip_sync_{job['line_id']}"
            if self.resume and self.state.can_resume(stage):
                self.logger.info("Resume: skipped %s", stage)
                from .io_utils import load_json
                total_cues += len(load_json(output)["mouth_cues"])
                continue
            raw_json = lip_dir / f".{job['line_id']}.rhubarb.json"
            result = rhubarb.analyze(job["audio_path"], job["transcript_path"], raw_json)
            raw_json.unlink(missing_ok=True)
            payload = {
                "line_id": job["line_id"], "character": job["character"],
                "audio_path": job["audio_path"].relative_to(self.config.project_dir).as_posix(),
                "duration_seconds": result["duration"], "mouth_cues": result["mouth_cues"],
            }
            validate(payload, self.schemas / "lip_sync.schema.json", f"lip sync {job['line_id']}")
            atomic_write_json(output, payload)
            self.state.complete(stage, [output])
            total_cues += len(result["mouth_cues"])
        return total_cues

