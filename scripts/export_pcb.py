#!/usr/bin/env python3
"""Validate a PCB snapshot and export a prototype fabrication package.

Invoked by run_checks.py inside its disposable snapshot using KiCad 9 Python.
Refills copper in the snapshot before validation and export.
"""
import csv, datetime, hashlib, json, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BOARD = ROOT / "ulva_controller.kicad_pcb"


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


run(sys.executable, ROOT / "scripts/export_schematic.py")
# Reject a schematic-only revision before touching the existing PCB or publishing files.
b = p.LoadBoard(str(BOARD))
schematic_refs = {
    c.get("ref")
    for c in ET.parse(BUILD / "controller.xml").getroot().findall("./components/comp")
}
pcb_refs = {f.GetReference() for f in b.GetFootprints()}
if schematic_refs != pcb_refs:
    sys.exit(
        "PCB update required before fabrication export. Missing on PCB: "
        + ", ".join(sorted(schematic_refs - pcb_refs))
        + "; missing in schematic: "
        + ", ".join(sorted(pcb_refs - schematic_refs))
    )
# Refill the snapshot board only after its component inventory matches.
p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(BOARD), b)
run(sys.executable, ROOT / "scripts/validate_pcb.py")
run(
    "kicad-cli",
    "pcb",
    "drc",
    "--schematic-parity",
    "--severity-all",
    "--all-track-errors",
    "--exit-code-violations",
    "--format",
    "json",
    "-o",
    BUILD / "controller.drc.json",
    BOARD,
)
with tempfile.TemporaryDirectory(prefix="ulva-pcb-") as td:
    out = Path(td)
    fab = out / "gerbers"
    fab.mkdir()
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
        str(fab) + "/",
        BOARD,
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
        "--generate-map",
        "--map-format",
        "pdf",
        "--generate-report",
        "--report-path",
        out / "drill-report.txt",
        "-o",
        str(fab) + "/",
        BOARD,
    )
    # Native KiCad exports provide traceable assembly and copper previews.
    for filename, layers in [
        ("pcb-assembly.svg", "F.Fab,F.Silkscreen,Edge.Cuts,Dwgs.User"),
        ("pcb-under-modules.svg", "F.Fab,F.Silkscreen,Edge.Cuts"),
        ("pcb-top.svg", "F.Cu,F.Silkscreen,Edge.Cuts"),
        ("pcb-bottom.svg", "B.Cu,B.Silkscreen,Edge.Cuts"),
    ]:
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
            "-o",
            out / filename,
            BOARD,
        )
    # Paste is separate from the bare-board order ZIP.
    run(
        "kicad-cli",
        "pcb",
        "export",
        "gerbers",
        "--layers",
        "F.Paste",
        "--use-drill-file-origin",
        "-o",
        str(out / "stencil") + "/",
        BOARD,
    )
    xml = ET.parse(BUILD / "controller.xml").getroot()
    components = {c.get("ref"): c for c in xml.findall("./components/comp")}
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    # Assembly ownership in the schematic determines the outsourced SMT subset.
    smd = sorted(
        (
            ref
            for ref, c in components.items()
            if c.findtext("./fields/field[@name='Assembly']") == "JLC PCBA SMT"
        ),
        key=lambda s: (s.rstrip("0123456789"), int("".join(filter(str.isdigit, s)))),
    )
    for ref, f in fps.items():
        if f.GetAttributes() & p.FP_SMD:
            ownership = components[ref].findtext("./fields/field[@name='Assembly']")
            assert ownership in {
                "JLC PCBA SMT",
                "Manual SMT",
                "PCB copper; no purchased part",
            }, f"Missing or invalid SMT Assembly field: {ref}"
    assert smd and all(fps[ref].GetAttributes() & p.FP_SMD for ref in smd)
    assert not {"U2", "L1", "NT1", "JP1", "JP2", "J26", "J27"} & set(smd)
    revision = b.GetTitleBlock().GetRevision()
    release_date = b.GetTitleBlock().GetDate()
    assert revision == xml.findtext("./design/sheet/title_block/rev")
    with (out / "assembly-bom.csv").open("w", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for ref in smd:
            c = components[ref]
            lcsc = c.findtext("./fields/field[@name='LCSC']")
            assert lcsc, ref
            w.writerow(
                [c.findtext("value"), ref, c.findtext("footprint").split(":")[1], lcsc]
            )
    with (out / "assembly-cpl.csv").open("w", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for ref in smd:
            f = fps[ref]
            w.writerow(
                [
                    ref,
                    f"{p.ToMM(f.GetPosition().x):.4f}mm",
                    f"{100-p.ToMM(f.GetPosition().y):.4f}mm",
                    "Top",
                    f"{f.GetOrientationDegrees()%360:.2f}",
                ]
            )
    (out / "README.md").write_text(
        f"# Ulva {revision} fabrication package\n\n"
        "The Gerber ZIP contains the bare-board layers and separate plated and "
        "nonplated drills. Stencil paste files are in `stencil/`.\n\n"
        "`assembly-bom.csv` and `assembly-cpl.csv` contain every component marked "
        "`Assembly=JLC PCBA SMT` in the schematic, including Extended parts. "
        "They do not apply current supplier tier or stock filters. Use the "
        "[order preparation tools](../../tools/README.md) to select parts before "
        "ordering. `full-bom.csv` includes the remaining BOM references.\n\n"
        "CPL rotations are KiCad angles. Confirm each supplier footprint's "
        "orientation and pin 1 in the assembly preview before ordering. "
        "File checks do not establish physical electrical, thermal or mechanical "
        "qualification.\n\n"
        "See the [hardware reference](../../docs/hardware.md) for operating "
        "limits and wiring, and the [parts guide](../../docs/bom.md) for "
        "assembly ownership. These links resolve within the source checkout.\n"
    )
    shutil.copyfile(BUILD / "ulva_controller.bom.csv", out / "full-bom.csv")
    # Only board fab layers and separate plated/nonplated drills go into the order ZIP.
    allowed = {
        ".gtl",
        ".gbl",
        ".gts",
        ".gbs",
        ".gto",
        ".gbo",
        ".gm1",
        ".drl",
        ".gbrjob",
    }
    files = [f for f in fab.iterdir() if f.suffix.lower() in allowed]
    assert len([f for f in files if f.suffix == ".drl"]) == 2
    assert (
        len(
            [
                f
                for f in files
                if f.suffix in {".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gm1"}
            ]
        )
        == 7
    )
    with zipfile.ZipFile(
        out / f"ulva-{revision}-{release_date}-gerbers.zip", "w", zipfile.ZIP_DEFLATED
    ) as z:
        for f in sorted(files):
            z.write(f, f.name)
    target = BUILD / f"manufacturing-{revision}"
    target.mkdir(parents=True, exist_ok=True)
    for f in out.iterdir():
        if f.is_dir():
            shutil.copytree(f, target / f.name, dirs_exist_ok=True)
        else:
            shutil.copyfile(f, target / f.name)
    (ROOT / "preview").mkdir(exist_ok=True)
    for filename in [
        "pcb-assembly.svg",
        "pcb-under-modules.svg",
        "pcb-top.svg",
        "pcb-bottom.svg",
    ]:
        shutil.copyfile(out / filename, ROOT / "preview" / filename)
report = {
    "revision": revision,
    "release_date": release_date,
    "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "erc": json.loads((BUILD / "validation.json").read_text())["erc"],
    "pcb_checks": json.loads((BUILD / "pcb-checks.json").read_text()),
    "drc": {
        k: len(v)
        for k, v in json.loads((BUILD / "controller.drc.json").read_text()).items()
        if k in ["violations", "unconnected_items", "schematic_parity"]
    },
    "smd_assembly_components": len(smd),
    "manufacturing_directory": str(target.relative_to(ROOT)),
    "physical_tests_performed": False,
    "cpl_rotation_status": "KiCad angles; confirm supplier part-library orientation in assembly preview before ordering",
    "sources_sha256": {
        str(f.relative_to(ROOT)): sha(f)
        for f in [
            BOARD,
            ROOT / "ulva_controller.kicad_pro",
            ROOT / "ulva_controller.kicad_dru",
            ROOT / "docs/hardware.md",
            ROOT / "docs/bom.md",
            ROOT / "tools/README.md",
            *ROOT.glob("*.kicad_sch"),
            ROOT / "scripts/export_pcb.py",
            ROOT / "scripts/validate_pcb.py",
            BUILD / "validation.json",
        ]
    },
    "artifacts_sha256": {
        str(f.relative_to(BUILD)): sha(f)
        for f in sorted(target.rglob("*"))
        if f.is_file()
    },
}
(BUILD / "pcb-validation.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False) + "\n"
)
print(
    json.dumps(
        {
            k: report[k]
            for k in [
                "revision",
                "drc",
                "smd_assembly_components",
                "physical_tests_performed",
            ]
        }
    )
)
