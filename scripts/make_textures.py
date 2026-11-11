"""Generate the procedural image textures used by the scene.

Run with the bpy venv python (needs numpy + Pillow):
    python scripts/make_textures.py

Writes into assets/textures/:
    mat_color.png   emerald prayer mat with a geometric gold border
    mat_gold.png    mask of the gold thread (drives metallic / roughness)
    mat_weave.png   fine woven height map (bump)
    floor_color.png walnut planks
    floor_rough.png plank roughness / grain
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "textures")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def smooth_noise(h, w, cell, octaves=4, seed=0):
    """Cheap value-noise fBm in [0,1]."""
    r = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        c = max(2, int(cell / (2 ** o)))
        gh, gw = h // c + 2, w // c + 2
        g = r.random((gh, gw)).astype(np.float32)
        img = Image.fromarray((g * 255).astype(np.uint8)).resize((gw * c, gh * c), Image.BICUBIC)
        acc += amp * np.asarray(img, np.float32)[:h, :w] / 255.0
        total += amp
        amp *= 0.5
    return acc / total


# ---------------------------------------------------------------- prayer mat
def make_mat():
    # Mat is 0.70 m x 1.10 m. Texture: 1400 x 2200 (2 px per mm), drawn at 2x for AA.
    W, H = 1400, 2200
    S = 2
    w, h = W * S, H * S
    emerald = (14, 84, 52)
    emerald_dark = (9, 60, 37)
    gold = (212, 175, 92)

    col = Image.new("RGB", (w, h), emerald)
    gm = Image.new("L", (w, h), 0)  # gold mask
    dc, dg = ImageDraw.Draw(col), ImageDraw.Draw(gm)

    def rect(x0, y0, x1, y1, width, fill=None):
        dc.rectangle([x0, y0, x1, y1], outline=gold, width=width, fill=fill)
        dg.rectangle([x0, y0, x1, y1], outline=255, width=width, fill=None)

    def line(pts, width):
        dc.line(pts, fill=gold, width=width, joint="curve")
        dg.line(pts, fill=255, width=width, joint="curve")

    def poly(pts, width, fill=False):
        if fill:
            dc.polygon(pts, fill=gold)
            dg.polygon(pts, fill=255)
        else:
            dc.polygon(pts, outline=gold, width=width)
            dg.polygon(pts, outline=255, width=width)

    m = int(0.035 * w)          # plain outer margin
    bw = int(0.12 * w)          # border band width
    # darker band behind the geometric border
    dc.rectangle([m, m, w - m, h - m], fill=emerald_dark)
    dc.rectangle([m + bw, m + bw, w - m - bw, h - m - bw], fill=emerald)
    lw = int(0.006 * w)
    rect(m, m, w - m, h - m, lw)
    rect(m + bw, m + bw, w - m - bw, h - m - bw, lw)
    # thin inner frame line
    ins = int(0.035 * w)
    rect(m + bw + ins, m + bw + ins, w - m - bw - ins, h - m - bw - ins, max(2, lw // 2))

    # repeating 8-point star + diamond chain along the band
    def star(cx, cy, r, width):
        pts_a = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 90)]
        pts_b = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(45, 405, 90)]
        poly(pts_a, width)
        poly(pts_b, width)
        rr = r * 0.28
        poly([(cx, cy - rr), (cx + rr, cy), (cx, cy + rr), (cx - rr, cy)], width, fill=True)

    def band(x0, y0, x1, y1, horizontal):
        length = (x1 - x0) if horizontal else (y1 - y0)
        n = max(3, int(round(length / (bw * 1.05))))
        step = length / n
        r = bw * 0.36
        for i in range(n):
            c = (i + 0.5) * step
            cx, cy = (x0 + c, (y0 + y1) / 2) if horizontal else ((x0 + x1) / 2, y0 + c)
            star(cx, cy, r, lw)
            # connecting diamonds between stars
            if i < n - 1:
                c2 = (i + 1.0) * step
                dx, dy = (x0 + c2, (y0 + y1) / 2) if horizontal else ((x0 + x1) / 2, y0 + c2)
                d = bw * 0.13
                poly([(dx, dy - d), (dx + d, dy), (dx, dy + d), (dx - d, dy)], max(2, lw // 2))

    cm = m + bw / 2
    band(m + bw, m, w - m - bw, m + bw, True)            # top
    band(m + bw, h - m - bw, w - m - bw, h - m, True)    # bottom
    band(m, m + bw, m + bw, h - m - bw, False)           # left
    band(w - m - bw, m + bw, w - m, h - m - bw, False)   # right
    for cx, cy in [(cm, cm), (w - cm, cm), (cm, h - cm), (w - cm, h - cm)]:
        star(cx, cy, bw * 0.36, lw)

    # small motif in the inner corners of the field
    fx0, fy0 = m + bw + ins, m + bw + ins
    fx1, fy1 = w - fx0, h - fy0
    k = bw * 0.55
    for (cx, cy, sx, sy) in [(fx0, fy0, 1, 1), (fx1, fy0, -1, 1), (fx0, fy1, 1, -1), (fx1, fy1, -1, -1)]:
        poly([(cx, cy), (cx + sx * k, cy), (cx, cy + sy * k)], lw, fill=False)

    col = col.resize((W, H), Image.LANCZOS)
    gm = gm.resize((W, H), Image.LANCZOS)

    # woven texture: fine over/under weave + fibre noise
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    p = 3.0  # px per thread
    warp = 0.5 + 0.5 * np.sin(2 * np.pi * xx / p)
    weft = 0.5 + 0.5 * np.sin(2 * np.pi * yy / p)
    checker = ((np.floor(xx / p) + np.floor(yy / p)) % 2).astype(np.float32)
    weave = checker * warp + (1 - checker) * weft
    fibre = smooth_noise(H, W, 6, 3, seed=3)
    pile = smooth_noise(H, W, 120, 4, seed=4)
    height = 0.55 * weave + 0.3 * fibre + 0.15 * pile
    Image.fromarray(np.clip(height * 255, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "mat_weave.png"))

    c = np.asarray(col, np.float32) / 255.0
    g = np.asarray(gm, np.float32)[..., None] / 255.0
    shade = 0.86 + 0.14 * height[..., None] + 0.08 * (pile[..., None] - 0.5)
    c = c * (shade * (1 - g) + (0.92 + 0.12 * weave[..., None]) * g)
    Image.fromarray(np.clip(c * 255, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "mat_color.png"))
    gm.save(os.path.join(OUT, "mat_gold.png"))


# ---------------------------------------------------------------- walnut floor
def make_floor():
    # 2048 px covers 2.0 m x 2.0 m, tiles seamlessly in Blender (repeat).
    N = 2048
    plank_w = 0.14  # metres
    rows = int(round(2.0 / plank_w))
    pw = N / rows
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    row = np.floor(yy / pw).astype(int)
    out = np.zeros((N, N, 3), np.float32)
    rough = np.zeros((N, N), np.float32)
    base_cols = np.array([[0.36, 0.22, 0.13], [0.31, 0.19, 0.11], [0.40, 0.25, 0.15],
                          [0.28, 0.17, 0.10], [0.34, 0.21, 0.12]], np.float32)
    # grain noise stretched along the plank length (x) for straight walnut figure
    gn = smooth_noise(N, N // 16, 24, 4, seed=11)
    grain_n = np.asarray(Image.fromarray((gn * 255).astype(np.uint8)).resize((N, N), Image.BICUBIC), np.float32) / 255.0
    fine = smooth_noise(N, N, 4, 2, seed=12)
    plank_id = np.zeros((N, N), np.int32)
    seam = np.zeros((N, N), np.float32)
    for r in range(rows):
        sel = row == r
        # random plank lengths along x (tileable: cut positions mod N)
        offs = rng.uniform(0, N)
        length = rng.uniform(0.55, 0.9) * N
        xs = (xx[sel] - offs) % N
        pid = (xs // length).astype(int) + r * 10
        plank_id[sel] = pid
        edge = np.minimum(xs % length, length - (xs % length))
        seam[sel] = np.maximum(seam[sel], (edge < 2.0).astype(np.float32))
    yl = (yy % pw)
    seam = np.maximum(seam, ((yl < 1.5) | (yl > pw - 1.5)).astype(np.float32))
    ids = np.unique(plank_id)
    lut_col = {i: base_cols[rng.integers(0, len(base_cols))] * rng.uniform(0.9, 1.1) for i in ids}
    lut_ph = {i: rng.uniform(0, 100) for i in ids}
    colmap = np.zeros((N, N, 3), np.float32)
    phase = np.zeros((N, N), np.float32)
    for i in ids:
        s = plank_id == i
        colmap[s] = lut_col[i]
        phase[s] = lut_ph[i]
    # grain: stretched sine rings warped by noise
    g = np.sin((yy * 0.9 + grain_n * 22.0 + phase) * 1.1)
    g = 0.5 + 0.5 * g
    sk = smooth_noise(N, N // 16, 40, 3, seed=13)
    streak = np.asarray(Image.fromarray((sk * 255).astype(np.uint8)).resize((N, N), Image.BICUBIC), np.float32) / 255.0
    tone = 0.80 + 0.14 * g * (0.5 + 0.5 * streak) + 0.12 * (streak - 0.5) + 0.06 * (fine - 0.5)
    out = colmap * tone[..., None]
    out *= (1 - 0.55 * seam)[..., None]
    rough = 0.42 + 0.18 * (1 - g) + 0.2 * seam
    Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "floor_color.png"))
    Image.fromarray(np.clip(rough * 255, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "floor_rough.png"))


if __name__ == "__main__":
    make_mat()
    make_floor()
    print("textures written to", OUT)
