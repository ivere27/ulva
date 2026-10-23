#!/usr/bin/env python3
"""Independent ZIP/drill re-import and bare-board previews (gerbonara 1.5).
Run in a Python environment with gerbonara installed after export_pcb.py.
"""
from pathlib import Path
import hashlib, json, math, warnings, re, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build/preview-python"))
from gerbonara import LayerStack
from gerbonara.graphic_objects import Flash, Line
from gerbonara.utils import MM

board = (ROOT / "ulva_controller.kicad_pcb").read_text()
revision = re.search(r"\(rev \"([^\"]+)\"\)", board).group(1)
release_date = re.search(r"\(date \"([^\"]+)\"\)", board).group(1)
source = (
    ROOT / f"build/manufacturing-{revision}/ulva-{revision}-{release_date}-gerbers.zip"
)
checks = json.loads((ROOT / "build/pcb-checks.json").read_text())
with warnings.catch_warnings(record=True) as notices:
    warnings.simplefilter("always")
    b = LayerStack.open(source)
    expected = {
        ("top", "copper"),
        ("bottom", "copper"),
        ("top", "mask"),
        ("bottom", "mask"),
        ("top", "silk"),
        ("bottom", "silk"),
        ("mechanical", "outline"),
    }
    assert set(b.graphic_layers) == expected
    (x0, y0), (x1, y1) = b.board_bounds()
    assert all(
        abs(a - z) < 0.001
        for a, z in zip([x0, y0, x1, y1], [-0.025, -0.025, 100.025, 100.025])
    )
    assert (
        len(b.drill_pth.objects) == checks["plated_drills"]
        and len(b.drill_npth.objects) == checks["nonplated_drills"] == 8
    )
    holes = [o for o in b.drill_npth.objects if isinstance(o, Flash)]
    slots = [o for o in b.drill_npth.objects if isinstance(o, Line)]
    assert len(holes) == len(slots) == 4
    assert {(o.x, o.y) for o in holes} == {(4, 4), (4, 96), (96, 4), (96, 96)}
    assert all(abs(o.aperture.diameter - 3.2) < 1e-6 for o in holes)
    assert {((o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2) for o in slots} == {
        (13, 97),
        (37, 97),
        (13, 73),
        (37, 73),
    }
    assert all(
        abs(math.hypot(o.x2 - o.x1, o.y2 - o.y1) + o.aperture.diameter - 4) < 1e-6
        and abs(o.aperture.diameter - 2.7) < 1e-6
        for o in slots
    )
    assert (
        sum(abs(o.x2 - o.x1) > 0.1 for o in slots) == 2
        and sum(abs(o.y2 - o.y1) > 0.1 for o in slots) == 2
    )
    report = {
        "result": "PASS",
        "tool": "gerbonara 1.5",
        "zip_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "board_outline_mm": [100, 100],
        "gerber_layers": 7,
        "plated_drills": len(b.drill_pth.objects),
        "npth_round_holes": 4,
        "npth_slots": 4,
        "coordinate_origin": "lower left; confirmed by asymmetric OLED slots",
        "parser_notices": sorted({str(w.message) for w in notices}),
    }
(ROOT / "build/gerber-verification.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
print(json.dumps({k: v for k, v in report.items() if k != "parser_notices"}))
