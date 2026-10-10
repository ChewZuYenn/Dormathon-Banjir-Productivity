"""Refine ONLY the two characters in an existing approved Blender scene.
Run: Blender --background --python refine_office_characters.py -- --inspect
The source .blend is never overwritten. No room rebuild is performed.
"""
import bpy
import math
import json
import hashlib
import sys
from pathlib import Path
from mathutils import Vector, Matrix

OUTPUT_DIR = Path(__file__).resolve().parent
SOURCE = OUTPUT_DIR / "office-reference-layout.blend"
DESTINATION = OUTPUT_DIR / "office-character-detail.blend"
ROOT_NAMES = ["Boss_POSE_ROOT / seated blockout only", "Assistant_POSE_ROOT / seated blockout only"]


def value(v):
    if isinstance(v, (str, bool, int, float)) or v is None:
        return v
    if isinstance(v, bpy.types.ID):
        return {"id": v.name, "type": v.bl_rna.identifier}
    try:
        return [value(x) for x in v]
    except TypeError:
        return str(v)


def rna(item):
    result = {}
    skip = {"rna_type", "is_updated", "is_updated_data", "is_updated_transform", "users", "tag", "session_uid", "is_runtime_data", "original"}
    for prop in item.bl_rna.properties:
        if prop.identifier in skip or prop.type == "COLLECTION":
            continue
        try:
            v = getattr(item, prop.identifier)
            if prop.type == "POINTER":
                if isinstance(v, bpy.types.ID) or v is None:
                    result[prop.identifier] = value(v)
                continue
            result[prop.identifier] = value(v)
        except (AttributeError, TypeError, ValueError):
            pass
    return result


def custom(item):
    return {k: value(item[k]) for k in item.keys()}


def node_tree(tree):
    if tree is None:
        return None
    return {
        "nodes": [{"rna": rna(n), "inputs": [(s.identifier, value(s.default_value)) for s in n.inputs if hasattr(s, "default_value")],
                   "outputs": [(s.identifier, value(s.default_value)) for s in n.outputs if hasattr(s, "default_value")]}
                  for n in tree.nodes],
        "links": sorted((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier) for l in tree.links),
    }


def fingerprint_data(data):
    if data is None:
        return None
    d = {"rna": rna(data), "custom": custom(data)}
    if isinstance(data, bpy.types.Mesh):
        d["vertices"] = [list(v.co) for v in data.vertices]
        d["edges"] = [list(e.vertices) for e in data.edges]
        d["faces"] = [(list(p.vertices), p.material_index, p.use_smooth) for p in data.polygons]
        d["attributes"] = []
        for a in data.attributes:
            if a.name.startswith("."):
                continue
            records = []
            for v in a.data:
                records.append(rna(v))
            d["attributes"].append((a.name, a.data_type, a.domain, records))
    if isinstance(data, bpy.types.Curve):
        d["splines"] = [{"rna": rna(s), "bezier": [rna(p) for p in s.bezier_points], "points": [rna(p) for p in s.points]} for s in data.splines]
    if hasattr(data, "materials"):
        d["materials"] = [m.name if m else None for m in data.materials]
    return d


def descendants(root):
    result = set()
    def visit(o):
        for child in o.children:
            result.add(child.name)
            visit(child)
    visit(root)
    return result


