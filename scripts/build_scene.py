"""Build the full Blender scene for "Why Do We Pray Five Times a Day?".

Run with Blender's Python (bpy 4.2):
    python scripts/build_scene.py            # builds + saves blender/five_daily_prayers.blend

Everything (room, mat, figure, lights, sky, camera, typography) is created here and
animated against the narration timeline from scripts/timing.py.
"""
import math
import os
import sys

import bpy  # noqa: I001  (bpy must be imported before bmesh/mathutils)
import bmesh
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from timing import FPS, SECTIONS, frame, load_timing  # noqa: E402

TEX = os.path.join(ROOT, "assets", "textures")
FONTS = os.path.join(ROOT, "assets", "fonts")
BLEND_OUT = os.path.join(ROOT, "blender", "five_daily_prayers.blend")

TL = load_timing()
ST = TL["starts"]
END = TL["end"]


def nxt(sec):
    i = SECTIONS.index(sec)
    return ST[SECTIONS[i + 1]] if i + 1 < len(SECTIONS) else END


# ------------------------------------------------------------------ helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def new_coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def mesh_obj(name, bm, coll=None, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return link(bpy.data.objects.new(name, me), coll)


def box(name, x0, x1, y0, y1, z0, z1, coll=None, mat=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    o = mesh_obj(name, bm, coll)
    if mat:
        o.data.materials.append(mat)
    return o


def arch_solid(name, width, z_bottom, z_spring, y0, y1, coll=None, mat=None, segs=32):
    """Prism whose XZ profile is a round-headed arch; extruded from y0 to y1."""
    r = width / 2
    prof = [(-r, z_bottom)]
    for i in range(segs + 1):
        a = math.pi - math.pi * i / segs
        prof.append((r * math.cos(a), z_spring + r * math.sin(a)))
    prof.append((r, z_bottom))
    bm = bmesh.new()
    vs = [bm.verts.new((x, y0, z)) for x, z in prof]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_obj(name, bm, coll)
    if mat:
        o.data.materials.append(mat)
    return o


def boolean(obj, cutter, mat_transfer=True):
    m = obj.modifiers.new("Cut_" + cutter.name, "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = cutter
    m.solver = "EXACT"
    if mat_transfer:
        m.material_mode = "TRANSFER"
    cutter.hide_render = True
    cutter.hide_viewport = True
    cutter.display_type = "WIRE"
    return m


def kf(target, path, t, value, index=-1):
    """Set + keyframe a property at time t (seconds)."""
    if isinstance(value, (tuple, list)):
        cur = getattr(target, path)
        n = len(cur)
        vals = list(value) + [1.0] * (n - len(value))
        setattr(target, path, vals[:n])
    else:
        setattr(target, path, value)
    target.keyframe_insert(path, frame=frame(t), index=index)


def set_interp(idblock, interp="BEZIER", ease=None):
    ad = idblock.animation_data
    if not ad or not ad.action:
        return
    for fc in ad.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = interp
            if ease:
                k.easing = ease
            k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"


# ------------------------------------------------------------------ materials
def mat_new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links


def principled(name, color, rough=0.6, metal=0.0, sheen=0.0, spec=0.5):
    m, n, l = mat_new(name)
    b = n["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    if sheen:
        b.inputs["Sheen Weight"].default_value = sheen
    return m


def add_bump(m, scale=(6, 6, 6), strength=0.15, detail=6, distance=0.02, stretch=None, kind="noise"):
    n, l = m.node_tree.nodes, m.node_tree.links
    b = n["Principled BSDF"]
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = stretch or scale
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    if kind == "noise":
        tx = n.new("ShaderNodeTexNoise")
        tx.inputs["Scale"].default_value = 1.0
        tx.inputs["Detail"].default_value = detail
        out = tx.outputs["Fac"]
    else:  # voronoi (crochet / pores)
        tx = n.new("ShaderNodeTexVoronoi")
        tx.inputs["Scale"].default_value = 1.0
        out = tx.outputs["Distance"]
    l.new(mp.outputs["Vector"], tx.inputs["Vector"])
    bp = n.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = strength
    bp.inputs["Distance"].default_value = distance
    l.new(out, bp.inputs["Height"])
    l.new(bp.outputs["Normal"], b.inputs["Normal"])
    return tx


def img_node(n, path, noncolor=False):
    t = n.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        t.image.colorspace_settings.name = "Non-Color"
    return t


def with_fade(m, name="Fade"):
    """Insert a keyframable alpha (Value node) between the BSDF and the output."""
    n, l = m.node_tree.nodes, m.node_tree.links
    out = n["Material Output"]
    src = out.inputs["Surface"].links[0].from_socket
    tr = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    v = n.new("ShaderNodeValue")
    v.name = v.label = name
    v.outputs[0].default_value = 1.0
    l.new(v.outputs[0], mix.inputs["Fac"])
    l.new(tr.outputs[0], mix.inputs[1])
    l.new(src, mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    m.surface_render_method = "DITHERED"
    try:
        m.use_transparent_shadow = True
    except AttributeError:
        pass
    return v.outputs[0]


def emission_mat(name, color, strength=1.0, alpha=1.0):
    m, n, l = mat_new(name)
    n.remove(n["Principled BSDF"])
    e = n.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    l.new(e.outputs[0], n["Material Output"].inputs["Surface"])
    return m, e


# ------------------------------------------------------------------ scene setup
def setup_scene():
    sc = bpy.context.scene
    sc.name = "FiveDailyPrayers"
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x = 1080
    sc.render.resolution_y = 1920
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.frame_start = 1
    sc.frame_end = frame(END) - 1
    ee = sc.eevee
    ee.taa_render_samples = 8
    ee.use_shadows = True
    ee.shadow_ray_count = 1
    ee.shadow_step_count = 6
    ee.use_raytracing = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.0
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = os.path.join(ROOT, "out", "frames", "")
    return sc


# ------------------------------------------------------------------ room
WALL_Y = 2.0          # inner face of the qibla (back) wall
ROOM_X = 2.2
FRONT_Y = -4.6
CEIL = 3.3
WIN_W, WIN_SILL, WIN_SPRING = 0.92, 0.72, 1.78   # arched window opening
SKY_Y = 16.0
HZ = 1.45             # horizon height on the sky backdrop


def build_room(coll):
    sage = principled("Wall_Sage", (0.30, 0.40, 0.25), rough=0.9, spec=0.3)
    add_bump(sage, stretch=(14, 14, 14), strength=0.05, detail=8)
    cream = principled("Plaster_Cream", (0.80, 0.70, 0.52), rough=0.88, spec=0.3)
    add_bump(cream, stretch=(10, 10, 10), strength=0.08, detail=8)
    ceiling = principled("Ceiling", (0.72, 0.64, 0.50), rough=0.95, spec=0.2)
    walnut_trim = principled("Walnut_Trim", (0.16, 0.09, 0.05), rough=0.45)

    # walnut floor
    fl, n, l = mat_new("Floor_Walnut")
    b = n["Principled BSDF"]
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.5, 0.5, 1)
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(90))   # planks run toward the qibla wall
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    ci = img_node(n, os.path.join(TEX, "floor_color.png"))
    ri = img_node(n, os.path.join(TEX, "floor_rough.png"), noncolor=True)
    for t in (ci, ri):
        l.new(mp.outputs["Vector"], t.inputs["Vector"])
    l.new(ci.outputs["Color"], b.inputs["Base Color"])
    l.new(ri.outputs["Color"], b.inputs["Roughness"])
    bp = n.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.12
    bp.inputs["Distance"].default_value = 0.003
    l.new(ri.outputs["Color"], bp.inputs["Height"])
    l.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.35

    floor = box("Floor", -ROOM_X - 0.2, ROOM_X + 0.2, FRONT_Y - 0.2, WALL_Y + 0.25, -0.1, 0.0, coll, fl)
    floor.data.materials.clear()
    floor.data.materials.append(fl)

    T = 0.2
    back = box("Wall_Back_Qibla", -ROOM_X - T, ROOM_X + T, WALL_Y, WALL_Y + T, -0.1, CEIL + T, coll, sage)
    box("Wall_Left", -ROOM_X - T, -ROOM_X, FRONT_Y - T, WALL_Y + T, -0.1, CEIL + T, coll, sage)
    box("Wall_Right", ROOM_X, ROOM_X + T, FRONT_Y - T, WALL_Y + T, -0.1, CEIL + T, coll, sage)
    box("Wall_Front", -ROOM_X - T, ROOM_X + T, FRONT_Y - T, FRONT_Y, -0.1, CEIL + T, coll, sage)
    box("Ceiling", -ROOM_X - T, ROOM_X + T, FRONT_Y - T, WALL_Y + T, CEIL, CEIL + T, coll, ceiling)
    # walnut skirting boards
    h = 0.11
    box("Skirting_Left", -ROOM_X, -ROOM_X + 0.018, FRONT_Y, WALL_Y, 0, h, coll, walnut_trim)
    box("Skirting_Right", ROOM_X - 0.018, ROOM_X, FRONT_Y, WALL_Y, 0, h, coll, walnut_trim)

    # cream plaster arch (shallow raised panel) on the qibla wall
    arch_w, arch_spring = 1.72, 1.98
    panel = arch_solid("Plaster_Arch", arch_w, 0.0, arch_spring, WALL_Y - 0.05, WALL_Y + 0.01, coll, cream)
    inner = arch_solid("Plaster_Arch_Recess", arch_w - 0.22, 0.0, arch_spring, WALL_Y - 0.10, WALL_Y - 0.03, coll, cream)
    boolean(panel, inner)
    # skirting split either side of the arch
    box("Skirting_Back_L", -ROOM_X, -arch_w / 2, WALL_Y - 0.018, WALL_Y, 0, h, coll, walnut_trim)
    box("Skirting_Back_R", arch_w / 2, ROOM_X, WALL_Y - 0.018, WALL_Y, 0, h, coll, walnut_trim)

    # window opening through wall + panel; the reveal takes the cream plaster material
    cutter = arch_solid("Window_Cutter", WIN_W, WIN_SILL, WIN_SPRING, WALL_Y - 0.3, WALL_Y + T + 0.3, coll, cream)
    boolean(back, cutter)
    cutter2 = arch_solid("Window_Cutter_Panel", WIN_W, WIN_SILL, WIN_SPRING, WALL_Y - 0.3, WALL_Y + T + 0.3, coll, cream)
    boolean(panel, cutter2)

    # sill + slim walnut window frame with muntins (casts the window-pane shadow)
    box("Window_Sill", -WIN_W / 2 - 0.08, WIN_W / 2 + 0.08, WALL_Y - 0.07, WALL_Y + 0.05, WIN_SILL - 0.045, WIN_SILL, coll, cream)
    frame_m = principled("Window_Frame", (0.20, 0.12, 0.07), rough=0.5)
    yc0, yc1 = WALL_Y + 0.08, WALL_Y + 0.11
    bw = 0.028
    box("Muntin_V", -bw / 2, bw / 2, yc0, yc1, WIN_SILL, WIN_SPRING + WIN_W / 2, coll, frame_m)
    for i, z in enumerate((1.25, WIN_SPRING)):
        box(f"Muntin_H{i}", -WIN_W / 2, WIN_W / 2, yc0, yc1, z - bw / 2, z + bw / 2, coll, frame_m)

    # gold-cream moulding around the window arch
    gold_trim = principled("Arch_Moulding", (0.78, 0.62, 0.36), rough=0.35, metal=0.6)
    cu = bpy.data.curves.new("Arch_Moulding", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.016
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    r = WIN_W / 2 + 0.035
    pts = [(-r, WIN_SILL)]
    for i in range(41):
        a = math.pi - math.pi * i / 40
        pts.append((r * math.cos(a), WIN_SPRING + r * math.sin(a)))
    pts.append((r, WIN_SILL))
    sp.points.add(len(pts) - 1)
    for p, (x, z) in zip(sp.points, pts):
        p.co = (x, WALL_Y - 0.055, z, 1)
    mo = link(bpy.data.objects.new("Arch_Moulding", cu), coll)
    cu.materials.append(gold_trim)
    return mo


# ------------------------------------------------------------------ sky / outside
class Sky:
    pass


def build_sky(coll):
    s = Sky()
    m, n, l = mat_new("Sky")
    n.remove(n["Principled BSDF"])
    tc = n.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(tc.outputs["Object"], sep.inputs[0])
    # gradient horizon -> zenith
    mr = n.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = HZ - 0.4
    s.band = mr.inputs["From Max"]
    s.band.default_value = HZ + 3
    l.new(sep.outputs["Y"], mr.inputs["Value"])
    pw = n.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 0.6
    l.new(mr.outputs[0], pw.inputs[0])
    mix = n.new("ShaderNodeMixRGB")
    l.new(pw.outputs[0], mix.inputs["Fac"])
    s.hor = mix.inputs["Color1"]
    s.zen = mix.inputs["Color2"]
    # sun glow around the disc position
    sunpos = n.new("ShaderNodeCombineXYZ")
    s.glow_x, s.glow_y = sunpos.inputs["X"], sunpos.inputs["Y"]
    xy = n.new("ShaderNodeCombineXYZ")
    l.new(sep.outputs["X"], xy.inputs["X"])
    l.new(sep.outputs["Y"], xy.inputs["Y"])
    dist = n.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    l.new(xy.outputs[0], dist.inputs[0])
    l.new(sunpos.outputs[0], dist.inputs[1])
    neg = n.new("ShaderNodeMath")
    neg.operation = "MULTIPLY"
    neg.inputs[1].default_value = -0.9
    l.new(dist.outputs["Value"], neg.inputs[0])
    ex = n.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    l.new(neg.outputs[0], ex.inputs[0])
    gs = n.new("ShaderNodeMath")
    gs.operation = "MULTIPLY"
    s.glow = gs.inputs[1]
    s.glow.default_value = 0.0
    l.new(ex.outputs[0], gs.inputs[0])
    gcol = n.new("ShaderNodeMixRGB")
    gcol.blend_type = "ADD"
    l.new(gs.outputs[0], gcol.inputs["Fac"])
    l.new(mix.outputs[0], gcol.inputs["Color1"])
    s.glow_col = gcol.inputs["Color2"]
    # stars
    vor = n.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 1.6
    l.new(tc.outputs["Object"], vor.inputs["Vector"])
    st = n.new("ShaderNodeMapRange")
    st.inputs["From Min"].default_value = 0.035
    st.inputs["From Max"].default_value = 0.0
    l.new(vor.outputs["Distance"], st.inputs["Value"])
    smul = n.new("ShaderNodeMath")
    smul.operation = "MULTIPLY"
    s.stars = smul.inputs[1]
    s.stars.default_value = 0
    l.new(st.outputs[0], smul.inputs[0])
    sadd = n.new("ShaderNodeMixRGB")
    sadd.blend_type = "ADD"
    sadd.inputs["Color2"].default_value = (1.0, 0.95, 0.85, 1)
    l.new(smul.outputs[0], sadd.inputs["Fac"])
    l.new(gcol.outputs[0], sadd.inputs["Color1"])
    em = n.new("ShaderNodeEmission")
    s.strength = em.inputs["Strength"]
    l.new(sadd.outputs[0], em.inputs["Color"])
    l.new(em.outputs[0], n["Material Output"].inputs["Surface"])

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    bmesh.ops.scale(bm, vec=(26, 12, 1), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 6, 0), verts=bm.verts)
    sky = mesh_obj("Sky_Backdrop", bm, coll)
    sky.rotation_euler = (math.radians(90), 0, 0)
    sky.location = (0, SKY_Y, -2.0)
    sky.data.materials.append(m)
    sky.visible_shadow = False
    # sky object coords: local y == world z + 2  -> account for offset
    mr.inputs["From Min"].default_value = HZ + 2.0 - 0.4
    s.offset = 2.0

    # sun disc
    sm, se = emission_mat("Sun_Disc", (1, 0.95, 0.85), 10)
    s.disc_col, s.disc_str = se.inputs["Color"], se.inputs["Strength"]
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=0.55)
    disc = mesh_obj("Sun_Disc", bm, coll)
    disc.rotation_euler = (math.radians(90), 0, 0)
    disc.data.materials.append(sm)
    disc.visible_shadow = False
    s.disc = disc

    # distant hills + a small domed silhouette on the horizon
    hm, he = emission_mat("Horizon_Silhouette", (0.1, 0.1, 0.1), 1.0)
    s.hills_col = he.inputs["Color"]
    bm = bmesh.new()
    top = []
    for i in range(81):
        x = -14 + 28 * i / 80
        z = HZ - 0.05 + 0.22 * math.sin(x * 0.7 + 1.0) + 0.12 * math.sin(x * 1.9 + 0.3)
        top.append(bm.verts.new((x, SKY_Y - 1.0, z)))
    bot = [bm.verts.new((v.co.x, SKY_Y - 1.0, -4)) for v in top]
    for i in range(80):
        bm.faces.new((bot[i], bot[i + 1], top[i + 1], top[i]))
    hills = mesh_obj("Horizon_Hills", bm, coll)
    hills.data.materials.append(hm)
    hills.visible_shadow = False
    # dome + minaret
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.75)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.01], context="VERTS")
    bmesh.ops.translate(bm, vec=(-1.6, SKY_Y - 1.5, HZ + 0.55), verts=bm.verts)
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.78, radius2=0.78, depth=0.6)
    bmesh.ops.translate(bm, vec=(-1.6, SKY_Y - 1.5, HZ + 0.27), verts=c["verts"])
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.12, radius2=0.1, depth=2.6)
    bmesh.ops.translate(bm, vec=(-0.45, SKY_Y - 1.5, HZ + 1.25), verts=c["verts"])
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.13, radius2=0.0, depth=0.45)
    bmesh.ops.translate(bm, vec=(-0.45, SKY_Y - 1.5, HZ + 2.75), verts=c["verts"])
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.04, radius2=0.0, depth=0.5)
    bmesh.ops.translate(bm, vec=(-1.6, SKY_Y - 1.5, HZ + 1.5), verts=c["verts"])
    dome = mesh_obj("Horizon_Mosque", bm, coll)
    dome.data.materials.append(hm)
    dome.visible_shadow = False
    return s


