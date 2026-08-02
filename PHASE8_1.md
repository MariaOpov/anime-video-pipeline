# Phase 8.1 — Character Physics, Collision & Contact Integration

Phase 8.1 starts with a read-only inventory. It does not assume that imported
MMD rigid-body helpers are already built as Blender rigid bodies, and it does
not rebuild physics automatically.

## Diagnostic boundary

`blender_scripts/inspect_phase8_1_physics.py` opens an existing character cache
or assembled scene and writes a JSON inventory. It never calls an mmd_tools
build/clean/update operator, changes the current frame, bakes a cache, saves the
`.blend`, or renders.

The inventory distinguishes:

- MMD rigid-body and joint helper objects;
- Blender rigid bodies and rigid-body constraints that are actually built;
- active, passive, and kinematic bodies;
- collision groups/masks available through either MMD metadata or Blender;
- cloth and collision modifiers plus their point-cache state;
- physics collections, hidden helper objects, and broken constraint references;
- the Rigid Body World, solver settings, and point-cache state;
- configured and effective render dimensions.

## Outputs

The diagnostic is intended to create separate generated files for:

- Aiko's character cache;
- Ren's character cache;
- the assembled Phase 3 scene.

Every output is validated against
`schemas/phase8_1_physics_inventory.schema.json` and checked for count and
render-dimension consistency by `verify_phase8_1_inventory.py`.

No collision, warm-up, contact-shadow, or render-quality change should be made
until these three inventories have been reviewed.

## Runtime integration

After cache and assembled-scene diagnostics, the runtime integration creates one scene-level Rigid Body World, links all existing Blender rigid bodies and constraints into dedicated simulation collections without removing them from their character collections, and evaluates a negative-frame warm-up while preserving the render/audio range. It does not rebuild mmd_tools physics, bake the cache, or apply a pose-clearance override.

## Ren wrist collider override

Vivian is the visible model for pipeline character `Ren`. Phase 8.1 applies
a character-scoped collider override before rigid-body warm-up:

- `017_右手首`: radial scale 1.15, length scale 1.05
- `021_左手首`: radial scale 1.15, length scale 1.05

The override is restricted to `PIPE_CHARACTER_REN`, is idempotent, and is
reported with base/applied scale and dimensions. It does not modify the
150 skirt rigid bodies and does not introduce a global arm-pose override.
