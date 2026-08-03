# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Collect the shippable web assets into www/ for Capacitor to wrap.

The repo root doubles as the GitHub Pages site, so it also holds scripts/,
.github/ and the node modules -- none of which belong inside an app binary.
This copies only what the app actually loads.

Run:  uv run scripts/build_www.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WWW = ROOT / "www"

FILES = [
    "index.html", "styles.css", "app.js", "syllabus.js",
    "sw.js", "manifest.webmanifest",
]
DIRS = ["icons", "data"]


def main() -> None:
    if WWW.exists():
        shutil.rmtree(WWW)
    WWW.mkdir(parents=True)

    missing = []
    for name in FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, WWW / name)
        else:
            missing.append(name)

    for name in DIRS:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, WWW / name)
        else:
            missing.append(name + "/")

    if missing:
        raise SystemExit(f"missing web assets: {', '.join(missing)}")

    total = sum(f.stat().st_size for f in WWW.rglob("*") if f.is_file())
    count = sum(1 for f in WWW.rglob("*") if f.is_file())
    print(f"www/ built: {count} files, {total / 1024:.0f} KB")


if __name__ == "__main__":
    main()