# ------------------------------------------------------------------ prayer mat
MAT_W, MAT_L = 0.70, 1.10
MAT_Y0 = -0.62  # near (camera-side) edge; far edge = MAT_Y0 + MAT_L


def build_mat(coll):
    m, n, l = mat_new("Prayer_Mat")
    b = n["Principled BSDF"]
    uv = n.new("ShaderNodeTexCoord")
    ci = img_node(n, os.path.join(TEX, "mat_color.png"))
    gi = img_node(n, os.path.join(TEX, "mat_gold.png"), noncolor=True)
    wi = img_node(n, os.path.join(TEX, "mat_weave.png"), noncolor=True)
    for t in (ci, gi, wi):
        l.new(uv.outputs["UV"], t.inputs["Vector"])
    l.new(ci.outputs["Color"], b.inputs["Base Color"])
    l.new(gi.outputs["Color"], b.inputs["Metallic"])
    rr = n.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.92
    rr.inputs["To Max"].default_value = 0.38
    l.new(gi.outputs["Color"], rr.inputs["Value"])
    l.new(rr.outputs[0], b.inputs["Roughness"])
    b.inputs["Sheen Weight"].default_value = 0.6
    b.inputs["Sheen Tint"].default_value = (0.4, 0.8, 0.55, 1)
    bp = n.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.35
    bp.inputs["Distance"].default_value = 0.002
    l.new(wi.outputs["Color"], bp.inputs["Height"])
    l.new(bp.outputs["Normal"], b.inputs["Normal"])
    # unroll reveal: hide everything beyond the roll position (object-space y)
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(uv.outputs["Object"], sep.inputs[0])
    lt = n.new("ShaderNodeMath")
    lt.operation = "LESS_THAN"
    l.new(sep.outputs["Y"], lt.inputs[0])
    reveal = lt.inputs[1]
    reveal.default_value = MAT_L + 0.1
    tr = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    l.new(lt.outputs[0], mix.inputs["Fac"])
    l.new(tr.outputs[0], mix.inputs[1])
    l.new(b.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], n["Material Output"].inputs["Surface"])
    m.surface_render_method = "DITHERED"
    m.use_transparent_shadow = True

    # flat mat: origin at near edge, extends +y; UVs 0..1 (v along length, top of texture = far end)
    bm = bmesh.new()
    nx, ny = 4, 24
    uvl = bm.loops.layers.uv.new()
    grid = [[bm.verts.new((-MAT_W / 2 + MAT_W * i / nx, MAT_L * j / ny, 0.0)) for i in range(nx + 1)] for j in range(ny + 1)]
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            for lp in f.loops:
                lp[uvl].uv = ((lp.vert.co.x + MAT_W / 2) / MAT_W, lp.vert.co.y / MAT_L)
    mat = mesh_obj("Prayer_Mat", bm, coll)
    mat.location = (0, MAT_Y0, 0.0015)
    mat.data.materials.append(m)
    so = mat.modifiers.new("Thickness", "SOLIDIFY")
    so.thickness = 0.006
    so.offset = 1.0

    # the roll (a cylinder of mat) that travels away from camera as it unrolls
    rm = principled("Prayer_Mat_Roll", (0.05, 0.30, 0.18), rough=0.85, sheen=0.5)
    add_bump(rm, stretch=(400, 400, 400), strength=0.2, detail=2)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=1.0, radius2=1.0, depth=MAT_W)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Euler((0, math.radians(90), 0)).to_matrix())
    roll = mesh_obj("Prayer_Mat_Roll", bm, coll, smooth=True)
    roll.data.materials.append(rm)
    # gold edge stripes on the roll ends
    gm = principled("Gold_Thread", (0.85, 0.66, 0.33), rough=0.35, metal=0.9)
    for sx in (-1, 1):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=1.02, radius2=1.02, depth=0.03)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Euler((0, math.radians(90), 0)).to_matrix())
        ring = mesh_obj(f"Prayer_Mat_Roll_Band{'L' if sx < 0 else 'R'}", bm, coll, smooth=True)
        ring.data.materials.append(gm)
        ring.parent = roll
        ring.location = (sx * (MAT_W / 2 - 0.06), 0, 0)

    # fringes on both short ends
    fr_m = principled("Mat_Fringe", (0.86, 0.80, 0.66), rough=0.9)
    fringes = []
    for end, y in (("Near", MAT_Y0), ("Far", MAT_Y0 + MAT_L)):
        bm = bmesh.new()
        k = 34
        for i in range(k):
            x = -MAT_W / 2 + 0.03 + (MAT_W - 0.06) * i / (k - 1)
            c = bmesh.ops.create_cone(bm, cap_ends=False, segments=5, radius1=0.0028, radius2=0.0022, depth=0.05)
            bmesh.ops.rotate(bm, verts=c["verts"], cent=(0, 0, 0), matrix=Euler((math.radians(90), 0, math.radians((i % 3 - 1) * 4))).to_matrix())
            sgn = -1 if end == "Near" else 1
            bmesh.ops.translate(bm, vec=(x, y + sgn * 0.024, 0.003), verts=c["verts"])
        fo = mesh_obj("Mat_Fringe_" + end, bm, coll, smooth=True)
        fo.data.materials.append(fr_m)
        fringes.append(fo)

    # ---- animate the unroll
    t0, t1 = ST["intro"] + 0.35, ST["intro"] + 3.1
    r0 = 0.05
    nfr = int((t1 - t0) * FPS)
    angle = 0.0
    prev_y = None
    for i in range(nfr + 1):
        u = i / nfr
        e = u * u * (3 - 2 * u)          # smoothstep ease
        y = 0.02 + e * (MAT_L - 0.02)    # revealed length
        rad = max(0.006, r0 * math.sqrt(max(0.0, 1 - y / MAT_L)))
        t = t0 + u * (t1 - t0)
        reveal.default_value = y
        reveal.keyframe_insert("default_value", frame=frame(t))
        if prev_y is not None:
            angle -= (y - prev_y) / max(rad, 0.01)
        prev_y = y
        roll.location = (0, MAT_Y0 + y + rad * 0.6, rad)
        roll.scale = (1, rad, rad)
        roll.rotation_euler = (angle, 0, 0)
        for p in ("location", "scale", "rotation_euler"):
            roll.keyframe_insert(p, frame=frame(t))
    # before the unroll: show only the tight roll at the near edge
    reveal.default_value = 0.02
    reveal.keyframe_insert("default_value", frame=1)
    for fc in m.node_tree.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    for fc in roll.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    # roll disappears once flat; far fringe appears
    roll.hide_render = False
    roll.keyframe_insert("hide_render", frame=frame(t1) - 1)
    roll.hide_render = True
    roll.keyframe_insert("hide_render", frame=frame(t1))
    fringes[1].hide_render = True
    fringes[1].keyframe_insert("hide_render", frame=1)
    fringes[1].hide_render = False
    fringes[1].keyframe_insert("hide_render", frame=frame(t1))
    return mat


