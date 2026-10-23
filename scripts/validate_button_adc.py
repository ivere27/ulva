#!/usr/bin/env python3
"""Simulate the exported button ladder, including chords and R/C corners.

Requires ngspice (included in the project's KiCad Docker image). Run after
export_schematic.py. Results model passive tolerances, not measured EMI or ADC.
"""
import argparse
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--netlist", type=Path, default=ROOT / "build/controller.xml")
parser.add_argument(
    "--output", type=Path, default=ROOT / "build/button-adc-simulation.json"
)
args = parser.parse_args()
simulator = shutil.which("ngspice")
if not simulator:
    raise SystemExit("ngspice is required; use kicad/kicad:9.0.9.")
xml = ET.parse(args.netlist).getroot()
components = {c.get("ref"): c for c in xml.findall("./components/comp")}
pins = {
    (n.get("ref"), n.get("pin")): net.get("name")
    for net in xml.findall("./nets/net")
    for n in net.findall("node")
}
nodes = {
    "3V3": "vcc",
    "GND": "0",
    "UI_BUTTON_ADC": "adc",
    "UI_BUTTON_OK": "keyok",
    "UI_BUTTON_DOWN": "keydown",
}
values = {"R12": 10000, "R13": 4700, "R14": 10000, "C15": 100e-9}
for ref, text in {"R12": "10k", "R13": "4.7k", "R14": "10k", "C15": "100nF"}.items():
    assert components[ref].findtext("value") == text, ref
    assert all(pins[ref, str(pin)] in nodes for pin in (1, 2)), ref
assert pins["J6", "6"] == "UI_BUTTON_ADC"
work = args.output.parent / "button-adc-spice"
work.mkdir(parents=True, exist_ok=True)


def component(ref, value):
    return f'{ref} {nodes[pins[ref,"1"]]} {nodes[pins[ref,"2"]]} {value:.12g}'


def run(name, lines):
    cir = work / (name + ".cir")
    cir.write_text("\n".join([name, *lines, ".end", ""]))
    result = subprocess.run(
        [simulator, "-b", str(cir)],
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    log = result.stdout + "\n" + result.stderr
    (work / (name + ".log")).write_text(log)
    return log


windows = {
    "UP": (-50, 250),
    "OK": (800, 1300),
    "DOWN": (1650, 2300),
    "NONE": (2850, 3600),
}
results = []
for pressed in itertools.product([False, True], repeat=3):
    expected = next(
        (name for name, on in zip(["UP", "OK", "DOWN"], pressed) if on), "NONE"
    )
    measured = []
    # 3V3 +/-5%, each of the three resistors +/-1%, independently.
    for corner, factors in enumerate(
        itertools.product([0.95, 1.05], [0.99, 1.01], [0.99, 1.01], [0.99, 1.01])
    ):
        lines = [f"VCC vcc 0 {3.3*factors[0]:.12g}"]
        lines += [
            component(ref, values[ref] * factor)
            for ref, factor in zip(["R12", "R13", "R14"], factors[1:])
        ]
        lines.append(component("C15", values["C15"]))
        for ref, on in zip(["SW2", "SW3", "SW4"], pressed):
            lines.append(
                f'R{ref} {nodes[pins[ref,"1"]]} {nodes[pins[ref,"2"]]} {0.1 if on else 1e12}'
            )
        lines += [".control", "op", "print v(adc)", "quit", ".endc"]
        name = (
            "buttons-" + "".join(str(int(q)) for q in pressed) + f"-corner-{corner:02d}"
        )
        log = run(name, lines)
        voltage = float(re.search(r"v\(adc\)\s*=\s*([-+\deE.]+)", log)[1]) * 1000
        measured.append(voltage)
        # C5 ATTEN3 calibrated error is +/-15mV in its specified range.
        lo, hi = windows[expected]
        adc_voltage = min(voltage, 3300)
        assert lo <= adc_voltage - 15 and adc_voltage + 15 <= hi, (
            pressed,
            voltage,
            expected,
        )
    results.append(
        {
            "pressed": [n for n, on in zip(["UP", "OK", "DOWN"], pressed) if on],
            "decoded": expected,
            "min_mv": min(measured),
            "max_mv": max(measured),
        }
    )

# Worst-case release: R12 +1%, C15 +10%, VDD +5%; UP opens at 5ms.
lines = [
    "VCC vcc 0 3.465",
    component("R12", 10100),
    component("R13", 4700),
    component("R14", 10000),
    component("C15", 110e-9),
    "VKEY control 0 PULSE(5 0 5m 1n 1n 20m 40m)",
    "SKEY adc 0 control 0 KEY",
    ".model KEY SW(Ron=0.1 Roff=1e12 Vt=1 Vh=0.1)",
    ".control",
    "tran 20u 20m",
    "meas tran release_10ms FIND v(adc) AT=15m",
    "quit",
    ".endc",
]
log = run("release-worst-rc", lines)
settled = float(re.search(r"release_10ms\s*=\s*([-+\deE.]+)", log, re.I)[1])
assert 3.465 - settled < 0.01, settled
report = {
    "result": "PASS",
    "dc_corner_runs": 128,
    "states": results,
    "assumptions": {
        "supply_v": [3.135, 3.465],
        "resistor_tolerance_percent": 1,
        "capacitor_tolerance_percent": 10,
        "closed_contact_ohm": 0.1,
        "open_contact_ohm": 1e12,
        "adc_error_budget_mv": 15,
        "adc_saturation_mv": 3300,
    },
    "worst_release_tau_ms": 1.111,
    "release_voltage_after_10ms_v": settled,
    "model_limits": "Ideal passives and switch resistance; no sampled ADC input, RF/relay interference, PCB parasitics, contact bounce or physical measurements.",
    "physical_tests_performed": False,
}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
