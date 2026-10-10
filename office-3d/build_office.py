"""Office layout / stage 01. Run inside Blender, not system Python.

Blender command: blender --background --python build_office.py
GUI: Scripting > Open > build_office.py > Run Script (creates a new scene).
This script resets the current scene. Save your own edits before running it.
No external assets, add-ons, API, character detail or final materials.
"""
import bpy
import math
import random
from pathlib import Path
from mathutils import Vector, Matrix

# ---- Beginner-editable layout settings (meters) ------------------------------
OUTPUT_DIR = Path(__file__).resolve().parent
ROOM_WIDTH = 7.6
ROOM_DEPTH = 5.6
WALL_HEIGHT = 3.15
BOSS_DESK_POSITION = (-1.65, -0.78)
ASSISTANT_DESK_POSITION = (1.72, 0.22)
BOSS_DESK_SIZE = (2.60, 1.18)
ASSISTANT_DESK_SIZE = (1.85, 1.04)
CAMERA_POSITION = (9.4, -13.8, 9.6)
CAMERA_TARGET = (0.0, 0.10, 1.12)
RENDER_SIZE = (1600, 900)
RENDER_SAMPLES = 64
SEED = 31

random.seed(SEED)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "METERS"
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = RENDER_SAMPLES
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = RENDER_SIZE
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.filepath = str(OUTPUT_DIR / "office-blockout-preview.png")
scene.render.image_settings.color_mode = "RGB"
# Rebuilding updates the single output .blend; avoid accumulating .blend1 backups.
bpy.context.preferences.filepaths.save_version = 0
scene.world = bpy.data.worlds.new("World / warm studio ambient")
scene.world.use_nodes = True
world_bg = scene.world.node_tree.nodes.get("Background")
world_bg.inputs["Color"].default_value = (0.82, 0.78, 0.67, 1)
world_bg.inputs["Strength"].default_value = 0.35

# All assets are editable, named, and grouped under moveable Empty roots.
collections = {}
for name in ("01_Room", "02_Boss_Workstation", "03_Assistant_Workstation", "04_Bookcase", "05_Window", "06_Plants_Props", "07_Pose_Placeholders", "08_Cameras", "09_Preview_Lights", "10_Studio_Ground"):
    col = bpy.data.collections.new(name)
    scene.collection.children.link(col)
    collections[name] = col
current_collection = collections["01_Room"]


def use_collection(name):
    global current_collection
    current_collection = collections[name]


def move_to_collection(obj):
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    current_collection.objects.link(obj)


