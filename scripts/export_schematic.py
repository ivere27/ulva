#!/usr/bin/env python3
"""Validate the current schematic and regenerate ignored build/ outputs.

Run in a KiCad 9 Python environment with kicad-cli and pcbnew installed.
"""

import collections
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SCHEMATIC = ROOT / "ulva_controller.kicad_sch"
BUILD = ROOT / "build"
CLI = shutil.which("kicad-cli")
if CLI is None:
    sys.exit("kicad-cli is required; run this script in the KiCad 9 environment.")


def run(*args, capture=False):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


project = ROOT / "ulva_controller.kicad_pro"
project_before = sha(project)
schematic_sources = sorted(ROOT.glob("ulva_*.kicad_sch"))
for source in schematic_sources:
    paper = re.search(r'^\s*\(paper "([^"]+)"', source.read_text(), re.MULTILINE)
    if paper is None or paper.group(1) != "A4":
        sys.exit(
            f"{source.name}: use an A4 sheet so the PDF prints at its intended size."
        )
version = run(CLI, "version", capture=True).stdout.strip()

with tempfile.TemporaryDirectory(prefix="ulva-schematic-") as temp:
    staging = Path(temp)
    netlist = staging / "controller.xml"
    erc_path = staging / "controller.erc.json"
    nets_path = staging / "controller.nets.json"
    fp_path = staging / "controller.footprints.json"
    monitor_path = staging / "controller.voltage-monitor.json"
    pdf = staging / "ulva_controller.pdf"
    bom = staging / "ulva_controller.bom.csv"

    run(
        CLI,
        "sch",
        "erc",
        "--severity-all",
        "--exit-code-violations",
        "--format",
        "json",
        "-o",
        erc_path,
        SCHEMATIC,
    )
    run(
        CLI,
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "-o",
        netlist,
        SCHEMATIC,
    )
    xml = ET.parse(netlist).getroot()
    revision = xml.findtext("./design/sheet/title_block/rev")
    if not revision:
        sys.exit("The root schematic must specify its current revision.")
    run(
        sys.executable,
        ROOT / "scripts/validate_schematic.py",
        netlist,
        "--report",
        nets_path,
    )
    footprints = run(
        sys.executable,
        ROOT / "scripts/check_footprints.py",
        netlist,
        "--project-dir",
        ROOT,
        capture=True,
    )
    fp_path.write_text(footprints.stdout)
    run(
        sys.executable,
        ROOT / "scripts/validate_voltage_monitor.py",
        netlist,
        "--report",
        monitor_path,
    )
    run(sys.executable, ROOT / "scripts/export_bom.py", netlist, bom)
    run(CLI, "sch", "export", "pdf", "--no-background-color", "-o", pdf, SCHEMATIC)

    if sha(project) != project_before:
        sys.exit(
            "Project settings changed during schematic export; inspect before publishing reports."
        )

    # Publish only after every schematic check succeeds. No PCB exporter is used.
    BUILD.mkdir(parents=True, exist_ok=True)
    artifacts = (netlist, erc_path, nets_path, fp_path, monitor_path, pdf, bom)
    for artifact in artifacts:
        shutil.copyfile(artifact, BUILD / artifact.name)
    artifact_paths = [BUILD / artifact.name for artifact in artifacts]

