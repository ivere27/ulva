#!/usr/bin/env python3
"""Validate PCB connectivity, module clearance and current-carrying paths."""
import json, math, re, xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
b = p.LoadBoard(str(ROOT / "ulva_controller.kicad_pcb"))
r = ET.parse(ROOT / "build/controller.xml").getroot()
fps = {f.GetReference(): f for f in b.GetFootprints()}
checks = []


def require(ok, description):
    if not ok:
        raise AssertionError(description)
    checks.append(description)


def xy(q):
    return (p.ToMM(q.x), p.ToMM(q.y))


def distance(a, z):
    return math.hypot(a[0] - z[0], a[1] - z[1])


def pad(ref, pin):
    return fps[ref].FindPadByNumber(str(pin))


def at(ref, pin=None):
    return xy(
        pad(ref, pin).GetPosition() if pin is not None else fps[ref].GetPosition()
    )


require(
    set(fps) == {c.get("ref") for c in r.findall("./components/comp")},
    "Exact schematic/PCB reference inventory",
)
expected = {}
for net in r.findall("./nets/net"):
    name = net.get("name")
    name = name.replace("/", "{slash}") if name.startswith("unconnected-") else name
    for node in net.findall("node"):
        expected[node.get("ref"), node.get("pin")] = name
for ref, f in fps.items():
    for q in f.Pads():
        if q.GetNumber():
            require(
                q.GetNetname() == expected[ref, q.GetNumber()],
                f"{ref}.{q.GetNumber()} net matches XML",
            )
require(b.GetCopperLayerCount() == 2, "Two copper layers")
require(
    b.GetDesignSettings().GetBoardThickness() == p.FromMM(1.6), "FR4 thickness 1.6 mm"
)
box = b.GetBoardEdgesBoundingBox()
require(
    abs(p.ToMM(box.GetWidth()) - 100) < 0.1
    and abs(p.ToMM(box.GetHeight()) - 100) < 0.1,
    "100 x 100 mm board",
)
revision = b.GetTitleBlock().GetRevision()
require(
    bool(revision) and revision == r.findtext("./design/sheet/title_block/rev"),
    "Schematic and PCB revisions match",
)
require(
    abs(at("J7")[0] - at("J6")[0] - 22.86) < 0.001,
    "DevKit header spacing 22.86 mm; J6 left, J7 right",
)
require(
    all(
        abs(fps[ref].GetOrientationDegrees() % 360 - 0) < 0.001 for ref in ["J6", "J7"]
    ),
    "Both DevKit sockets at 0 degrees",
)
require(
    at("J6", 1)[1] < at("J6", 16)[1] and at("J7", 1)[1] < at("J7", 16)[1],
    "Both pin1 ends face the upper antenna",
)
require(
    {ref for ref in fps if ref.startswith("TP")} == {"TP2"}, "Single GND test point"
)
require(
    {ref for ref in fps if re.fullmatch(r"J\d+", ref)}
    == {f"J{i}" for i in range(1, 28)},
    "All 27 connectors present",
)
require(
    not {"C2", "F1", "R7", "R9", "R10"} & set(fps),
    "No unsupported SW-I2C or third DIP components",
)
for ref, pin in [
    ("J6", "2"),
    ("J6", "16"),
    ("J5", "2"),
    ("J5", "3"),
    ("J7", "2"),
    ("J7", "3"),
    ("J7", "7"),
    ("J7", "6"),
    ("J7", "10"),
    ("J7", "11"),
    ("J7", "13"),
    ("J7", "14"),
    ("J7", "16"),
    ("D2", "2"),
]:
    q = pad(ref, pin)
    require(
        q.GetNetname().startswith("unconnected-")
        and not any(t.GetNetCode() == q.GetNetCode() for t in b.GetTracks()),
        f"{ref}.{pin}: reserved/unused pad has no carrier copper",
    )
for n in [
    "CFG0_N",
    "CFG1_N",
    "CFG2_N",
    "SW_I2C_SDA",
    "SW_I2C_SCL",
    "PROBE_3V3",
    "UI_BUZZER",
    "UI_RGB_BUZZ",
    "UI_UP_N",
    "UI_OK_N",
    "UI_DOWN_N",
]:
    require(
        not any(t.GetNetname() == n for t in b.GetTracks()),
        n + ": unsupported copper absent",
    )
require(
    fps["J5"].GetFPID().GetLibItemName() == "PinHeader_1x04_P2.54mm_Vertical",
    "Four-position male passive-piezo header",
)
require(
    fps["R26"].GetValue() == "1k" and distance(at("R26", 1), at("J7", 8)) < 5,
    "Piezo series input within 5 mm of dedicated GPIO4; RGB27 has no carrier trace",
)
require(
    fps["SW1"].GetFPID().GetLibItemName()
    == "SW_DIP_SPSTx02_Slide_9.78x7.26mm_W7.62mm_P2.54mm",
    "Two-pole DIP footprint",
)
require(
    distance(at("SW1"), (49.19, 81.73)) < 0.001
    and fps["SW1"].GetOrientationDegrees() % 360 == 0,
    "DIP centered immediately above AC0/DC0, signal pins face the left ADC network",
)
require(at("SW1", 1)[1] < at("SW1", 2)[1], "DIP switch 1 is above switch 2")


