# Anime Video Pipeline — Phase 1

A Windows-first foundation for an offline, reusable anime production pipeline.
Phase 1 turns a text script into validated screenplay and shot-list JSON, indexes
local assets, and selects motions with deterministic fallbacks. Blender, voice,
lip-sync, and FFmpeg are intentionally reserved for later phases.

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
 screenplay.json + shot_list.json + asset_index.json + pipeline_state.json
```

The pipeline is stage-based and idempotent. Each completed stage is recorded in
`generated/pipeline_state.json`; `--resume` skips completed stages whose outputs
still exist. Original assets are only read, never modified or deleted.

## Quick start (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_pipeline.py --project projects/demo --dry-run
python run_pipeline.py --project projects/demo --preset preview
```

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

1. Piper TTS, dialogue timing, Rhubarb lip-sync.
2. Blender import, retargeting, placement, cameras, preview rendering.
3. FFmpeg audio mix, subtitles, and final export.
4. Optional ComfyUI and improved emotional animation.

