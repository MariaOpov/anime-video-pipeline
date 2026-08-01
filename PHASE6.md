# Phase 6 — Anime Pipeline Studio and AI motion intent

Phase 6 adds a local browser-based production console without replacing the
tested command-line pipeline. The Studio edits `script.txt`, generates a
schema-constrained motion-intent contract, launches allowlisted pipeline jobs,
shows incremental logs, previews the final MP4, and renders the Phase 5 release
gates as a dashboard.

## Setup and launch

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_phase6.ps1
.\run_studio.ps1
```

The browser opens `http://127.0.0.1:8000`. The server refuses a non-loopback
host, exposes no CORS policy, accepts no arbitrary command, and serves only
allowlisted project documents and artifacts. Press `Ctrl+C` in PowerShell to
stop it.

Use a different port or project if needed:

```powershell
.\run_studio.ps1 -Project "projects\demo" -Port 8088
```

## Ollama AI mode

Ollama is optional. Rules mode works without it. To enable the configured local
model:

```powershell
ollama pull qwen2.5:3b
ollama serve
```

Ollama receives the full `motion_intent.schema.json` through its structured
output `format` field with streaming disabled. The response is parsed as JSON,
validated again locally, checked against every original scene, shot, and
character identity, and written atomically only after all checks pass.

## Recommended workflow

1. Edit and save the script.
2. Run Phase 1 so `screenplay.json` matches the saved script.
3. Generate a motion intent using Rules or Ollama.
4. Review or edit the JSON and select **Validate & Save**.
5. Run Phase 2 for a quick dialogue check or **Run All 5 Phases** for delivery.

## Motion-intent trust boundary

`generated/motion_intent_plan.json` contains only semantic intent:

- exact scene, shot, and character identities;
- an action tag, emotion, intensity, and subtle gesture list;
- optional look target and constrained camera suggestion;
- confidence and short production notes;
- SHA-256 of the screenplay used to create the plan.

It cannot contain paths, shell commands, Python, Blender code, bone names, or
raw keyframes. The deterministic motion selector remains the authority that
maps an action tag to a compatible local asset and fallback chain.

If `script.txt` changes, the existing plan becomes stale. Phase 1 safely ignores
that stale plan so it can regenerate the screenplay; the Studio then requires a
new plan. A structurally invalid or identity-changing plan is rejected.

## Studio API

- `GET /api/status`: project, Ollama, artifact, job, and quality status.
- `GET/PUT /api/script`: read or atomically save the project script.
- `GET /api/documents/{name}`: allowlisted generated JSON documents.
- `POST /api/motion-intent/generate`: rules or Ollama generation.
- `PUT /api/motion-intent`: validate and save an edited plan.
- `POST /api/jobs`: launch Phase 1, Phase 2, or the complete production.
- `GET /api/jobs/current`: incremental log polling.
- `GET /api/artifacts/{name}`: allowlisted video or subtitle delivery.

Interactive API documentation is available locally at `/api/docs`.

The same planner can be used from PowerShell after Phase 1:

```powershell
.\.venv\Scripts\python.exe generate_motion_intent.py `
  --project projects/demo `
  --mode rules
```

Replace `rules` with `ollama` when the configured local model is running.
