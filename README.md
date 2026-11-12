# Foundry MCP Bridge (Scenes), unofficial build

An unofficial variant of [Foundry MCP Bridge](https://github.com/adambdooley/foundry-vtt-mcp) by Adam Dooley (MIT licence, see `LICENSE`). It adds two tools:

- **`manage-scenes`**: describe, create and edit Foundry scenes (name, background image, background colour, size, grid, darkness, navigation). It never deletes anything, and it reports a warning if Foundry did not keep a requested change.
- **`upload-file`**: upload an image from the PC running Claude into the world's own folder on the Foundry server (`worlds/<world>/uploads/...`), so it can be used as a scene background or token image. Only png, jpg, webp and gif up to 20 MB, and the file must really be an image.
- **`manage-journals`**: create, update and describe journals (no delete): exact text and image pages, folders, who can see them, and `{{actor: Name}}`-style links that become clickable Foundry links. Scripts and event handlers are stripped from the HTML. Unit-tested with a faked Foundry only; not yet run against a real world.
- **`manage-scene-objects`**: place tokens, lights, walls (walls, doors, secret doors, invisible walls, windows) and map pins linked to journals by grid square (positions measured from the top-left of the map), describe what is on a scene, and remove only the objects this tool created. **`preview-scene`**: renders the map with a numbered grid plus its tokens and lights to a PNG so positions can be checked. Unit-tested with a faked Foundry only; not yet run against a real world.
- **`inspect-document`**: read-only look at raw Foundry data (list, get with path/depth limits, schema) so exact fields can be checked instead of guessed. **Custom ComfyUI**: the Configure Map Generation dialog can point map generation at a ComfyUI you already run (host, port, https) instead of the built-in one. Unit-tested with a faked Foundry only.
- **`generate-image`** and **`describe-image-generation`**: generate maps, portraits, tokens and handouts with your own ComfyUI (built-in or custom). Per-kind profiles (**Configure Image Generation**) choose a checkpoint workflow (SDXL) or **MiniMax H3 Image**, which also takes reference pictures (`reference_images`, named <Picture 1>... in the prompt) to keep a character consistent. Results are uploaded to the world. The old `generate-map`, `check-map-status` and `cancel-map-job` tools are switched off. Generation checked against a real ComfyUI; the dialog not yet in a real world.
- **`measure-grid`**: measures the grid drawn into a map picture (pixels per square and offset), from a scene background or an image, optionally over a floor `region`; says "no grid" for gridless maps. `manage-actors` also takes `tokenImg` to set the token picture separately from the portrait.
- **`manage-regions`**: creates regions (difficult terrain, traps that run a macro, pop-up text, teleports) from shapes in grid squares, lists them, removes the ones it made, and `behavior_types` shows what each behavior accepts. `preview-scene` takes a `region` to zoom in on one area for precise wall placement.
- **Map extras (0.8.6.16)**: `manage-scene-objects` also places tiles and ambient sounds and sets token width/height; `manage-scenes` sets opening view, weather, fog mode, grid shift and grid style; the difficult-terrain preset uses the dnd5e behavior when present. Unit-tested with a faked Foundry only.
- **World housekeeping (0.8.6.17)**: new `manage-world` tool (list/create folders, move, rename, delete with `confirm`); `manage-actors` and `create-actor-from-compendium` take `token` (size, disposition...), dnd5e `hp` and `folder`. Unit-tested with a faked Foundry only.
- **Roll tables and macros (0.8.6.18)**: `manage-roll-tables` (create from rows, update, list, describe, roll to chat) and `manage-macros` (create, update, list, describe, execute; usable from region `executeMacro` behaviors). Unit-tested with a faked Foundry only.
- **Layouts (0.8.6.20)**: `layout` builds a map layout step by step (rooms, corridors, roads, rivers, doors; grid snapping with freeform and rotation), shows it as a text map after every change, supports undo and redo, overlays a reference picture such as a book page, renders a flat-colour sketch for `generate-image` reference_images, and `apply_walls` builds walls and doors from the layout and places them on the scene. Runs in the MCP server; unit-tested with a faked Foundry only.
- **Combat control (0.8.6.38)**: the new `combat` tool runs Foundry's own combat tracker (so tracker modules built on it keep working): `start` builds the encounter from the tokens on a scene (all, hostile, friendly, players, npcs or names; hidden tokens included), rolls initiative and begins; `add`, `remove`, `roll`, `set_initiative`, `next`, `previous`, `next_round`, `damage` and `heal` (through the system, reporting hp before and after), `defeat` and `end`. Every action returns a short readout: round, whose turn, one line per combatant. Unit-tested; not yet tried on a live Foundry.
- **Checks after placing walls, smaller results (0.8.6.37)**: `layout apply_walls` and `build` now run the wall check right after placing walls, join ends that stop just short of another wall, drop duplicates and report only what is left (`wallCheck`). To save tokens, `preview-scene` results list only the tokens, lights and pins in view (and nothing when labels are off or `legend:false`), a zoomed picture defaults to 1000 px, and `manage-scene-objects describe kind wall` returns short rows and accepts a `region`. Unit-tested; not yet tried on a live Foundry.
- **Wall check and clearer preview (0.8.6.36)**: `manage-scene-objects` has a new action `check_walls` that reads a scene's walls and reports ends that stop just short of another wall (with the point they should join), loose ends, doors that touch no wall, duplicate, tiny and diagonal walls; `fix: true` joins the gaps and removes duplicates of walls the tool placed. `preview-scene` now draws every element (walls, doors, tokens, lights, regions, tiles, pins) with dark outlines, thicker lines, door end ticks and dots at wall ends. Unit-tested; not yet tried on a live Foundry.
- **Edit part of a picture (0.8.6.35)**: `edit-image-area` changes one area of a map, portrait or item with MiniMax H3 and leaves the rest pixel-identical: the area is outlined in red on the whole picture, H3 redraws the inside and removes the outline, and only the area is pasted back. `edit` works from a Notes for Claude area note, a scene map with an area in grid squares, or any image with an area in percent or pixels, and returns a before and after preview; `commit` backs the scene up, uploads the picture, sets it as the scene map and marks the note done. Also: a softer pink-edge cleanup for actor tokens. Unit-tested; not yet tried on a live Foundry.
- **Notes for Claude fix (0.8.6.34)**: the select, rectangle and polygon tools now work on Foundry v14 (they used the wrong canvas coordinate call and PixiJS 8 drawing calls; v14 uses PixiJS 7). Tried in a live Foundry: select, both area tools, numbered pins, saving notes and reading them with `annotations`.
- **Notes for Claude (0.8.6.33)**: a "Notes for Claude" group in the GM's scene controls (upper left) with select, rectangle and polygon tools and a notes list. Click an object or draw an area, write what should change, and the note is kept on the scene with a numbered pin; the new `annotations` tool lets Claude list open notes (with the object or area in grid squares and what is inside it), resolve them with a reply the GM sees, and clear finished ones. Needs 0.8.6.34 or later on Foundry v14.
- **Running the table (0.8.6.32)**: `campaign-memory` (a GM-only journal as long-term memory: `brief` at the start of a session, `log` what happened, `recall` by words), `read-table` (recent chat and rolls, the combat tracker, party vitals and who is online in one call, with `since_id` to see only what is new) and `reveal` (show or hide tokens, lights, tiles, sounds, drawings and secret doors on any scene, and reset fog). `make-actor-art` tokens now show only the named subject and lose the magenta fringe. Unit-tested; not yet tried on a live Foundry.
- **Loot, art and sharing (0.8.6.31)**: `make-chest` (a loot chest actor with items, currency and ownership, optionally placed as a token), `add-compendium-items` (add items to an actor by exact name, stacking repeats), `make-actor-art` (portrait and transparent square token generated, uploaded and set on the actor and its placed tokens), `manage-journals` takes `pin` (create and pin on a scene in one call) and `share-with-players` (show an image full-screen or open a journal for players). `make-prop` clears enclosed background pockets, `audit-world` recognises default dnd5e actor images. Unit-tested; not yet tried on a live Foundry.
- **Polish (0.8.6.30)**: `manage-scene-objects` gains `update` (move or edit pins, lights, tokens, tiles, sounds and door states it placed); `scene` works as the scene argument of `manage-scenes` and `update-scene-music`; `move-token` takes `units:"squares"` and `get-token-details` finds tokens on any scene; `layout` puts roads under buildings, defaults the build file extension and aligns town layouts; `audit-world` also checks pins, dark scenes without lights, default actor images and unowned characters. MiniMax H3 images are always generated at 2 megapixels or more and can be shrunk afterwards (`make-prop` `final_size`, `generate-image` `max_side`). Unit-tested; not yet tried on a live Foundry.
- **Towns and world audit (0.8.6.29)**: `layout` gains a `building` shape (a block with doors on chosen sides), `repeat` for rows of shapes and a `portals` action listing each door with the squares outside and inside it; new read-only `audit-world` lists what is missing or broken in the world (backgrounds, walls, tokens, music, broken or hidden teleports, empty playlists). `setup-scene-sound` describe shows the scene music. Unit-tested; not yet tried on a live Foundry.
- **Files, backups and scene sound (0.8.6.27)**: `browse-files` lists files on the server (find music and art already uploaded for other worlds); `manage-scene-backups` copies a scene to a Backups folder and restores it into the original scene (id kept, safety copy first); `setup-scene-sound` sets a scene's music playlist and ambient sounds in one call; token detection modes use the v14 format. Unit-tested; not yet tried on a live Foundry.
- **Fixes (0.8.6.25)**: `manage-playlists create` works on Foundry v14 (it used a removed collection method); `update-token` now exposes its `options` and `scene` inputs.
- **Preview tiles, actor vision/light and audio (0.8.6.24)**: `preview-scene` draws tiles; the token options of `manage-actors` and `update-token` cover vision range and mode, light (presets, animation), detection modes and any other prototype token field, and tokens are found on any scene; `upload-file` takes audio (mp3, ogg, wav, flac, m4a); `manage-playlists` can add and remove sounds; `control-playlist` adds pause, resume, next, previous, set-volume, now-playing and stop-all. Unit-tested; not yet tried on a live Foundry.
- **Teleports and props (0.8.6.23)**: `manage-regions` gains `link`, which joins two places (same scene or two scenes) with teleport regions, one way or both. New `make-prop` tool generates an object on a flat colour, removes the background, uploads a transparent PNG and can lay it on a scene as a tile. Unit-tested; not yet tried on a live Foundry.
- **Modules (0.8.6.22)**: new `manage-modules` tool lists the installed Foundry modules, describes them (requirements, settings, public API), reads and changes their settings, calls functions of their public API and switches them on or off (with a plan first, then `confirm`; reload needed). Unit-tested; not yet tried on a live Foundry.
- **Checking and building (0.8.6.21)**: `preview-scene` can now draw chosen `layers` (tokens only, walls and doors only, light radii, regions), number tokens, lights and regions with a legend instead of overlapping names, dim the map, and return an exact text map with `text:true` (no image). `layout` gains `check` (unconnected areas, doors that connect nothing, objects on rock or sharing a square), `place` (tokens, lights and pins inside named shapes, spread out and away from walls), `lights` (proposes torches for rooms and caves), `align` (finds the shift that makes a generated picture match the layout) and `build` (sketch, generate, upload, scene, align and walls in one call). Unit-tested; not yet tried on a live Foundry.

It installs under its own id, `foundry-mcp-bridge-scenes`, so it can sit next to the original module. **Enable only one of the two per world:** both connect to the same MCP server port and the modules are marked as conflicting.

> Status: `manage-scenes` has been checked against a real Foundry v14.369 world (describe, create, rename, grid, darkness, global light, background image set and clear). `upload-file` is unit-tested with a faked Foundry only and has not yet been run against a real world. On v14 the canvas colour and background image live on the scene's first Level, which this build handles.

## Install in Foundry (needs the Setup-screen admin)

1. Leave your world and go to the **Setup** screen.
2. **Add-on Modules > Install Module**, paste this into **Manifest URL**, click **Install**:

   ```
   https://raw.githubusercontent.com/ElPlatypo/vtt-mcp-test/main/foundry-mcp-bridge-scenes/module.json
   ```

3. Launch the world, then **Manage Modules**: enable **Foundry MCP Bridge (Scenes)** and **disable** the original "Foundry MCP Bridge".
4. In the module settings, check that **Allow Write Operations** is on. This module has its own settings, separate from the original.

## Update the MCP server on the PC that runs Claude

The Foundry module talks to the MCP server on your own PC. Replace the server's backend with the one in `mcp-server/`:

1. Fully quit anything using the server (Claude Desktop from its tray icon, any Claude Code session).
2. In the installed server's `dist` folder (the Windows installer puts it at `%LOCALAPPDATA%\FoundryMCPServer\foundry-mcp-server\packages\mcp-server\dist\`), rename `backend.bundle.cjs` to `backend.bundle.cjs.original`.
3. Copy `mcp-server/backend.bundle.cjs` from this repo into that folder.
4. Start a new Claude session. `manage-scenes` appears among the `foundry-mcp` tools.

## Using it

Open your world in a browser tab (the bridge only works while a GM tab is open), then ask Claude things like:

- "Describe all scenes."
- "Create a scene called Cave Mouth, 4000 by 3000, grid 100 px, 5 ft."
- "Rename Cave Mouth to Cragmaw Entrance and set darkness to 0.6."
- "Set the background of Cragmaw Entrance to worlds/my-world/maps/cave.webp." (the image must already be on the Foundry server; `upload-file` can put it there)
- "Upload C:\maps\cave.webp to the maps folder, then use it as the background of Cragmaw Entrance."

## Layout of this repository

| Path | What it is |
|---|---|
| `foundry-mcp-bridge-scenes/` | The Foundry module: `module.json` (the manifest) and the zip it downloads. |
| `mcp-server/` | The MCP server files for the PC running Claude. `backend.bundle.cjs` is the changed part; `index.cjs` is unchanged from upstream v0.8.6. |
| `source/manage-scenes.patch` | Every source change against upstream v0.8.6, as a diff. |
| `LICENSE` | Upstream MIT licence. |

## What changed against upstream 0.8.6

See `source/manage-scenes.patch`. In short: the new `manage-scenes` tool (server tool definition and routing, module handler), the module id changed to `foundry-mcp-bridge-scenes` (with the socket name following it), the server-to-module message prefix kept as `foundry-mcp-bridge` so the unmodified server stays compatible, a conflict flag against the original module, and tests.