def footprint_layer_bounds(ref, layer):
    boxes = [
        item.GetBoundingBox() for item in fps[ref].GraphicalItems()
        if isinstance(item, p.PCB_SHAPE) and item.GetLayer() == layer
    ]
    require(bool(boxes), ref + ": body/courtyard geometry is present")
    return (
        min(p.ToMM(box.GetLeft()) for box in boxes),
        min(p.ToMM(box.GetTop()) for box in boxes),
        max(p.ToMM(box.GetRight()) for box in boxes),
        max(p.ToMM(box.GetBottom()) for box in boxes),
    )


def bounds_gap(a, z):
    return math.hypot(max(0, a[0] - z[2], z[0] - a[2]),
                      max(0, a[1] - z[3], z[1] - a[3]))


sw1_body = footprint_layer_bounds("SW1", p.F_Fab)
sw1_courtyard = footprint_layer_bounds("SW1", p.F_CrtYd)
require(
    distance(((sw1_body[0] + sw1_body[2]) / 2, (sw1_body[1] + sw1_body[3]) / 2), (53, 83)) < 0.001,
    "DIP body center is (53,83) mm in the chosen lower-center USB plan area",
)
for ref in ["J8", "J10"]:
    require(
        bounds_gap(sw1_body, footprint_layer_bounds(ref, p.F_Fab)) > 0,
        "SW1 body does not overlap " + ref + " body",
    )
    require(
        bounds_gap(sw1_courtyard, footprint_layer_bounds(ref, p.F_CrtYd)) >= 1,
        "SW1 courtyard has at least 1 mm clearance to " + ref,
    )
for rr, number in [("R5", 1), ("R6", 2)]:
    require(
        fps[rr].GetValue() == "1k"
        and pad(rr, 1).GetNetname() == "3V3"
        and pad(rr, 2).GetNetname() == pad("SW1", number).GetNetname() == f"CFG_SW{number}_N",
        rr + ": retained 1k pullup connects 3V3 to its relocated switch input",
    )
    require(
        distance(at(rr, 2), at("SW1", number)) < 5,
        rr + ": pullup is within 5 mm of its SW1 signal pad",
    )
require(
    all(at(ref)[0] < 9 and at(ref)[1] < 25 for ref in ["J4", "AE1", "R11"]),
    "RF433 socket, antenna pad and series resistor grouped at the upper left",
)
require(
    distance(at("J3"), (21, 2.5)) < 0.001
    and fps["J3"].GetOrientationDegrees() % 360 == 90,
    "OLED header aligned at y2.5 with piezo, RTC and DHT20; module and slots translated together",
)
require(
    distance(at("J5"), (45, 2.5)) < 0.001
    and fps["J5"].GetOrientationDegrees() % 360 == 90,
    "Piezo header at top edge right of OLED and above buttons",
)
for ref, origin, last in [("J2", (62, 2.5), "5"), ("J1", (81, 2.5), "4")]:
    require(
        distance(at(ref), origin) < 0.001
        and fps[ref].GetOrientationDegrees() % 360 == 90,
        ref + ": horizontal socket on the upper row, right of piezo",
    )
    require(
        at(ref, 1)[0] < at(ref, last)[0]
        and abs(at(ref, 1)[1] - at(ref, last)[1]) < 0.001,
        ref + ": pin numbering runs left to right",
    )
require(
    distance(at("C1", 1), at("J1", 1)) < 4 and fps["C1"].GetValue() == "100nF",
    "DHT20 100 nF bypass remains within 4 mm of its VDD socket pin",
)
require(
    distance(at("J4"), (4, 14.5)) < 0.001
    and fps["J4"].GetOrientationDegrees() % 360 == 0,
    "J4 vertical socket at left upper edge, pin order verified",
)
require(
    distance(at("AE1"), (4, 9)) < 0.001
    and abs(distance(at("AE1"), at("J4", 1)) - 5.5) < 0.001
    and distance(at("R11", 1), at("J4", 3)) < 4,
    "RF433 antenna pad 5.5 mm above first pin; data resistor local to socket",
)
for ref, val in [
    ("R5", "1k"),
    ("R6", "1k"),
    ("R27", "10k"),
    ("R28", "20k"),
    ("C12", "100nF"),
]:
    require(fps[ref].GetValue() == val, ref + ": weighted ADC value")
require(
    distance(at("C12", 1), at("J6", 7)) < 10,
    "ADC filter capacitor within 10 mm of GPIO6",
)
for ref in ["R27", "R28"]:
    require(
        distance(at(ref), at("J6", 7)) < 15, ref + ": ADC mixing resistor local to MCU"
    )
    bounds = footprint_layer_bounds(ref, p.F_CrtYd)
    require(
        fps[ref].GetLayer() == p.F_Cu
        and at("J6")[0] < bounds[0] < bounds[2] < at("J7")[0]
        and 46.5 < bounds[1] < bounds[3] < 85.1,
        ref + ": courtyard lies beneath the raised DevKit, between headers and below the antenna keepout",
    )
for ref, val in [("R12", "10k"), ("R13", "4.7k"), ("R14", "10k"), ("C15", "100nF")]:
    require(fps[ref].GetValue() == val, ref + ": button ADC ladder value")
require(
    distance(at("C15", 1), at("J6", 6)) < 5, "Button ADC filter within 5 mm of GPIO1"
)
for ref, val in [
    ("R31", "150k"),
    ("R32", "10k"),
    ("R33", "1k"),
    ("C16", "100nF"),
    ("D7", "BAT54S"),
]:
    require(
        fps[ref].GetValue() == val and fps[ref].GetLayer() == p.F_Cu,
        ref + ": 24V monitor part on top assembly layer",
    )