# ------------------------------------------------------------------ lantern
def build_lantern(coll):
    brass = principled("Lantern_Brass", (0.72, 0.52, 0.25), rough=0.3, metal=1.0)
    gm, ge = emission_mat("Lantern_Glass", (1.0, 0.55, 0.22), 0.0)
    ge_node = ge
    # glass gets a subtle base look when unlit: mix emission with a frosted bsdf
    n, l = gm.node_tree.nodes, gm.node_tree.links
    frost = n.new("ShaderNodeBsdfPrincipled")
    frost.inputs["Base Color"].default_value = (0.75, 0.6, 0.4, 1)
    frost.inputs["Roughness"].default_value = 0.4
    add = n.new("ShaderNodeAddShader")
    l.new(frost.outputs[0], add.inputs[0])
    l.new(ge.outputs[0], add.inputs[1])
    l.new(add.outputs[0], n["Material Output"].inputs["Surface"])

    x, y = -0.56, 0.22
    bm = bmesh.new()
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.085, radius2=0.085, depth=0.03)
    bmesh.ops.translate(bm, vec=(0, 0, 0.015), verts=c["verts"])
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.075, radius2=0.075, depth=0.02)
    bmesh.ops.translate(bm, vec=(0, 0, 0.255), verts=c["verts"])
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.08, radius2=0.01, depth=0.12)
    bmesh.ops.translate(bm, vec=(0, 0, 0.325), verts=c["verts"])
    c = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.018)
    bmesh.ops.translate(bm, vec=(0, 0, 0.395), verts=c["verts"])
    # 8 thin posts
    for i in range(8):
        a = 2 * math.pi * (i + 0.5) / 8
        c = bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.006, radius2=0.006, depth=0.22)
        bmesh.ops.translate(bm, vec=(0.074 * math.cos(a), 0.074 * math.sin(a), 0.14), verts=c["verts"])
    frame_o = mesh_obj("Lantern_Frame", bm, coll, smooth=False)
    frame_o.data.materials.append(brass)
    bm = bmesh.new()
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.07, radius2=0.07, depth=0.22)
    bmesh.ops.translate(bm, vec=(0, 0, 0.14), verts=c["verts"])
    glass = mesh_obj("Lantern_Glass", bm, coll)
    glass.data.materials.append(gm)
    glass.visible_shadow = False
    for o in (frame_o, glass):
        o.location = (x, y, 0)
    ld = bpy.data.lights.new("Lantern_Light", "POINT")
    ld.color = (1.0, 0.62, 0.32)
    ld.shadow_soft_size = 0.05
    ld.energy = 0
    lo = link(bpy.data.objects.new("Lantern_Light", ld), coll)
    lo.location = (x, y, 0.16)
    return ld, ge_node.inputs["Strength"]


