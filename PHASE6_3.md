# Phase 6.3 — Cinematic Blocking Director

Phase 6.3 turns validated shot and performance contracts into deterministic
character placement, body facing, shot composition, and bounded camera motion.
It does not let an LLM provide coordinates, lenses, transforms, or keyframes.

## Directed blocking layers

1. **Stable staging** — recurring characters keep a consistent left/right screen
   order and receive non-overlapping stage positions.
2. **Body facing** — each character turns toward the validated gaze target by a
   bounded yaw while head and eye animation remain under Phase 6.2 control.
3. **Shot composition** — the director chooses from `two_shot`, `close_up`,
   `over_shoulder`, and `single` using the existing shot contract.
4. **Camera motion** — optional slow dolly and lateral-drift moves use
   application-owned values and keyed start/end transforms.
5. **Safety audit** — framing, camera-clearance, screen-order, and placement
   conflicts are recorded before Blender runs and fail the release gate.

## Demo expectation

The four-shot rooftop demo should produce:

- 4 blocked shots;
- 8 character placements and 8 body-facing assignments;
- 3 moving cameras with 12 camera transform keys;
- 32 placement transform keys;
- 0 framing, collision, continuity, or blocking conflicts.

The first shot is a slowly tightening two-shot. The apology uses a close-up,
the question uses an over-shoulder composition, and the final response eases
out while preserving Aiko on screen-left and Ren on screen-right.

## Configuration

`projects/demo/project.yaml` enables the director under
`phase6.cinematic_blocking`:

```yaml
cinematic_blocking:
  enabled: true
  character_spacing: 2.2
  body_turn_degrees: 10.0
  camera_motion_enabled: true
  camera_motion_strength: 0.18
  safe_frame_fraction: 0.86
  minimum_camera_clearance: 1.5
```

All values are schema-bounded. The director uses no randomness and produces the
same contract for the same screenplay, intent, performance, and configuration.

## Acceptance

Run the complete production from Studio or PowerShell. The Studio's
**Cinematic Blocking Timeline** shows composition, subject/listener, camera
movement, lens, and character placement for every shot.

`generated/phase3_scene_report.json` should report the expected counts above.
The production report must pass `cinematic_blocking_applied` and all 30 quality
gates. Any non-zero blocking risk or a requested move without Blender camera
keys prevents release.

## Current boundary

The director blocks one stable stage plane and application-owned camera
templates. Environment-aware navigation, occlusion ray tests, collision with
arbitrary production sets, depth-of-field pulls, and handheld noise remain
future work. Real PMX model scale and origin normalization belongs to the model
onboarding stage.
