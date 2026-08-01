# Phase 4 — Media finishing

Phase 4 turns the Blender acceptance render into a delivery video without
rendering the 3D scene again.

## Data flow

```text
phase3_preview.mp4 + dialogue_timeline.json
                  |
                  +----> dialogue_vi.srt
                  |
                  v
        subtitles + EBU R128 loudness normalization
                  |
                  v
             final_video.mp4
                  |
                  +----> phase4_report.json
```

## Setup and run

```powershell
.\setup_phase4.ps1
.\run_phase4.ps1
```

`setup_phase4.ps1` installs `imageio-ffmpeg` inside `.venv`; its Windows wheel
contains the FFmpeg executable. No system-wide installation or PATH edit is
required.

## Subtitle behavior

`subtitle_mode: auto` checks whether FFmpeg exposes the libass `subtitles`
filter. When available, subtitles are burned into every frame. Otherwise, the
pipeline preserves the video stream and adds a selectable `mov_text` subtitle
track. The generated UTF-8 SRT is retained in both cases.

## Audio behavior

The Phase 3 dialogue mix is normalized with FFmpeg's EBU R128 `loudnorm`
filter. Demo defaults target -16 LUFS, -1.5 dB true peak, and an 11 LU loudness
range. The input preview remains unchanged.

## Acceptance criteria

Phase 4 is complete when:

1. Four Vietnamese subtitle entries are generated.
2. Dialogue remains audible and synchronized.
3. Subtitles are visible or available as a selectable MP4 track.
4. `final_video.mp4` opens and has a non-zero verified duration.
5. `phase4_report.json` reports status `complete`.