require(
    pad("J7", 9).GetNetname() == "VIN24_ADC" and pad("J7", 9).GetPinType() == "input",
    "GPIO5 is connected and configured as an ADC input",
)
require(
    distance(at("C16", 1), at("J7", 9)) < 5,
    "24V ADC storage/filter capacitor within 5 mm of GPIO5",
)
require(
    distance(at("D7", 3), at("J7", 9)) < 6,
    "24V ADC BAT54S junction within 6 mm of GPIO5",
)
require(
    {q.GetNumber(): q.GetNetname() for q in fps["D7"].Pads()}
    == {"1": "GND", "2": "3V3", "3": "VIN24_ADC"},
    "HJC BAT54S physical pads: anode1 GND, junction3 ADC, cathode2 3V3",
)
ground_vias = [
    t for t in b.GetTracks() if isinstance(t, p.PCB_VIA) and t.GetNetname() == "GND"
]
for ref, pin in [("R32", 2), ("C16", 2), ("D7", 1)]:
    require(
        any(distance(at(ref, pin), xy(t.GetPosition())) < 2 for t in ground_vias),
        ref + ": local ground via within 2 mm of monitor return pad",
    )
for rr, sw in [("R12", "SW2"), ("R13", "SW3"), ("R14", "SW4")]:
    require(
        at(rr)[0] == at(sw)[0]
        and at(rr)[1] == 9
        and fps[rr].GetOrientationDegrees() % 360 == 0,
        rr + ": ladder resistor aligned above its button in a single row",
    )
rf = [z for z in b.Zones() if z.GetZoneName().startswith("ESP32 antenna")]
require(
    len(rf) == 1
    and rf[0].GetIsRuleArea()
    and all(rf[0].GetLayerSet().Contains(l) for l in [p.F_Cu, p.B_Cu])
    and all(
        [
            rf[0].GetDoNotAllowTracks(),
            rf[0].GetDoNotAllowVias(),
            rf[0].GetDoNotAllowPads(),
            rf[0].GetDoNotAllowCopperPour(),
        ]
    ),
    "Antenna copper/tracks/pads/vias keepout enforced on both layers",
)
require(
    [xy(q) for q in rf[0].Outline().COutline(0).CPoints()]
    == [
        (40, 21),
        (66, 21),
        (66, 31.5),
        (63, 31.5),
        (63, 46.5),
        (44, 46.5),
        (44, 31.5),
        (40, 31.5),
    ],
    "Antenna upper keepout x40..66: 4 mm on both sides of x44..62 reference",
)
require(
    {
        z.GetLayer()
        for z in b.Zones()
        if not z.GetIsRuleArea() and z.GetNetname() == "GND"
    }
    == {p.F_Cu, p.B_Cu},
    "GND pours on both layers",
)
outline = []
for item in b.GetDrawings():
    if isinstance(item, p.PCB_SHAPE) and item.GetLayer() == p.Dwgs_User:
        outline.append(
            {
                tuple(round(v, 3) for v in xy(q))
                for q in (item.GetStart(), item.GetEnd())
            }
        )
for a, z, label in [
    ((40.3, 85.1), (65.7, 85.1), "USB edge"),
    ((40.3, 31.5), (65.7, 31.5), "DevKit antenna edge"),
    ((44, 25), (62, 25), "Central prototype antenna outline"),
    ((11, 1), (39, 1), "OLED body 1 mm below top edge"),
    ((40.5, 85.1), (65.5, 85.1), "USB envelope; low components allowed"),
]:
    require({a, z} in outline, label + ": mechanical envelope documented")
for ref in ["J21", "J22", "J23"]:
    require(
        at(ref)[0] > 90 and abs(fps[ref].GetOrientationDegrees() % 360 - 90) < 0.01,
        ref + ": COM terminal enters from right edge",
    )
for ref in ["J15", "J16", "J17"]:
    require(
        at(ref)[0] < 9 and abs(fps[ref].GetOrientationDegrees() % 360 - 270) < 0.01,
        ref + ": AC terminal enters from left edge",
    )
require(
    abs(at("J9")[0] + at("J11")[0] - 100) < 0.001
    and abs((at("J9")[1] + 5.08) - (at("J11")[1] - 5.08)) < 0.011,
    "AC1/DC1: left/right port bodies aligned",
)
require(
    fps["J9"].GetOrientationDegrees() % 360 == 0
    and fps["J11"].GetOrientationDegrees() % 360 == 180,
    "Port 1 cables point out to their respective sides",
)
require(
    all(
        abs(at(q)[1] - 94.7775) < 0.001 and fps[q].GetOrientationDegrees() % 360 == 90
        for q in ["J8", "J10"]
    ),
    "AC0/DC0 cables both exit the bottom edge",
)
require(
    abs(at("J8")[0] + 5.08 - 38) < 0.001 and abs(at("J10")[0] + 5.08 - 62) < 0.001,
    "Bottom port bodies centered at x38 and x62",
)
for ref, x in [
    ("J12", 10.5),
    ("J13", 16.5),
    ("J14", 22.5),
    ("J18", 74.5),
    ("J19", 80.5),
    ("J20", 86.5),
]:
    require(
        distance(at(ref), (x, 94)) < 0.001
        and fps[ref].GetOrientationDegrees() % 360 == 0,
        ref + ": bottom-facing terminal in horizontal row",
    )
