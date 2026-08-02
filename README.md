# Anime Video Pipeline — Phase 8

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
Phase 6.2 directs those poses around dialogue beats, inferred gaze, deterministic
blinks, emotional posture, and subtle listener reactions. Phase 6.3 adds stable
character staging, body facing, shot composition, bounded camera moves, and a
blocking safety audit.
Phase 7 onboards real PMX/PMD characters through a guarded local import,
normalizes and caches them, maps trusted rig and facial aliases, and blocks
production when model, texture, morph, or license checks do not satisfy the
project policy.
Phase 8 gives every cast member a canonical root/spine/head/arms/legs/eyes/IK
contract, converts A/T poses to a neutral dialogue rest pose with quaternion
correction, normalizes cast proportions, locks characters to the floor, and
frames each shot from evaluated world-space bounds. A failed harmonization or
framing audit blocks rendering and release.

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
Phase 3 manifest ----------> Blender blocking/cameras + WAV + mouth/pose keys
          ^
          |
 Phase 7 local PMX --------> inspected rig/morph/texture cache
          |
          v
 Phase 8 harmonization ----> neutral pose / scale / grounding / adaptive camera
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

Onboard one local PMX/PMD character before the next production build:

```powershell
.\run_phase7.ps1 `
  -Character Aiko `
  -Model "D:\Models\Flavia\芙拉薇娅.pmx" `
  -Creator "Unknown" `
  -Source "Unknown" `
  -LicenseName "Unknown"
```

The original model folder, staged bundle, profile, registry, and Blender cache
stay local and are excluded from Git. See `PHASE7.md` before publishing any
model-derived output or redistributing assets.

Audit character harmonization without rendering:

```powershell
.\run_phase8.ps1
```

Add `-Render` only after the report is clean. Phase 8 writes diagnostics before
render approval and exits non-zero if any cast member or shot is not production
ready. See `PHASE8.md` for configuration and acceptance.

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

- `generated/phase3_manifest.json`: validated Blender assembly and blocking contract.
- `generated/phase8_harmonization_plan.json`: deterministic cast target/control plan.
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

Phase 5 checks the Phase 1–4 delivery contracts plus integrated Phase 6–8
performance, asset, and harmonization evidence; it compares Blender counts to
the manifest and verifies final subtitles, audio, duration, dimensions, and file
size. See `PHASE5.md` for the full release gate.

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

## Phase 6.2 Performance Director

Phase 6.2 expands the four speaker clips into eight shot-aware performances:
four speakers and four listeners. It infers Aiko/Ren look targets, aligns the
discrete gestures to exact dialogue ranges, schedules reproducible blinks,
adds emotional resting posture, and gives the listener a small reaction beat.
The Studio renders these clips and their beats on a performance timeline.

The Phase 3 manifest records dialogue beats, gaze events,
blink events, listeners, and overlap conflicts. Blender supports common MMD
`blink`/`まばたき` morphs and uses the demo eye meshes as a fallback. Phase 5
requires the requested gaze/blink events to produce real keyframes and raises
the complete demo audit to 29 gates. See `PHASE6_2.md`.

## Phase 6.3 Cinematic Blocking Director

Phase 6.3 places recurring characters on a stable stage, turns their bodies
toward validated look targets, selects a deterministic composition per shot,
and inserts subtle camera transform keys. The four-shot demo uses a two-shot,
a close-up, and over-shoulder framing while preserving Aiko/Ren screen order.

The manifest carries placement, body-facing, lens, camera
movement, and pre-Blender risk metrics. Blender reports the transforms it
actually keyed. Phase 5 rejects missing keys or any framing, collision,
continuity, or placement risk, raising the complete demo audit to 30 gates.
See `PHASE6_3.md`.

## Phase 7 Production Character Onboarding

Phase 7 imports one PMX/PMD bundle through `mmd_tools`, preserves the complete
texture directory, scales and grounds the model, resolves application-owned rig
and facial aliases, packs available images, and saves a character-only Blender
cache. Its validated profile becomes a local registry entry; Phase 3 then
replaces only the matching mannequin.

The Phase 7 portion of manifest version 6 records only safe project-relative cache/profile
contracts plus coverage metrics. Phase 5 requires every configured production
character to load with matching bone, mouth, texture, and license counts,
raising the complete demo audit to 31 gates. See `PHASE7.md`.

## Phase 8 Character Harmonization

Phase 8 upgrades the manifest to version 6 and separates model onboarding from
shot-time harmonization. The shared alias contract recognizes Japanese,
Chinese, common humanoid, and Blender-suffixed bone names. Missing source root
or leg-IK controls receive deterministic pipeline-owned root/foot-lock
fallbacks; gesture deltas are composed over the neutral quaternion pose.

Blender measures evaluated meshes after pose, scale, grounding, blocking, and
animation. Full-body shots must retain head and feet; close-ups must retain the
face region. It writes `generated/phase8_harmonization_report.json`, and Phase 5
adds schema, character-readiness, and adaptive-framing gates for 34 total gates.
See `PHASE8.md`.

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

1. Phase 9 motion retargeting and a curated production VMD library.
2. Environment-aware blocking, occlusion checks, and model-specific cloth/hair wind.
3. Optional ComfyUI backgrounds and image-to-video inserts.
