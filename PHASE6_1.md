# Phase 6.1 — Deterministic procedural gesture execution

Phase 6.1 closes the gap between semantic motion intent and visible Blender
movement. It does not ask an LLM to generate animation curves. Instead, it
converts an allowlisted gesture vocabulary into small, bounded pose rotations
and applies them through fixed application-owned bone aliases.

## Trust boundary

The motion-intent JSON can contain `action`, `emotion`, `intensity`, approved
`gestures`, and an optional character `look_at` target. It cannot contain bone
names, file paths, Blender data paths, rotations, keyframes, Python, or shell
commands.

`anime_pipeline.gestures` samples every performance clip at six normalized
positions and clamps each Euler component to ±0.65 radians. Blender resolves
only the aliases `spine`, `head`, `arm.L`, `arm.R`, `leg.L`, and `leg.R` through
a fixed table covering the demo rig and common MMD names. Unknown gestures fail
validation. Missing aliases are counted and fail the Phase 5 release audit.

## Rule-generated demo performance

The deterministic rules inspect the screenplay context in addition to emotion:

- wind or `gió` in the shot description adds `wind_sway`;
- apology language adds `look_down`;
- a question adds `head_tilt`;
- affirmative language adds `nod`;
- dialogue actions receive restrained alternating arm motion;
- `breathe` adds subtle torso/head movement.

For the four-shot demo this produces eight gesture requests, four performance
clips, and normally 96 keyed bone poses. The exact pose-key count can be lower
for very short clips whose six sample positions round to the same frame.

## Run from Studio

1. Launch `run_studio.ps1`.
2. Run Phase 1 if the script changed.
3. Select **Generate Rules** or **Generate with Ollama**.
4. Review the gesture list and select **Validate & Save**.
5. Run Phase 1 again to apply the current intent to the trusted motion plan.
6. Select **Run All 5 Phases** with rendering enabled.

The Studio metrics show gesture and pose-key counts after the production report
is refreshed.

## Run from PowerShell

```powershell
.\.venv\Scripts\python.exe generate_motion_intent.py `
  --project projects/demo `
  --mode rules

.\.venv\Scripts\python.exe run_pipeline.py `
  --project projects/demo `
  --preset preview

.\run_phase3.ps1 -Render
.\run_phase4.ps1
.\.venv\Scripts\python.exe finalize_phase5.py --project projects/demo
```

`projects/demo/project.yaml` controls the executor with
`phase6.procedural_gestures.enabled` and `amplitude_scale`. The accepted scale
range is 0.1–3.0; the default is 1.0.

## Acceptance report

`generated/phase3_scene_report.json` records performance targets, clips,
gestures, inserted pose keys, and skipped aliases. A successful demo production
should report four clips, eight gestures, a positive pose-key count, and zero
skipped aliases before Phase 6.2 listener expansion. The final production
report adds the `procedural_gestures_applied` quality gate.

`wind_sway` animates the character's body. Cloth, hair, and environment wind
require model-specific physics or simulation and are intentionally out of scope
for this deterministic executor.
