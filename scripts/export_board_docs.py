#!/usr/bin/env python3
"""Refresh the board images and routing viewer assets included in the repository.

Requires the same KiCad and rendering tools as export_previews.py.
Use --reuse-previews to publish existing previews after checking their hashes.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
IMAGES = (
    "pcb-fabricated-top.png",
    "pcb-fabricated-bottom.png",
    "pcb-routing.png",
    "pcb-placement.png",
)


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-previews",
        action="store_true",
        help="Use existing preview/ images if they still match the current PCB",
    )
    args = parser.parse_args()
    if not args.reuse_previews:
        run(sys.executable, ROOT / "scripts/export_previews.py")

    manifest = ROOT / "build/preview-validation.json"
    if not manifest.is_file():
        parser.error("No previews found; run without --reuse-previews first.")
    preview = json.loads(manifest.read_text())
    hashes = dict(preview["sources_sha256"], **preview["artifacts_sha256"])
    for relative, expected in hashes.items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            parser.error(
                f"Stale or missing preview input: {relative}. "
                "Run without --reuse-previews to regenerate."
            )

    if importlib.util.find_spec("pcbnew"):
        run(sys.executable, ROOT / "scripts/export_routing_viewer.py")
    else:
        run(
            "docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{ROOT}:/work", "-w", "/work", "kicad/kicad:9.0.9",
            "python3", "scripts/export_routing_viewer.py",
        )

    # The viewer's metadata and separate SVG are bound to the same preview.
    # Publish both viewer assets and only the selected documentation images.
    images = ROOT / "docs/images"
    viewer = ROOT / "docs/routing"
    images.mkdir(parents=True, exist_ok=True)
    viewer.mkdir(parents=True, exist_ok=True)
    for filename in IMAGES:
        shutil.copyfile(ROOT / "preview" / filename, images / filename)
    for filename in ("index.html", "board.svg"):
        shutil.copyfile(ROOT / "build/routing-viewer" / filename, viewer / filename)
    print(json.dumps({
        "revision": preview["revision"],
        "images": [f"docs/images/{name}" for name in IMAGES],
        "viewer": "docs/routing/index.html",
        "board_svg": "docs/routing/board.svg",
    }, indent=2))


if __name__ == "__main__":
    main()
