"""Rasterize mesh triangles into a top-down heightmap grid (numpy, no bpy).

Coordinate convention (Blender Z-up -> Godot Y-up):
    Godot X =  Blender X
    Godot Y =  Blender Z   (height)
    Godot Z = -Blender Y
Image column j -> Godot X = origin_x + j * spacing
Image row    i -> Godot Z = origin_z + i * spacing  (i.e. Blender Y decreases downward)
Pixels sample the terrain at exact vertex positions, matching Terrain3D where
each heightmap pixel is one terrain vertex.
"""

import numpy as np

# Max candidate pixels evaluated per vectorized batch (memory guard).
_BATCH_PIXELS = 4_000_000
_EPS = 1e-6


def compute_grid(min_x, max_x, min_y, max_y, spacing):
    """Return (width, height) of a grid covering the XY bounds at the given spacing."""
    width = int(np.floor((max_x - min_x) / spacing + _EPS)) + 1
    height = int(np.floor((max_y - min_y) / spacing + _EPS)) + 1
    return max(width, 1), max(height, 1)


def rasterize(verts, tris, min_x, max_y, spacing, width, height):
    """Rasterize triangles into a (height, width) float32 array.

    verts: (N, 3) float array of world-space positions (meters).
    tris:  (T, 3) int array of vertex indices.
    Where several surfaces overlap, the highest one wins.
    Pixels not covered by any triangle are NaN.
    """
    out = np.full(width * height, -np.inf, dtype=np.float64)
    if len(tris) == 0:
        return np.full((height, width), np.nan, dtype=np.float32)

    # Vertex positions in pixel space (col, row).
    px = (verts[:, 0] - min_x) / spacing
    py = (max_y - verts[:, 1]) / spacing
    pz = verts[:, 2]

    ax, bx, cx = px[tris[:, 0]], px[tris[:, 1]], px[tris[:, 2]]
    ay, by, cy = py[tris[:, 0]], py[tris[:, 1]], py[tris[:, 2]]
    az, bz, cz = pz[tris[:, 0]], pz[tris[:, 1]], pz[tris[:, 2]]

    denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)

    c0 = np.ceil(np.minimum(np.minimum(ax, bx), cx) - _EPS).astype(np.int64)
    c1 = np.floor(np.maximum(np.maximum(ax, bx), cx) + _EPS).astype(np.int64)
    r0 = np.ceil(np.minimum(np.minimum(ay, by), cy) - _EPS).astype(np.int64)
    r1 = np.floor(np.maximum(np.maximum(ay, by), cy) + _EPS).astype(np.int64)
    np.clip(c0, 0, width - 1, out=c0)
    np.clip(c1, 0, width - 1, out=c1)
    np.clip(r0, 0, height - 1, out=r0)
    np.clip(r1, 0, height - 1, out=r1)

    nw = c1 - c0 + 1
    nh = r1 - r0 + 1
    valid = (nw > 0) & (nh > 0) & (np.abs(denom) > 1e-12)
    counts = np.where(valid, nw * nh, 0)

    tri_data = (ax, ay, az, bx, by, bz, cx, cy, cz, denom, c0, r0, nw)

    # Triangles covering a huge pixel area are processed alone, in row bands.
    big = np.nonzero(counts > _BATCH_PIXELS)[0]
    small = np.nonzero((counts > 0) & (counts <= _BATCH_PIXELS))[0]

    # Batch small triangles so each batch evaluates ~_BATCH_PIXELS candidates.
    if len(small):
        csum = np.cumsum(counts[small])
        batch_ids = csum // _BATCH_PIXELS
        splits = np.nonzero(np.diff(batch_ids))[0] + 1
        for group in np.split(small, splits):
            _raster_batch(out, width, group, counts[group], tri_data)

    for t in big:
        rows_per_band = max(1, _BATCH_PIXELS // int(nw[t]))
        for band_start in range(int(r0[t]), int(r1[t]) + 1, rows_per_band):
            band_end = min(int(r1[t]), band_start + rows_per_band - 1)
            _raster_single_band(out, width, t, band_start, band_end, tri_data)

    out[np.isneginf(out)] = np.nan
    return out.reshape(height, width).astype(np.float32)


def _raster_batch(out, width, group, counts, tri_data):
    ax, ay, az, bx, by, bz, cx, cy, cz, denom, c0, r0, nw = tri_data
    total = int(counts.sum())
    idx = np.repeat(group, counts)
    starts = np.repeat(np.cumsum(counts) - counts, counts)
    local = np.arange(total, dtype=np.int64) - starts
    w = nw[idx]
    col = c0[idx] + local % w
    row = r0[idx] + local // w
    _write(out, width, idx, col, row, tri_data)


def _raster_single_band(out, width, t, row_start, row_end, tri_data):
    c0, nw = tri_data[10], tri_data[12]
    cols = np.arange(c0[t], c0[t] + nw[t], dtype=np.int64)
    rows = np.arange(row_start, row_end + 1, dtype=np.int64)
    col = np.tile(cols, len(rows))
    row = np.repeat(rows, len(cols))
    idx = np.full(col.shape, t, dtype=np.int64)
    _write(out, width, idx, col, row, tri_data)


def _write(out, width, idx, col, row, tri_data):
    ax, ay, az, bx, by, bz, cx, cy, cz, denom = tri_data[:10]
    x = col.astype(np.float64)
    y = row.astype(np.float64)
    d = denom[idx]
    w0 = ((by[idx] - cy[idx]) * (x - cx[idx]) + (cx[idx] - bx[idx]) * (y - cy[idx])) / d
    w1 = ((cy[idx] - ay[idx]) * (x - cx[idx]) + (ax[idx] - cx[idx]) * (y - cy[idx])) / d
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -_EPS) & (w1 >= -_EPS) & (w2 >= -_EPS)
    if not inside.any():
        return
    idx = idx[inside]
    h = w0[inside] * az[idx] + w1[inside] * bz[idx] + w2[inside] * cz[idx]
    np.maximum.at(out, row[inside] * width + col[inside], h)


def fill_holes(heights, mode, value=0.0):
    """Replace NaN pixels. mode: 'MIN' (lowest height) or 'VALUE'."""
    mask = np.isnan(heights)
    if not mask.any():
        return heights, int(mask.sum())
    if mode == 'MIN':
        fill = np.nanmin(heights) if (~mask).any() else 0.0
    else:
        fill = value
    heights = heights.copy()
    heights[mask] = fill
    return heights, int(mask.sum())
