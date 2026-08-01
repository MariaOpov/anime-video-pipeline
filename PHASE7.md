# Phase 7 — Production character onboarding

Phase 7 replaces selected demo mannequins with locally owned PMX/PMD characters
without allowing an uninspected model bundle to enter a production render. The
source model and its texture folder remain local and are never committed.
It requires the same enabled `mmd_tools` extension already used by the project's
Blender installation.

## First onboarding

Keep the `.pmx`/`.pmd` and all referenced textures together in their original
folder. Find the model path, then onboard it as one project character:

```powershell
Get-ChildItem "$env:USERPROFILE\Downloads","D:\MMD" `
  -Recurse `
  -File `
  -Include "*.pmx","*.pmd" |
  Select-Object Name, FullName
```

```powershell
.\run_phase7.ps1 `
  -Character Aiko `
  -Model "D:\Models\Flavia\芙拉薇娅.pmx" `
  -Creator "Unknown" `
  -Source "Unknown" `
  -LicenseName "Unknown"
```

Use the real creator, source URL/file, and license whenever known. `Unknown` is
permitted by the demo configuration but remains visible as a license warning.
Do not publish the model or its textures unless its license explicitly permits
redistribution.

## Guarded import flow

1. Validate the project character and PMX/PMD source.
2. Hash the model and copy its complete bundle into a content-addressed local
   directory so relative texture references remain intact.
3. Import through the installed `mmd_tools` operator in background Blender.
4. Normalize height, ground position, collection ownership, and orientation.
5. Resolve application-owned aliases for spine, head, arms, legs, eyes, five
   mouth vowels, and blink.
6. Pack available textures and save a reusable character-only `.blend` cache.
7. Validate the generated profile and activate it in the local registry.

The source bundle, registry, profile, and Blender cache live below ignored
`local_assets/` and `blender_cache/` directories. The repository contains only
the importer, schemas, configuration, and tests.

## Production integration

The next Phase 3 manifest embeds only a validated, project-relative contract.
Blender appends the cached collection, removes the matching demo mannequin,
uses the mapped rig aliases for procedural performance, and uses the real mouth
and blink morphs when available. Any character without an active profile keeps
its mannequin, allowing one-model acceptance before a full cast is available.

Phase 5 adds the `production_character_assets_ready` gate. It checks that every
configured character was ready in the manifest, loaded in Blender, resolved to
the expected number of bones and mouth morphs, and retained the audited texture
and license status.

## Acceptance

After onboarding, run a complete preview:

```powershell
.\run_all.ps1 -Render
```

```powershell
$Report = Get-Content `
  ".\projects\demo\generated\production_report.json" `
  -Encoding UTF8 | ConvertFrom-Json

$Report.summary | Select-Object `
  passed_gate_count, quality_gate_count, `
  production_character_count, production_character_loaded_count, `
  resolved_character_bone_alias_count, `
  resolved_character_mouth_morph_count, `
  character_texture_missing_count, character_license_warning_count
```

Acceptance requires the model to face the camera correctly, remain grounded,
stay within the cinematic framing, animate the intended head/body gestures,
lip-sync with its own morphs, blink, and render with no missing texture.
If a model faces backward, change `phase7.rotation_z_degrees` to `180.0`, rerun
onboarding, and repeat the acceptance render.

## Failure handling

The Blender profile is written even when the final coverage gate rejects it.
Inspect `projects/demo/local_assets/characters/<character>/character.profile.json`
to see exact bone/morph names and missing textures. A failed onboarding never
updates the active registry, so the last known-good production setup remains in
effect.