# ------------------------------------------------------------------ figure
CLOTH = (0.74, 0.64, 0.47)
SKIN = (0.50, 0.33, 0.22)
KUFI = (0.92, 0.88, 0.78)
HAIR = (0.045, 0.032, 0.026)

# Pose skeletons (figure-local metres, figure faces +Y). Each chain: list of (x, y, z, rx, ry).
# Proportions and poses follow the reference sheets in assets/reference/.
def mirror(chain):
    return [(-x, y, z, rx, ry) for x, y, z, rx, ry in chain]


def L_R(chain):
    return [chain, mirror(chain)]


POSES = {
    "qiyam": dict(
        offset=(0, -0.36, 0),
        robe=[
            [(0, 0.0, 0.05, 0.25, 0.21), (0, 0, 0.40, 0.215, 0.17), (0, 0, 0.88, 0.19, 0.145),
             (0, 0, 1.10, 0.175, 0.125), (0, 0.0, 1.30, 0.195, 0.13), (0, -0.01, 1.42, 0.17, 0.11),
             (0, -0.01, 1.48, 0.065, 0.06)],
            *L_R([(0.15, -0.01, 1.42, 0.056, 0.056), (0.2, 0.0, 1.30, 0.056, 0.056),
                  (0.205, 0.05, 1.13, 0.056, 0.056), (0.13, 0.17, 1.03, 0.055, 0.055), (0.05, 0.20, 1.04, 0.052, 0.052)]),
        ],
        skin=[
            [(-0.06, 0.21, 1.04, 0.03, 0.022), (0.03, 0.235, 1.065, 0.032, 0.02)],
            [(0.06, 0.225, 1.075, 0.03, 0.022), (-0.03, 0.245, 1.095, 0.032, 0.02)],
            [(0, -0.01, 1.44, 0.05, 0.05), (0, 0.0, 1.57, 0.048, 0.048)],
            *L_R([(0.1, -0.02, 0.035, 0.04, 0.035), (0.11, 0.14, 0.025, 0.04, 0.022)]),
        ],
        head=((0, 0.005, 1.665), (0, 0, 0)),
    ),
    "ruku": dict(
        offset=(0, -0.36, 0),
        robe=[
            [(0, -0.02, 0.035, 0.24, 0.20), (0, -0.04, 0.45, 0.2, 0.17), (0, -0.07, 0.85, 0.19, 0.16),
             (0, 0.08, 0.97, 0.18, 0.14), (0, 0.28, 0.99, 0.19, 0.14), (0, 0.44, 0.99, 0.17, 0.12),
             (0, 0.50, 0.99, 0.06, 0.06)],
            *L_R([(0.15, 0.45, 0.99, 0.056, 0.056), (0.2, 0.40, 0.86, 0.056, 0.056),
                  (0.19, 0.27, 0.66, 0.056, 0.056), (0.15, 0.13, 0.52, 0.052, 0.052)]),
        ],
        skin=[
            *L_R([(0.15, 0.12, 0.52, 0.03, 0.03), (0.13, 0.06, 0.47, 0.034, 0.02)]),
            [(0, 0.48, 0.99, 0.05, 0.05), (0, 0.6, 0.985, 0.048, 0.048)],
            *L_R([(0.1, -0.02, 0.035, 0.04, 0.035), (0.11, 0.14, 0.025, 0.04, 0.022)]),
        ],
        head=((0, 0.68, 0.975), (-90, 0, 0)),
    ),
    "sujud": dict(
        offset=(0, -0.06, 0),
        robe=[
            [(0, -0.43, 0.075, 0.2, 0.08), (0, -0.05, 0.10, 0.22, 0.10), (0, -0.10, 0.36, 0.2, 0.15),
             (0, -0.07, 0.52, 0.19, 0.15), (0, 0.12, 0.47, 0.18, 0.14), (0, 0.32, 0.33, 0.19, 0.13),
             (0, 0.40, 0.26, 0.06, 0.06)],
            *L_R([(0.15, 0.34, 0.33, 0.056, 0.056), (0.22, 0.42, 0.22, 0.056, 0.056),
                  (0.24, 0.47, 0.12, 0.055, 0.055), (0.19, 0.55, 0.05, 0.05, 0.045)]),
        ],
        skin=[
            *L_R([(0.18, 0.56, 0.025, 0.032, 0.014), (0.15, 0.67, 0.016, 0.032, 0.012)]),
            [(0, 0.38, 0.28, 0.05, 0.05), (0, 0.47, 0.2, 0.048, 0.048)],
            *L_R([(0.08, -0.5, 0.13, 0.032, 0.035), (0.08, -0.46, 0.03, 0.036, 0.024)]),
        ],
        head=((0, 0.535, 0.13), (-128, 0, 0)),
    ),
    "jalsa": dict(
        offset=(0, -0.2, 0),
        robe=[
            [(0, -0.16, 0.10, 0.21, 0.13), (0, 0.10, 0.13, 0.25, 0.12), (0, 0.33, 0.12, 0.24, 0.1)],
            [(0, -0.12, 0.18, 0.21, 0.16), (0, -0.1, 0.42, 0.18, 0.13), (0, -0.09, 0.66, 0.195, 0.13),
             (0, -0.09, 0.78, 0.17, 0.11), (0, -0.09, 0.84, 0.06, 0.06)],
            *L_R([(0.15, -0.09, 0.78, 0.056, 0.056), (0.22, -0.07, 0.62, 0.056, 0.056),
                  (0.20, 0.03, 0.42, 0.056, 0.056), (0.15, 0.16, 0.27, 0.052, 0.052)]),
        ],
        skin=[
            *L_R([(0.15, 0.16, 0.27, 0.03, 0.025), (0.14, 0.27, 0.24, 0.034, 0.016)]),
            [(0, -0.09, 0.80, 0.05, 0.05), (0, -0.085, 0.93, 0.048, 0.048)],
            *L_R([(0.07, -0.18, 0.04, 0.04, 0.03), (0.05, -0.3, 0.03, 0.035, 0.022)]),
        ],
        head=((0, -0.08, 1.02), (0, 0, 0)),
    ),
}


