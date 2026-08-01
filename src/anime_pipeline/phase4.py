"""Phase 4 subtitle generation, audio finishing, and final MP4 export."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .io_utils import atomic_write_json, load_json, validate


def srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("SRT timestamps cannot be negative")
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(timeline: dict[str, Any], include_speaker_names: bool = False) -> str:
    blocks = []
    for index, line in enumerate(timeline["lines"], start=1):
        start, end = float(line["start_seconds"]), float(line["end_seconds"])
        if end <= start:
            raise ValueError(f"Invalid subtitle timing for {line['line_id']}")
        text = str(line["text"]).strip().replace("\r\n", "\n").replace("\r", "\n")
        if include_speaker_names:
            text = f"{line['character']}: {text}"
        blocks.append(
            f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n"
        )
    return "\n".join(blocks)


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is not installed. Run setup_phase4.ps1") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg_version() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_version()


def supports_filter(executable: str, filter_name: str) -> bool:
    result = subprocess.run(
        [executable, "-hide_banner", "-filters"], capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        return False
    return any(
        len(parts := line.split()) >= 2 and parts[1] == filter_name
        for line in result.stdout.splitlines()
    )


def build_ffmpeg_command(executable: str, *, input_video: str, subtitle_file: str,
                         output_video: str, settings: dict[str, Any],
                         subtitle_mode: str) -> list[str]:
    if subtitle_mode not in {"burn", "soft"}:
        raise ValueError(f"Unsupported subtitle mode: {subtitle_mode}")
    audio_filter = (
        f"loudnorm=I={float(settings.get('loudness_target_lufs', -16)):g}:"
        f"TP={float(settings.get('true_peak_db', -1.5)):g}:"
        f"LRA={float(settings.get('loudness_range_lu', 11)):g}"
    )
    command = [executable, "-y", "-hide_banner", "-i", input_video]
    if subtitle_mode == "burn":
        style = settings.get(
            "subtitle_style",
            "FontName=Arial,FontSize=22,Outline=2,Shadow=0,MarginV=24,Alignment=2",
        )
        subtitle_filter = f"subtitles='{subtitle_file}':force_style='{style}'"
        command += [
            "-vf", subtitle_filter,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", settings.get("video_codec", "libx264"),
            "-preset", settings.get("video_preset", "medium"),
            "-crf", str(int(settings.get("crf", 20))),
        ]
    else:
        command += [
            "-i", subtitle_file,
            "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
            "-c:v", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", f"language={settings.get('subtitle_language_code', 'vie')}",
        ]
    command += [
        "-c:a", settings.get("audio_codec", "aac"),
        "-b:a", settings.get("audio_bitrate", "192k"),
        "-af", audio_filter,
        "-movflags", "+faststart", output_video,
    ]
    return command


class Phase4Runner:
    def __init__(self, config: ProjectConfig, schemas: Path, executable: str | None = None):
        self.config = config
        self.schemas = schemas
        self.settings = config.data.get("phase4", {})
        self.executable = executable

    def plan(self) -> dict[str, Any]:
        if not self.settings.get("enabled", False):
            raise ValueError("Phase 4 is disabled in project.yaml")
        timeline_path = self.config.generated_dir / "dialogue_timeline.json"
        report_path = self.config.generated_dir / "phase3_scene_report.json"
        if not timeline_path.is_file():
            raise ValueError(f"Phase 2 timeline not found: {timeline_path}")
        if not report_path.is_file():
            raise ValueError(f"Phase 3 report not found: {report_path}. Run run_phase3.ps1 -Render")
        timeline = load_json(timeline_path)
        validate(timeline, self.schemas / "dialogue_timeline.schema.json", "dialogue timeline")
        phase3_report = load_json(report_path)
        if phase3_report.get("status") != "complete" or not phase3_report.get("preview_video"):
            raise ValueError("Phase 3 preview is incomplete. Run run_phase3.ps1 -Render")

        input_video = self._project_path("input_video", phase3_report["preview_video"])
        subtitle_file = self._project_path("subtitle_file", "subtitles/dialogue_vi.srt")
        output_video = self._project_path("output_video", "output/final_video.mp4")
        if not input_video.is_file():
            raise ValueError(f"Phase 3 preview video not found: {input_video}")
        if input_video == output_video:
            raise ValueError("Phase 4 output must not overwrite the Phase 3 preview")

        executable = self.executable or ffmpeg_executable()
        requested_mode = self.settings.get("subtitle_mode", "auto")
        has_subtitles_filter = supports_filter(executable, "subtitles")
        if requested_mode == "burn" and not has_subtitles_filter:
            raise ValueError("Burned subtitles were required but this FFmpeg has no subtitles filter")
        mode = "burn" if requested_mode == "burn" or (
            requested_mode == "auto" and has_subtitles_filter
        ) else "soft"
        return {
            "timeline": timeline, "executable": executable, "subtitle_mode": mode,
            "input_video": input_video, "subtitle_file": subtitle_file,
            "output_video": output_video,
        }

    def run(self, dry_run: bool = False) -> str:
        plan = self.plan()
        timeline = plan["timeline"]
        if dry_run:
            return (
                f"{len(timeline['lines'])} subtitle(s), {plan['subtitle_mode']} subtitle mode, "
                "loudness normalization ready."
            )

        subtitle_file: Path = plan["subtitle_file"]
        subtitle_file.parent.mkdir(parents=True, exist_ok=True)
        subtitle_text = build_srt(
            timeline, bool(self.settings.get("include_speaker_names", False))
        )
        temporary_subtitle = subtitle_file.with_suffix(subtitle_file.suffix + ".tmp")
        temporary_subtitle.write_text(subtitle_text, encoding="utf-8", newline="\n")
        os.replace(temporary_subtitle, subtitle_file)

        output_video: Path = plan["output_video"]
        output_video.parent.mkdir(parents=True, exist_ok=True)
        temporary_video = output_video.with_name(f".{output_video.stem}.tmp{output_video.suffix}")
        relative = lambda path: path.relative_to(self.config.project_dir).as_posix()
        command = build_ffmpeg_command(
            plan["executable"], input_video=relative(plan["input_video"]),
            subtitle_file=relative(subtitle_file), output_video=relative(temporary_video),
            settings=self.settings, subtitle_mode=plan["subtitle_mode"],
        )
        result = subprocess.run(
            command, cwd=self.config.project_dir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0 or not temporary_video.is_file():
            temporary_video.unlink(missing_ok=True)
            detail = result.stderr.strip()[-4000:] or result.stdout.strip()[-4000:]
            raise RuntimeError(f"FFmpeg Phase 4 export failed: {detail}")
        os.replace(temporary_video, output_video)

        duration, size = self._probe(output_video)
        report = {
            "phase": 4, "status": "complete", "ffmpeg_version": ffmpeg_version(),
            "input_video": relative(plan["input_video"]),
            "subtitle_file": relative(subtitle_file),
            "subtitle_count": len(timeline["lines"]),
            "subtitle_mode": plan["subtitle_mode"], "audio_normalized": True,
            "output_video": relative(output_video), "duration_seconds": duration,
            "width": size[0], "height": size[1],
            "output_size_bytes": output_video.stat().st_size,
        }
        atomic_write_json(self.config.generated_dir / "phase4_report.json", report)
        return (
            f"{report['subtitle_count']} subtitle(s), {report['subtitle_mode']} mode, "
            f"{duration:.3f}s, {size[0]}x{size[1]}, {report['output_size_bytes']} byte(s)."
        )

    def _probe(self, path: Path) -> tuple[float, tuple[int, int]]:
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(str(path))
        try:
            metadata = next(reader)
        finally:
            reader.close()
        duration = float(metadata.get("duration", 0))
        size = metadata.get("size")
        if duration <= 0 or not size or len(size) != 2:
            raise RuntimeError(f"Final video verification failed: {path}")
        return duration, (int(size[0]), int(size[1]))

    def _project_path(self, key: str, default: str) -> Path:
        path = (self.config.project_dir / self.settings.get(key, default)).resolve()
        try:
            path.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"phase4.{key} must stay inside the project directory") from exc
        return path
