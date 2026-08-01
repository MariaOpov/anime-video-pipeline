# Phase 6.2 — Performance Director

Phase 6.2 turns continuous shot-wide motion into directed acting. It consumes
only validated Phase 1, Phase 2, and Phase 6 contracts and produces a version 3
Phase 3 manifest. No LLM generates timing, target names, or Blender keyframes.

## Directed performance layers

1. **Dialogue beats** — one speech beat per line plus a timed window for each
   discrete gesture. Apology movement occurs early, a question tilt occurs late,
   and an affirmation nod lands near the beginning of the response.
2. **Automatic gaze** — rules infer the other recurring scene character when
   `look_at` is empty. Speakers and listeners turn their head and eyes through a
   bounded transition.
3. **Deterministic blinks** — a SHA-256 project/character seed schedules natural
   2.45–4.30 second intervals reproducibly. Blender prefers `blink`,
   `eye_blink`, `eyeblink`, or `まばたき` morphs and falls back to the demo eyes.
4. **Listener reactions** — a character elsewhere in the same scene receives a
   subtle breathing and reaction clip while another character speaks.
5. **Emotional posture** — sadness, happiness, anger, determination, surprise,
   and fear adjust the bounded resting head/spine pose.

## Demo expectation

The four-shot rooftop demo should produce:

- 8 performance clips: 4 speaker and 4 listener;
- 12 gesture requests;
- 4 dialogue beats;
- 8 gaze targets;
- 9 deterministic blink events;
- 4 listener reactions;
- 0 performance conflicts and 0 skipped bone aliases.

The exact pose, gaze, and blink keyframe totals are implementation outputs and
must be positive. Phase 5 verifies them rather than hard-coding a count.

## Run

After applying the patch, launch Studio and generate a new Rules plan so the
four speaker intents contain Aiko/Ren look targets. Then select **Run All 5
Phases**. Fresh build is not required: motion-intent modification time forces
the affected Phase 1 planning contracts to refresh.

The Studio's **Performance Timeline** displays each speaker/listener segment and
marks speech, gesture, and reaction peaks. Hover a segment or beat for details.

## Acceptance

Inspect `generated/phase3_scene_report.json` and confirm:

```json
{
  "performance_clip_count": 8,
  "dialogue_beat_count": 4,
  "gaze_target_count": 8,
  "blink_event_count": 9,
  "listener_reaction_count": 4,
  "performance_conflict_count": 0,
  "skipped_bone_alias_count": 0
}
```

The production report must pass `performance_direction_applied` and all 29
quality gates. A rig without a supported gaze or blink target fails visibly
instead of silently shipping a degraded animation.