def skin_object(name, chains, mat, coll, subsurf=2):
    me = bpy.data.meshes.new(name)
    verts, edges, radii, roots = [], [], [], []
    for ch in chains:
        start = len(verts)
        for i, (x, y, z, rx, ry) in enumerate(ch):
            verts.append((x, y, z))
            radii.append((rx, ry))
            if i:
                edges.append((start + i - 1, start + i))
        roots.append(start)
    me.from_pydata(verts, edges, [])
    o = link(bpy.data.objects.new(name, me), coll)
    sk = o.modifiers.new("Skin", "SKIN")
    sk.use_smooth_shade = True
    sk.branch_smoothing = 0.6
    for i, r in enumerate(radii):
        o.data.skin_vertices[0].data[i].radius = r
        o.data.skin_vertices[0].data[i].use_root = i in roots
    ss = o.modifiers.new("Subdivision", "SUBSURF")
    ss.levels = 2
    ss.render_levels = subsurf
    o.data.materials.append(mat)
    return o


def build_figure_materials(tag):
    robe = principled(f"Robe_Cream_{tag}", CLOTH, rough=0.82, sheen=0.7, spec=0.35)
    robe.node_tree.nodes["Principled BSDF"].inputs["Sheen Tint"].default_value = (1, 0.95, 0.85, 1)
    add_bump(robe, stretch=(9, 9, 2.2), strength=0.35, detail=4, distance=0.03)
    skin = principled(f"Skin_{tag}", SKIN, rough=0.55, spec=0.4)
    kufi = principled(f"Kufi_{tag}", KUFI, rough=0.85, sheen=0.5)
    add_bump(kufi, stretch=(70, 70, 70), strength=0.6, kind="voronoi", distance=0.01)
    hair = principled(f"Hair_{tag}", HAIR, rough=0.7)
    add_bump(hair, stretch=(300, 300, 300), strength=0.4, detail=2)
    fades = [with_fade(m) for m in (robe, skin, kufi, hair)]
    return dict(robe=robe, skin=skin, kufi=kufi, hair=hair), fades


def build_head(name, pos, rot, mats, coll, parent):
    piv = link(bpy.data.objects.new(name + "_Pivot", None), coll)
    piv.parent = parent
    piv.location = pos
    piv.rotation_euler = Euler([math.radians(a) for a in rot])
    # faceless head: smooth ellipsoid, no features
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=20, radius=1.0)
    head = mesh_obj(name + "_Head", bm, coll, smooth=True)
    head.parent = piv
    head.scale = (0.088, 0.103, 0.118)
    head.data.materials.append(mats["skin"])
    # cream kufi cap
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=36, v_segments=20, radius=1.0)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 0.18], context="VERTS")
    kufi = mesh_obj(name + "_Kufi", bm, coll, smooth=True)
    kufi.parent = piv
    kufi.scale = (0.097, 0.112, 0.112)
    kufi.location = (0, -0.004, 0.022)
    kufi.data.materials.append(mats["kufi"])
    so = kufi.modifiers.new("Thickness", "SOLIDIFY")
    so.thickness = 0.06
    return piv


def build_figure(coll):
    poses = {}
    for name, p in POSES.items():
        mats, fades = build_figure_materials(name)
        root = link(bpy.data.objects.new(f"Worshipper_{name}", None), coll)
        root.location = p["offset"]
        robe = skin_object(f"Worshipper_{name}_Robe", p["robe"], mats["robe"], coll)
        skin = skin_object(f"Worshipper_{name}_Skin", p["skin"], mats["skin"], coll)
        for o in (robe, skin):
            o.parent = root
        piv = build_head(f"Worshipper_{name}", p["head"][0], p["head"][1], mats, coll, root)
        objs = [robe, skin] + [c for c in piv.children]
        poses[name] = dict(root=root, objs=objs, fades=fades)
    return poses


def animate_figure(poses):
    # which pose is shown in each section (closing keeps the Isha qiyam)
    plan = {
        "fajr": "qiyam", "dhuhr": "ruku", "asr": "sujud", "maghrib": "jalsa",
        "isha": "qiyam", "closing": "qiyam",
    }
    XF_IN, XF_OUT = 0.35, 0.55   # crossfade window around each section start
    vis = {k: [] for k in poses}  # list of (t_on_start, t_on_end) visibility windows
    order = ["fajr", "dhuhr", "asr", "maghrib", "isha", "closing"]
    for i, sec in enumerate(order):
        pose = plan[sec]
        t_in = ST[sec]
        t_out = ST[order[i + 1]] if i + 1 < len(order) else END + 1
        # merge consecutive sections with same pose
        if vis[pose] and abs(vis[pose][-1][1] - t_in) < 1e-6:
            vis[pose][-1] = (vis[pose][-1][0], t_out)
        else:
            vis[pose].append((t_in, t_out))
    for name, d in poses.items():
        sockets = d["fades"]
        keys = [(0.0, 0.0)]
        hide = [(0.0, True)]
        for (a, b) in vis[name]:
            keys += [(a - XF_IN, 0.0), (a + XF_OUT, 1.0)]
            hide += [(a - XF_IN - 0.05, False)]
            if b < END:
                keys += [(b - XF_IN, 1.0), (b + XF_OUT, 0.0)]
                hide += [(b + XF_OUT + 0.05, True)]
        for s in sockets:
            for t, v in keys:
                s.default_value = v
                s.keyframe_insert("default_value", frame=max(1, frame(t)))
        for o in d["objs"]:
            for t, h in hide:
                o.hide_render = h
                o.keyframe_insert("hide_render", frame=max(1, frame(t)))
            # fully faded objects shouldn't cast shadows either
        for nt in {s.id_data for s in sockets}:
            set_interp(nt, "BEZIER")


