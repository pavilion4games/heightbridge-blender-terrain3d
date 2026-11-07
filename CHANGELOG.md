# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-07

### Added
- Export selected (or all visible) meshes as a Terrain3D heightmap: 32-bit float EXR or 16-bit R16 RAW.
- Uses the evaluated mesh, so modifiers, geometry nodes and shape keys are included.
- Region alignment so the Terrain3D import position is a whole number, with padding to whole regions.
- JSON sidecar with image size, height range and suggested Terrain3D import settings.
- File › Export menu entry and a 3D Viewport sidebar panel.

[1.0.0]: https://github.com/pavilion4games/heightbridge-blender-terrain3d/releases/tag/v1.0.0
