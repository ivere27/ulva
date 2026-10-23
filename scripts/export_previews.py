#!/usr/bin/env python3
"""Refresh PCB SVG/PNG previews from the current board, including unrouted work.

Run with Python 3, gerbonara 1.5.0 and resvg-py 0.2.6. Dependencies may be
installed in build/preview-python. KiCad 9 runs locally or in the pinned Docker
image. Temporary Gerbers are only rendering inputs; no fabrication ZIP, BOM,
CPL, design validation report, or authoritative KiCad file is overwritten.
"""
import argparse
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import warnings

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "kicad/kicad:9.0.9"
BOARD_FILES = [
    ROOT / f"ulva_controller.{suffix}"
    for suffix in ["kicad_pcb", "kicad_pro", "kicad_dru"]
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def native_plot(staging):
    import pcbnew as p

    snapshot = staging / "board"
    snapshot.mkdir()
    for source in BOARD_FILES:
        shutil.copyfile(source, snapshot / source.name)
    board = snapshot / "ulva_controller.kicad_pcb"
    b = p.LoadBoard(str(board))
    details = {
        "revision": b.GetTitleBlock().GetRevision(),
        "kicad_version": subprocess.check_output(
            ["kicad-cli", "version"], text=True
        ).strip(),
        "components": len(list(b.GetFootprints())),
        "plated_drills": sum(
            pad.GetAttribute() == p.PAD_ATTRIB_PTH and pad.GetDrillSize().x > 0
            for f in b.GetFootprints()
            for pad in f.Pads()
        )
        + sum(isinstance(t, p.PCB_VIA) for t in b.GetTracks()),
        "nonplated_drills": sum(
            pad.GetAttribute() == p.PAD_ATTRIB_NPTH and pad.GetDrillSize().x > 0
            for f in b.GetFootprints()
            for pad in f.Pads()
        ),
    }
    (staging / "board-details.json").write_text(json.dumps(details, indent=2) + "\n")
    views = {
        "pcb-assembly": "F.Fab,F.Silkscreen,Edge.Cuts,Dwgs.User",
        "pcb-under-modules": "F.Fab,F.Silkscreen,Edge.Cuts",
        "pcb-top": "F.Cu,F.Silkscreen,Edge.Cuts",
        "pcb-bottom": "B.Cu,B.Silkscreen,Edge.Cuts",
        "pcb-placement": "F.Fab,F.CrtYd,F.Silkscreen,Edge.Cuts,Dwgs.User",
    }
    for name, layers in views.items():
        extra = ["--black-and-white"] if name == "pcb-placement" else []
        run(
            "kicad-cli",
            "pcb",
            "export",
            "svg",
            "--layers",
            layers,
            "--mode-single",
            "--fit-page-to-board",
            "--exclude-drawing-sheet",
            "--sketch-pads-on-fab-layers",
            *extra,
            "-o",
            staging / f"{name}.svg",
            board,
        )

    gerbers = staging / "gerbers"
    gerbers.mkdir()
    run(
        "kicad-cli",
        "pcb",
        "export",
        "gerbers",
        "--layers",
        "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
        "--use-drill-file-origin",
        "--subtract-soldermask",
        "-o",
        str(gerbers) + "/",
        board,
    )
    run(
        "kicad-cli",
        "pcb",
        "export",
        "drill",
        "--format",
        "excellon",
        "--excellon-units",
        "mm",
        "--excellon-separate-th",
        "--excellon-oval-format",
        "route",
        "--drill-origin",
        "plot",
        "-o",
        str(gerbers) + "/",
        board,
    )

    # Only the disposable routing drawing omits pours and rule areas.
    # Keep references alive while detaching zones (pcbnew SWIG ownership).
    removed = []
    for zone in list(b.Zones()):
        if zone.GetIsRuleArea() or zone.GetNetname() == "GND":
            removed.append(zone)
            b.Remove(zone)
    p.SaveBoard(str(board), b)
    routing = staging / "pcb-routing.svg"
    run(
        "kicad-cli",
        "pcb",
        "export",
        "svg",
        "--layers",
        "F.Cu,B.Cu,F.Silkscreen,Edge.Cuts",
        "--mode-single",
        "--fit-page-to-board",
        "--exclude-drawing-sheet",
        "-o",
        routing,
        board,
    )
    routing.write_text(
        re.sub(
            r"(<svg\b[^>]*>)",
            r'\1\n<rect x="0" y="0" width="100%" height="100%" fill="#202020"/>',
            routing.read_text(),
            count=1,
            flags=re.S,
        )
    )


def export_previews(width):
    dependency_dir = ROOT / "build/preview-python"
    if dependency_dir.is_dir():
        sys.path.insert(0, str(dependency_dir))
    try:
        from gerbonara import LayerStack
        import resvg_py
    except ImportError as exc:
        raise SystemExit(
            "Install preview dependencies: python3 -m pip install "
            "--target build/preview-python gerbonara==1.5.0 "
            "resvg-py==0.2.6"
        ) from exc

    sources = {str(path.relative_to(ROOT)): sha(path) for path in BOARD_FILES}
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="preview-render-", dir=build) as td:
        staging = Path(td)
        if shutil.which("kicad-cli") and importlib.util.find_spec("pcbnew"):
            run(sys.executable, __file__, "--native-stage", staging)
        else:
            run(
                "docker",
                "run",
                "--rm",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{ROOT}:/work",
                "-w",
                "/work",
                IMAGE,
                "python3",
                "scripts/export_previews.py",
                "--native-stage",
                Path("/work") / staging.relative_to(ROOT),
            )

        details = json.loads((staging / "board-details.json").read_text())
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always")
            stack = LayerStack.open(staging / "gerbers")
            expected_layers = {
                (side, layer)
                for side in ["top", "bottom"]
                for layer in ["copper", "mask", "silk"]
            }
            expected_layers.add(("mechanical", "outline"))
            assert set(stack.graphic_layers) == expected_layers
            assert len(stack.drill_pth.objects) == details["plated_drills"]
            assert len(stack.drill_npth.objects) == details["nonplated_drills"]
            for side in ["top", "bottom"]:
                svg = str(stack.to_pretty_svg(side=side, margin=2))
                (staging / f"pcb-fabricated-{side}.svg").write_text(svg)

        png_sizes = {}
        for svg in sorted(staging.glob("pcb-*.svg")):
            # resvg handles Gerbonara's filter/mask composition as well as
            # KiCad's native SVG, so copper, solder mask and drill colors agree.
            png = resvg_py.svg_to_bytes(
                svg_path=str(svg),
                width=width,
                dpi=96,
                background="white",
                resources_dir=str(staging),
            )
            assert png[:8] == b"\x89PNG\r\n\x1a\n"
            dimensions = struct.unpack(">II", png[16:24])
            assert dimensions[0] == width and dimensions[1] > 0
            svg.with_suffix(".png").write_bytes(png)
            png_sizes[svg.with_suffix(".png").name] = dimensions

        assert sources == {
            str(path.relative_to(ROOT)): sha(path) for path in BOARD_FILES
        }, "KiCad sources changed while rendering; previews were not published."
        artifacts = sorted([*staging.glob("pcb-*.svg"), *staging.glob("pcb-*.png")])
        assert len(artifacts) == 16
        preview = ROOT / "preview"
        preview.mkdir(exist_ok=True)
        for artifact in artifacts:
            os.replace(artifact, preview / artifact.name)
        report = {
            "generated_at_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "scope": "Current PCB preview rendering only; unfinished routing is shown as-is.",
            **details,
            "sources_sha256": sources,
            "source_files_unchanged": True,
            "fabrication_package_updated": False,
            "renderers": {
                name: importlib.metadata.version(name)
                for name in ["gerbonara", "resvg-py"]
            },
            "png_sizes_px": png_sizes,
            "artifacts_sha256": {
                f"preview/{p.name}": sha(preview / p.name) for p in artifacts
            },
            "parser_notices": sorted({str(w.message) for w in notices}),
        }
        (build / "preview-validation.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    "revision": details["revision"],
                    "preview_files": len(artifacts),
                    "source_files_unchanged": True,
                    "preview_directory": str(preview),
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-stage", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--width", type=int, default=1600, help="PNG width in pixels")
    args = parser.parse_args()
    if args.native_stage:
        native_plot(args.native_stage)
    else:
        if args.width <= 0:
            parser.error("--width must be positive")
        export_previews(args.width)
