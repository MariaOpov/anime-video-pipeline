# System architecture

## Design goals

- Windows 10/11 first, command-line friendly, and offline by default.
- Blender is the eventual scene, animation, and rendering authority.
- Generated AI data is treated as untrusted and validated before Blender sees it.
- Local tagged motions are preferred over unreliable text-to-motion generation.
- Every expensive stage has explicit outputs and resumable state.
- Original scripts and assets are read-only inputs.

## Layers

1. **Project layer** — `project.yaml`, `script.txt`, and user-owned assets.
2. **Planning layer** — screenplay analysis, schema validation, shot timing.
3. **Asset layer** — metadata index, licensing checks, compatibility search.
4. **Animation plan** — motion selection and deterministic fallback chains.
5. **Dialogue layer (Phase 2)** — Piper/recorded WAV, normalization, timing, Rhubarb cues.
6. **Blender layer (Phase 3/6.1)** — validated manifest, shot cameras, audio
   strips, face animation, and bounded procedural body performance.
7. **Media layer (Phase 4)** — SRT generation, loudness normalization, final MP4 export.
8. **Operations layer (Phase 5)** — one-command orchestration, logs, QA gates,
   atomic outputs, stage timing, dry-run, and resume.
9. **Studio layer (Phase 6)** — local FastAPI UI, schema-constrained motion
   intent, allowlisted jobs, artifact preview, and quality visualization.
10. **Gesture executor (Phase 6.1)** — semantic gesture clips, fixed bone aliases,
    deterministic pose synthesis, and Blender keyframe insertion.
11. **Performance Director (Phase 6.2)** — dialogue beat timing, speaker/listener
    roles, gaze targets, deterministic blinks, emotional posture, and conflict audit.
12. **Cinematic Blocking Director (Phase 6.3)** — stable stage positions, body
    facing, shot composition, bounded camera motion, and blocking risk audit.
13. **Character onboarding (Phase 7)** — content-addressed PMX/PMD bundles,
    normalized Blender caches, trusted bone/morph aliases, and asset readiness gates.
14. **Character Harmonizer (Phase 8)** — canonical semantic controls, quaternion
    rest-pose correction, cast scale/grounding, evaluated bounds, and adaptive framing.

## Project directory contract

```text
project/
├── project.yaml
├── script.txt
├── assets/
│   ├── characters/
│   ├── motions/
│   ├── environments/
│   ├── props/
│   ├── music/
│   └── sound_effects/
├── generated/
│   ├── screenplay.json
│   ├── shot_list.json
│   ├── asset_index.json
│   ├── motion_plan.json
│   ├── pipeline_state.json
│   ├── motion_intent_plan.json
│   ├── phase3_manifest.json
│   ├── phase3_scene_report.json
│   ├── phase8_harmonization_plan.json
│   ├── phase8_harmonization_report.json
│   ├── phase5_run_record.json
│   └── production_report.json
├── local_assets/                 # ignored; source bundles, profiles, registry
├── blender_cache/                # ignored; normalized character .blend files
├── dialogue/
├── lip_sync/
├── subtitles/
├── blender_scenes/
├── renders/
├── output/
│   └── final_video.mp4
└── logs/
```

Phase 2 adds `dialogue_timeline.json`, one WAV and transcript per line, and one
validated lip-sync JSON per line. Later phases consume these stable contracts
instead of reparsing raw script text inside Blender.

Phase 3 adds `phase3_manifest.json` as the trust boundary between system Python
and Blender. Blender consumes only resolved shots, frame ranges, audio paths,
camera instructions, and validated mouth cues. It produces an assembled scene,
an optional preview MP4, and `phase3_scene_report.json`.

Phase 4 consumes the rendered Phase 3 preview and the validated dialogue
timeline. It generates UTF-8 SRT, chooses burned or soft subtitles based on the
local FFmpeg build, normalizes dialogue loudness, exports `final_video.mp4`, and
probes the result before writing `phase4_report.json`.

