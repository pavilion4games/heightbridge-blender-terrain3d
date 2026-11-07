"""Heightmap file writers (numpy only, no bpy).

EXR is written directly (uncompressed, 32-bit float, scanline) instead of via
bpy image saving, so no color management or half-float conversion can alter
the height values. Godot/Terrain3D read the heights from the R channel.
"""

import json
import struct

import numpy as np


def _attr(name, type_name, data):
    return (name.encode() + b"\0" + type_name.encode() + b"\0"
            + struct.pack("<i", len(data)) + data)


def write_exr(path, heights, channels=("R",)):
    """Write a (H, W) float array as a 32-bit float uncompressed OpenEXR.

    Every channel in `channels` receives the same height data.
    """
    heights = np.ascontiguousarray(heights, dtype="<f4")
    h, w = heights.shape
    channels = sorted(channels)  # EXR requires alphabetical channel order

    chlist = b""
    for ch in channels:
        # name, pixel_type=2 (FLOAT), pLinear=0, reserved x3, xSampling, ySampling
        chlist += ch.encode() + b"\0" + struct.pack("<iB3xii", 2, 0, 1, 1)
    chlist += b"\0"
    box = struct.pack("<iiii", 0, 0, w - 1, h - 1)

    header = b"".join((
        struct.pack("<ii", 20000630, 2),
        _attr("channels", "chlist", chlist),
        _attr("compression", "compression", b"\x00"),
        _attr("dataWindow", "box2i", box),
        _attr("displayWindow", "box2i", box),
        _attr("lineOrder", "lineOrder", b"\x00"),
        _attr("pixelAspectRatio", "float", struct.pack("<f", 1.0)),
        _attr("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0)),
        _attr("screenWindowWidth", "float", struct.pack("<f", 1.0)),
        b"\0",
    ))

    row_bytes = w * 4 * len(channels)
    block_size = 8 + row_bytes
    first = len(header) + 8 * h
    offsets = np.arange(h, dtype="<u8") * block_size + first

    with open(path, "wb") as f:
        f.write(header)
        f.write(offsets.tobytes())
        for y in range(h):
            row = heights[y].tobytes()
            f.write(struct.pack("<ii", y, row_bytes))
            f.write(row * len(channels))


def write_r16(path, heights, min_h, max_h):
    """Write little-endian unsigned 16-bit RAW, normalized to [min_h, max_h]."""
    rng = max_h - min_h
    if rng <= 0:
        data = np.zeros(heights.shape, dtype="<u2")
    else:
        norm = (np.nan_to_num(heights, nan=min_h) - min_h) / rng
        data = np.clip(np.round(norm * 65535.0), 0, 65535).astype("<u2")
    with open(path, "wb") as f:
        f.write(data.tobytes())


def write_sidecar(path, info):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