for a, z in [("J15", "J21"), ("J16", "J22"), ("J17", "J23")]:
    require(
        abs(at(a)[0] + at(z)[0] - 100) < 0.001
        and abs((at(a)[1] + 1.5) - (at(z)[1] - 1.5)) < 0.001,
        a + "/" + z + ": side terminal bodies share a row",
    )
for a, z in [("J12", "J20"), ("J13", "J19"), ("J14", "J18")]:
    require(
        abs(at(a)[0] + at(z)[0] + 3 - 100) < 0.001,
        a + "/" + z + ": bottom terminal body centers are symmetric",
    )
for port, refs in [("J9", ["J15", "J16", "J17"]), ("J11", ["J21", "J22", "J23"])]:
    require(
        all(at(q)[1] < at(port)[1] for q in refs),
        port + ": three related terminals above its side port",
    )
    require(
        all(abs(at(z)[1] - at(a)[1] - 6) < 0.001 for a, z in zip(refs, refs[1:])),
        port + ": matching 6 mm vertical terminal pitch",
    )
for refs in [("J12", "J13", "J14"), ("J18", "J19", "J20")]:
    require(
        all(abs(at(z)[0] - at(a)[0] - 6) < 0.001 for a, z in zip(refs, refs[1:])),
        "Bottom terminal group: 6 mm horizontal pitch",
    )
require(
    abs(at("J9")[1] - 75.075) < 0.001 and abs(at("J11")[1] - 85.225) < 0.001,
    "Both side IDC ports retain the lower side sites",
)
require(
    {at(q) for q in ["H1", "H2", "H3", "H4"]} == {(4, 4), (96, 4), (4, 96), (96, 96)},
    "Four corner mounting holes at the specified coordinates",
)
require(
    at("J9")[1] < at("J8")[1] and at("J11")[1] < at("J10")[1],
    "Port 1 is on each side; port 0 is at the bottom",
)
require(
    distance(at("J27"), (12, 39.2)) < 0.001 and distance(at("J26"), (88, 47.8)) < 0.001,
    "CAN2 left and CAN1 right share body center y43.5",
)
require(
    fps["J27"].GetOrientationDegrees() % 360 == 270
    and fps["J26"].GetOrientationDegrees() % 360 == 90,
    "CAN cables exit opposite side edges without mirrored pin numbering",
)
require(
    all(
        fps[q].GetOrientationDegrees() % 360 == 90 and at(q)[0] == 94
        for q in ["J24", "J25"]
    )
    and abs(at("J25")[1] - at("J24")[1] - 7) < 0.001
    and at("J24")[1] == 13,
    "Right upper +24V / 0V input pair at 7 mm pitch, facing right",
)
for ref, x in [("SW2", 45), ("SW3", 57), ("SW4", 69)]:
    require(
        distance(at(ref), (x, 14)) < 0.001, ref + ": 12 mm button pitch in the upper UI"
    )
for ref, pos in [("H5", (13, 3)), ("H6", (37, 3)), ("H7", (13, 27)), ("H8", (37, 27))]:
    require(distance(at(ref), pos) < 0.001, ref + ": OLED slot center")
for ref in ["H7", "H8"]:
    require(
        abs(fps[ref].GetOrientationDegrees() % 180 - 90) < 0.01,
        ref + ": lower OLED slot allows Y adjustment",
    )
com_refs = {f"J{i}" for i in range(18, 24)}
require(
    {k for k, v in expected.items() if v == "DC_DRIVER_COM"}
    == {(ref, "1") for ref in com_refs} | {("Q2", "2"), ("R20", "2"), ("D2", "1")},
    "DRIVER COM remains separate from the board supply return",
)
require(
    {k for k, v in expected.items() if v == "POWER_0V"}
    == {("J25", "1"), ("J26", "2"), ("J27", "2"), ("NT1", "1")},
    "Both CAN supplies return through J25, not DRIVER COM",
)
require(pad("NT1", 2).GetNetname() == "GND", "NT1 bonds supply return to logic GND")


