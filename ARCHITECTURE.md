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
6. **Blender layer (Phase 3)** — validated manifest, shot cameras, audio strips, face animation.
7. **Media layer (Phase 4)** — subtitles, audio mix, and FFmpeg export.
8. **Operations layer** — logs, atomic outputs, stage state, dry-run, resume.

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
│   └── pipeline_state.json
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

## Failure boundaries

- Invalid configuration stops before any production output is written.
- Invalid Ollama JSON is rejected; `auto` mode falls back to deterministic rules.
- Missing asset files are warnings and produce unresolved assignments.
- A missing exact action follows the configured chain and finally tries `idle`.
- JSON outputs use atomic replacement, avoiding half-written files after a crash.
- Resume skips only a completed stage whose recorded output still exists.

## Security and licensing

Asset paths are resolved below configured library roots; metadata that attempts
to escape a root is ignored. Each asset records source, creator, commercial-use,
modification, and attribution status. Unknown licensing is surfaced rather than
silently assumed to be safe.
