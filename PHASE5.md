# Phase 5 — One-command production and quality gates

Phase 5 turns the individual production tools into one guarded Windows command.
It runs the offline dialogue pipeline, Blender assembly and render, media
finishing, then audits the complete artifact chain before declaring success.

## Run

After the Phase 1, 2, and 4 setup scripts have installed local dependencies:

```powershell
.\run_all.ps1 -Render
```

For a new checkout that has no `.venv` or local runtime tools yet:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run_all.ps1 -Render -Setup
```

`-Render` is required deliberately: Blender rendering is the expensive stage
and must be explicitly approved. Phase 1 and Phase 2 resume valid line-level
outputs by default. Add `-Fresh` to regenerate them.

Use a non-default Blender executable or project like this:

```powershell
.\run_all.ps1 `
  -Render `
  -Blender "D:\Blender_5.1\blender.exe" `
  -Project "projects\demo" `
  -Preset preview
```

## Execution order

1. Verify Python, Piper, Rhubarb, FFmpeg, Blender, project configuration, and
   voice models.
2. Run Phase 1 planning and Phase 2 dialogue/lip-sync with safe resume.
3. Build the validated Phase 3 manifest, assemble Blender, and render the MP4.
4. Generate subtitles, normalize dialogue, and export the Phase 4 delivery MP4.
5. Apply release quality gates and create the production report.

If a command fails, execution stops immediately. The failed stage and elapsed
time remain in `generated/phase5_run_record.json` for diagnosis.

## Quality gates

- Phase 1 JSON contracts exist and the screenplay/shot counts agree.
- Asset warnings and unresolved motion assignments stay within configured limits.
- Every dialogue line has a non-empty WAV and a valid, identity-matched lip-sync file.
- Timing warnings stay within the configured limit and mouth cues are non-empty.
- Blender camera, audio-strip, and mouth-cue counts match the validated manifest.
- Procedural performance clip and gesture counts match, pose keys are non-empty,
  and no required bone alias is skipped.
- Dialogue beats, gaze, blinks, and listener reactions match the manifest,
  create real Blender keyframes, and contain zero clip conflicts.
- Blocking placements, body facing, and camera moves match the manifest, create
  real Blender keys, and contain zero framing, collision, continuity, or staging risks.
- Every activated Phase 7 character is ready and loaded with matching rig,
  facial morph, missing-texture, and license-warning counts.
- The assembled scene and rendered Phase 3 preview exist.
- The Phase 4 MP4, subtitle count, loudness flag, dimensions, duration, and size pass.
- The final duration does not exceed `maximum_video_duration`.

Thresholds live in the `phase5` block of `project.yaml`. Strict zero-warning
defaults make accidental degradation visible; projects may raise a limit
explicitly when a known exception is acceptable.

## Outputs

- `generated/phase5_run_record.json`: stage status and elapsed time.
- `generated/production_report.json`: tool versions, metrics, every quality gate,
  artifact paths and byte sizes, and the zero-cost estimate.
- `output/final_video.mp4`: the verified delivery artifact produced by Phase 4.

Both reports are generated files and are excluded from Git. The schema for the
release report is `schemas/production_report.schema.json`.
