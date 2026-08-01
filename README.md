# Anime Video Pipeline — Phase 2

A Windows-first foundation for an offline, reusable anime production pipeline.
Phase 1 turns a text script into validated screenplay and shot-list JSON, indexes
local assets, and selects motions with deterministic fallbacks. Phase 2 adds
offline Piper speech, exact dialogue timing, recorded-voice overrides, and
Rhubarb mouth cues mapped to configurable MMD/Blender morph names.

## Architecture

```text
script.txt + project.yaml
          |
          v
 Configuration validation
          |
          v
 Screenplay analyzer --------> Ollama (optional, local)
          |                    Rule analyzer (fallback)
          v
 JSON Schema validation
          |
          +----> Asset index ----> License warnings
          |
          v
Motion selector -----------> Exact match / fallback chain / safe idle
          |
          v
Piper / recorded WAV ------> Normalize + silence padding
          |
          v
Dialogue timeline ---------> Rhubarb phonetic recognizer
          |
          v
screenplay.json + dialogue_timeline.json + lip_sync/*.json
```

The pipeline is stage-based and idempotent. Each completed stage is recorded in
`generated/pipeline_state.json`; `--resume` skips completed stages whose outputs
still exist. Original assets are only read, never modified or deleted.

## Quick start (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_pipeline.py --project projects/demo --dry-run
python run_pipeline.py --project projects/demo --preset preview
```

Install Phase 2 after Phase 1 setup:

```powershell
.\setup_phase2.ps1
python run_pipeline.py --project projects/demo --phase 2 --dry-run
python run_pipeline.py --project projects/demo --phase 2 --preset preview
```

`setup_phase2.ps1` downloads tools locally and does not commit them. The demo
uses `vi_VN-vais1000-medium`; its source dataset is CC BY 4.0, so productions
that use this voice must provide attribution. Piper and Rhubarb retain their
own upstream licenses and are not redistributed by this repository.

Optional local LLM:

```powershell
ollama pull qwen2.5:3b
ollama serve
```

Set `screenplay.analyzer: ollama` in `project.yaml` to require it, or leave
`auto` to use Ollama when available and fall back safely when unavailable.

## Phase 1 outputs

- `generated/screenplay.json`: normalized scenes, shots, characters, dialogue.
- `generated/shot_list.json`: flattened production shot list.
- `generated/asset_index.json`: searchable asset metadata.
- `generated/motion_plan.json`: selected motion per character per shot.
- `generated/pipeline_state.json`: resumable stage status.
- `logs/pipeline.log`: readable execution log.

## Phase 2 outputs

- `dialogue/<line_id>.wav`: normalized 16-bit PCM dialogue with padding.
- `dialogue/<line_id>.txt`: exact transcript supplied to Rhubarb.
- `generated/dialogue_timeline.json`: absolute seconds and frame ranges.
- `lip_sync/<line_id>.json`: Rhubarb cues plus mapped mouth morph names.

To replace generated speech, put a 16-bit PCM WAV at
`dialogue/recorded/<line_id>.wav` and rerun Phase 2. Original recordings are
never modified. For Vietnamese and other non-English dialogue, use Rhubarb's
`phonetic` recognizer; English projects may choose `pocketSphinx`.

## Asset metadata

Place one `.asset.yaml` sidecar anywhere below an asset-library directory. The
`file_path` is resolved relative to that sidecar. Missing files and incomplete
licensing are reported without modifying the source assets.

## Commands

```powershell
python run_pipeline.py --project projects/demo --dry-run
python run_pipeline.py --project projects/demo --preset preview
python run_pipeline.py --project projects/demo --resume
python -m unittest discover -s tests -v
```

`--dry-run` validates inputs and reports planned work without writing generated
production outputs. Use `--verbose` for console debug messages.

## Next phases

1. Blender applies Phase 2 mouth cues to model shape keys.
2. Blender import, retargeting, placement, cameras, preview rendering.
3. FFmpeg audio mix, subtitles, and final export.
4. Optional ComfyUI and improved emotional animation.
