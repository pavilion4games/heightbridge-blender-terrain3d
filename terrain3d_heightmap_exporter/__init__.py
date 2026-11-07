"""Terrain3D Heightmap Exporter.

Exports selected mesh objects as a top-down heightmap that Godot's Terrain3D
importer can load: 32-bit float EXR (real heights in meters) or 16-bit R16 RAW.
"""

import os
import time

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty
from bpy_extras.io_utils import ExportHelper

from . import sampler, writers

MAX_DIMENSION = 16384

FORMAT_EXT = {'EXR': ".exr", 'R16': ".r16"}


def _collect_geometry(context, objects, apply_modifiers, unit_scale):
    """Return world-space (verts, tris) of all objects merged, in meters."""
    depsgraph = context.evaluated_depsgraph_get()
    all_verts, all_tris = [], []
    offset = 0
    for obj in objects:
        src = obj.evaluated_get(depsgraph) if apply_modifiers else obj
        mesh = src.to_mesh()
        try:
            mesh.calc_loop_triangles()
            nv = len(mesh.vertices)
            nt = len(mesh.loop_triangles)
            if nv == 0 or nt == 0:
                continue
            co = np.empty(nv * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", co)
            co = co.reshape(nv, 3)
            tris = np.empty(nt * 3, dtype=np.int64)
            mesh.loop_triangles.foreach_get("vertices", tris)
        finally:
            src.to_mesh_clear()

        mat = np.array(obj.matrix_world, dtype=np.float64)
        co = co @ mat[:3, :3].T + mat[:3, 3]
        all_verts.append(co * unit_scale)
        all_tris.append(tris.reshape(nt, 3) + offset)
        offset += nv

    if not all_verts:
        return None, None
    return np.concatenate(all_verts), np.concatenate(all_tris)


class EXPORT_OT_terrain3d_heightmap(bpy.types.Operator, ExportHelper):
    """Export selected meshes as a heightmap for Godot Terrain3D"""
    bl_idname = "export_scene.terrain3d_heightmap"
    bl_label = "Export Terrain3D Heightmap"
    bl_options = {'PRESET'}

    filename_ext = ".exr"
    filter_glob: bpy.props.StringProperty(default="*.exr;*.r16", options={'HIDDEN'})

    file_format: EnumProperty(
        name="Format",
        items=(
            ('EXR', "EXR (32-bit float)",
             "Real heights in meters. Recommended for Terrain3D"),
            ('R16', "R16 RAW (16-bit)",
             "Normalized 16-bit heights. Import needs the height range and size "
             "(written to the .json sidecar)"),
        ),
        default='EXR',
    )
    selection_only: BoolProperty(
        name="Selected Only",
        description="Export only selected mesh objects (otherwise all visible meshes)",
        default=True,
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Use the evaluated mesh (modifiers, geometry nodes, shape keys)",
        default=True,
    )
    use_unit_scale: BoolProperty(
        name="Apply Unit Scale",
        description="Multiply coordinates by the scene's Unit Scale so output is in meters",
        default=True,
    )
    vertex_spacing: FloatProperty(
        name="Vertex Spacing",
        description="Distance in meters between heightmap pixels. "
                    "Must match Terrain3D's vertex_spacing (default 1.0)",
        default=1.0, min=0.01, soft_max=10.0, precision=3, unit='NONE',
    )
    bounds_mode: EnumProperty(
        name="Bounds",
        items=(
            ('AUTO', "Auto", "Use the XY bounding box of the exported meshes"),
            ('CUSTOM', "Custom", "Use a custom XY rectangle (meters, Blender axes)"),
        ),
        default='AUTO',
    )
    bounds_min: FloatVectorProperty(name="Min XY", size=2, default=(-512.0, -512.0))
    bounds_max: FloatVectorProperty(name="Max XY", size=2, default=(512.0, 512.0))
    snap_to_grid: BoolProperty(
        name="Snap Bounds to Grid",
        description="Align the bounds to multiples of the vertex spacing so the "
                    "terrain lines up with Terrain3D's vertex grid",
        default=True,
    )
    align_regions: BoolProperty(
        name="Align to Regions",
        description="Move the top-left corner onto Terrain3D's region grid and pad the "
                    "image to whole regions, so Import Position is an exact integer",
        default=True,
    )
    region_size: EnumProperty(
        name="Region Size",
        description="Must match region_size on the Terrain3D node",
        items=[(str(s), str(s), "") for s in (64, 128, 256, 512, 1024, 2048)],
        default='256',
    )
    height_scale: FloatProperty(
        name="Height Scale", default=1.0, soft_min=0.0, soft_max=10.0,
        description="Multiply heights by this factor",
    )
    height_offset: FloatProperty(
        name="Height Offset", default=0.0, unit='NONE',
        description="Add this value (meters) to heights after scaling",
    )
    hole_fill: EnumProperty(
        name="Empty Pixels",
        description="What to write where no mesh covers the grid",
        items=(
            ('MIN', "Lowest Height", "Fill with the lowest sampled height"),
            ('VALUE', "Fixed Value", "Fill with a fixed height"),
        ),
        default='MIN',
    )
    hole_value: FloatProperty(name="Fill Height", default=0.0)
    write_sidecar: BoolProperty(
        name="Write Info JSON",
        description="Write a .json file with size, height range and Terrain3D import settings",
        default=True,
    )

    def check(self, context):
        # Keep the file extension in sync with the chosen format.
        if not os.path.basename(self.filepath):
            return False
        base, cur = os.path.splitext(self.filepath)
        if cur.lower() not in FORMAT_EXT.values():
            base = self.filepath
        new_path = base + FORMAT_EXT[self.file_format]
        if new_path != self.filepath:
            self.filepath = new_path
            return True
        return False

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, "file_format")

        box = layout.box()
        box.label(text="Source", icon='MESH_DATA')
        box.prop(self, "selection_only")
        box.prop(self, "apply_modifiers")
        box.prop(self, "use_unit_scale")

        box = layout.box()
        box.label(text="Grid", icon='MESH_GRID')
        box.prop(self, "vertex_spacing")
        box.prop(self, "bounds_mode")
        if self.bounds_mode == 'CUSTOM':
            box.prop(self, "bounds_min")
            box.prop(self, "bounds_max")
        box.prop(self, "snap_to_grid")
        box.prop(self, "align_regions")
        row = box.row()
        row.active = self.align_regions
        row.prop(self, "region_size")

        box = layout.box()
        box.label(text="Height", icon='EMPTY_SINGLE_ARROW')
        box.prop(self, "height_scale")
        box.prop(self, "height_offset")
        box.prop(self, "hole_fill")
        if self.hole_fill == 'VALUE':
            box.prop(self, "hole_value")

        layout.prop(self, "write_sidecar")

    def execute(self, context):
        t0 = time.perf_counter()

        if self.selection_only:
            objects = [o for o in context.selected_objects if o.type == 'MESH']
        else:
            objects = [o for o in context.visible_objects if o.type == 'MESH']
        if not objects:
            self.report({'ERROR'}, "No mesh objects to export")
            return {'CANCELLED'}

        unit_scale = context.scene.unit_settings.scale_length if self.use_unit_scale else 1.0
        verts, tris = _collect_geometry(context, objects, self.apply_modifiers, unit_scale)
        if verts is None:
            self.report({'ERROR'}, "Meshes have no faces")
            return {'CANCELLED'}

        sp = self.vertex_spacing
        if self.bounds_mode == 'AUTO':
            min_x, min_y = verts[:, 0].min(), verts[:, 1].min()
            max_x, max_y = verts[:, 0].max(), verts[:, 1].max()
        else:
            min_x, min_y = self.bounds_min
            max_x, max_y = self.bounds_max
            if max_x <= min_x or max_y <= min_y:
                self.report({'ERROR'}, "Custom bounds: Max must be greater than Min")
                return {'CANCELLED'}
        rs = int(self.region_size)
        if self.align_regions:
            # Terrain3D slices the image into region_size chunks starting at the
            # import position, so put the top-left corner on the region grid and
            # pad to whole regions. Adjacent regions don't share edge vertices, so
            # an extent of exactly N regions fits in N regions.
            cell = rs * sp
            min_x = np.floor(min_x / cell + 1e-6) * cell
            max_y = np.ceil(max_y / cell - 1e-6) * cell
            width = max(1, int(np.ceil((max_x - min_x) / sp - 1e-6)))
            height = max(1, int(np.ceil((max_y - min_y) / sp - 1e-6)))
            width = -(-width // rs) * rs
            height = -(-height // rs) * rs
            max_x = min_x + (width - 1) * sp
            min_y = max_y - (height - 1) * sp
        else:
            if self.snap_to_grid:
                min_x = np.floor(min_x / sp + 1e-6) * sp
                max_y = np.ceil(max_y / sp - 1e-6) * sp
                max_x = np.ceil(max_x / sp - 1e-6) * sp
                min_y = np.floor(min_y / sp + 1e-6) * sp
            width, height = sampler.compute_grid(min_x, max_x, min_y, max_y, sp)

        if max(width, height) > MAX_DIMENSION:
            self.report({'ERROR'},
                        f"Heightmap would be {width}x{height} px (max {MAX_DIMENSION}). "
                        "Increase Vertex Spacing or reduce the bounds")
            return {'CANCELLED'}

        # Terrain3D import position = top-left corner in Godot world space
        # (Godot X = Blender X, Godot Z = -Blender Y). The importer's
        # import_position is a Vector2i, so it must be a whole number.
        pos_x, pos_z = float(min_x), float(-max_y)
        warnings = []
        if abs(pos_x - round(pos_x)) > 1e-4 or abs(pos_z - round(pos_z)) > 1e-4:
            warnings.append(f"Import position ({pos_x:g}, {pos_z:g}) is not a whole number; "
                            "Terrain3D's importer truncates it. Enable Align to Regions")
        # Terrain3D limit: position / vertex_spacing within +/- region_size * 16.
        limit = rs * 16
        vx0, vz0 = pos_x / sp, pos_z / sp
        if min(vx0, vz0) < -limit - 1e-6 or max(vx0 + width, vz0 + height) > limit + 1e-6:
            warnings.append(f"Terrain exceeds Terrain3D's world bounds for region size {rs} "
                            f"(+/-{limit * sp:g} m). Use a larger Region Size")

        heights = sampler.rasterize(verts, tris, min_x, max_y, sp, width, height)
        if np.isnan(heights).all():
            self.report({'ERROR'}, "No mesh surface inside the export bounds")
            return {'CANCELLED'}
        heights = heights * self.height_scale + self.height_offset
        heights, holes = sampler.fill_holes(heights, self.hole_fill, self.hole_value)
        min_h = float(heights.min())
        max_h = float(heights.max())

        path = bpy.path.ensure_ext(self.filepath, FORMAT_EXT[self.file_format])
        if self.file_format == 'EXR':
            writers.write_exr(path, heights)
        else:
            writers.write_r16(path, heights, min_h, max_h)

        if self.write_sidecar:
            info = {
                "file": os.path.basename(path),
                "format": self.file_format,
                "width": width,
                "height": height,
                "vertex_spacing": sp,
                "min_height": min_h,
                "max_height": max_h,
                "empty_pixels": holes,
                "blender_bounds_xy": [float(min_x), float(min_y), float(max_x), float(max_y)],
                "terrain3d": {
                    "vertex_spacing": sp,
                    "region_size": rs if self.align_regions else None,
                    "import_position": [int(round(pos_x)), int(round(pos_z))],
                    "height_offset": 0.0,
                    "import_scale": 1.0,
                },
                "warnings": warnings,
            }
            if self.file_format == 'R16':
                info["terrain3d"]["r16_range"] = [min_h, max_h]
                info["terrain3d"]["r16_size"] = [width, height]
            writers.write_sidecar(os.path.splitext(path)[0] + ".json", info)

        for w in warnings:
            self.report({'WARNING'}, w)
        dt = time.perf_counter() - t0
        self.report({'INFO'},
                    f"Exported {width}x{height} heightmap "
                    f"(heights {min_h:.2f}..{max_h:.2f} m) in {dt:.1f}s: {path}")
        return {'FINISHED'}


class VIEW3D_PT_terrain3d_heightmap(bpy.types.Panel):
    bl_label = "Terrain3D Heightmap"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Terrain3D"

    def draw(self, context):
        layout = self.layout
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        layout.label(text=f"{len(meshes)} mesh(es) selected", icon='MESH_DATA')
        layout.operator(EXPORT_OT_terrain3d_heightmap.bl_idname, icon='EXPORT')


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_terrain3d_heightmap.bl_idname,
                         text="Terrain3D Heightmap (.exr/.r16)")


classes = (EXPORT_OT_terrain3d_heightmap, VIEW3D_PT_terrain3d_heightmap)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
