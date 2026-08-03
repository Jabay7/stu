# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate PWA icons with no image libraries -- writes PNGs byte by byte.

Art: dark tile, three ascending bars (the "first rung" motif).
Run:  uv run scripts/make_icons.py
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "icons"

BG = (11, 16, 32)          # #0B1020
BAR_DIM = (56, 189, 148)   # muted teal
BAR_MID = (74, 222, 160)
BAR_HOT = (125, 240, 168)  # brightest = top rung


def write_png(path: Path, size: int, pixels: list[list[tuple[int, int, int]]]) -> None:
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in pixels)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit truecolor
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def render(size: int) -> list[list[tuple[int, int, int]]]:
    """Three left-aligned bars, each shorter and dimmer as you go down."""
    # bar geometry as fractions of the canvas so every size looks identical
    bars = [
        (0.24, 0.62, BAR_HOT),   # (top, width) -- top rung, longest, brightest
        (0.44, 0.46, BAR_MID),
        (0.64, 0.30, BAR_DIM),
    ]
    height = 0.12
    left = 0.19
    radius = 0.5 * height * size

    grid = [[BG for _ in range(size)] for _ in range(size)]

    for top_f, width_f, color in bars:
        y0, y1 = top_f * size, (top_f + height) * size
        x0, x1 = left * size, (left + width_f) * size
        for y in range(int(y0), min(int(y1) + 1, size)):
            for x in range(int(x0), min(int(x1) + 1, size)):
                # round the bar caps
                cy = min(max(y + 0.5, y0 + radius), y1 - radius)
                cx = min(max(x + 0.5, x0 + radius), x1 - radius)
                dx, dy = (x + 0.5) - cx, (y + 0.5) - cy
                if dx * dx + dy * dy <= radius * radius + 0.5:
                    grid[y][x] = color
    return grid


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # 180 is what iOS uses for the home-screen icon; 192/512 are the PWA manifest sizes.
    for size, name in [(192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")]:
        write_png(OUT / name, size, render(size))
        print(f"wrote icons/{name}  ({size}x{size})")


if __name__ == "__main__":
    main()
