"""Tile rendered stills into one contact sheet with TikTok/Reels safe-zone guides.

    python scripts/contact_sheet.py out/stills out/contact_sheet.png [--guides]
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

src, dst = sys.argv[1], sys.argv[2]
guides = "--guides" in sys.argv
files = sorted(glob.glob(os.path.join(src, "*.png")))
thumb_w = 270
ims = []
for f in files:
    im = Image.open(f).convert("RGB")
    s = thumb_w / im.width
    im = im.resize((thumb_w, int(im.height * s)), Image.LANCZOS)
    if guides:
        d = ImageDraw.Draw(im, "RGBA")
        # approximate platform UI zones: bottom ~20%, right ~12%, top ~7%
        W, H = im.size
        d.rectangle([0, int(H * 0.80), W, H], fill=(255, 0, 0, 50))
        d.rectangle([int(W * 0.88), 0, W, H], fill=(255, 0, 0, 50))
        d.rectangle([0, 0, W, int(H * 0.07)], fill=(255, 0, 0, 35))
    d = ImageDraw.Draw(im)
    d.text((6, 6), os.path.basename(f), fill=(255, 255, 0))
    ims.append(im)
cols = min(5, len(ims))
rows = (len(ims) + cols - 1) // cols
h = ims[0].height
sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * 6, rows * h + (rows + 1) * 6), (30, 30, 30))
for i, im in enumerate(ims):
    sheet.paste(im, (6 + (i % cols) * (thumb_w + 6), 6 + (i // cols) * (h + 6)))
sheet.save(dst)
print("wrote", dst, sheet.size)