def wide_path(start_ref, start_pin, end_ref, end_pin, width, drill_min=0.4):
    starts = [pad for pad in fps[start_ref].Pads() if pad.GetNumber() == start_pin]
    ends = [pad for pad in fps[end_ref].Pads() if pad.GetNumber() == end_pin]
    name = starts[0].GetNetname()
    require(
        all(pad.GetNetname() == name for pad in ends),
        f"{start_ref}.{start_pin} to {end_ref}.{end_pin}: same supply net",
    )

    def point(v):
        return (v.x, v.y)

    segments = [
        t
        for t in b.GetTracks()
        if not isinstance(t, p.PCB_VIA)
        and t.GetNetname() == name
        and t.GetWidth() >= p.FromMM(width)
    ]
    transitions = [
        t
        for t in b.GetTracks()
        if isinstance(t, p.PCB_VIA)
        and t.GetNetname() == name
        and t.GetDrillValue() >= p.FromMM(drill_min)
    ]
    pads = [pad for f in fps.values() for pad in f.Pads() if pad.GetNetname() == name]
    nodes = set()
    for t in segments:
        nodes.update(
            [(point(t.GetStart()), t.GetLayer()), (point(t.GetEnd()), t.GetLayer())]
        )
    for item in [*pads, *transitions]:
        for layer in (p.F_Cu, p.B_Cu):
            if item.IsOnLayer(layer):
                nodes.add((point(item.GetPosition()), layer))
    parent = {node: node for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def join(a, c):
        parent[find(a)] = find(c)

    for t in segments:
        a, z = point(t.GetStart()), point(t.GetEnd())
        dx, dy = z[0] - a[0], z[1] - a[1]
        length2 = dx * dx + dy * dy
        for pos, layer in nodes:
            if layer != t.GetLayer():
                continue
            scale = (
                0
                if not length2
                else max(
                    0, min(1, ((pos[0] - a[0]) * dx + (pos[1] - a[1]) * dy) / length2)
                )
            )
            if math.hypot(
                pos[0] - a[0] - scale * dx, pos[1] - a[1] - scale * dy
            ) <= p.FromMM(0.0001):
                join((a, layer), (pos, layer))
    for item in [
        *transitions,
        *[pad for pad in pads if pad.GetAttribute() == p.PAD_ATTRIB_PTH],
    ]:
        pos = point(item.GetPosition())
        join((pos, p.F_Cu), (pos, p.B_Cu))
    # Wide tracks may attach within a pad, offset from its center to clear an
    # adjacent pad. Native DRC checks actual copper overlap and clearances.
    for pad in pads:
        pos = point(pad.GetPosition())
        for node, layer in nodes:
            if pad.IsOnLayer(layer) and pad.HitTest(p.VECTOR2I(*node)):
                join((pos, layer), (node, layer))
    start_nodes = [
        (point(pad.GetPosition()), layer)
        for pad in starts
        for layer in (p.F_Cu, p.B_Cu)
        if pad.IsOnLayer(layer)
    ]
    end_nodes = [
        (point(pad.GetPosition()), layer)
        for pad in ends
        for layer in (p.F_Cu, p.B_Cu)
        if pad.IsOnLayer(layer)
    ]
    require(
        any(find(a) == find(z) for a in start_nodes for z in end_nodes),
        f"{start_ref}.{start_pin} to {end_ref}.{end_pin}: continuous >= {width:g} mm tracks and >= {drill_min:g} mm transition drills",
    )


for name in ["AC2_IN", "EACRET"]:
    require(
        b.FindNet(name).GetNetClassName() == "AC_24V", name + ": AC net class active"
    )
    ts = [t for t in b.GetTracks() if t.GetNetname() == name]
    require(
        ts
        and all(
            not isinstance(t, p.PCB_VIA) and t.GetWidth() == p.FromMM(2) for t in ts
        ),
        name + ": 2 mm conductor; layer changes use connector/relay THT pads",
    )
for ref in ["J12", "J13", "J14", "J15", "J16", "J17"]:
    wide_path(ref, "1", "K1", "13", 2)
for ref in ["J8", "J9"]:
    wide_path("K1", "14", ref, "5", 2)
for ref in sorted(com_refs):
    wide_path(ref, "1", "Q2", "2", 2)
for n in ["DC_DRIVER_COM", "DC_ZONE_RETURN", "POWER_0V"]:
    require(b.FindNet(n).GetNetClassName() == "DC_Return", n + ": return class active")
    vs = [t for t in b.GetTracks() if t.GetNetname() == n and isinstance(t, p.PCB_VIA)]
    require(
        vs and all(t.GetDrillValue() >= p.FromMM(0.4) for t in vs),
        n + ": >=0.4 mm via drills",
    )
    require(
        any(
            distance(xy(a.GetPosition()), xy(z.GetPosition())) < 1.11
            for i, a in enumerate(vs)
            for z in vs[i + 1 :]
        ),
        n + ": paired current-carrying vias present",
    )
    for t in b.GetTracks():
        if t.GetNetname() != n or isinstance(t, p.PCB_VIA):
            continue
        if n == "DC_DRIVER_COM" and t.GetWidth() == p.FromMM(1):
            require(
                t.GetLayer() == p.F_Cu
                and all(
                    76 <= x <= 90 and 77 <= y <= 88.5
                    for x, y in [xy(t.GetStart()), xy(t.GetEnd())]
                ),
                "COM 1 mm tracks restricted to local clamp/pulldown branches, including the R20 fanout",
            )
        else:
            require(t.GetWidth() >= p.FromMM(2), n + ": main tracks >=2 mm")
heat = [z for z in b.Zones() if z.GetZoneName() == "Q2 drain heat spreading"]
require(
    len(heat) == 2
    and {z.GetLayer() for z in heat} == {p.F_Cu, p.B_Cu}
    and all(
        z.GetNetname() == "DC_ZONE_RETURN" and z.GetFilledArea() / 1e12 >= 35
        for z in heat
    ),
    "Q2 drain heat copper >=35 mm2 per layer",
)
for a, ap, z, zp, w in [
    ("J24", "1", "U2", "5", 0.6),
    ("U2", "6", "L1", "1", 0.6),
    ("L1", "2", "D4", "2", 1),
    ("D4", "1", "J6", "14", 1),
]:
    wide_path(a, ap, z, zp, w)
for ref in ["C6", "C7"]:
    wide_path("L1", "2", ref, "1", 1)
# J11 logic power must retain the widened branch through its layer transition.
wide_path("D4", "1", "J11", "9", 0.5, 0.3)
# The upper-right 3V3 feed reaches the CAN1 TX pullup without narrow necks.
wide_path("J1", "1", "R25", "1", 0.5, 0.3)
lx = pad("U2", 6).GetNetname()
ts = [t for t in b.GetTracks() if t.GetNetname() == lx]
require(
    ts
    and all(not isinstance(t, p.PCB_VIA) and t.GetLayer() == p.F_Cu for t in ts)
    and not any(not z.GetIsRuleArea() and z.GetNetname() == lx for z in b.Zones()),
    "Buck switching node stays on F.Cu without vias/pours",
)
for u, j, d, f, c1, c2, term, jp, tx, rx in [
    ("U3", "J26", "D5", "F2", "C10", "C11", "R24", "JP1", ("J7", 4), ("J7", 5)),
    ("U4", "J27", "D6", "F3", "C13", "C14", "R29", "JP2", ("J6", 8), ("J6", 9)),
]:
    require(
        pad(*tx).GetNetname() == pad(u, 1).GetNetname()
        and pad(*rx).GetNetname() == pad(u, 4).GetNetname(),
        j + ": selected GPIO TX/RX pair reaches its own transceiver",
    )
    require(
        distance(at(c1), at(u)) < 6 and distance(at(c2), at(u)) < 8,
        j + ": local 100nF and 1uF bypass",
    )
    require(
        min(distance(at(d), at(j, pin)) for pin in [3, 4]) < 8,
        j + ": ESD protection next to connector",
    )
    require(
        fps[jp].IsExcludedFromBOM(), jp + ": copper bridge excluded from purchase BOM"
    )
    for pin, drill in [("1", 1.8), ("2", 1.8), ("3", 1.1), ("4", 1.1)]:
        require(
            abs(p.ToMM(pad(j, pin).GetDrillSize().x) - drill) < 0.001,
            j + "." + pin + ": AMASS lead drill",
        )
    wide_path("J24", "1", f, "1", 0.8)
    wide_path(f, "2", j, "1", 0.8)
    wide_path("J25", "1", j, "2", 2)
    for q in [pad(u, 1), pad(u, 4), pad(j, 3), pad(j, 4)]:
        require(
            any(t.GetNetCode() == q.GetNetCode() for t in b.GetTracks()),
            q.GetNetname() + ": routed",
        )
    wide_path(c1, "1", u, "3", 0.3)
    wide_path(c1, "2", u, "2", 0.3)
require(
    distance(at("R20", 1), at("Q2", 1)) < 2, "DC gate pulldown within 2 mm of Q2 gate"
)


# Geometric spacing is checked separately from the pending loaded thermal test.
def fab_left(ref):
    return min(
        p.ToMM(g.GetBoundingBox().GetLeft())
        for g in fps[ref].GraphicalItems()
        if isinstance(g, p.PCB_SHAPE) and g.GetLayer() == p.F_Fab
    )


require(
    fab_left("D4") - 65.7 >= 4,
    "D4 body outside DevKit with >=4 mm horizontal clearance",
)
require(
    fab_left("L1") - 65.7 >= 3,
    "Inductor body outside DevKit with >=3 mm horizontal clearance",
)
require(
    distance(at("U2"), at("Q2")) >= 17,
    "Buck regulator and DC MOSFET centers separated by >=17 mm",
)
require(
    distance(at("U1"), at("Q2")) >= 10,
    "DC optocoupler and MOSFET centers separated by >=10 mm",
)
require(
    distance(at("F3"), (76, 16.5)) < 0.001, "CAN2 fuse on the upper-right supply branch"
)
for name, y, width in [("POWER_0V", 16.5, 2), ("CAN2_24V", 19.5, 1.5)]:
    require(
        any(
            not isinstance(t, p.PCB_VIA)
            and t.GetNetname() == name
            and t.GetLayer() == p.B_Cu
            and abs(xy(t.GetStart())[1] - y) < 0.001
            and abs(xy(t.GetEnd())[1] - y) < 0.001
            and abs(xy(t.GetStart())[0] - xy(t.GetEnd())[0]) > 50
            and t.GetWidth() >= p.FromMM(width)
            for t in b.GetTracks()
        ),
        name + ": straight upper bus parallel to the other CAN2 power conductor",
    )
can2_vias = [
    t
    for t in b.GetTracks()
    if t.GetNetname() == "CAN2_24V" and isinstance(t, p.PCB_VIA)
]
require(
    len(can2_vias) == 2
    and all(t.GetDrillValue() >= p.FromMM(0.4) for t in can2_vias)
    and distance(xy(can2_vias[0].GetPosition()), xy(can2_vias[1].GetPosition())) <= 1.1,
    "CAN2 supply layer transition has a pair of >=0.4 mm drill vias",
)
# Functional labels move with their footprint; board-level branding is separate.
silk_clearance = json.loads((ROOT / "ulva_controller.kicad_pro").read_text())["board"]["design_settings"]["rules"]["min_silk_clearance"]
require(silk_clearance >= 0.2, "Native DRC requires at least 0.20 mm silkscreen clearance")


def silk_texts(layer):
    result = [
        (None, t) for t in b.GetDrawings()
        if isinstance(t, p.PCB_TEXT) and t.GetLayer() == layer and t.IsVisible()
    ]
    for ref, footprint in fps.items():
        for t in [footprint.Reference(), footprint.Value(), *footprint.GraphicalItems()]:
            if isinstance(t, p.PCB_TEXT) and t.GetLayer() == layer and t.IsVisible():
                result.append((ref, t))
    return result


def shown(t):
    return t.GetShownText(False)


def has_word(t, value):
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", shown(t))


front = silk_texts(p.F_SilkS)
rear = silk_texts(p.B_SilkS)
for ref in [f"J{i}" for i in range(1, 28)]:
    labels = [t for owner, t in front if owner == ref and has_word(t, ref)]
    require(len(labels) == 1, ref + ": exactly one visible designator attached to its footprint")
    require(
        min(distance(xy(labels[0].GetPosition()), xy(q.GetPosition())) for q in fps[ref].Pads()) < 15,
        ref + ": attached designator remains local to its connector",
    )
for ref in ["J6", "J7", *[f"J{i}" for i in range(12, 26)], "K1", "U2", "L1"]:
    text = fps[ref].Reference()
    require(
        text.IsVisible() and text.GetLayer() == p.F_SilkS and shown(text) == ref,
        ref + ": silk identifier uses the footprint reference field",
    )
for ref in ["U2", "L1"]:
    require(
        distance(xy(fps[ref].Reference().GetPosition()), at(ref)) < 6,
        ref + ": reference remains within 6 mm of its part instead of a stale board coordinate",
    )
require(not any(has_word(t, "C15") for _, t in front), "C15 silk omitted beneath the DevKit; Fab identifier retained")
require(
    not any(owner is None and re.search(r"(?<![A-Za-z0-9_])(?:J[1-9][0-9]*|U2|L1|K1)(?![A-Za-z0-9_])", shown(t)) for owner, t in front),
    "No detached front connector or relocated-part identifiers",
)
for ref, label in {
    "J1": "J1 DHT20", "J2": "J2 RTC", "J3": "J3 OLED", "J4": "J4 RF433",
    "J5": "J5 PIEZO", "J8": "AC0 / J8", "J9": "AC1 / J9",
    "J10": "DC0 / J10", "J11": "DC1 / J11", "J26": "CAN1 J26", "J27": "CAN2 J27",
    "SW1": "CFG SW1", "SW2": "UP", "SW3": "OK", "SW4": "DOWN",
    "JP1": "TERM1", "JP2": "TERM2", "J24": "+24V DC", "J25": "0V",
}.items():
    matches = [t for owner, t in front if owner == ref and shown(t) == label]
    require(len(matches) == 1, ref + ": correct functional text attached to its footprint")
    if re.search(r"\b(?:J[0-9]+|SW1)\b", label):
        require("${REFERENCE}" in matches[0].GetText(), ref + ": embedded designator follows reference renumbering")
for ref in ["J8", "J9", "J10", "J11"]:
    numerals = [t for owner, t in front if owner == ref and shown(t) == "1"]
    require(len(numerals) == 1, ref + ": one footprint-local pin-1 numeral")
    marker = numerals[0]
    require(
        abs(marker.GetTextAngle().AsDegrees() % 360) < 0.001 and not marker.IsMirrored(),
        ref + ": pin-1 numeral upright from the front",
    )
    x, y = xy(marker.GetPosition())
    px, py = at(ref, 1)
    outside = (y > py and abs(x - px) < 1) if ref in ["J8", "J10"] else (
        x < px and abs(y - py) < 1 if ref == "J9" else x > px and abs(y - py) < 1
    )
    require(outside and distance((x, y), (px, py)) < 5, ref + ": numeral remains at the outer pin-1 end")

for ref in ["J13", "J15", "J16", "J17"]:
    require(any(owner == ref and shown(t) == "AC IN" for owner, t in front), ref + ": AC input scope explicit")
for ref in ["J19", "J21", "J22", "J23"]:
    require(any(owner == ref and " ".join(shown(t).split()) == "DRV COM" for owner, t in front), ref + ": driver COM scope explicit")

rear_by_text = {}
for _, text in rear:
    rear_by_text.setdefault(shown(text), []).append(text)
require(all(text.IsMirrored() for _, text in rear), "Every rear silk text is mirrored for bottom-side reading")
for label in [
    "24VAC / 24VDC ONLY", "EXT FUSE", "J5 1 SIG / 4 GND",
    "CAN 1 +24V / 2 0V", "CAN 3 H / 4 L", "2026-09-20 / 2 LAYERS",
]:
    require(label not in rear_by_text, "Obsolete or unscoped rear legend absent: " + label)
for ref, label in {
    "J5": "J5 PIEZO", "J24": "J24 +24VDC", "J25": "J25 POWER 0V",
    "J26": "CAN1 J26", "J27": "CAN2 J27", "J8": "J8 AC0", "J9": "J9 AC1",
    "J10": "J10 DC0", "J11": "J11 DC1",
}.items():
    require(len(rear_by_text.get(label, [])) == 1, ref + ": explicit rear connector legend")
    require(any(owner == ref and shown(t) == label for owner, t in rear), ref + ": local rear legend follows its footprint")
    require(
        min(distance(xy(rear_by_text[label][0].GetPosition()), xy(q.GetPosition())) for q in fps[ref].Pads()) < 15,
        ref + ": rear label is local to its connector",
    )
for group in [
    ["J5 PIEZO", "PIN 1 PWM / PIN 4 GND"],
    ["DC INPUT", "J24 +24VDC", "J25 POWER 0V"],
    ["AC INPUT J12-J17", "ISOLATED 24VAC", "ONE SOURCE", "EXTERNAL AC FUSE"],
    ["CAN J26 / J27", "PIN 1 +24V / PIN 2 0V", "PIN 3 H / PIN 4 L"],
    ["IDC J8 / J9 / J10 / J11", "PIN 7 SDA / PIN 8 SCL", "PIN 9 +5V / PIN 10 GND"],
    ["J18-J23 DRIVER COM", "COMMAND RETURN ONLY", "NO MOTOR POWER"],
]:
    require(all(len(rear_by_text.get(label, [])) == 1 for label in group), group[0] + ": complete rear legend group")
    positions = [xy(rear_by_text[label][0].GetPosition()) for label in group]
    require(
        max(x for x, _ in positions) - min(x for x, _ in positions) < 1
        and all(1.5 <= right[1] - left[1] <= 8 for left, right in zip(positions, positions[1:])),
        group[0] + ": heading and pin/usage rows form one readable vertical group",
    )
for ref, pins in {
    "J5": {"1": "UI_PIEZO", "4": "GND"},
    "J24": {"1": "VIN_24V"}, "J25": {"1": "POWER_0V"},
    "J26": {"1": "CAN_24V", "2": "POWER_0V", "3": "CAN_H", "4": "CAN_L"},
    "J27": {"1": "CAN2_24V", "2": "POWER_0V", "3": "CAN2_H", "4": "CAN2_L"},
}.items():
    require(all(pad(ref, number).GetNetname() == net for number, net in pins.items()), ref + ": rear pin legend matches PCB nets")
for ref, bus in [("J8", 0), ("J9", 1), ("J10", 0), ("J11", 1)]:
    pins = {"7": f"I2C{bus}_SDA", "8": f"I2C{bus}_SCL", "9": "EXP_5V", "10": "GND"}
    require(all(pad(ref, number).GetNetname() == net for number, net in pins.items()), ref + ": IDC legend matches bus and power pins")

icons = [g for g in b.Groups() if g.GetName().startswith("ULVA sea lettuce icon")]
require(len(icons) == 1 and len(icons[0].GetItems()) == 25, "One 25-curve ULVA icon")
box = icons[0].GetBoundingBox()
require(
    abs(p.ToMM(box.GetWidth()) - 11.772655) < 0.001
    and abs(p.ToMM(box.GetHeight()) - 11.54) < 0.001,
    "ULVA icon bounding box is 11.773 x 11.540 mm",
)
require(
    all(abs(p.ToMM(item.GetWidth()) - 0.36) < 0.000001 for item in icons[0].GetItems()),
    "ULVA icon uses 0.36 mm silkscreen strokes",
)
require(
    distance(xy(box.GetCenter()), (53, 37.25)) < 0.001
    and all(item.GetLayer() == p.F_SilkS for item in icons[0].GetItems()),
    "ULVA icon centered below the antenna text row in front silkscreen only",
)
branding = {
    t.GetText(): t
    for t in b.GetDrawings()
    if isinstance(t, p.PCB_TEXT)
    and t.GetLayer() == p.F_SilkS
    and t.GetText() in ["ULVA", revision]
}
require(
    set(branding) == {"ULVA", revision}
    and distance(xy(branding["ULVA"].GetPosition()), (50.2, 28.25)) < 0.001
    and distance(xy(branding[revision].GetPosition()), (58.1, 28.25)) < 0.001,
    "Product and revision form one horizontal text row centered in the antenna outline",
)
require(
    branding["ULVA"].GetBoundingBox().GetRight() + p.FromMM(0.8)
    <= branding[revision].GetBoundingBox().GetLeft()
    and max(t.GetBoundingBox().GetBottom() for t in branding.values()) + p.FromMM(1)
    <= box.GetTop()
    and all(
        t.GetBoundingBox().GetLeft() >= p.FromMM(44)
        and t.GetBoundingBox().GetRight() <= p.FromMM(62)
        and t.GetBoundingBox().GetTop() >= p.FromMM(25)
        and t.GetBoundingBox().GetBottom() <= p.FromMM(31.5)
        for t in branding.values()
    ),
    "Branding row fits antenna outline, with >=0.8 mm between texts and >=1 mm to the icon",
)

report = {
    "result": "PASS",
    "checks": len(checks),
    "components": len(fps),
    "tracks": sum(not isinstance(t, p.PCB_VIA) for t in b.GetTracks()),
    "vias": sum(isinstance(t, p.PCB_VIA) for t in b.GetTracks()),
    "gnd_copper_mm2": {
        b.GetLayerName(z.GetLayer()): round(z.GetFilledArea() / 1e12, 2)
        for z in b.Zones()
        if not z.GetIsRuleArea() and z.GetNetname() == "GND"
    },
    "q2_heat_copper_mm2": {
        b.GetLayerName(z.GetLayer()): round(z.GetFilledArea() / 1e12, 2) for z in heat
    },
    "physical_validation": "PENDING: central PCB antenna / OLED 5 mm gap (not edge-mounted RF qualification), bottom AC0/DC0 IDC / USB XY overlap; SW1 at lower-center body (53,83), immediately above AC0/DC0, switch1 above switch2; elevated DevKit/USB and actual case switch access unqualified; left vertical RF433 module/antenna, OLED supports 1 mm below the top edge and piezo plug; upper RTC module/battery body vs buttons/piezo and DHT20 body/case/airflow unqualified; socket/OLED mating, RF, supply and loaded thermal tests; remapped CAN1 GPIO24/23 and independent GPIO4 piezo / GPIO27 RGB operation; 24V monitor ADC calibration/noise/power-off backfeed and low SMT clearance beneath DevKit",
}
report["plated_drills"] = report["vias"] + sum(
    q.GetAttribute() == p.PAD_ATTRIB_PTH and q.GetDrillSize().x > 0
    for f in fps.values()
    for q in f.Pads()
)
report["nonplated_drills"] = sum(
    q.GetAttribute() == p.PAD_ATTRIB_NPTH and q.GetDrillSize().x > 0
    for f in fps.values()
    for q in f.Pads()
)
(ROOT / "build/pcb-checks.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