# ------------------------------------------------------------------ lights + time of day
class R:
    """A value that ramps from a (section start) to b (section end)."""
    def __init__(self, a, b):
        self.a, self.b = a, b


def sun_rot(el, az):
    el, az = math.radians(el), math.radians(az)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    return (-d).to_track_quat("-Z", "Y").to_euler()


STATES = {
    #           sky zenith           sky horizon          band   skyStr stars  hills
    "intro":   dict(zen=(0.20, 0.27, 0.42), hor=(0.95, 0.74, 0.52), band=3.2, sky=1.1, stars=0.0, hills=(0.16, 0.14, 0.14),
                    disc=(1.2, -1.5), disc_col=(1, 0.8, 0.55), disc_str=0, glow=0.25, glow_col=(1, 0.6, 0.35),
                    sun_e=0.0, sun_el=10, sun_az=20, sun_col=(1, 0.8, 0.6),
                    world=(0.62, 0.55, 0.46), world_s=0.9, fill=(1.0, 0.86, 0.72), fill_e=55, lamp=0, room=(1.0, 0.85, 0.7), room_e=60),
    "fajr":    dict(zen=(0.010, 0.022, 0.085), hor=(0.62, 0.46, 0.40), band=0.55, sky=1.15, stars=0.9, hills=(0.012, 0.016, 0.035),
                    disc=(1.2, -1.2), disc_col=(1, 0.7, 0.5), disc_str=0, glow=0.12, glow_col=(0.9, 0.55, 0.4),
                    sun_e=0.0, sun_el=-3, sun_az=25, sun_col=(0.6, 0.7, 1),
                    world=(0.13, 0.20, 0.42), world_s=0.75, fill=(0.40, 0.55, 1.0), fill_e=55, lamp=0, room=(0.5, 0.62, 1.0), room_e=30),
    "dhuhr":   dict(zen=(0.16, 0.38, 0.85), hor=(0.72, 0.84, 0.95), band=4.5, sky=1.5, stars=0.0, hills=(0.30, 0.36, 0.28),
                    disc=(0.35, 4.1), disc_col=(1, 0.97, 0.9), disc_str=25, glow=0.6, glow_col=(1, 0.95, 0.85),
                    sun_e=8.0, sun_el=62, sun_az=8, sun_col=(1, 0.95, 0.86),
                    world=(0.62, 0.64, 0.62), world_s=0.6, fill=(0.85, 0.92, 1.0), fill_e=70, lamp=0, room=(1.0, 0.95, 0.88), room_e=45),
    "asr":     dict(zen=(0.26, 0.38, 0.66), hor=(1.0, 0.70, 0.40), band=2.8, sky=1.35, stars=0.0, hills=(0.24, 0.20, 0.14),
                    disc=R((0.9, 3.2), (1.1, 2.4)), disc_col=(1, 0.82, 0.52), disc_str=18, glow=0.8, glow_col=(1, 0.65, 0.3),
                    sun_e=7.0, sun_el=R(36, 19), sun_az=R(6, 11), sun_col=(1, 0.70, 0.40),
                    world=(0.72, 0.52, 0.34), world_s=0.45, fill=(1.0, 0.78, 0.55), fill_e=50, lamp=0, room=(1.0, 0.75, 0.5), room_e=30),
    "maghrib": dict(zen=(0.30, 0.20, 0.40), hor=(1.0, 0.45, 0.30), band=2.0, sky=1.3, stars=0.0, hills=(0.10, 0.05, 0.08),
                    disc=R((1.1, 0.3), (1.15, 0.0)), disc_col=(1, 0.45, 0.22), disc_str=14, glow=R(1.4, 1.0), glow_col=(1, 0.42, 0.3),
                    sun_e=R(1.5, 0.0), sun_el=R(4, -1), sun_az=12, sun_col=(1, 0.45, 0.3),
                    world=(0.62, 0.36, 0.38), world_s=0.65, fill=(1.0, 0.52, 0.48), fill_e=60, lamp=0, room=(1.0, 0.6, 0.55), room_e=40),
    "isha":    dict(zen=(0.004, 0.008, 0.03), hor=(0.012, 0.02, 0.06), band=0.4, sky=1.0, stars=1.4, hills=(0.002, 0.003, 0.008),
                    disc=(1.5, -2.0), disc_col=(1, 0.45, 0.22), disc_str=0, glow=0.0, glow_col=(1, 0.42, 0.3),
                    sun_e=0.0, sun_el=-12, sun_az=32, sun_col=(1, 0.45, 0.3),
                    world=(0.06, 0.08, 0.17), world_s=0.55, fill=(0.25, 0.35, 0.7), fill_e=12, lamp=70, room=(1.0, 0.7, 0.45), room_e=10),
    "closing": dict(zen=(0.004, 0.008, 0.03), hor=(0.012, 0.02, 0.06), band=0.4, sky=1.0, stars=1.4, hills=(0.002, 0.003, 0.008),
                    disc=(1.5, -2.0), disc_col=(1, 0.45, 0.22), disc_str=0, glow=0.0, glow_col=(1, 0.42, 0.3),
                    sun_e=0.0, sun_el=-12, sun_az=32, sun_col=(1, 0.45, 0.3),
                    world=(0.07, 0.09, 0.18), world_s=0.6, fill=(0.25, 0.35, 0.7), fill_e=14, lamp=70, room=(1.0, 0.7, 0.45), room_e=16),
}
# per-section transition length (s) from the previous look into this one
TRANS = {"intro": 0.1, "fajr": 1.4, "dhuhr": 1.4, "asr": 1.3, "maghrib": 1.1, "isha": 1.6, "closing": 1.0}


def build_lights(coll, sky, lantern_light, lantern_glow):
    sc = bpy.context.scene
    world = bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]

    sun_d = bpy.data.lights.new("Sun", "SUN")
    sun_d.angle = math.radians(1.8)
    sun = link(bpy.data.objects.new("Sun", sun_d), coll)

    fill_d = bpy.data.lights.new("Window_Skylight", "AREA")
    fill_d.shape = "RECTANGLE"
    fill_d.size, fill_d.size_y = 0.9, 1.3
    fill_d.use_shadow = True
    fill = link(bpy.data.objects.new("Window_Skylight", fill_d), coll)
    fill.location = (0, WALL_Y - 0.55, 1.5)
    fill.rotation_euler = (math.radians(-90), 0, 0)   # facing -y, into the room

    room_d = bpy.data.lights.new("Room_Bounce", "AREA")
    room_d.shape = "RECTANGLE"
    room_d.size, room_d.size_y = 3.5, 5.0
    room_d.use_shadow = False
    room_d.specular_factor = 0.0   # soft bounce only; no hotspot reflections on the floor
    room = link(bpy.data.objects.new("Room_Bounce", room_d), coll)
    room.location = (0, -1.2, CEIL - 0.05)

    props = {
        "zen": (sky.zen, "default_value"), "hor": (sky.hor, "default_value"),
        "sky": (sky.strength, "default_value"), "stars": (sky.stars, "default_value"),
        "hills": (sky.hills_col, "default_value"),
        "disc_col": (sky.disc_col, "default_value"), "disc_str": (sky.disc_str, "default_value"),
        "glow": (sky.glow, "default_value"), "glow_col": (sky.glow_col, "default_value"),
        "sun_e": (sun_d, "energy"), "sun_col": (sun_d, "color"),
        "world": (bg.inputs["Color"], "default_value"), "world_s": (bg.inputs["Strength"], "default_value"),
        "fill": (fill_d, "color"), "fill_e": (fill_d, "energy"),
        "room": (room_d, "color"), "room_e": (room_d, "energy"),
        "lamp": (lantern_light, "energy"),
    }

    def val(v, which):
        return (v.a if which == "a" else v.b) if isinstance(v, R) else v

    for i, sec in enumerate(SECTIONS):
        st = STATES[sec]
        t_a = ST[sec] + TRANS[sec]
        t_b = nxt(sec) - 0.05
        if sec == "intro":
            t_a = 0.0
        for which, t in (("a", t_a), ("b", t_b)):
            for k, (tgt, path) in props.items():
                kf(tgt, path, t, val(st[k], which))
            # band (horizon->zenith gradient height)
            kf(sky.band, "default_value", t, HZ + sky.offset + val(st["band"], which))
            dx, dz = val(st["disc"], which)
            kf(sky.disc, "location", t, (dx, SKY_Y - 0.3, dz))
            kf(sky.glow_x, "default_value", t, dx)
            kf(sky.glow_y, "default_value", t, dz + sky.offset)
            sun.rotation_euler = sun_rot(val(st["sun_el"], which), val(st["sun_az"], which))
            sun.keyframe_insert("rotation_euler", frame=frame(t))
            # lantern glass glows with the lamp
            kf(lantern_glow, "default_value", t, val(st["lamp"], which) * 0.045)
    for ld in (sun_d, fill_d, room_d, lantern_light):
        ld.shadow_maximum_resolution = 0.03
    for idb in (sun_d, fill_d, room_d, lantern_light, sun, sky.disc, world.node_tree,
                sky.strength.id_data, sky.hills_col.id_data, sky.disc_col.id_data, lantern_glow.id_data):
        set_interp(idb, "BEZIER")
    return sun


