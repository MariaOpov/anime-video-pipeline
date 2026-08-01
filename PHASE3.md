# Phase 3 — Blender scene automation

Phase 3 converts the validated Phase 1–2 outputs into an editable Blender scene.
It does not overwrite the original mannequin or imported character asset.

## Data flow

```text
shot_list.json + dialogue_timeline.json + lip_sync/*.json
                 + current motion_intent_plan.json
                 + activated Phase 7 character profiles
                            |
                            v
                  phase3_manifest.json
                            |
                            v
       blocking + cameras + markers + WAV + mouth/pose keys
                            |
                            v
                 phase3_assembled.blend
                            |
                            +----> phase3_preview.mp4 (optional)
```

## Commands

Validate inputs and assemble the editable scene:

```powershell
.\run_phase3.ps1
```

Assemble and render the acceptance preview:

```powershell
.\run_phase3.ps1 -Render
```

The runner resumes Phase 2, prepares the manifest with system Python, opens the
configured base `.blend` in background mode, and saves a separate output scene.
The render configuration supports Blender 5.x's `media_type = VIDEO` API and
falls back to the older `file_format = FFMPEG` API when necessary.

## Demo behavior

- One camera and one timeline marker are created for every shot.
- Validated staging sets stable character positions and bounded body facing.
- Shot composition selects two-shot, close-up, over-shoulder, or single framing;
  enabled camera moves receive keyed start/end transforms.
- Every dialogue WAV becomes a Blender sound strip at its absolute start frame.
- Rhubarb cues animate `A`, `I`, `U`, `E`, `O`, `closed`, and `neutral` keys.
- A current validated motion-intent plan becomes bounded head, spine, arm, and
  leg pose keys; without one, assembly retains the Phase 3-only behavior.
- A small fallback mouth mesh is created for each demo mannequin.
- An activated Phase 7 cache replaces only its matching mannequin and supplies
  mapped real rig, mouth, and blink targets.

The fallback is intentionally simple. Phase 7 resolves real PMX/MMD mouth
morphs and records them in the validated character profile.

## Acceptance criteria

Phase 3 is complete when:

1. `phase3_assembled.blend` opens successfully.
2. The timeline contains four camera markers and four dialogue sound strips.
3. Both mannequin mouths animate during their own dialogue.
4. `phase3_preview.mp4` contains picture and synchronized speech.
5. `phase3_scene_report.json` reports 4 cameras, 4 audio strips, 62 mouth cues,
   8 performance clips, 12 gestures, 4 dialogue beats, 8 gaze targets,
   deterministic blinks, 4 listener reactions, 4 blocked shots, 8 placements,
   3 camera moves, and 0 conflicts, risks, or skipped aliases.