def snapshot(excluded):
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    objects = {}
    for obj in scene.objects:
        if obj.name in excluded:
            continue
        objects[obj.name] = {
            "rna": rna(obj), "world_matrix": value(obj.matrix_world), "custom": custom(obj),
            "collections": sorted(c.name for c in obj.users_collection), "data": fingerprint_data(obj.data),
            "modifiers": [rna(m) for m in obj.modifiers], "constraints": [rna(c) for c in obj.constraints],
        }
    materials = {m.name: {"rna": rna(m), "custom": custom(m), "nodes": node_tree(m.node_tree)} for m in bpy.data.materials if not m.name.startswith("Character /")}
    render = rna(scene.render)
    render.pop("filepath", None)  # Output destination is not a visual scene change.
    return {
        "objects": objects, "materials": materials,
        "collections": {c.name: {"rna": rna(c), "children": sorted(x.name for x in c.children)} for c in bpy.data.collections},
        "settings": {"scene": rna(scene), "custom": custom(scene), "render": render, "image": rna(scene.render.image_settings),
                     "cycles": rna(scene.cycles), "view": rna(scene.view_settings), "display": rna(scene.display_settings),
                     "units": rna(scene.unit_settings), "world": rna(scene.world), "world_nodes": node_tree(scene.world.node_tree)},
        "texts": {t.name: t.as_string() for t in bpy.data.texts},
    }


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inspect():
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    roots = [bpy.data.objects[n] for n in ROOT_NAMES]
    excluded = set(ROOT_NAMES)
    for root in roots:
        excluded.update(descendants(root))
    base = snapshot(excluded)
    inspection = {"source": str(SOURCE), "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  "protected_snapshot_sha256": digest(base), "protected_object_count": len(base["objects"]),
                  "protected_material_count": len(base["materials"]), "character_objects": sorted(excluded),
                  "roots": {r.name: {"world": value(r.matrix_world), "parent": r.parent.name, "dimensions": list(r.dimensions)} for r in roots},
                  "active_camera": bpy.context.scene.camera.name}
    internal = OUTPUT_DIR.parent / ".workbuddy-ai"
    (internal / "office-character-base-snapshot.json").write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    (internal / "office-character-base-inspection.json").write_text(json.dumps(inspection, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CHARACTER_BASE_INSPECTED", json.dumps(inspection, ensure_ascii=False))


# ---- Character-only geometry ------------------------------------------------
# Face looks toward -Y, exactly as the original seated placeholders.
# Sizes preserve the seat/hip/arm position while giving the reference a big head.
COLLECTION = None
ROOT = None
PREFIX = ""
M = {}


def mat(name, rgb, roughness=0.68, metallic=0.0):
    m = bpy.data.materials.new("Character / " + name)
    m.diffuse_color = (*rgb, 1)
    m.use_nodes = True
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        b = m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    b.name = "Principled BSDF"
    out = next((n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    if not out.inputs["Surface"].is_linked:
        m.node_tree.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    return m


def setup_materials():
    global M
    M = {
        "skin": mat("warm peach skin", (0.92, 0.52, 0.26), 0.72),
        "inner_ear": mat("peach ear folds", (0.73, 0.32, 0.16)),
        "male_hair": mat("boss near-black side parted hair", (0.015, 0.019, 0.018), 0.62),
        "female_hair": mat("assistant espresso shoulder length hair", (0.025, 0.013, 0.016), 0.65),
        "male_strand": mat("boss subtle charcoal hair grooves", (0.030, 0.035, 0.032)),
        "female_strand": mat("assistant subtle brown hair grooves", (0.043, 0.024, 0.028)),
        "eyes": mat("black dot eyes and male eyebrows", (0.007, 0.006, 0.008), 0.51),
        "female_brow": mat("assistant warm brown eyebrows", (0.16, 0.09, 0.035)),
        "glint": mat("small eye glints", (0.94, 0.89, 0.78), 0.3),
        "mouth": mat("reference muted berry mouth", (0.39, 0.025, 0.075)),
        "nose": mat("reference tiny rose nose", (0.50, 0.065, 0.11)),
        "suit": mat("deep slate blue suit wool", (0.054, 0.075, 0.105), 0.86),
        "lapel": mat("slate blue tailored lapel", (0.071, 0.096, 0.133), 0.82),
        "seam": mat("dark tailored seams", (0.023, 0.035, 0.052), 0.85),
        "shirt": mat("warm white shirt", (0.87, 0.90, 0.88), 0.82),
        "shirt_seam": mat("white shirt collar stitching", (0.58, 0.65, 0.65)),
        "tie": mat("boss desaturated blue tie", (0.075, 0.18, 0.31), 0.77),
        "shoe": mat("charcoal leather shoes", (0.024, 0.027, 0.032), 0.48),
        "sole": mat("dark shoe sole", (0.012, 0.015, 0.019), 0.87),
        "button": mat("slate suit buttons", (0.022, 0.028, 0.044), 0.53),
        "pen": mat("reference gray writing pen", (0.28, 0.30, 0.30), 0.4, 0.2),
        "pen_tip": mat("metal pen clip and tip", (0.42, 0.43, 0.42), 0.32, 0.6),
        "nail": mat("subtle peach fingernails", (0.97, 0.64, 0.39), 0.7),
    }
    skin_b = M["skin"].node_tree.nodes.get("Principled BSDF")
    skin_b.inputs["Subsurface Weight"].default_value = 0.07
    skin_b.inputs["Subsurface Radius"].default_value = (0.9, 0.45, 0.25)
    # Fine procedural weave, limited to the NEW character suit material.
    nodes = M["suit"].node_tree.nodes
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 155
    noise.inputs["Detail"].default_value = 2
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.002
    M["suit"].node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    M["suit"].node_tree.links.new(bump.outputs["Normal"], nodes.get("Principled BSDF").inputs["Normal"])


def finish(obj, label, material, smooth=True):
    obj.name = PREFIX + " / " + label
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    COLLECTION.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = ROOT
    obj.matrix_world = world
    if obj.type == "MESH" and smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    return obj


def mesh(label, vertices, faces, material, smooth=True):
    data = bpy.data.meshes.new(PREFIX + " / " + label + " mesh")
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(PREFIX + " / " + label, data)
    COLLECTION.objects.link(obj)
    return finish(obj, label, material, smooth)


def sphere(label, pos, scale, material, segments=40, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1, location=pos)
    obj = bpy.context.object
    obj.scale = scale
    return finish(obj, label, material)


def path(label, points, radius, material):
    data = bpy.data.curves.new(PREFIX + " / " + label, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 18
    data.bevel_depth = radius
    data.bevel_resolution = 4
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for p, co in zip(spline.bezier_points, points):
        p.co = co
        p.handle_left_type = "AUTO"
        p.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(PREFIX + " / " + label, data)
    COLLECTION.objects.link(obj)
    return finish(obj, label, material)


def capsule(label, a, b, ra, rb, material, radial=24):
    # One smooth contiguous mesh, not an exposed cylinder/sphere joint.
    a, b = Vector(a), Vector(b)
    length = (b - a).length
    axis = (b - a).normalized()
    u = axis.cross(Vector((0, 0, 1)))
    if u.length < 0.1:
        u = axis.cross(Vector((0, 1, 0)))
    u.normalize()
    v = axis.cross(u).normalized()
    profile = [(0.0, 0.001), (0.04, ra * 0.60), (0.12, ra * 0.96), (0.25, ra),
               (0.50, (ra + rb) * 0.50), (0.77, rb), (0.9, rb * 0.96), (0.97, rb * 0.6), (1.0, 0.001)]
    verts = []
    for t, radius in profile:
        center = a + axis * length * t
        for j in range(radial):
            angle = j * math.tau / radial
            verts.append(tuple(center + radius * (u * math.cos(angle) + v * math.sin(angle))))
    faces = []
    for i in range(len(profile) - 1):
        for j in range(radial):
            k, n = i * radial + j, i * radial + (j + 1) % radial
            faces.append((k, n, n + radial, k + radial))
    return mesh(label, verts, faces, material)


def panel(label, vertices, material, thickness=0.008, bevel=0.004):
    obj = mesh(label, vertices, [tuple(range(len(vertices)))], material, False)
    sol = obj.modifiers.new("Tailored fabric thickness", "SOLIDIFY")
    sol.thickness = thickness
    sol.offset = 0
    edge = obj.modifiers.new("Soft sewn edge", "BEVEL")
    edge.width = bevel
    edge.segments = 3
    normal = obj.modifiers.new("Fabric normals", "WEIGHTED_NORMAL")
    return obj


def build_character(root, female=False):
    global ROOT, PREFIX, COLLECTION
    ROOT = root
    PREFIX = "Assistant character" if female else "Boss character"
    COLLECTION = bpy.data.collections["07_Pose_Placeholders"]
    x, y, _ = root.matrix_world.translation
    factor = 0.94 if female else 1.04
    hair = M["female_hair"] if female else M["male_hair"]
    strand = M["female_strand"] if female else M["male_strand"]
    root["Character detail"] = "Reference-based face, side-part hair, tailored suit, articulated fingers, gray pen; static seated mesh, not rigged"
    root["Reference"] = "IMG_6499.JPG / female assistant" if female else "IMG_6500.JPG / male boss"
    # Seated hips and both feet retain their original world positions.
    sphere("seated trouser pelvis", (x, y - 0.015, 0.72), (0.185 * factor, 0.15, 0.13), M["suit"])
    for side in (-1, 1):
        xx = x + side * 0.105
        hip, knee, ankle = (xx, y - 0.035, 0.73), (xx, y - 0.38, 0.55), (xx, y - 0.42, 0.16)
        capsule("bent trouser thigh", hip, knee, 0.087 * factor, 0.075 * factor, M["suit"])
        sphere("rounded trouser knee", knee, (0.075 * factor, 0.079, 0.078), M["suit"])
        capsule("trouser shin", knee, ankle, 0.073 * factor, 0.057 * factor, M["suit"])
        path("pressed trouser crease", [(xx, y - 0.455, 0.50), (xx, y - 0.468, 0.34), (xx, y - 0.47, 0.20)], 0.0017, M["seam"])
        sphere("shoe sole", (xx, y - 0.50, 0.091), (0.077, 0.156, 0.018), M["sole"])
        sphere("rounded leather shoe", (xx, y - 0.50, 0.126), (0.072, 0.15, 0.046), M["shoe"])
        path("shoe vamp seam", [(xx - 0.056, y - 0.50, 0.15), (xx, y - 0.535, 0.169), (xx + 0.056, y - 0.50, 0.15)], 0.0018, M["sole"])
    # Rounded tailored jacket with a real continuous torso surface.
    levels = [(0.73, 0.17, 0.13), (0.79, 0.18, 0.145), (0.98, 0.21, 0.16),
              (1.17, 0.224, 0.153), (1.25, 0.205, 0.135), (1.315, 0.105, 0.080), (1.33, 0.073, 0.062)]
    n = 48
    verts, faces = [], []
    for z, rx, ry in levels:
        for j in range(n):
            phi = j * math.tau / n
            verts.append((x + rx * factor * math.cos(phi), y - 0.025 + ry * math.sin(phi), z))
    for i in range(len(levels) - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    faces += [tuple(reversed(range(n))), tuple((len(levels) - 1) * n + j for j in range(n))]
    torso = mesh("tailored jacket body", verts, faces, M["suit"])
    sub = torso.modifiers.new("Smooth tailored body", "SUBSURF")
    sub.levels = 2
    sub.render_levels = 2
    capsule("visible peach neck", (x, y - 0.032, 1.30), (x, y - 0.032, 1.43), 0.058, 0.056, M["skin"])
    capsule("white shirt neck band", (x, y - 0.032, 1.313), (x, y - 0.032, 1.363), 0.068, 0.064, M["shirt"])
    def P(dx, z, dy=-0.197):
        return (x + dx * factor, y + dy, z)
    panel("white shirt front", [P(-0.092, 1.302, -0.142), P(0.092, 1.302, -0.142), P(0.106, 1.19), P(0, 0.986, -0.188), P(-0.106, 1.19)], M["shirt"])
    for side in (-1, 1):
        panel("shirt pointed collar", [P(side * 0.005, 1.312, -0.151), P(side * 0.088, 1.323, -0.140), P(side * 0.108, 1.22, -0.203), P(side * 0.035, 1.268, -0.208)], M["shirt"])
        path("collar fine edge", [P(side * 0.008, 1.307, -0.156), P(side * 0.04, 1.272, -0.212), P(side * 0.095, 1.234, -0.212)], 0.0015, M["shirt_seam"])
        lapel = [P(side * 0.094, 1.31, -0.153), P(side * 0.192, 1.259, -0.135), P(side * 0.165, 1.213, -0.176),
                 P(side * 0.205, 1.184, -0.145), P(side * 0.103, 1.083, -0.186), P(side * 0.006, 0.957, -0.187)]
        panel("notched suit lapel", lapel, M["lapel"])
        path("dark notched lapel outline", lapel[0:5] + [lapel[-1]], 0.0032, M["seam"])
        path("jacket pocket welt", [P(side * 0.09, 0.981, -0.177), P(side * 0.173, 0.996, -0.160)], 0.0040, M["seam"])
    if not female:
        panel("blue tie knot", [P(0, 1.283, -0.221), P(0.033, 1.245, -0.227), P(0.024, 1.212, -0.232), P(-0.024, 1.212, -0.232), P(-0.033, 1.245, -0.227)], M["tie"], 0.013)
        panel("blue tie blade", [P(-0.013, 1.212, -0.231), P(0.014, 1.212, -0.231), P(0.042, 1.054, -0.210), P(0, 1.014, -0.208), P(-0.039, 1.053, -0.210)], M["tie"], 0.013)
        path("tie central fold", [P(0.004, 1.199, -0.239), P(0.011, 1.15, -0.236), P(0.018, 1.080, -0.223)], 0.0013, M["lapel"])
    for z in (0.926, 0.842):
        sphere("jacket front button", P(0.008, z, -0.173), (0.010, 0.006, 0.010), M["button"], 24, 12)
    # Arms follow the original seated pose. Fingers are distinct, curved geometry.
    for side in (-1, 1):
        shoulder = Vector((x + side * 0.19 * factor, y - 0.03, 1.21))
        elbow = Vector((x + side * 0.285, y - 0.30, 1.095))
        hand = Vector((x + side * 0.24, y - 0.49, 1.059))
        wrist = hand + Vector((0, 0.075, 0.012))
        sphere("rounded suit shoulder", shoulder, (0.085 * factor, 0.087, 0.10), M["suit"])
        capsule("jacket upper sleeve", shoulder, elbow, 0.082 * factor, 0.071 * factor, M["suit"])
        sphere("soft sleeve elbow", elbow, (0.073 * factor, 0.074, 0.065), M["suit"])
        capsule("jacket forearm sleeve", elbow, wrist + Vector((0, 0.018, 0)), 0.068 * factor, 0.052 * factor, M["suit"])
        capsule("white shirt cuff", wrist + Vector((0, 0.035, 0.006)), wrist + Vector((0, -0.018, -0.004)), 0.050, 0.046, M["shirt"])
        sphere("cuff button", tuple(wrist + Vector((side * 0.044, 0.002, 0.016))), (0.006, 0.007, 0.006), M["button"], 24, 12)
        path("sleeve elbow seam", [(elbow.x - 0.051, elbow.y - 0.037, elbow.z + 0.023), (elbow.x, elbow.y - 0.06, elbow.z + 0.05), (elbow.x + 0.051, elbow.y - 0.037, elbow.z + 0.023)], 0.0018, M["seam"])
        sphere("soft hand palm", tuple(hand), (0.052, 0.061, 0.029), M["skin"])
        writing = side == -1
        for finger in range(4):
            dx = (finger - 1.5) * 0.021
            start = hand + Vector((dx, -0.024, 0.001))
            if writing:
                middle = start + Vector((0.006, -0.018, -0.011))
                tip = start + Vector((0.012, -0.030, -0.021))
            else:
                middle = start + Vector((0.003, -0.035, -0.010))
                tip = start + Vector((0.007, -0.058 + abs(finger - 1.5) * 0.010, -0.020))
            path("curved writing finger" if writing else "resting finger", [tuple(start), tuple(middle), tuple(tip)], 0.010, M["skin"])
            sphere("small fingertip", tuple(tip), (0.010, 0.011, 0.010), M["skin"], 24, 12)
            nail = tip + Vector((0, 0.002, 0.009))
            sphere("subtle fingernail", tuple(nail), (0.0055, 0.009, 0.0018), M["nail"], 24, 12)
        thumb_start = hand + Vector((side * -0.043, 0.015, 0.006))
        thumb_end = hand + Vector((side * -0.022, -0.036, 0.016 if writing else -0.01))
        path("opposed thumb", [tuple(thumb_start), tuple(thumb_start + Vector((side * -0.006, -0.022, 0.01))), tuple(thumb_end)], 0.015, M["skin"])
        if writing:
            tip = hand + Vector((0.012, -0.048, -0.034))
            top = tip + Vector((-0.050, 0.048, 0.190))
            capsule("gray pen held in writing hand", tuple(tip), tuple(top), 0.008, 0.010, M["pen"], 20)
            capsule("pen metallic nib", tuple(tip + Vector((0.002, -0.002, -0.012))), tuple(tip + Vector((-0.004, 0.004, 0.018))), 0.002, 0.007, M["pen_tip"], 20)
            path("pen metallic clip", [tuple(top + Vector((0.008, 0, -0.01))), tuple(top + Vector((0.011, -0.007, -0.048))), tuple(top + Vector((0.009, -0.007, -0.059)))], 0.002, M["pen_tip"])
    # The reference uses a large round head, small black eyes, berry mouth/nose.
    rx, ry, rz = (0.253, 0.213, 0.300) if female else (0.264, 0.218, 0.307)
    cx, cy, cz = x, y - 0.050, 1.664
    def head_point(theta, phi, shell=1.0):
        z = math.cos(theta)
        jaw = 1.0 - 0.10 * max(0, -z) ** 1.5
        return (cx + rx * shell * jaw * math.sin(theta) * math.cos(phi),
                cy + ry * shell * math.sin(theta) * math.sin(phi), cz + rz * shell * z)
    verts, faces = [], []
    ns, nt = 96, 56
    for i in range(nt + 1):
        theta = 0.0001 + (math.pi - 0.0002) * i / nt
        for j in range(ns):
            verts.append(head_point(theta, j * math.tau / ns))
    for i in range(nt):
        for j in range(ns):
            k, q = i * ns + j, i * ns + (j + 1) % ns
            faces.append((k, k + ns, q + ns, q))
    face_mat = M["skin"].copy()
    face_mat.name = "Character / " + ("assistant" if female else "boss") + " face with integrated rosy cheeks"
    attr = face_mat.node_tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "face_color"
    face_mat.node_tree.links.new(attr.outputs["Color"], face_mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"])
    face = mesh("round face with soft chin", verts, faces, face_mat)
    colors = face.data.color_attributes.new(name="face_color", type="FLOAT_COLOR", domain="POINT")
    # Blush is part of the face mesh itself: no patch border or overlapping shell.
    for vertex, color in zip(face.data.vertices, colors.data):
        dx, dy, dz = vertex.co.x - cx, vertex.co.y - cy, vertex.co.z - cz
        blend = 0.0
        if dy < -0.02:
            for side in (-1, 1):
                distance = math.sqrt(((dx - side * 0.172) / 0.075) ** 2 + ((dz + 0.055) / 0.074) ** 2)
                if distance < 1:
                    blend = max(blend, math.cos(distance * math.pi / 2) ** 2 * 0.56)
        color.color = tuple(M["skin"].diffuse_color[i] * (1 - blend) + (0.95, 0.24, 0.19)[i] * blend for i in range(3)) + (1,)
    def F(dx, dz, out=0.004):
        zn = dz / rz
        jaw = 1.0 - 0.10 * max(0, -zn) ** 1.5
        depth = ry * math.sqrt(max(0.01, 1 - (dx / (rx * jaw)) ** 2 - zn ** 2))
        return (cx + dx, cy - depth - out, cz + dz)
    for side in (-1, 1):
        sphere("round ear", (cx + side * rx * 0.973, cy - 0.004, cz - 0.018), (0.047, 0.037, 0.065), M["skin"])
        sphere("inner ear peach hollow", (cx + side * rx * 1.032, cy - 0.034, cz - 0.020), (0.024, 0.008, 0.035), M["inner_ear"])
        path("ear inner fold", [(cx + side * rx * 1.036, cy - 0.044, cz + 0.006), (cx + side * rx * 1.080, cy - 0.041, cz - 0.02), (cx + side * rx * 1.025, cy - 0.043, cz - 0.036)], 0.005, M["skin"])
        sphere("small black dot eye", F(side * 0.081, 0.006, 0.006), (0.0182, 0.009, 0.0197 if female else 0.0177), M["eyes"])
        sphere("tiny eye reflection", F(side * 0.081 - 0.004, 0.012, 0.015), (0.0033, 0.0020, 0.0033), M["glint"], 24, 12)
        brow = M["female_brow"] if female else M["eyes"]
        coords = [F(side * 0.047, 0.081, 0.008), F(side * 0.082, 0.096, 0.008), F(side * 0.116, 0.105, 0.008)]
        path("brown angled eyebrow" if female else "thick black angled eyebrow", coords, 0.008 if female else 0.010, brow)
        # Rounded curve endcaps avoid squared extrusion ends.
        for co in (coords[0], coords[-1]):
            sphere("eyebrow soft end", co, (0.0078, 0.008, 0.0078) if female else (0.01, 0.008, 0.01), brow, 24, 12)
        if female:
            path("upper eyelash", [F(side * 0.074, 0.020, 0.013), F(side * 0.081, 0.033, 0.013), F(side * 0.084, 0.040, 0.01)], 0.0037, M["eyes"])
            path("outer eyelash", [F(side * 0.088, 0.017, 0.013), F(side * 0.103, 0.025, 0.012)], 0.0034, M["eyes"])
        # Rosy cheeks are integrated into the face vertex colors above.
    # Tiny rose triangle, as in the original drawings, rather than a realistic nose.
    nose_verts = [F(0, -0.065, 0.014), F(-0.010, -0.083, 0.016), F(0.010, -0.083, 0.016), F(0, -0.077, 0.028)]
    nose = mesh("tiny rose triangular nose", nose_verts, [(0, 1, 3), (1, 2, 3), (2, 0, 3), (0, 2, 1)], M["nose"])
    bev = nose.modifiers.new("Soft reference nose", "BEVEL")
    bev.width, bev.segments = 0.003, 3
    path("small berry horizontal mouth", [F(-0.029, -0.143, 0.007), F(0, -0.142, 0.009), F(0.030, -0.141, 0.007)], 0.0060, M["mouth"])
    sphere("mouth rounded left end", F(-0.029, -0.143, 0.007), (0.0058, 0.006, 0.0058), M["mouth"], 24, 12)
    sphere("mouth rounded right end", F(0.030, -0.141, 0.007), (0.0058, 0.006, 0.0058), M["mouth"], 24, 12)
    # A continuous asymmetric side-part cap, front swept fringe, closed soft edge.
    def boundary(phi):
        front_weight = max(0.0, min(1.0, (-math.sin(phi) - 0.14) / 0.64))
        front_weight = front_weight * front_weight * (3 - 2 * front_weight)
        back = -0.91 if female else -0.065
        # Asymmetric raised part on viewer-left; sweep ends above the right temple.
        # Broad front weight keeps the female bob away from the eyebrows/cheeks.
        forehead = 0.66 - 0.25 * math.cos(phi)
        return math.acos(max(-0.98, min(0.98, back * (1 - front_weight) + forehead * front_weight)))
    hs, ht = 128, 48
    hv, hf = [], []
    for i in range(ht + 1):
        for j in range(hs):
            phi = j * math.tau / hs
            theta = 0.0001 + (boundary(phi) - 0.0001) * i / ht
            co = head_point(theta, phi, 1.055)
            if female and math.sin(phi) > -0.45 and i / ht > 0.72:
                # Full shoulder-length bob, slightly flared at the ends.
                co = (co[0] + 0.025 * math.cos(phi) * ((i / ht - 0.72) / 0.28), co[1] + 0.015, co[2] - 0.034 * ((i / ht - 0.72) / 0.28))
            hv.append(co)
    for i in range(ht):
        for j in range(hs):
            a, b = i * hs + j, i * hs + (j + 1) % hs
            hf.append((a, a + hs, b + hs, b))
    cap = mesh("shoulder length side-part bob" if female else "short swept side-part hair cap", hv, hf, hair)
    solid = cap.modifiers.new("Soft solid hair edge", "SOLIDIFY")
    solid.thickness = 0.013
    solid.offset = -1
    # Sparse sculpted strands follow the cap, not separate sausage-shaped locks.
    for idx, phi in enumerate((-2.98, -2.66, -2.32, -1.94, -1.56, -1.18, -0.80, -0.43, 0.10, 0.65, 1.25, 1.95, 2.60)):
        points = []
        for k in range(8):
            t = 0.24 + 0.70 * k / 7
            ph = phi + (0.11 if math.sin(phi) < 0 else 0.025) * math.sin(t * math.pi)
            theta = boundary(ph) * t
            points.append(head_point(theta, ph, 1.060))
        path("subtle swept hair strand", points, 0.0017, strand)
    # Short parting groove swept from off-center crown toward the upper forehead.
    path("side parting groove", [head_point(t, -2.12 + 0.18 * t, 1.061) for t in (0.08, 0.22, 0.40, 0.62, 0.78)], 0.0030, strand)
    return root


def compare_snapshots(before, after):
    changes = []
    for section in before:
        if before[section] == after[section]:
            continue
        if isinstance(before[section], dict):
            for key in set(before[section]) | set(after[section]):
                if before[section].get(key) != after[section].get(key):
                    changes.append(section + "/" + key)
        else:
            changes.append(section)
    return sorted(changes)


def refine():
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    roots = [bpy.data.objects[n] for n in ROOT_NAMES]
    old = set(ROOT_NAMES)
    for r in roots:
        old.update(descendants(r))
    before = snapshot(old)
    root_world = {r.name: r.matrix_world.copy() for r in roots}
    root_parent = {r.name: r.parent.name for r in roots}
    # Delete only the named placeholder descendants; reject any unexpected asset.
    # Chairs are in workstation collections and are not descendants of pose roots.
    for r in roots:
        expected_prefix = "Boss pose / " if r.name.startswith("Boss_") else "Assistant pose / "
        names = descendants(r)
        assert all(n.startswith(expected_prefix) for n in names), "Unexpected non-character descendant"
        assert all(bpy.data.objects[n].users_collection[:] == (bpy.data.collections["07_Pose_Placeholders"],) for n in names), "Unexpected character collection membership"
        for name in list(names):
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    setup_materials()
    build_character(roots[0], female=False)
    build_character(roots[1], female=True)
    excluded = set(ROOT_NAMES)
    for r in roots:
        excluded.update(descendants(r))
        assert r.matrix_world == root_world[r.name], "Character root moved"
        assert r.parent.name == root_parent[r.name], "Workstation parent changed"
    after = snapshot(excluded)
    changes = compare_snapshots(before, after)
    assert not changes, "Protected scene changed: " + str(changes)
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    scene.render.filepath = str(OUTPUT_DIR / "office-character-detail-preview.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(DESTINATION))
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == source_hash, "Source overwritten"
    report = {"source": SOURCE.name, "output": DESTINATION.name, "source_sha256": source_hash,
              "protected_objects": len(before["objects"]), "protected_materials": len(before["materials"]),
              "protected_before_sha256": digest(before), "protected_after_sha256": digest(after),
              "protected_changes": changes, "character_objects": len(excluded), "total_objects": len(scene.objects),
              "root_positions_unchanged": True, "camera": scene.camera.name, "resolution": [scene.render.resolution_x, scene.render.resolution_y],
              "notes": "Only two characters replaced. Render output filepath is the only output setting change. New shadows/reflections from characters are expected."}
    (OUTPUT_DIR / "人物细化-场景一致性检查.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CHARACTERS_SAVED_VALIDATED", json.dumps(report, ensure_ascii=False), flush=True)
    if "--no-render" not in sys.argv:
        bpy.ops.render.render(write_still=True)
        print("CHARACTERS_RENDERED_OK", scene.render.filepath, flush=True)


if __name__ == "__main__":
    if "--inspect" in sys.argv:
        inspect()
    elif "--refine" in sys.argv:
        refine()
    else:
        raise SystemExit("Use -- --inspect or -- --refine [--no-render]. Source is never rebuilt.")