erc = json.loads((BUILD / "controller.erc.json").read_text())
violations = [v for sheet in erc.get("sheets", []) for v in sheet.get("violations", [])]
counts = collections.Counter(v.get("severity", "unknown") for v in violations)
nets = json.loads((BUILD / "controller.nets.json").read_text())
footprints = json.loads((BUILD / "controller.footprints.json").read_text())
sources = [
    *schematic_sources,
    project,
    ROOT / "fp-lib-table",
    ROOT / "sym-lib-table",
    ROOT / "Ulva.kicad_sym",
    *ROOT.glob("Ulva.pretty/*.kicad_mod"),
    ROOT / "scripts/validate_schematic.py",
    ROOT / "scripts/check_footprints.py",
    ROOT / "scripts/export_bom.py",
    Path(__file__),
    ROOT / "README.md",
    ROOT / "docs/hardware.md",
    ROOT / "scripts/validate_voltage_monitor.py",
    ROOT / "scripts/validate_button_adc.py",
]
record = {
    "revision": revision,
    "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "kicad_version": version,
    "print_format": "A4",
    "schematic_pages": len(xml.findall("./design/sheet")),
    "scope": "Schematic, BOM, PDF and component footprint assignments only.",
    "erc": {
        "error": counts["error"],
        "warning": counts["warning"],
        "exclusion": sum(bool(v.get("excluded")) for v in violations),
    },
    "design_status": nets["design_status"],
    "net_checks": nets["checks"],
    "physical_components": len(xml.findall("./components/comp")),
    "footprints": footprints,
    "voltage_monitor": json.loads(
        (BUILD / "controller.voltage-monitor.json").read_text()
    ),
    "project_unchanged_during_export": True,
    "pcb": {
        "included": (ROOT / "ulva_controller.kicad_pcb").exists(),
        "validated": False,
        "scope_note": "PCB validation and fabrication are handled separately by export_pcb.py; see pcb-validation.json.",
    },
    "physical_tests_performed": False,
    "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)},
    "artifacts_sha256": {
        str(p.relative_to(ROOT)): sha(p) for p in sorted(artifact_paths)
    },
    "limitations": [
        "Buttons use GPIO1 ADC1_CH0, R12 10k / R13 4.7k / R14 10k and C15 100nF; 10ms scan and 30ms debounce example provided. Simultaneous presses prioritize UP, then OK, then DOWN. Product integration and actual board ADC/noise/button tests remain pending; see docs/hardware.md.",
        "SW1 uses GPIO6 ADC1_CH5 only: R5/R6 1k, R27 10k, R28 20k, C12 100nF. Nominal states are 0/1.065/2.129/3.3V; GPIO24/23 are CAN1 TX/RX and GPIO7/8 are CAN2 TX/RX. ADC calibration, boot decoding and field voltage/noise checks remain to be implemented and physically verified; see docs/hardware.md.",
        "J5 is a four-position male header for a high-impedance passive piezo: pin1 signal through R26 1k from dedicated GPIO4; RGB27 remains on DevKit only, pin4 GND, pins2/3 NC. GPIO8 is CAN2 RX. Exact piezo selection, connector fit, independent RGB/piezo operation, boot behavior and sound level remain physically unqualified.",
        f"This report validates the schematic only. {revision} PCB placement, routing, mechanical envelopes and fabrication are checked separately by export_pcb.py.",
        "CAN1 uses GPIO24/23 and U3/J26; CAN2 uses GPIO7/8 and U4/J27; UP/OK/DOWN share GPIO1 ADC1_CH0; GPIO5 ADC1_CH4 monitors VIN_24V and GPIO4 drives the independent piezo. Independent H/L, terminations and fused outputs share supply/ground. J26+J27 combined control-power budget remains1A; physical two-channel operation and firmware are unqualified.",
        "GPIO5 voltage monitor uses R31 150k/R32 10k, R33 1k, C16 100nF and HJC BAT54S D7 (C7420333). D7 pins1/3/2 connect to logic GND/ADC/3V3. ADC calibration/integration, leakage/temperature, noise and power sequencing remain unqualified; BAT54S does not block backfeed when 3V3 is off. See docs/hardware.md.",
        "An external AC fuse before the selected J15.1 or J12.1 input is mandatory and cannot be verified from onboard connectivity.",
        "J12–J17 are six parallel alternative inputs: connect only one to the single isolated 24VAC source. Both AC ports share that source; combined normal AC current remains <=2Arms.",
        "Each I2C bus has four unique expander addresses total across its AC and DC ports; expansion ports and the relay coil share a 210mA normal 5V budget.",
        "No AC contact TVS/snubber is fitted. Relay inductive-load switching, pickup at low voltage/high temperature, release with flyback diode, bounce, thermal behavior and fault clearing are not physically qualified.",
        "J24 accepts nominal24V DC positive; existing J25 accepts negative. NT1 bonds POWER_0V (J25/J26.2/J27.2) to logic GND. Six DRIVER COM inputs are separate on the PCB; externally connect driver COM to the same PSU negative for the board5V U1/Q2 gate drive. Q2 still switches DC_ZONE_RETURN; external expander pull-down/ESD paths can carry OFF current and require actual driver-release qualification. Motor current must remain outside this board.",
        "SY8301ABC is a1A-capable converter, not a qualified1A24V-to5V assembled supply. Raw output is5.096V; D4 diode drop lowers EXP_5V. Verify biased capacitance, startup, Wi-Fi peaks, sustained temperature and USB/24V power sequences on the actual DevKit revision. U2/L1 are hand-soldered; PCB placement, completed routing and fabrication checks are separate from this schematic report.",
    ],
}
record_path = BUILD / "validation.json"
record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(
    json.dumps(
        {
            "revision": revision,
            "erc": record["erc"],
            "schematic_pages": record["schematic_pages"],
            "net_checks": record["net_checks"],
            "physical_components": record["physical_components"],
            "pcb_included": record["pcb"]["included"],
            "record": str(record_path),
        },
        ensure_ascii=False,
    )
)
