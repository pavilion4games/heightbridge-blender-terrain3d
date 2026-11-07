# Heightbridge: Blender → Terrain3D Heightmap Exporter

A Blender extension (Blender 5.0+) that exports terrain meshes as heightmaps for the Godot [**Terrain3D**](https://github.com/TokisanGames/Terrain3D) importer.

- **EXR (recommended):** 32-bit float, one `R` channel, containing the real heights in meters.
- **R16:** 16-bit little-endian RAW, normalized from the lowest height to the highest. When you import it, Terrain3D needs the height range and image size; both are in the `.json` sidecar.

The exporter reads the evaluated mesh, so modifiers, geometry nodes and shape keys are included. It samples straight down at every vertex of the grid. Where surfaces overlap, it keeps the highest one.

## Install

1. Download `terrain3d_heightmap_exporter-<version>.zip` from the [latest release](https://github.com/pavilion4games/heightbridge-blender-terrain3d/releases/latest).
2. In Blender, go to **Edit › Preferences › Get Extensions › ⌄ › Install from Disk…** and pick the zip. Don't unzip it.

## Use

Select your terrain mesh(es), then use either:
- **File › Export › Terrain3D Heightmap (.exr/.r16)**, or
- **3D Viewport › Sidebar (N) › Terrain3D › Export Terrain3D Heightmap**

| Option | Meaning |
|---|---|
| Vertex Spacing | Meters per pixel. It must match `vertex_spacing` on the Terrain3D node (default 1.0). |
| Bounds | **Auto** uses the meshes' XY bounding box. **Custom** uses a fixed rectangle in Blender XY. |
| Snap Bounds to Grid | Aligns the edges to multiples of the spacing. It is ignored when Align to Regions is on. |
| Align to Regions | On by default. Moves the top-left corner onto Terrain3D's region grid and pads the image to whole regions, so the **Import Position** is an exact integer. The importer's `import_position` is a `Vector2i`. |
| Region Size | Must match `region_size` on the Terrain3D node (Terrain3D's default is 256). |
| Apply Unit Scale | Multiplies coordinates by the scene's Unit Scale so the output is in meters. |
| Height Scale / Offset | `height * scale + offset` |
| Empty Pixels | Fills pixels that no mesh covers, including region padding, with the lowest height or a fixed value. |
| Write Info JSON | Writes `<name>.json` with the size, height range and suggested Terrain3D import settings. |

## Import in Godot (Terrain3D)

Tested with Terrain3D 1.0.2 on Godot 4.6.2.

1. Open `addons/terrain_3d/tools/importer.tscn`. On that Terrain3D node, set **Region Size** and **Vertex Spacing** to `terrain3d.region_size` and `terrain3d.vertex_spacing` from the JSON.
2. Set **Height File Name** to the exported `.exr` or `.r16` file.
3. Set **Import Position** to `terrain3d.import_position` from the JSON. That value is the top-left corner in Godot world space, so the terrain lands where it was in Blender.
4. Keep **Import Scale** at `1.0` and **Height Offset** at `0.0`. The EXR already contains real meters.
5. For **R16** only: set **R16 Range** to `r16_range` and **R16 Size** to `r16_size` from the JSON.
6. Click **Run Import**. Set **Destination Directory**, then click **Save to Disk**.
7. On your game's Terrain3D node, use the same region size and vertex spacing, and point **Data Directory** at that folder.

If the JSON lists `warnings`, fix them first. The two warnings are a non-integer import position, and a terrain larger than Terrain3D's world bounds, which is ±16 × region_size × vertex_spacing meters.

## Axis mapping

| Blender | Godot |
|---|---|
| +X | +X |
| +Z (up) | +Y (up) |
| +Y | −Z |

Image column → +X. Image row → +Z in Godot, which is −Y in Blender. The top row of the image is the mesh's max‑Y edge.

## Build from source

The add-on lives in [`terrain3d_heightmap_exporter/`](terrain3d_heightmap_exporter/). To build the installable zip into `dist/`, run either:

```
python build.py
```
```
blender --command extension build --source-dir terrain3d_heightmap_exporter --output-dir dist
```

## Releasing

1. Bump `version` in `terrain3d_heightmap_exporter/blender_manifest.toml` and add an entry to `CHANGELOG.md`.
2. Commit, then tag and push: `git tag v1.2.3 && git push origin v1.2.3`

The [Release workflow](.github/workflows/release.yml) builds the zip and attaches it to a GitHub Release. The tag must match the manifest version.

## License

[GPL-3.0-or-later](LICENSE), as required for Blender add-ons. The heightmaps you export are your own; the license doesn't apply to them.
