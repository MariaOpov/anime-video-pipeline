"""Phase 1 orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assets import build_asset_index
from .config import load_config
from .io_utils import atomic_write_json, load_json, validate
from .motions import MotionSelector, create_motion_plan
from .phase2 import Phase2Runner
from .screenplay import OllamaAnalyzer, RuleBasedAnalyzer
from .state import PipelineState


class PipelineError(RuntimeError):
    pass


@dataclass
class PipelineResult:
    summary: str


class Pipeline:
    def __init__(self, project_dir: Path, preset_override: str | None, dry_run: bool,
                 resume: bool, verbose: bool, phase: int = 1):
        self.project_dir = project_dir
        self.preset_override = preset_override
        self.dry_run = dry_run
        self.resume = resume
        self.verbose = verbose
        self.phase = phase
        self.root = Path(__file__).resolve().parents[2]
        self.schemas = self.root / "schemas"

    def run(self) -> PipelineResult:
        try:
            config = load_config(self.project_dir, self.schemas, self.preset_override)
        except (OSError, ValueError) as exc:
            raise PipelineError(str(exc)) from exc
        logger = self._logger(config.project_dir / "logs" / "pipeline.log")
        logger.info("Starting Phase 1%s", " dry-run" if self.dry_run else "")
        try:
            script = config.script_path.read_text(encoding="utf-8-sig")
            if not script.strip():
                raise ValueError("script.txt is empty")
            screenplay = self._analyze(config, script, logger)
            validate(screenplay, self.schemas / "screenplay.schema.json", "screenplay")
            assets, warnings = build_asset_index(config.asset_paths, self.schemas / "asset.schema.json")
            selector = MotionSelector(assets, config.data.get("motion_fallbacks"))
            motion_plan = create_motion_plan(screenplay, selector, config.data.get("characters", {}))
            shot_list = self._flatten_shots(screenplay)
            for warning in warnings:
                logger.warning(warning)
            unresolved = sum(
                assignment["motion_id"] is None
                for shot in motion_plan["shots"] for assignment in shot["assignments"]
            )
            if self.dry_run:
                if self.phase == 2:
                    phase2 = Phase2Runner(config, self.schemas, logger, dry_run=True, resume=self.resume)
                    phase2_summary = phase2.run(screenplay, shot_list)
                    return PipelineResult(
                        f"DRY RUN PHASE 2 OK — {len(screenplay['scenes'])} scene(s), "
                        f"{len(shot_list['shots'])} shot(s), {phase2_summary}"
                    )
                return PipelineResult(
                    f"DRY RUN OK — {len(screenplay['scenes'])} scene(s), {len(shot_list['shots'])} shot(s), "
                    f"{len(assets)} asset(s), {unresolved} unresolved motion assignment(s), {len(warnings)} warning(s)."
                )
            generated = config.generated_dir
            state = PipelineState(generated / "pipeline_state.json")
            outputs = {
                "screenplay": generated / "screenplay.json",
                "shot_list": generated / "shot_list.json",
                "asset_index": generated / "asset_index.json",
                "motion_plan": generated / "motion_plan.json",
            }
            payloads: dict[str, Any] = {
                "screenplay": screenplay, "shot_list": shot_list,
                "asset_index": {"assets": assets, "warnings": warnings}, "motion_plan": motion_plan,
            }
            for stage, output in outputs.items():
                if self.resume and state.can_resume(stage):
                    logger.info("Resume: skipped %s", stage)
                    continue
                atomic_write_json(output, payloads[stage])
                state.complete(stage, [output])
            if self.phase == 2:
                phase2 = Phase2Runner(config, self.schemas, logger, dry_run=False, resume=self.resume)
                phase2_summary = phase2.run(screenplay, shot_list)
                return PipelineResult(
                    f"PHASE 2 COMPLETE — {len(screenplay['scenes'])} scene(s), "
                    f"{len(shot_list['shots'])} shot(s), {phase2_summary} Outputs: {config.project_dir}"
                )
            return PipelineResult(
                f"PHASE 1 COMPLETE — {len(screenplay['scenes'])} scene(s), {len(shot_list['shots'])} shot(s), "
                f"{len(assets)} asset(s), {unresolved} unresolved motion assignment(s). Outputs: {generated}"
            )
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            logger.exception("Pipeline failed")
            raise PipelineError(str(exc)) from exc

    def _analyze(self, config: Any, script: str, logger: logging.Logger) -> dict[str, Any]:
        settings = config.data.get("screenplay", {})
        mode = settings.get("analyzer", "auto")
        ollama = OllamaAnalyzer(settings.get("ollama_endpoint", "http://127.0.0.1:11434"),
                                settings.get("ollama_model", "qwen2.5:3b"))
        if mode in {"auto", "ollama"} and ollama.available():
            try:
                logger.info("Using local Ollama screenplay analyzer")
                result = ollama.analyze(config.data["project_name"], script, config.fps,
                                        config.data["maximum_video_duration"])
                validate(result, self.schemas / "screenplay.schema.json", "Ollama screenplay")
                return result
            except Exception as exc:  # Network/model failures must not crash auto mode.
                if mode == "ollama":
                    raise ValueError(f"Ollama analysis failed: {exc}") from exc
                logger.warning("Ollama failed; using rule analyzer: %s", exc)
        elif mode == "ollama":
            raise ValueError("Ollama was required but is not reachable")
        logger.info("Using deterministic rule-based screenplay analyzer")
        return RuleBasedAnalyzer(config.fps, config.data["maximum_video_duration"]).analyze(
            config.data["project_name"], script
        )

    @staticmethod
    def _flatten_shots(screenplay: dict[str, Any]) -> dict[str, Any]:
        shots, start = [], 0.0
        for scene in screenplay["scenes"]:
            for shot in scene["shots"]:
                end = start + shot["duration_seconds"]
                shots.append({"scene_id": scene["scene_id"], "shot_id": shot["shot_id"],
                              "start_seconds": round(start, 3), "end_seconds": round(end, 3),
                              "duration_seconds": shot["duration_seconds"], "camera": shot["camera"]})
                start = end
        return {"fps": screenplay["fps"], "total_duration_seconds": round(start, 3), "shots": shots}

    def _logger(self, path: Path) -> logging.Logger:
        logger = logging.getLogger(f"anime_pipeline.{self.project_dir}")
        logger.setLevel(logging.DEBUG)
        if logger.handlers:
            return logger
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG if self.verbose else logging.WARNING)
        logger.addHandler(console)
        return logger
