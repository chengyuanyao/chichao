# CLAUDE.md

This file gives Claude Code the repository-specific context needed to work safely in this project.

## Project overview

`chichao` is a dependency-free LAN browser RTS. The Python server is authoritative and runs the
20 Hz simulation; the browser client uses the vendored three.js build and WebGL2. There is no
package-manager or frontend build step.

The game and most code comments are Chinese. Preserve the language and terminology already used
near the code being changed.

## Run and test

```bash
python server.py              # starts on 0.0.0.0:18081 by default
python run_tests.py           # runs every offline tests/*_test.py
python tests/map_test.py      # runs one offline test directly
python tests/integration_test.py http://127.0.0.1:18081
```

On Windows, `start-game.bat` is the normal player-facing launcher. On Linux and macOS, use
`./start-game.sh`. `HOST` and `PORT` override the listener; `IFL_CHEATS=1` exposes the debugging
cash endpoint beyond localhost.

Before finishing a code change, run the focused test for the affected behavior and then
`python run_tests.py` when practical. The integration test requires a separately running server
and is intentionally skipped by `run_tests.py`.

## Repository map

- `server.py`: HTTP/SSE API, rooms, maps, pathfinding, authoritative simulation, visibility,
  combat, economy, and static-file serving.
- `catalog.py`: shared unit, structure, faction, and public catalog definitions. `server.py`
  re-exports these symbols for compatibility with existing tests and imports.
- `easter_eggs.py`: deterministic flavor payload helpers; decorative map props were removed, so
  do not reintroduce client-rendered scenery through this module.
- `public/app.js`: client networking, state reconciliation, input, lobby, HUD, and minimap.
- `public/render3d.js`: procedural three.js scene, terrain, unit/building meshes, picking, fog, and
  visual effects.
- `public/postfx.js`: bloom, tone mapping, and FXAA pipeline.
- `public/styles.css` and `public/index.html`: game UI and layout.
- `tests/`: executable offline regression scripts. Tests generally import modules directly and
  use plain assertions instead of a third-party test framework.

## Important constraints

- Keep runtime code compatible with Python 3.6 and the Python standard library. Do not add a
  Python or JavaScript dependency without an explicit project-level decision.
- Keep the simulation authoritative on the server. Client-side changes must not decide combat,
  resources, visibility, placement validity, or victory.
- Protect the room registry with `LOCK` and each match's mutable simulation state with
  `room_lock(room)`. Do not put per-room terrain, pathfinding, or simulation state in module-level
  mutable globals.
- Changing selection on the client must not cancel already issued move or attack orders. Explicit
  commands such as move, attack, stop, or repair may replace/cancel orders as their behavior
  requires.
- Static world data is sent in the first SSE frame and cached by the client. Incremental frames
  should not resend large map/catalog payloads.
- Preserve fog-of-war rules: explored terrain remains known, while enemy mobile entities require
  current vision. Team/alliance vision is shared.
- Mountains and rivers are gameplay blockers, not decoration. Map edits must preserve spawn and
  ore reachability; validate them with `tests/map_test.py` and `tests/water_test.py` as applicable.
- Unit or structure balance changes belong in `catalog.py` and should be accompanied by a focused
  regression test. Keep UI-visible catalog data derived from the same source.
- The renderer intentionally batches procedural geometry and avoids per-object draw calls. When
  adding visuals, preserve instancing/merged geometry, visibility culling, and dirty-update paths.
- three.js is vendored under `public/vendor/`; the game must remain playable without internet
  access.

## Change hygiene

- Prefer a small regression test that demonstrates the behavior before or alongside a fix.
- Update `README.md` when controls, gameplay rules, balance descriptions, maps, launch behavior,
  ports, or architecture materially change.
- Do not commit generated logs, PID files, or `__pycache__` directories.