def material(name, color, roughness=0.65, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


# Simple preview-only materials; refinement happens after layout approval.
M = {
    "sage": material("Preview / sage painted wall", (0.29, 0.38, 0.25)),
    "sage_alt": material("Preview / sage panel variation", (0.33, 0.42, 0.28)),
    "cream": material("Preview / warm cream trim", (0.83, 0.78, 0.63)),
    "oak": material("Preview / honey oak", (0.49, 0.29, 0.115), 0.48),
    "oak_light": material("Preview / pale honey desktop", (0.69, 0.49, 0.25), 0.5),
    "walnut": material("Preview / walnut edges", (0.24, 0.115, 0.055), 0.48),
    "chair": material("Preview / sage upholstered chair", (0.38, 0.46, 0.33), 0.85),
    "chair_light": material("Preview / oatmeal upholstered chair", (0.72, 0.67, 0.52), 0.87),
    "steel": material("Preview / satin dark metal", (0.12, 0.15, 0.135), 0.35, 0.45),
    "screen_frame": material("Preview / graphite monitor frame", (0.065, 0.095, 0.075), 0.43),
    "screen": material("Preview / blank muted glass screen", (0.12, 0.25, 0.225), 0.24),
    "keys": material("Preview / ivory keyboard", (0.75, 0.74, 0.63), 0.57),
    "paper": material("Preview / cream paper", (0.91, 0.87, 0.73), 0.83),
    "paper_edge": material("Preview / paper stack shadows", (0.68, 0.65, 0.54), 0.83),
    "folder": material("Preview / kraft folders", (0.62, 0.44, 0.23), 0.85),
    "rust": material("Preview / muted terracotta", (0.48, 0.24, 0.135)),
    "leaf": material("Preview / olive green leaves", (0.22, 0.34, 0.12), 0.8),
    "leaf_light": material("Preview / sage leaves", (0.38, 0.48, 0.24), 0.8),
    "soil": material("Preview / soil", (0.12, 0.085, 0.05)),
    "boss_pose": material("Placeholder / boss untextured clay", (0.76, 0.61, 0.41), 0.82),
    "assistant_pose": material("Placeholder / assistant untextured clay", (0.78, 0.71, 0.57), 0.82),
    "rug": material("Preview / faded sage rug", (0.33, 0.40, 0.33), 0.94),
    "rug_edge": material("Preview / warm oatmeal rug border", (0.66, 0.66, 0.50), 0.94),
    "ground": material("Preview / cream studio background", (0.78, 0.72, 0.60), 0.92),
    "blue": material("Preview / book muted blue", (0.24, 0.35, 0.37)),
}
# The window is an opaque scenic insert, not final glass: reliable fast preview.
M["window"] = material("Preview / pale daylight window insert", (0.61, 0.77, 0.71), 0.4)
window_bsdf = M["window"].node_tree.nodes.get("Principled BSDF")
window_bsdf.inputs["Emission Color"].default_value = (0.58, 0.73, 0.65, 1)
window_bsdf.inputs["Emission Strength"].default_value = 0.16


def finish(obj, name, mat=None, parent=None, smooth=False):
    obj.name = name
    move_to_collection(obj)
    if mat:
        obj.data.materials.append(mat)
    if parent:
        # Flush scale/location changes before saving the world transform.
        # Without this, a newly scaled sphere can revert to its unit size.
        bpy.context.view_layer.update()
        matrix = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = matrix
    if smooth and obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    return obj


def empty(name, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.30
    current_collection.objects.link(obj)
    obj.location = location
    obj.matrix_world = Matrix.Translation(Vector(location))
    if parent:
        obj.parent = parent
    bpy.context.view_layer.update()
    return obj


def cube(name, location, size, mat=None, bevel=0.02, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("Soft rounded edges / editable", "BEVEL")
        modifier.width = min(bevel, min(size) * 0.4)
        modifier.segments = 3
        modifier.affect = "EDGES"
        normal = obj.modifiers.new("Weighted surface normals", "WEIGHTED_NORMAL")
        normal.keep_sharp = True
    return finish(obj, name, mat, parent)


def sphere(name, location, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1, location=location)
    obj = bpy.context.object
    obj.scale = scale
    return finish(obj, name, mat, parent, True)


def cylinder(name, location, radius, depth, mat, parent=None, radius2=None):
    if radius2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=depth, location=location)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=radius, radius2=radius2, depth=depth, location=location)
    obj = bpy.context.object
    modifier = obj.modifiers.new("Rounded rim", "BEVEL")
    modifier.width = min(radius * 0.08, depth * 0.1, 0.015)
    modifier.segments = 3
    return finish(obj, name, mat, parent, True)


def rod(name, start, end, radius, mat, parent=None):
    a, b = Vector(start), Vector(end)
    obj = cylinder(name, (a + b) / 2, radius, (b - a).length, mat, parent)
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return obj


def curve(name, points, radius, mat, parent=None):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 12
    data.bevel_depth = radius
    data.bevel_resolution = 3
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bezier, point in zip(spline.bezier_points, points):
        bezier.co = point
        bezier.handle_left_type = "AUTO"
        bezier.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    current_collection.objects.link(obj)
    if mat:
        data.materials.append(mat)
    if parent:
        matrix = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = matrix
    return obj


# ---- Room: open front and right, wall opening is genuine geometry ------------
use_collection("01_Room")
room_root = empty("ROOM_ROOT / move room shell")
cube("Room / rounded display foundation", (0, 0, -0.16), (ROOM_WIDTH + 0.16, ROOM_DEPTH + 0.16, 0.32), M["oak"], 0.15, room_root)
# Parquet-like alternating square blocks. Individual editable pieces.
floor_mats = [material(f"Preview / parquet tone {i:02}", (0.61 + i * 0.018, 0.40 + i * 0.015, 0.19 + i * 0.010), 0.65) for i in range(6)]
x0, y0 = -ROOM_WIDTH / 2, -ROOM_DEPTH / 2
nx, ny = 10, 8
sx, sy = ROOM_WIDTH / nx, ROOM_DEPTH / ny
for i in range(nx):
    for j in range(ny):
        # Each square contains three strips, direction alternates.
        for k in range(3):
            if (i + j) % 2:
                pos = (x0 + (i + 0.5) * sx, y0 + j * sy + (k + 0.5) * sy / 3, 0.012)
                dims = (sx - 0.008, sy / 3 - 0.007, 0.04)
            else:
                pos = (x0 + i * sx + (k + 0.5) * sx / 3, y0 + (j + 0.5) * sy, 0.012)
                dims = (sx / 3 - 0.007, sy - 0.008, 0.04)
            cube(f"Floor / parquet {i:02}_{j:02}_{k}", pos, dims, random.choice(floor_mats), 0.007, room_root)
# Back wall, vertical panel rhythms.
cube("Back wall / structural shell", (0, ROOM_DEPTH / 2 + 0.07, WALL_HEIGHT / 2), (ROOM_WIDTH + 0.16, 0.17, WALL_HEIGHT), M["sage"], 0.03, room_root)
for i in range(24):
    width = ROOM_WIDTH / 24
    cube(f"Back wall / panel {i:02}", (-ROOM_WIDTH / 2 + (i + 0.5) * width, ROOM_DEPTH / 2 - 0.023, WALL_HEIGHT / 2), (width - 0.014, 0.032, WALL_HEIGHT - 0.08), M["sage_alt"] if i % 4 == 0 else M["sage"], 0.008, room_root)
cube("Back wall / baseboard", (0, ROOM_DEPTH / 2 - 0.053, 0.11), (ROOM_WIDTH, 0.09, 0.18), M["cream"], 0.014, room_root)
cube("Back wall / crown trim", (0, ROOM_DEPTH / 2 - 0.015, WALL_HEIGHT), (ROOM_WIDTH + 0.13, 0.20, 0.11), M["cream"], 0.025, room_root)
# Left window spans y=-1.55..0.75 and z=1.10..2.65.
left_x = -ROOM_WIDTH / 2 - 0.07
opening_y = (-1.55, 0.75)
opening_z = (1.10, 2.65)
cube("Left wall / below window", (left_x, 0, opening_z[0] / 2), (0.17, ROOM_DEPTH, opening_z[0]), M["sage"], 0.025, room_root)
cube("Left wall / above window", (left_x, 0, (opening_z[1] + WALL_HEIGHT) / 2), (0.17, ROOM_DEPTH, WALL_HEIGHT - opening_z[1]), M["sage"], 0.025, room_root)
for suffix, lo, hi in (("front", -ROOM_DEPTH / 2, opening_y[0]), ("rear", opening_y[1], ROOM_DEPTH / 2)):
    cube(f"Left wall / {suffix} window side", (left_x, (lo + hi) / 2, (opening_z[0] + opening_z[1]) / 2), (0.17, hi - lo, opening_z[1] - opening_z[0]), M["sage"], 0.025, room_root)
for i in range(18):
    yy = -ROOM_DEPTH / 2 + (i + 0.5) * ROOM_DEPTH / 18
    ranges = [(0.08, 1.04), (2.71, WALL_HEIGHT - 0.05)] if opening_y[0] < yy < opening_y[1] else [(0.08, WALL_HEIGHT - 0.05)]
    for lo, hi in ranges:
        cube(f"Left wall / panel {i:02}_{lo:.1f}", (-ROOM_WIDTH / 2 + 0.025, yy, (lo + hi) / 2), (0.035, ROOM_DEPTH / 18 - 0.015, hi - lo), M["sage_alt"] if i % 4 == 0 else M["sage"], 0.007, room_root)
cube("Left wall / baseboard", (-ROOM_WIDTH / 2 + 0.053, 0, 0.11), (0.09, ROOM_DEPTH, 0.18), M["cream"], 0.014, room_root)
cube("Left wall / crown trim", (-ROOM_WIDTH / 2 - 0.015, 0, WALL_HEIGHT), (0.20, ROOM_DEPTH + 0.08, 0.11), M["cream"], 0.025, room_root)
# Two flat rounded rugs to make the work zones easy to inspect.
for name, x, y, w, d in (("boss", -1.65, -0.78, 3.25, 2.35), ("assistant", 1.72, 0.22, 2.45, 2.00)):
    cube(f"Rug / {name} border", (x, y, 0.055), (w, d, 0.022), M["rug_edge"], 0.12, room_root)
    cube(f"Rug / {name} center", (x, y, 0.069), (w - 0.16, d - 0.16, 0.012), M["rug"], 0.10, room_root)


# ---- Window ---------------------------------------------------------------
use_collection("05_Window")
window_root = empty("WINDOW_ROOT / on left wall")
wx, wy = -ROOM_WIDTH / 2 + 0.07, (opening_y[0] + opening_y[1]) / 2
ww, wh = opening_y[1] - opening_y[0], opening_z[1] - opening_z[0]
# Keep pale insert behind structural frame.
cube("Window / scenic daylight insert", (-ROOM_WIDTH / 2 - 0.11, wy, (opening_z[0] + opening_z[1]) / 2), (0.025, ww - 0.04, wh - 0.04), M["window"], 0.01, window_root)
for yy in (opening_y[0], opening_y[1]):
    cube("Window / cream vertical surround", (wx, yy, (opening_z[0] + opening_z[1]) / 2), (0.13, 0.09, wh + 0.14), M["cream"], 0.018, window_root)
for zz in (opening_z[0], opening_z[1]):
    cube("Window / cream horizontal surround", (wx, wy, zz), (0.13, ww + 0.12, 0.10), M["cream"], 0.018, window_root)
for yy in (wy - ww / 6, wy + ww / 6):
    cube("Window / inner vertical mullion", (wx, yy, (opening_z[0] + opening_z[1]) / 2), (0.095, 0.055, wh), M["cream"], 0.012, window_root)
cube("Window / inner horizontal mullion", (wx, wy, 1.88), (0.095, ww, 0.055), M["cream"], 0.012, window_root)
cube("Window / broad rounded sill", (-ROOM_WIDTH / 2 + 0.14, wy, opening_z[0] - 0.035), (0.37, ww + 0.30, 0.095), M["cream"], 0.028, window_root)
rod("Window / curtain rail", (-ROOM_WIDTH / 2 + 0.19, opening_y[0] - 0.15, 2.88), (-ROOM_WIDTH / 2 + 0.19, opening_y[1] + 0.15, 2.88), 0.022, M["oak"], window_root)
# Simple tied curtain placeholders, no cloth simulation.
for yy in (opening_y[0] - 0.11, opening_y[1] + 0.11):
    for j in range(4):
        cylinder("Window / simple curtain fold", (-ROOM_WIDTH / 2 + 0.24 + (j % 2) * 0.025, yy + (j - 1.5) * 0.055, 1.98), 0.038, 1.69, M["cream"], window_root)


# ---- Desks, monitors, paper stacks -----------------------------------------
def paper_stack(prefix, x, y, z, parent, sheets=13):
    for i in range(sheets):
        paper = cube(f"{prefix} / sheet {i:02}", (x + random.uniform(-0.016, 0.016), y + random.uniform(-0.012, 0.012), z + 0.007 + i * 0.012), (0.35, 0.26, 0.010), M["paper"] if i % 3 else M["paper_edge"], 0.003, parent)
        paper.rotation_euler.z = random.uniform(-0.028, 0.028)
    cube(prefix + " / kraft folder on top", (x, y, z + sheets * 0.012 + 0.012), (0.36, 0.27, 0.016), M["folder"], 0.008, parent)


def monitor(prefix, x, y, top, parent):
    cube(prefix + " / stand foot", (x, y, top + 0.022), (0.33, 0.23, 0.038), M["steel"], 0.030, parent)
    cube(prefix + " / stand stem", (x, y + 0.026, top + 0.18), (0.066, 0.060, 0.32), M["steel"], 0.012, parent)
    cube(prefix + " / screen housing", (x, y, top + 0.45), (0.73, 0.085, 0.46), M["screen_frame"], 0.036, parent)
    cube(prefix + " / blank screen", (x, y - 0.045, top + 0.46), (0.66, 0.012, 0.37), M["screen"], 0.017, parent)
    # Blank screen: no labels, logos, text or imaginary financial numbers.
    cube(prefix + " / keyboard base", (x, y - 0.36, top + 0.021), (0.53, 0.19, 0.036), M["keys"], 0.018, parent)
    for row in range(3):
        for col in range(11):
            cube(f"{prefix} / key {row}_{col}", (x - 0.228 + col * 0.0455, y - 0.41 + row * 0.051, top + 0.044), (0.032, 0.035, 0.010), M["cream"], 0.003, parent)
    sphere(prefix + " / mouse", (x + 0.37, y - 0.35, top + 0.035), (0.045, 0.071, 0.032), M["keys"], parent)


def cup(prefix, x, y, z, parent, mat):
    cylinder(prefix + " / ceramic mug", (x, y, z + 0.073), 0.064, 0.135, mat, parent)
    cylinder(prefix + " / dark drink insert", (x, y, z + 0.142), 0.052, 0.004, M["soil"], parent)
    curve(prefix + " / mug handle", [(x + 0.05, y, z + 0.12), (x + 0.11, y, z + 0.11), (x + 0.11, y, z + 0.046), (x + 0.05, y, z + 0.04)], 0.013, mat, parent)


def desk(name, x, y, width, depth, mat):
    root = empty(name + "_ROOT / move entire workstation", (x, y, 0))
    tabletop_z = 0.94
    top = 1.00
    cube(name + " / thick rounded desktop", (x, y, tabletop_z), (width, depth, 0.12), mat, 0.058, root)
    cube(name + " / narrow front apron", (x, y - depth / 2 + 0.07, 0.835), (width - 0.18, 0.055, 0.11), M["oak"], 0.014, root)
    for i, dx in enumerate((-width / 2 + 0.115, width / 2 - 0.115)):
        for j, dy in enumerate((-depth / 2 + 0.13, depth / 2 - 0.13)):
            cylinder(f"{name} / tapered wood leg {i}_{j}", (x + dx, y + dy, 0.472), 0.061, 0.85, M["oak"], root, 0.079)
    # Side drawer beneath desk, no large front modesty panel that hides pose.
    drawer_x = x - width / 2 + 0.33
    cube(name + " / drawer enclosure", (drawer_x, y + 0.12, 0.71), (0.44, depth - 0.36, 0.28), M["oak"], 0.028, root)
    for zz in (0.644, 0.776):
        cube(name + " / drawer front", (drawer_x, y - depth / 2 + 0.155, zz), (0.41, 0.027, 0.12), mat, 0.009, root)
        rod(name + " / drawer handle", (drawer_x - 0.055, y - depth / 2 + 0.126, zz), (drawer_x + 0.055, y - depth / 2 + 0.126, zz), 0.011, M["steel"], root)
    monitor(name + " / computer", x - 0.29, y + 0.05, top, root)
    paper_stack(name + " / high file stack", x + width / 2 - 0.28, y + 0.18, top, root, 16 if name == "Boss" else 13)
    # Obvious separate blank paper and notebook for future interaction anchors.
    paper = cube(name + " / blank interactive paper anchor", (x + 0.37, y - 0.32, top + 0.009), (0.29, 0.23, 0.009), M["paper"], 0.003, root)
    paper.rotation_euler.z = -0.12
    paper["Future interaction"] = "Boss: To-do List" if name == "Boss" else "Assistant: AI Summary"
    cube(name + " / closed notebook", (x - width / 2 + 0.25, y + 0.21, top + 0.027), (0.24, 0.31, 0.047), M["rust"] if name == "Boss" else M["chair"], 0.012, root)
    rod(name + " / pen", (x + 0.18, y - 0.14, top + 0.019), (x + 0.40, y - 0.17, top + 0.019), 0.009, M["steel"], root)
    cup(name + " / cup", x - width / 2 + 0.24, y - 0.35, top, root, M["chair_light"] if name == "Boss" else M["chair"])
    return root


use_collection("02_Boss_Workstation")
boss = desk("Boss", *BOSS_DESK_POSITION, *BOSS_DESK_SIZE, M["oak_light"])
use_collection("03_Assistant_Workstation")
assistant = desk("Assistant", *ASSISTANT_DESK_POSITION, *ASSISTANT_DESK_SIZE, M["oak_light"])


# ---- Office chairs: rounded back, seat, armrests, real five-star base --------
def chair(name, x, y, parent, mat, large=False):
    root = empty(name + "_CHAIR_ROOT / move chair", (x, y, 0))
    matrix = root.matrix_world.copy()
    root.parent = parent
    root.matrix_world = matrix
    bpy.context.view_layer.update()
    seat_z = 0.57
    width = 0.68 if large else 0.60
    cube(name + " chair / rounded seat cushion", (x, y, seat_z), (width, 0.61, 0.13), mat, 0.095, root)
    back = cube(name + " chair / rounded backrest", (x, y + 0.285, 0.99), (width, 0.12, 0.79 if large else 0.68), mat, 0.057, root)
    back.rotation_euler.x = -0.08
    cylinder(name + " chair / support column", (x, y, 0.31), 0.046, 0.43, M["steel"], root)
    cylinder(name + " chair / central base hub", (x, y, 0.13), 0.081, 0.10, M["steel"], root)
    for i in range(5):
        angle = i * math.tau / 5
        xx, yy = x + math.cos(angle) * 0.34, y + math.sin(angle) * 0.34
        rod(f"{name} chair / base spoke {i}", (x, y, 0.15), (xx, yy, 0.10), 0.023, M["steel"], root)
        wheel = cylinder(f"{name} chair / caster wheel {i}", (xx, yy, 0.077), 0.048, 0.04, M["steel"], root)
        wheel.rotation_euler.x = math.pi / 2
    for dx in (-width / 2 + 0.018, width / 2 - 0.018):
        rod(name + " chair / arm support", (x + dx, y + 0.12, 0.58), (x + dx, y + 0.12, 0.85), 0.018, M["steel"], root)
        cube(name + " chair / soft arm pad", (x + dx, y - 0.04, 0.86), (0.09, 0.42, 0.064), mat, 0.028, root)
    return root


use_collection("02_Boss_Workstation")
boss_chair_y = BOSS_DESK_POSITION[1] + 1.0
boss_chair = chair("Boss", BOSS_DESK_POSITION[0] + 0.02, boss_chair_y, boss, M["chair"], True)
use_collection("03_Assistant_Workstation")
assistant_chair_y = ASSISTANT_DESK_POSITION[1] + 0.88
assistant_chair = chair("Assistant", ASSISTANT_DESK_POSITION[0], assistant_chair_y, assistant, M["chair_light"])


# ---- Seated neutral posing mannequins (NO final cartoon character detail) ----
use_collection("07_Pose_Placeholders")
def mannequin(name, x, y, parent, mat, scale=1.0):
    root = empty(name + "_POSE_ROOT / seated blockout only", (x, y, 0))
    world = root.matrix_world.copy()
    root.parent = parent
    root.matrix_world = world
    root["Stage"] = "Seated proportions / blank head / no facial detail, hair, rig or clothing"
    sphere(name + " pose / pelvis", (x, y - 0.015, 0.70), (0.18 * scale, 0.14, 0.14), mat, root)
    sphere(name + " pose / torso", (x, y - 0.020, 1.015), (0.20 * scale, 0.145, 0.33), mat, root)
    cylinder(name + " pose / neck", (x, y - 0.033, 1.355), 0.055, 0.09, mat, root)
    sphere(name + " pose / blank head", (x, y - 0.050, 1.56), (0.15 * scale, 0.135, 0.20), mat, root)
    # Two bent legs clearly seated, shoes on floor in front of the chair.
    for side in (-1, 1):
        xx = x + side * 0.105
        hip = (xx, y - 0.035, 0.71)
        knee = (xx, y - 0.38, 0.55)
        ankle = (xx, y - 0.42, 0.17)
        rod(name + " pose / thigh", hip, knee, 0.075 * scale, mat, root)
        sphere(name + " pose / knee", knee, (0.077, 0.077, 0.077), mat, root)
        rod(name + " pose / shin", knee, ankle, 0.060 * scale, mat, root)
        sphere(name + " pose / foot", (xx, y - 0.49, 0.12), (0.076, 0.16, 0.058), mat, root)
        # Bent forearms resting on edge of desk rather than passing through it.
        shoulder = (x + side * 0.19 * scale, y - 0.03, 1.21)
        elbow = (x + side * 0.285, y - 0.30, 1.095)
        hand = (x + side * 0.24, y - 0.49, 1.055)
        sphere(name + " pose / shoulder", shoulder, (0.085, 0.085, 0.085), mat, root)
        rod(name + " pose / upper arm", shoulder, elbow, 0.059 * scale, mat, root)
        sphere(name + " pose / elbow", elbow, (0.061, 0.061, 0.061), mat, root)
        rod(name + " pose / forearm", elbow, hand, 0.047, mat, root)
        sphere(name + " pose / hand", hand, (0.061, 0.088, 0.031), mat, root)
    return root

boss_pose = mannequin("Boss", BOSS_DESK_POSITION[0] + 0.02, boss_chair_y - 0.075, boss, M["boss_pose"], 1.04)
assistant_pose = mannequin("Assistant", ASSISTANT_DESK_POSITION[0], assistant_chair_y - 0.06, assistant, M["assistant_pose"], 0.93)


# ---- Bookcase --------------------------------------------------------------
use_collection("04_Bookcase")
book_root = empty("BOOKCASE_ROOT / move bookcase", (0.33, 2.37, 0))
bx, by = 0.33, 2.37
bw, bd, bh = 1.67, 0.46, 2.49
cube("Bookcase / inset back panel", (bx, by + bd / 2 - 0.026, bh / 2 + 0.085), (bw, 0.055, bh), M["oak"], 0.015, book_root)
for dx in (-bw / 2, bw / 2):
    cube("Bookcase / vertical side", (bx + dx, by, bh / 2 + 0.085), (0.075, bd + 0.055, bh), M["oak_light"], 0.019, book_root)
for j, z in enumerate((0.16, 0.72, 1.28, 1.84, 2.57)):
    cube(f"Bookcase / shelf {j}", (bx, by - 0.004, z), (bw + 0.11, bd + 0.09, 0.08), M["oak_light"], 0.022, book_root)
for dx in (-0.68, 0.68):
    cube("Bookcase / raised foot", (bx + dx, by, 0.082), (0.09, 0.35, 0.12), M["oak"], 0.017, book_root)
book_colors = [M["chair"], M["rust"], M["cream"], M["blue"], M["folder"]]
for shelf_i, shelf_z in enumerate((0.20, 0.76, 1.32)):
    xx = bx - 0.68
    for i in range(10):
        width = random.uniform(0.075, 0.12)
        height = random.uniform(0.29, 0.45)
        obj = cube(f"Bookcase / blank book {shelf_i:02}_{i:02}", (xx + width / 2, by - 0.085, shelf_z + height / 2), (width, 0.26, height), book_colors[(i + shelf_i) % len(book_colors)], 0.005, book_root)
        # Two cream decorative bands, no text.
        for zz in (shelf_z + 0.065, shelf_z + height - 0.065):
            cube("Bookcase / plain book spine band", (xx + width / 2, by - 0.219, zz), (width * 0.72, 0.006, 0.010), M["paper"], 0.001, book_root)
        xx += width + 0.023
        if xx > bx + 0.45:
            break
for dx in (-0.37, 0.36):
    cube("Bookcase / cream storage box", (bx + dx, by - 0.075, 2.06), (0.54, 0.31, 0.36), M["cream"], 0.018, book_root)
    cube("Bookcase / blank box handle", (bx + dx, by - 0.235, 2.06), (0.09, 0.009, 0.025), M["oak"], 0.009, book_root)


# ---- Sparse plants for scale and life, not final detailing ------------------
use_collection("06_Plants_Props")
def plant(name, x, y, z, scale=1.0, parent=None):
    root = empty(name + "_ROOT", (x, y, z))
    if parent:
        matrix = root.matrix_world.copy()
        root.parent = parent
        root.matrix_world = matrix
    h = 0.31 * scale
    cylinder(name + " / terracotta pot", (x, y, z + h / 2), 0.16 * scale, h, M["rust"], root, 0.20 * scale)
    cylinder(name + " / soil", (x, y, z + h), 0.17 * scale, 0.009, M["soil"], root)
    for i in range(9):
        angle = i * 2.399
        length = (0.39 + (i % 3) * 0.17) * scale
        end = Vector((x + math.cos(angle) * 0.24 * scale, y + math.sin(angle) * 0.24 * scale, z + h + length))
        rod(name + " / stem", (x, y, z + h), end, 0.008 * scale, M["leaf"], root)
        leaf = sphere(name + " / simple broad leaf", end, (0.085 * scale, 0.17 * scale, 0.26 * scale), M["leaf"] if i % 2 else M["leaf_light"], root)
        leaf.rotation_euler = (end - Vector((x, y, z + h))).to_track_quat("Z", "Y").to_euler()
    return root

plant("Plant / back left", -2.76, 2.17, 0.04, 1.22)
plant("Plant / right corner", 3.08, 2.00, 0.04, 1.04)
plant("Plant / bookshelf top", bx - 0.43, by, 2.62, 0.34)
plant("Plant / windowsill", -ROOM_WIDTH / 2 + 0.16, -0.36, 1.12, 0.34)
# Blank wall art echoes the soft reference, no text.
cube("Wall art / rounded cream frame", (-1.66, ROOM_DEPTH / 2 - 0.10, 2.15), (0.84, 0.06, 0.74), M["cream"], 0.025)
cube("Wall art / blank clay artwork", (-1.66, ROOM_DEPTH / 2 - 0.139, 2.15), (0.71, 0.012, 0.61), M["folder"], 0.009)


# ---- Actual cameras and preview-only lighting ------------------------------
use_collection("08_Cameras")
def camera(name, location, target, ortho_scale=None, lens=44):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    current_collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.clip_end = 200
    if ortho_scale:
        data.type = "ORTHO"
        data.ortho_scale = ortho_scale
    else:
        data.type = "PERSP"
        data.lens = lens
    data.passepartout_alpha = 0.88
    return obj

scene.camera = camera("CAM_01 / layout preview - oblique front", CAMERA_POSITION, CAMERA_TARGET, 14.6)
# Alternate low-front view for inspecting desk and seated body proportions.
camera("CAM_02 / lower front - proportions check", (8.8, -14.8, 6.7), (0, 0.20, 1.35), 12.5)
scene.camera["Purpose"] = "Open-front layout preview, all desks/chairs inside frame; not final cinematic lighting"

use_collection("09_Preview_Lights")
def area(name, location, target, energy, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    current_collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj

area("Preview / large window key", (-4.8, -2.6, 6.6), (0, 0.2, 0.5), 1100, 5.0, (1.0, 0.90, 0.73))
area("Preview / front softbox fill", (5.0, -5.0, 7.0), (0, 0.0, 1.0), 750, 6.0, (1.0, 0.96, 0.88))
area("Preview / warm top bounce", (0.2, 2.0, 6.5), (0, 0, 0), 550, 4.0, (1.0, 0.90, 0.75))
sun_data = bpy.data.lights.new("Preview / soft afternoon sun", "SUN")
sun_data.energy = 1.1
sun_data.angle = math.radians(12)
sun_data.color = (1.0, 0.91, 0.77)
sun = bpy.data.objects.new(sun_data.name, sun_data)
current_collection.objects.link(sun)
sun.rotation_euler = (math.radians(29), math.radians(-25), math.radians(-38))

use_collection("10_Studio_Ground")
cube("Studio / seamless ground (hide for room-only export)", (0, 0, -0.345), (200, 200, 0.10), M["ground"], 0)

# Beginner-friendly viewport: camera view, material colors, no light overlays.
for screen in bpy.data.screens:
    for area_ui in screen.areas:
        if area_ui.type == "VIEW_3D":
            space = area_ui.spaces.active
            space.region_3d.view_perspective = "CAMERA"
            space.overlay.show_extras = False
            space.shading.type = "MATERIAL"
            space.shading.use_scene_world = False
            space.shading.use_scene_lights = False
# Select the boss workstation root: G/R/S on root moves the full desk + pose.
bpy.ops.object.select_all(action="DESELECT")
boss.select_set(True)
bpy.context.view_layer.objects.active = boss
scene["Stage"] = "01 / layout blockout, editable geometry and seated mannequins only"
scene["How to move desks"] = "Select Boss_ROOT or Assistant_ROOT in Outliner, press G then X/Y. Children include chair and pose."
scene["Next step"] = "Approve layout, then refine wood/fabric/glass shaders, lighting, and simple cartoon characters."
scene["Reference palette"] = "Warm honey parquet, sage wall panels, cream trim, rounded cozy dollhouse shapes."
# A readable embedded note; no external dependency or third-party assets.
notes = bpy.data.texts.new("START_HERE / scene notes")
notes.write("STAGE 01: OFFICE LAYOUT\n\nOpen this .blend directly. Numpad 0 = active camera. F12 = render.\nAll geometry is editable and named. No textures or add-ons required.\n\nCollections 02 and 03 contain desks, computers and chairs.\nSelect Boss_ROOT or Assistant_ROOT to move the full workstation with pose.\nCollection 07 has BLANK seated mannequin placeholders, not final characters.\nCollection 09 lights are preview-only. Collection 10 is studio background.\nCAM_02 is a lower front alternate view.\n\nbuild_office.py rebuilds the scene and discards unsaved scene edits.\nUse Save As before changing or rebuilding.\n\nApprove layout before final materials, lights, or cartoon character work.\n")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# Save before render so an interrupted render still leaves an editable scene.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / "office-blockout.blend"))
bpy.ops.render.render(write_still=True)
print("OFFICE_BUILD_OK", len(scene.objects), "objects", scene.render.filepath)
