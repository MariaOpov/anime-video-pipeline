# Phase 8 — Character Harmonization

Phase 8 makes characters interchangeable at shot time. Phase 7 answers “is
this local model safe and complete enough to load?” Phase 8 answers “does this
loaded cast share a usable rig, neutral pose, scale, floor, and camera space?”
The second answer is measured in Blender from evaluated scene geometry.

## Contract

Every character is adapted to the application-owned controls below. Gesture,
blocking, and camera code uses only these names:

- `root`, `spine`, `head`
- `arm.L`, `arm.R`, `leg.L`, `leg.R`
- `eyes`
- `leg_ik.L`, `leg_ik.R`

The resolver accepts Japanese MMD, Chinese, common Blender/humanoid names, and
numeric suffixes such as `.001`. A source rig without a dedicated root or leg
IK receives pipeline-owned root and grounded foot-lock controls. Source model
names never become editable AI fields.

## Configuration

`projects/demo/project.yaml` contains the production policy:

```yaml
phase8:
  enabled: true
  report: generated/phase8_harmonization_report.json
  default_target_height_meters: 1.72
  character_heights:
    Aiko: 1.68
    Ren: 1.78
  floor_z: 0.0
  height_tolerance_ratio: 0.02
  ground_tolerance_meters: 0.015
  rest_pose_max_degrees: 18.0
  neutral_arm_degrees: 12.0
  safe_frame_fraction: 0.88
  headroom_fraction: 0.06
  footroom_fraction: 0.04
```

Target heights describe cast proportions, not source-model scale. Re-running
Phase 8 remeasures the loaded meshes and deterministically reapplies the policy.

## Execution order

1. Validate the version 6 Phase 3 manifest and write the Phase 8 plan atomically.
2. Append active Phase 7 caches and retain base-scene characters without caches.
3. Resolve canonical controls and record rest-space bone directions.
4. Correct each A/T pose to the neutral dialogue arm angle with quaternions.
5. Scale evaluated mesh height to the configured target and ground it to `floor_z`.
6. Lock source leg IK, or create application-owned grounded foot controls.
7. Key blocking on the pipeline root so scale and floor offsets remain intact.
8. At each shot boundary, measure evaluated world-space bounds and the head bone.
9. Fit/key the camera, project required regions back into frame, and record evidence.
10. Block render and release if any character or shot fails.

`run_phase8.ps1` finishes by running `verify_phase8.py`, which validates both
the version 6 manifest and the runtime report schema before declaring success.

Gesture rotations are quaternion deltas over the neutral pose. This prevents a
procedural gesture from restoring the original A-pose or reversing a semantic
left/right action on another rig.

## Run and inspect

Generate the harmonized `.blend` and audit without paying the render cost:

```powershell
.\run_phase8.ps1 `
  -Blender "D:\Blender_5.1\blender.exe" `
  -Project "projects\demo"
```

Render only when the audit passes:

```powershell
.\run_phase8.ps1 -Render
```

Inspect the result:

```powershell
$Report = Get-Content `
  ".\projects\demo\generated\phase8_harmonization_report.json" `
  -Raw -Encoding UTF8 | ConvertFrom-Json

$Report.summary
$Report.characters | Select-Object `
  character, target_height_meters, measured_height_meters, `
  neutral_pose_passed, grounding_passed, bone_axes_verified, `
  foot_lock_mode, ready
$Report.shots | Select-Object `
  shot_id, required_region, head_visible, feet_visible, framing_passed
```

## Outputs and gates

- `generated/phase8_harmonization_plan.json`: trusted pre-Blender targets.
- `generated/phase8_harmonization_report.json`: strict runtime character/shot audit.
- `generated/phase3_scene_report.json`: integrated Phase 8 counters.
- `blender_scenes/phase3_assembled.blend`: editable harmonized scene.

Phase 5 validates the report schema and adds two blocking decisions:
`character_harmonization_ready` and `adaptive_camera_framing_ready`. Together
with the schema check, the complete release audit contains 34 gates.

## Acceptance

Acceptance requires all configured cast members to report:

- 10/10 canonical controls resolved, including safe root/IK fallbacks;
- neutral dialogue pose within the configured arm-angle tolerance;
- measured height within the configured ratio;
- floor error within the configured meter tolerance;
- verified opposite left/right arm axes;
- source IK or deterministic root-grounded foot lock;
- `ready: true`.

Every shot must report a visible head and its required region. Full-body shots
also require visible feet; close-ups audit the face region instead. The runtime
report must contain zero issues before `-Render` proceeds.

The repository cannot perform the final visual acceptance without the user's
local PMX bundle, Phase 7 cache, `mmd_tools`, and Blender installation. Unknown
model licensing remains a warning: a clean Phase 8 geometry report does not
grant redistribution or commercial rights.