# ------------------------------------------------------------------ camera
CAM_LENS = 26.0
CAM_SENSOR = 36.0


def build_camera(coll):
    cd = bpy.data.cameras.new("Camera")
    cd.lens = CAM_LENS
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = CAM_SENSOR
    cd.clip_start = 0.01
    cd.clip_end = 60
    cam = link(bpy.data.objects.new("Camera", cd), coll)
    tgt = link(bpy.data.objects.new("Camera_Target", None), coll)
    tgt.empty_display_size = 0.2
    c = cam.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    bpy.context.scene.camera = cam

    i0 = ST["intro"]
    mid = lambda s: (ST[s] + nxt(s)) / 2  # noqa: E731
    keys = [
        # time, camera position, look-at target
        (i0 + 0.0, (0.10, -1.00, 0.34), (0.0, 0.05, 0.02)),
        (i0 + 1.6, (0.12, -1.30, 0.48), (0.0, 0.15, 0.05)),
        (i0 + 3.6, (0.22, -2.40, 0.95), (0.0, 0.60, 0.75)),
        (i0 + 6.4, (0.30, -3.60, 1.20), (0.0, 1.00, 1.40)),
        (mid("fajr"), (0.45, -3.10, 1.15), (0.0, 1.20, 1.40)),
        (mid("dhuhr"), (-1.55, -2.55, 1.35), (0.10, 0.40, 0.95)),
        (mid("asr"), (0.25, -3.20, 1.65), (0.0, 0.40, 0.95)),
        (mid("maghrib"), (-0.20, -2.90, 1.05), (0.0, 1.60, 1.45)),
        (mid("isha"), (-1.25, -2.90, 2.10), (-0.30, 0.15, 0.30)),
        (ST["closing"] + 1.2, (0.20, -2.80, 1.30), (0.0, 0.80, 1.25)),
        (END, (0.08, -3.90, 1.45), (0.0, 1.00, 1.45)),
    ]
    for t, p, q in keys:
        kf(cam, "location", t, p)
        kf(tgt, "location", t, q)
    for o in (cam, tgt):
        set_interp(o, "BEZIER")
    return cam


# ------------------------------------------------------------------ typography
TEXT_D = 0.20                       # distance of the text plane in front of the camera
PX = (2 * TEXT_D * (CAM_SENSOR / 2) / CAM_LENS) / 1920.0   # metres per pixel at TEXT_D
SAFE_CX = 492                       # text column centre (px) - nudged left of the right-side UI
MAX_W = 840                         # max text width in px (keeps clear of edges)
CREAM = (0.98, 0.92, 0.80)
GOLD = (0.93, 0.74, 0.40)
FONT_SERIF = os.path.join(FONTS, "EBGaramond12-Regular.otf")
FONT_SANS = os.path.join(FONTS, "Montserrat-Medium.ttf")
FONT_SANS_R = os.path.join(FONTS, "Montserrat-Regular.ttf")


def px_to_local(x, y):
    return ((x - 540) * PX, (960 - y) * PX)


def text_mat(name, color, strength=1.25):
    m, e = emission_mat(name, color, strength)
    fade = with_fade(m, "Alpha")
    m.use_transparent_shadow = True
    return m, fade


def make_text(cam, coll, name, body, y_px, size_px, font, color, spacing=1.0, max_w=MAX_W, line=1.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = size_px * PX
    cu.space_character = spacing
    cu.space_line = line
    o = link(bpy.data.objects.new(name, cu), coll)
    o.parent = cam
    lx, ly = px_to_local(SAFE_CX, y_px)
    o.location = (lx, ly, -TEXT_D)
    o.visible_shadow = False
    m, fade = text_mat(name + "_Mat", color)
    cu.materials.append(m)
    bpy.context.view_layer.update()
    w = o.dimensions.x / PX
    if w > max_w:
        cu.size *= max_w / w
    return o, fade


def make_rule(cam, coll, name, y_px, w_px, color):
    """Thin gold divider with a small diamond in the middle."""
    bm = bmesh.new()
    hw, hh = w_px * PX / 2, 1.6 * PX
    for x0, x1 in ((-hw, -9 * PX), (9 * PX, hw)):
        vs = [bm.verts.new(v) for v in ((x0, -hh, 0), (x1, -hh, 0), (x1, hh, 0), (x0, hh, 0))]
        bm.faces.new(vs)
    d = 6 * PX
    vs = [bm.verts.new(v) for v in ((0, -d, 0), (d, 0, 0), (0, d, 0), (-d, 0, 0))]
    bm.faces.new(vs)
    o = mesh_obj(name, bm, coll)
    o.parent = cam
    lx, ly = px_to_local(SAFE_CX, y_px)
    o.location = (lx, ly, -TEXT_D)
    o.visible_shadow = False
    m, fade = text_mat(name + "_Mat", color)
    o.data.materials.append(m)
    return o, fade


def make_scrim(cam, coll, name, y0_px, y1_px, w_px=980, alpha=0.55):
    """Soft dark-green vignette card behind a block of text for readability."""
    m, n, l = mat_new(name + "_Mat")
    n.remove(n["Principled BSDF"])
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (-1, -1, 0)
    mp.inputs["Scale"].default_value = (2, 2, 1)
    l.new(tc.outputs["UV"], mp.inputs["Vector"])
    gr = n.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    l.new(mp.outputs["Vector"], gr.inputs["Vector"])
    pw = n.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 0.7
    l.new(gr.outputs["Fac"], pw.inputs[0])
    a = n.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    a.inputs[1].default_value = alpha
    l.new(pw.outputs[0], a.inputs[0])
    v = n.new("ShaderNodeValue")
    v.name = v.label = "Alpha"
    v.outputs[0].default_value = 1.0
    a2 = n.new("ShaderNodeMath")
    a2.operation = "MULTIPLY"
    l.new(a.outputs[0], a2.inputs[0])
    l.new(v.outputs[0], a2.inputs[1])
    em = n.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.004, 0.018, 0.012, 1)
    tr = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    l.new(a2.outputs[0], mix.inputs["Fac"])
    l.new(tr.outputs[0], mix.inputs[1])
    l.new(em.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], n["Material Output"].inputs["Surface"])
    m.surface_render_method = "BLENDED"
    m.use_transparent_shadow = True

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new()
    hw = w_px * PX / 2
    hh = (y1_px - y0_px) * PX / 2
    vs = [bm.verts.new(v) for v in ((-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0))]
    f = bm.faces.new(vs)
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    o = mesh_obj(name, bm, coll)
    o.parent = cam
    lx, ly = px_to_local(SAFE_CX, (y0_px + y1_px) / 2)
    o.location = (lx, ly, -TEXT_D - 0.002)
    o.visible_shadow = False
    o.data.materials.append(m)
    return o, v.outputs[0]


