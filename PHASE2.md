# Phase 2 — Offline voice and lip-sync

## Scope

Phase 2 converts every screenplay dialogue line into a normalized WAV, records
its exact position in seconds and frames, and generates mouth cues without an
online API.

```text
screenplay.json
      |
      +--> recorded override, when present
      |             or
      +--> Piper TTS voice
                    |
                    v
         16-bit PCM normalization + padding
                    |
             +------+------+
             |             |
             v             v
 dialogue_timeline.json   Rhubarb JSON
                           |
                           v
                   mapped mouth morphs
```

## Install on Windows

Run Phase 1 setup first, then:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_phase2.ps1
```

The script installs Piper in `.venv`, downloads the configured Vietnamese voice
to `tools/piper_voices`, and downloads Rhubarb to `tools/rhubarb`. All of these
local dependencies are ignored by Git.

## Validate and run

```powershell
.\.venv\Scripts\python.exe run_pipeline.py --project projects/demo --phase 2 --dry-run
.\.venv\Scripts\python.exe run_pipeline.py --project projects/demo --phase 2 --preset preview
```

Use `--resume` to preserve completed line-level TTS and lip-sync stages:

```powershell
.\.venv\Scripts\python.exe run_pipeline.py --project projects/demo --phase 2 --resume
```

## Recorded voice override

Generated line IDs are visible in `generated/dialogue_timeline.json`. To replace
one generated voice, create a 16-bit PCM WAV with the matching name:

```text
projects/demo/dialogue/recorded/scene_001_shot_001_line_001.wav
```

Run Phase 2 again without `--resume` for that line. The original recording is
read-only input and is excluded from Git by default.

## Rhubarb installation

Rhubarb must stay beside the complete `res` directory distributed in its
Windows ZIP. `setup_phase2.ps1` copies the complete distribution and verifies
`res/sphinx/cmudict-en-us.dict` before reporting success.

## Current demo limitation

Both demo characters use `vi_VN-vais1000-medium`; Ren uses a slower
`length_scale`, which does not turn it into a true male voice. Separate licensed
voices can be configured under `phase2.voices` later.

## Morph mapping

Rhubarb's A–H/X shapes are mapped by `phase2.mouth_morph_mapping`. The defaults
target `A`, `I`, `U`, `E`, `O`, `closed`, and `neutral`. Real PMX models often use
Japanese morph names, so mappings are intentionally project-specific.
