#!/usr/bin/env python3
"""Build a routing viewer and separate SVG from the current native KiCad board.

Run with KiCad's Python after scripts/export_previews.py.
Reads the production PCB and its existing routing SVG; never saves the board.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pcbnew as pcb

ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mm(value: int) -> float:
    return round(pcb.ToMM(value), 6)


def xy(point) -> list[float]:
    return [mm(point.x), mm(point.y)]


def build(output: Path) -> dict:
    source = ROOT / "ulva_controller.kicad_pcb"
    source_svg = ROOT / "preview/pcb-routing.svg"
    # Require the latest preview report to bind the plotted SVG to this PCB.
    manifest = ROOT / "build/preview-validation.json"
    preview = json.loads(manifest.read_text())
    guarded = dict(preview["sources_sha256"], **preview["artifacts_sha256"])
    assert "preview/pcb-routing.svg" in guarded
    baseline = {name: sha(ROOT / name) for name in guarded}
    mismatch = [name for name in guarded if baseline[name] != guarded[name]]
    if mismatch:
        raise RuntimeError(f"Current PCB / preview binding differs: {mismatch}")
    board_sha = sha(source)
    svg_sha = sha(source_svg)
    board = pcb.LoadBoard(str(source))
    nets = {
        code: {
            "id": code,
            "name": net.GetNetname(),
            "segments": [],
            "vias": [],
            "pads": [],
        }
        for code, net in board.GetNetInfo().NetsByNetcode().items()
        if code
    }
    segments, vias, pads = [], [], []
    for item in board.GetTracks():
        common = {"uuid": item.m_Uuid.AsString(), "net": item.GetNetCode()}
        if item.GetClass() == "PCB_VIA":
            entry = dict(
                common,
                kind="via",
                at=xy(item.GetPosition()),
                width=mm(item.GetWidth(pcb.F_Cu)),
                drill=mm(item.GetDrillValue()),
                layers=[
                    board.GetLayerName(n)
                    for n in (pcb.F_Cu, pcb.B_Cu)
                    if item.IsOnLayer(n)
                ],
            )
            vias.append(entry)
            nets[entry["net"]]["vias"].append(len(vias) - 1)
        elif item.GetClass() == "PCB_TRACK":
            entry = dict(
                common,
                kind="track",
                start=xy(item.GetStart()),
                end=xy(item.GetEnd()),
                width=mm(item.GetWidth()),
                length=mm(item.GetLength()),
                layers=[board.GetLayerName(item.GetLayer())],
            )
            segments.append(entry)
            nets[entry["net"]]["segments"].append(len(segments) - 1)
        else:
            raise RuntimeError(f"Unsupported track geometry: {item.GetClass()}")
    footprint_count = 0
    for footprint in board.GetFootprints():
        footprint_count += 1
        for pad in footprint.Pads():
            if not pad.GetNetCode():
                continue
            layers = [
                board.GetLayerName(n) for n in (pcb.F_Cu, pcb.B_Cu) if pad.IsOnLayer(n)
            ]
            if not layers:
                continue
            entry = {
                "uuid": pad.m_Uuid.AsString(),
                "net": pad.GetNetCode(),
                "kind": "pad",
                "ref": footprint.GetReference(),
                "number": pad.GetNumber(),
                "value": footprint.GetValue(),
                "at": xy(pad.GetPosition()),
                "size": xy(pad.GetSize()),
                "angle": pad.GetOrientationDegrees(),
                "shape": int(pad.GetShape()),
                "drill": xy(pad.GetDrillSize()),
                "round_radius": (
                    mm(pad.GetRoundRectCornerRadius())
                    if pad.GetShape() == pcb.PAD_SHAPE_ROUNDRECT
                    else 0
                ),
                "layers": layers,
            }
            # This viewer uses exact dimensions for the pad shapes present on ULVA.
            if pad.GetShape() not in (
                pcb.PAD_SHAPE_CIRCLE,
                pcb.PAD_SHAPE_RECT,
                pcb.PAD_SHAPE_OVAL,
                pcb.PAD_SHAPE_ROUNDRECT,
            ):
                raise RuntimeError(
                    f"Unsupported connected pad: {entry['ref']}.{entry['number']}"
                )
            pads.append(entry)
            nets[entry["net"]]["pads"].append(len(pads) - 1)
    for net in nets.values():
        net["length"] = round(sum(segments[i]["length"] for i in net["segments"]), 6)
        net["widths"] = sorted({segments[i]["width"] for i in net["segments"]})
        net["layers"] = sorted(
            {
                layer
                for group, items in (
                    ("segments", segments),
                    ("vias", vias),
                    ("pads", pads),
                )
                for i in net[group]
                for layer in items[i]["layers"]
            }
        )
        net["connections"] = sorted(
            {f"{pads[i]['ref']}.{pads[i]['number']}" for i in net["pads"]}
        )

    svg = ET.fromstring(source_svg.read_text())
    view_box = [float(n) for n in svg.attrib["viewBox"].split()]
    edge_box = board.GetBoardEdgesBoundingBox()
    offset = [mm(-edge_box.GetX()), mm(-edge_box.GetY())]
    # KiCad's existing fitted SVG is translated from the native PCB coordinates.
    # Spot-check the translation against an actual plated pad hole in the plot.
    circles = {
        (round(float(e.attrib["cx"]), 4), round(float(e.attrib["cy"]), 4))
        for e in svg.iter(f"{{{SVG_NS}}}circle")
    }
    drilled = [pad for pad in pads if max(pad["drill"]) > 0]
    assert drilled and all(
        (round(pad["at"][0] + offset[0], 4), round(pad["at"][1] + offset[1], 4))
        in circles
        for pad in drilled
    ), "SVG/native PCB origin mismatch"
    color_layers = {"#C83434": "F.Cu", "#4D7FC4": "B.Cu"}
    primitives = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}

    def annotate(element, inherited: dict) -> None:
        styles = dict(inherited)
        for prop in element.attrib.get("style", "").split(";"):
            if ":" in prop:
                key, value = prop.split(":", 1)
                styles[key.strip()] = value.strip()
        if element.tag.split("}")[-1] in primitives:
            colors = {
                styles.get("fill"),
                styles.get("stroke"),
                element.get("fill"),
                element.get("stroke"),
            }
            for color, layer in color_layers.items():
                if color in colors:
                    element.set("data-copper-layer", layer)
            if "#FFFFFF" in colors:
                element.set("data-hole", "true")
        for child in element:
            annotate(child, styles)

    annotate(svg, {})
    svg.set("id", "board")
    svg.set("width", "100%")
    svg.set("height", "100%")
    svg.set("role", "img")
    svg.set("aria-label", f"ULVA {board.GetTitleBlock().GetRevision()} routing map")
    highlight = ET.SubElement(
        svg,
        f"{{{SVG_NS}}}g",
        {
            "id": "highlight",
            "transform": f"translate({offset[0]} {offset[1]})",
            "pointer-events": "none",
        },
    )
    ET.SubElement(
        svg,
        f"{{{SVG_NS}}}g",
        {
            "id": "selection-marker",
            "transform": highlight.attrib["transform"],
            "pointer-events": "none",
        },
    )
    board_svg = ET.tostring(svg, encoding="unicode") + "\n"
    board_svg_sha = hashlib.sha256(board_svg.encode("utf-8")).hexdigest()
    data = {
        "revision": board.GetTitleBlock().GetRevision(),
        "source": source.name,
        "sha256": board_sha,
        "svg_sha256": svg_sha,
        "board_svg_sha256": board_svg_sha,
        "viewBox": view_box,
        "offset": offset,
        "footprints": footprint_count,
        "segments": segments,
        "vias": vias,
        "pads": pads,
        "nets": sorted(nets.values(), key=lambda net: net["name"].casefold()),
    }
    template = (
        (ROOT / "scripts/routing_viewer.html")
        .read_text()
        .replace("__REVISION__", data["revision"])
    )
    assert preview["revision"] == data["revision"]
    assert template.count("__BOARD_DATA__") == 1 and "__BOARD_SVG__" not in template
    html = template.replace(
        "__BOARD_DATA__",
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
            "<", "\\u003c"
        ),
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(html)
    (output / "board.svg").write_text(board_svg, encoding="utf-8")
    (output / "board-data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    after = {name: sha(ROOT / name) for name in guarded}
    assert baseline == after and sha(source) == board_sha and sha(source_svg) == svg_sha
    validation = {
        "source_sha256": board_sha,
        "svg_sha256": svg_sha,
        "pcb_and_preview_files_unchanged": len(guarded),
        "revision": data["revision"],
        "counts": {
            "footprints": footprint_count,
            "segments": len(segments),
            "vias": len(vias),
            "nets": len(nets),
            "pads": len(pads),
        },
        "total_track_length_mm": round(sum(t["length"] for t in segments), 6),
        "svg_origin_spot_checks": len(drilled),
        "connected_pad_shapes": dict(Counter(pad["shape"] for pad in pads)),
        "viewer_sha256": sha(output / "index.html"),
        "board_svg_sha256": sha(output / "board.svg"),
    }
    (output / "extraction-validation.json").write_text(
        json.dumps(validation, indent=2) + "\n"
    )
    return validation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/routing-viewer")
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    # Avoid a KiCad SWIG shutdown crash; the native board was never mutated.
    os._exit(0)
