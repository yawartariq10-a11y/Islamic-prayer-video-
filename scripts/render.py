"""Render frames from blender/five_daily_prayers.blend.

    python scripts/render.py                          # full animation -> out/frames/
    python scripts/render.py --frames 1 120 300       # specific stills -> out/stills/
    python scripts/render.py --start 1 --end 400      # a frame range (resumable)
    python scripts/render.py --times 5.0 12.3          # stills at times in seconds
Options: --scale 50 (resolution %), --samples 16, --outdir PATH
Existing frames are skipped so an interrupted render can be resumed.
"""
import argparse
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BLEND = os.path.join(ROOT, "blender", "five_daily_prayers.blend")

ap = argparse.ArgumentParser()
ap.add_argument("--frames", type=int, nargs="*")
ap.add_argument("--times", type=float, nargs="*")
ap.add_argument("--start", type=int)
ap.add_argument("--end", type=int)
ap.add_argument("--step", type=int, default=1)
ap.add_argument("--scale", type=int, default=100)
ap.add_argument("--samples", type=int)
ap.add_argument("--outdir")
ap.add_argument("--overwrite", action="store_true")
args = ap.parse_args(sys.argv[1:])

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
sc.render.resolution_percentage = args.scale
if args.samples:
    sc.eevee.taa_render_samples = args.samples

still = args.frames is not None or args.times is not None
frames = list(args.frames or [])
if args.times:
    frames += [int(round(t * sc.render.fps)) + 1 for t in args.times]
if not still:
    frames = list(range(args.start or sc.frame_start, (args.end or sc.frame_end) + 1, args.step))
outdir = args.outdir or os.path.join(ROOT, "out", "stills" if still else "frames")
os.makedirs(outdir, exist_ok=True)

t_all = time.time()
for i, f in enumerate(frames):
    path = os.path.join(outdir, f"{f:04d}.png")
    if os.path.exists(path) and not args.overwrite:
        continue
    t = time.time()
    sc.frame_set(f)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"[render] frame {f} ({i + 1}/{len(frames)}) {time.time() - t:.1f}s", flush=True)
print(f"[render] done {len(frames)} frames in {time.time() - t_all:.0f}s", flush=True)
