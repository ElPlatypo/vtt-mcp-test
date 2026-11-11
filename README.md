# Foundry MCP Bridge (Scenes), unofficial build

An unofficial variant of [Foundry MCP Bridge](https://github.com/adambdooley/foundry-vtt-mcp) by Adam Dooley (MIT licence, see `LICENSE`). It adds two tools:

- **`manage-scenes`**: describe, create and edit Foundry scenes (name, background image, background colour, size, grid, darkness, navigation). It never deletes anything, and it reports a warning if Foundry did not keep a requested change.
- **`upload-file`**: upload an image from the PC running Claude into the world's own folder on the Foundry server (`worlds/<world>/uploads/...`), so it can be used as a scene background or token image. Only png, jpg, webp and gif up to 20 MB, and the file must really be an image.
- **`manage-journals`**: create, update and describe journals (no delete): exact text and image pages, folders, who can see them, and `{{actor: Name}}`-style links that become clickable Foundry links. Scripts and event handlers are stripped from the HTML. Unit-tested with a faked Foundry only; not yet run against a real world.
- **`manage-scene-objects`**: place tokens, lights, walls (walls, doors, secret doors, invisible walls, windows) and map pins linked to journals by grid square (positions measured from the top-left of the map), describe what is on a scene, and remove only the objects this tool created. **`preview-scene`**: renders the map with a numbered grid plus its tokens and lights to a PNG so positions can be checked. Unit-tested with a faked Foundry only; not yet run against a real world.

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