def animate_text(obj, fade, t_in, t_out, rise_px=14, dur=0.55):
    """Fade + gentle rise in; fade out. Keeps object hidden when invisible."""
    base = obj.location.copy()
    fade.default_value = 0.0
    fade.keyframe_insert("default_value", frame=max(1, frame(t_in)))
    fade.default_value = 1.0
    fade.keyframe_insert("default_value", frame=frame(t_in + dur))
    if t_out is not None:
        fade.keyframe_insert("default_value", frame=frame(t_out))
        fade.default_value = 0.0
        fade.keyframe_insert("default_value", frame=frame(t_out + 0.45))
    if rise_px:
        obj.location = base - Vector((0, rise_px * PX, 0))
        obj.keyframe_insert("location", frame=max(1, frame(t_in)))
        obj.location = base
        obj.keyframe_insert("location", frame=frame(t_in + dur + 0.25))
        set_interp(obj, "BEZIER")
    obj.hide_render = True
    obj.keyframe_insert("hide_render", frame=1)
    obj.hide_render = False
    obj.keyframe_insert("hide_render", frame=max(1, frame(t_in) - 1))
    if t_out is not None:
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=frame(t_out + 0.5))
    set_interp(fade.id_data, "BEZIER")


NAME_LEAD = {"fajr": 0.55, "dhuhr": 0.5, "asr": 0.5, "maghrib": 0.95, "isha": 1.0}
PRAYERS = [
    ("fajr", "FAJR", "DAWN TO SUNRISE"),
    ("dhuhr", "DHUHR", "AFTER SOLAR NOON"),
    ("asr", "ASR", "AFTERNOON"),
    ("maghrib", "MAGHRIB", "JUST AFTER SUNSET"),
    ("isha", "ISHA", "AFTER TWILIGHT"),
]


def build_typography(cam, coll):
    # ---- title in two beats
    i0 = ST["intro"]
    t_out = ST["fajr"] - 0.7
    sc, sf = make_scrim(cam, coll, "Title_Scrim", 250, 610, alpha=0.58)
    animate_text(sc, sf, i0 + 2.0, t_out, rise_px=0, dur=0.8)
    o, f = make_text(cam, coll, "Title_Line1", "WHY DO WE PRAY", 370, 96, FONT_SERIF, CREAM, spacing=1.08)
    animate_text(o, f, i0 + 2.1, t_out)
    r, rf = make_rule(cam, coll, "Title_Rule", 437, 300, GOLD)
    animate_text(r, rf, i0 + 3.2, t_out, rise_px=0)
    o, f = make_text(cam, coll, "Title_Line2", "FIVE TIMES A DAY?", 500, 96, FONT_SERIF, GOLD, spacing=1.08)
    animate_text(o, f, i0 + 3.35, t_out)

    # ---- per-prayer cards
    for sec, name, sub in PRAYERS:
        t_in = ST[sec] + NAME_LEAD[sec]
        t_end = nxt(sec) - 0.55
        y1 = 700 if sec == "asr" else 580
        sc, sf = make_scrim(cam, coll, f"{name}_Scrim", 250, y1, alpha=0.62)
        animate_text(sc, sf, t_in - 0.15, t_end, rise_px=0, dur=0.7)
        o, f = make_text(cam, coll, f"{name}_Name", name, 380, 168, FONT_SERIF, GOLD, spacing=1.12)
        animate_text(o, f, t_in, t_end, rise_px=18, dur=0.7)
        r, rf = make_rule(cam, coll, f"{name}_Rule", 462, 260, GOLD)
        animate_text(r, rf, t_in + 0.25, t_end, rise_px=0)
        o, f = make_text(cam, coll, f"{name}_Sub", sub, 512, 34, FONT_SANS, CREAM, spacing=1.45)
        animate_text(o, f, t_in + 0.35, t_end)
        if sec == "asr":
            o, f = make_text(cam, coll, "ASR_Note", "Check your local timetable\nfor the exact start.",
                             615, 40, FONT_SANS, CREAM, spacing=1.04, line=1.15)
            animate_text(o, f, ST["asr"] + 2.4, t_end)

    # ---- closing: all five names in order, then the timetable reminder
    c0 = ST["closing"]
    sc, sf = make_scrim(cam, coll, "Closing_Scrim", 200, 1180, alpha=0.55)
    animate_text(sc, sf, c0 + 0.1, None, rise_px=0, dur=0.8)
    y = 300
    for i, (_, name, _) in enumerate(PRAYERS):
        o, f = make_text(cam, coll, f"Closing_{name}", name, y, 92, FONT_SERIF, GOLD if i % 2 == 0 else CREAM, spacing=1.12)
        animate_text(o, f, c0 + 0.35 + 0.42 * i, None, rise_px=12, dur=0.6)
        if i < 4:
            d, df = make_rule(cam, coll, f"Closing_Dot{i}", y + 63, 40, GOLD)
            animate_text(d, df, c0 + 0.55 + 0.42 * i, None, rise_px=0)
        y += 126
    o, f = make_text(cam, coll, "Closing_Note", "Check your local mosque’s\nprayer timetable.",
                     y + 30, 44, FONT_SANS, CREAM, spacing=1.04, line=1.15)
    animate_text(o, f, c0 + 2.8, None, rise_px=12, dur=0.7)


# ------------------------------------------------------------------ compositor
def build_compositor(sc):
    sc.use_nodes = True
    nt = sc.node_tree
    n, l = nt.nodes, nt.links
    for x in list(n):
        n.remove(x)
    rl = n.new("CompositorNodeRLayers")
    gl = n.new("CompositorNodeGlare")
    gl.glare_type = "FOG_GLOW"
    gl.quality = "MEDIUM"
    gl.threshold = 0.9
    gl.mix = -0.82
    gl.size = 8
    l.new(rl.outputs["Image"], gl.inputs["Image"])
    # (the soft vignette is applied at encode time in make_reel.sh)
    comp = n.new("CompositorNodeComposite")
    l.new(gl.outputs["Image"], comp.inputs["Image"])


# ------------------------------------------------------------------ main
def main():
    reset()
    sc = setup_scene()
    c_room = new_coll("Room")
    c_out = new_coll("Outside_Sky")
    c_mat = new_coll("Prayer_Mat")
    c_fig = new_coll("Worshipper")
    c_light = new_coll("Lighting")
    c_cam = new_coll("Camera_and_Text")

    build_room(c_room)
    sky = build_sky(c_out)
    build_mat(c_mat)
    lamp, glow = build_lantern(c_mat)
    poses = build_figure(c_fig)
    animate_figure(poses)
    build_lights(c_light, sky, lamp, glow)
    cam = build_camera(c_cam)
    build_typography(cam, c_cam)
    build_compositor(sc)

    if TL["audio"]:
        sc.sequence_editor_create()
        sc.sequence_editor.sequences.new_sound("Voiceover", TL["audio"], channel=1, frame_start=1)

    # record the timeline used, for reference inside the .blend
    txt = bpy.data.texts.new("TIMELINE.txt")
    txt.write(f"timing source: {TL['source']}\nend: {END:.2f}s\n")
    for s in SECTIONS:
        txt.write(f"{s:8s} {ST[s]:6.2f}s  frame {frame(ST[s])}\n")

    os.makedirs(os.path.dirname(BLEND_OUT), exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT, compress=True)
    print(f"[build] saved {BLEND_OUT}  ({TL['source']} timing, {sc.frame_end} frames)")


if __name__ == "__main__":
    main()
