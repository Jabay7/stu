# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Render the social preview card shown when the link is shared.

The only script here with a dependency -- it's build-time only, never shipped to
the browser. Run it again if the tagline or company count changes.

Run:  uv run scripts/make_og.py
Out:  og-image.png (1200x630)
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1200, 630

BG = (11, 16, 32)
TEXT = (232, 237, 247)
MUTED = (138, 151, 180)
BAR_HOT = (125, 240, 168)
BAR_MID = (74, 222, 160)
BAR_DIM = (56, 189, 148)


# Has to work on Windows locally and on Ubuntu in CI, so try both families
# before giving up. Pillow's default face is a bitmap that ignores `size`, which
# silently renders the whole card at ~11px -- worth avoiding.
FONTS = {
    True: ["DejaVuSans-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    False: ["DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"],
}


def font(size: int, bold: bool = False):
    for candidate in FONTS[bold]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    raise SystemExit("no scalable font found -- install DejaVu or run on Windows")


def main() -> None:
    meta_path = ROOT / "data" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    employers = meta.get("employers_ok", meta.get("companies_ok", 0))
    total = meta.get("total", 0)
    majors = sum(1 for m in meta.get("majors", []) if m.get("count"))

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Faint accent wash in the lower right so the card isn't a flat rectangle.
    # Blurred, or the ellipse reads as a hard-edged shape rather than a glow.
    glow = Image.new("RGB", (W, H), BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 560, H - 430, W + 260, H + 300], fill=(18, 48, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    img = Image.blend(img, glow, 0.75)
    d = ImageDraw.Draw(img)

    # The mark: three ascending rungs.
    x, y, h, gap = 90, 150, 26, 22
    for width, color in ((250, BAR_HOT), (185, BAR_MID), (120, BAR_DIM)):
        d.rounded_rectangle([x, y, x + width, y + h], radius=h // 2, fill=color)
        y += h + gap

    d.text((90, 330), "STU", font=font(112, bold=True), fill=TEXT)
    d.text((92, 462), "Entry-level jobs for every major", font=font(40), fill=TEXT)

    sub = f"{total} roles  ·  {employers} employers  ·  {majors} majors  ·  refreshed nightly"
    d.text((92, 528), sub, font=font(26), fill=MUTED)

    out = ROOT / "og-image.png"
    img.save(out, "PNG", optimize=True)
    print(f"wrote {out.name} ({W}x{H}) — {total} roles, {employers} employers, {majors} majors")


if __name__ == "__main__":
    main()
