# Anime Video Pipeline — Phase 6.1

A Windows-first foundation for an offline, reusable anime production pipeline.
Phase 1 turns a text script into validated screenplay and shot-list JSON, indexes
local assets, and selects motions with deterministic fallbacks. Phase 2 adds
offline Piper speech, exact dialogue timing, recorded-voice overrides, and
Rhubarb mouth cues mapped to configurable MMD/Blender morph names. Phase 3
assembles those contracts inside Blender as shot cameras, synchronized audio,
and animated mouth shape keys. Phase 4 generates subtitles, normalizes audio,
and exports a verified delivery MP4 through a local FFmpeg runtime. Phase 5
orchestrates the entire production with one command and refuses release unless
every configured quality gate passes. Phase 6 adds a local web Studio and
schema-constrained Ollama motion planning. Phase 6.1 turns the validated
semantic gestures into bounded Blender pose keyframes while preserving the
deterministic asset resolver and fixed bone aliases as the final authority.

## Architecture

```text
script.txt + project.yaml
          |
          v
 Phase 6 Studio -----------> Script editor / live logs / video / QA
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
          +----> Motion intent ----> Ollama or rules ----> Motion selector
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
          |
          v
Phase 3 manifest ----------> Blender cameras + WAV strips + mouth/pose keys
          |
          v
Phase 3 preview -----------> SRT + loudness normalization + final MP4
          |
          v
Phase 5 quality gates -----> production_report.json
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

Assemble a Blender scene after Phase 2:

```powershell
.\run_phase3.ps1
.\run_phase3.ps1 -Render
```

The first command creates the editable `.blend`; `-Render` also renders the
configured preview MP4. The demo uses 50% resolution for a faster acceptance
render while retaining the project's 24 fps timeline.

Finish the rendered preview:

```powershell
.\setup_phase4.ps1
.\run_phase4.ps1
```

The Phase 4 setup installs a project-local FFmpeg binary. No global PATH change
is required. `auto` subtitle mode burns subtitles when the local build supports
the libass subtitles filter and otherwise creates a selectable MP4 subtitle
track.

Run all production phases and the final audit with one command:

```powershell
.\run_all.ps1 -Render
```

Use `-Setup` on a fresh checkout to install the local Python, voice, lip-sync,
and FFmpeg dependencies first. Resume is enabled by default; `-Fresh` forces
Phase 1–2 regeneration. Rendering requires the explicit `-Render` switch so an
expensive Blender job cannot start accidentally.

Launch the local production Studio:

```powershell
.\setup_phase6.ps1
.\run_studio.ps1
```

The Studio opens on `http://127.0.0.1:8000` and provides a script editor,
schema-validated motion JSON editor, Ollama/rules generation, allowlisted
pipeline controls, incremental logs, final-video playback, and all release
gates. It is loopback-only and does not expose remote command execution.

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

## Phase 3 outputs

- `generated/phase3_manifest.json`: validated Blender assembly contract.
- `blender_scenes/phase3_assembled.blend`: cameras, sound strips, mouth keys,
  and procedural body-pose keyframes.
- `generated/phase3_scene_report.json`: machine-readable assembly result.
- `renders/phase3_preview.mp4`: optional Blender preview with dialogue audio.

Phase 3 opens the configured base scene read-only and saves to a separate output
scene. The demo creates non-destructive fallback mouth controls; real MMD models
can expose their own configured morph names instead.

## Phase 4 outputs

- `subtitles/dialogue_vi.srt`: UTF-8 subtitles generated from exact timing.
- `output/final_video.mp4`: H.264/AAC delivery video with normalized dialogue.
- `generated/phase4_report.json`: subtitle mode, duration, dimensions, and size.

Phase 4 never overwrites the Phase 3 preview. The output is first written to a
temporary MP4, verified, and atomically promoted to `final_video.mp4`.

## Phase 5 outputs

- `generated/phase5_run_record.json`: status and elapsed time for every stage.
- `generated/production_report.json`: tool versions, QA results, metrics, and artifacts.

Phase 5 checks all Phase 1–4 contracts, enforces configurable warning limits,
compares Blender counts to the manifest, and verifies final subtitles, audio,
duration, dimensions, and file size. See `PHASE5.md` for the full release gate.

## Phase 6 outputs

- `generated/motion_intent_plan.json`: AI/rules semantic motion contract.
- Local Studio at `http://127.0.0.1:8000` with script, JSON, logs, video, and QA.

The motion-intent plan is signed with the screenplay SHA-256 and must preserve
every scene, shot, and character identity. It contains no executable code or
asset paths. The existing motion selector resolves its action tags to trusted
local motion assets. Phase 6.1 maps only approved gesture names to bounded
rotations on fixed bone aliases; AI still cannot provide bone names or raw
keyframes. See `PHASE6.md` and `PHASE6_1.md` for the workflow and API.

## Phase 6.1 procedural gestures

After saving a current motion-intent plan, rerun Phase 1 and production. Phase 3
then emits one performance clip per character/shot and replaces the demo's
generic arm loop with deterministic `breathe`, `look_down`, `head_tilt`, `nod`,
`wind_sway`, look-target, and restrained talking motion. Phase 5 verifies that
every clip produced pose keys and that no required bone alias was skipped.

The demo rules produce eight gestures across four shots: wind/body sway in the
opening, Ren looking down while apologizing, Aiko tilting her head for the
question, and Ren nodding in the final affirmation. `wind_sway` moves the body;
cloth and hair physics remain model-specific future work.

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
.\run_all.ps1 -Render
.\run_studio.ps1
```

`--dry-run` validates inputs and reports planned work without writing generated
production outputs. Use `--verbose` for console debug messages.

## Possible extensions

1. Optional ComfyUI backgrounds and image-to-video inserts.
2. Import and retarget a production MMD character/motion library.
3. Eye animation, richer emotional posing, and model-specific cloth/hair wind.