Phase 5 treats all earlier outputs as a release candidate. It compares counts
across contracts, checks every material artifact, enforces project thresholds,
records tool versions and stage durations, and writes a schema-validated
`production_report.json`. A failed gate creates a failed report and returns a
non-zero exit code.

Phase 6 sits above the existing pipeline instead of bypassing it. Its local UI
can edit the script and propose semantic motion intent, but JSON Schema plus
screenplay identity checks form a trust boundary before the deterministic
motion selector sees the proposal. Job endpoints choose from fixed commands;
they never accept a shell command from the browser.

Phase 6.1 extends that trust boundary through Blender. The validated plan may
name only an allowlisted semantic gesture. System Python converts each gesture
to bounded Euler rotations for abstract aliases such as `head`, `spine`, and
`arm.L`; Blender resolves those aliases against a fixed application-owned map.
Neither Ollama nor edited JSON can specify a real bone name, rotation, data path,
or keyframe. Phase 5 rejects a production if a required alias is missing or a
performance clip creates no pose keys.

Phase 6.2 never changes that authority boundary. It derives timing and secondary
acting only from validated screenplay, dialogue timeline, and motion intent.
Blink schedules use stable project/character hashes rather than nondeterministic
randomness. The manifest carries events, while Blender chooses only fixed
application-owned targets: common blink morph aliases, an optional eye bone, or
the demo eye-mesh fallback.

Phase 6.3 derives spatial staging only from validated shot, gaze, and performance
contracts. System Python chooses application-owned positions, lenses, and camera
templates, then audits framing, clearance, screen order, and placement overlap.
Blender inserts only those validated transforms and reports the actual placement
and camera key counts. No AI-produced coordinate reaches the scene.

Phase 7 establishes a local asset trust boundary before Phase 3. The importer
copies the full source bundle into a content-addressed project directory,
imports it through `mmd_tools`, normalizes its collection/root transform, packs
available images, and writes a schema-validated profile. Phase 3 sees only an
activated profile with project-relative paths and application-owned aliases;
the original PMX and textures are never read directly during normal production.

Phase 8 operates after cache append and before performance/camera assembly. It
resolves every armature to the same application-owned root, body, eye, and IK
semantics; source-specific names never enter gesture code. Blender composes
bounded gesture quaternions over a neutral dialogue pose, scales each cast
member to configured proportions, grounds its evaluated mesh, and moves the
pipeline root rather than destroying the grounding offset. Camera placement is
then recomputed at each shot boundary from evaluated world-space bounds and the
real head target. A separate schema-validated report records both character and
shot evidence.

## Failure boundaries

- Invalid configuration stops before any production output is written.
- Invalid Ollama JSON is rejected; `auto` mode falls back to deterministic rules.
- Missing asset files are warnings and produce unresolved assignments.
- A missing exact action follows the configured chain and finally tries `idle`.
- JSON outputs use atomic replacement, avoiding half-written files after a crash.
- Resume skips only a completed stage whose recorded output still exists.
- One-command production stops at the first execution failure; the final audit
  reports all detectable quality failures together.
- A stale motion-intent digest is ignored during screenplay regeneration; a
  malformed plan or changed shot/character identity is rejected.
- Studio binds to loopback only and serves project paths through fixed
  document/artifact allowlists.
- Unknown procedural gestures fail validation, generated rotations are clamped,
  and unresolved bone aliases fail the final production gate.
- Overlapping character clips, missing gaze keys, or missing blink keys fail the
  Performance Director release gate.
- Missing placement/camera keys or any blocking, continuity, framing, or camera
  clearance risk fails the Cinematic Blocking release gate.
- Missing character cache, required rig/mouth/blink aliases, or required texture
  and license metadata prevents Phase 7 activation and fails the release gate.
- An A/T-pose residual, height mismatch, axis inversion, floor error, missing
  canonical control, cropped required region, or hidden head/feet prevents
  Phase 8 rendering and fails the release gate.

## Security and licensing

Asset paths are resolved below configured library roots; metadata that attempts
to escape a root is ignored. Each asset records source, creator, commercial-use,
modification, and attribution status. Unknown licensing is surfaced rather than
silently assumed to be safe.
