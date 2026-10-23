#!/usr/bin/env python3
"""Calculate the exported 24V monitor; optionally check its RC/clamp topology in SPICE.

The demonstration diode model is not an HJC manufacturer model. Power-off
simulation forces the rail to zero; it does not predict an unpowered DevKit.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def value(text):
    for suffix, scale in [("nF", 1e-9), ("k", 1e3)]:
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * scale
    return float(text)


def simulate(upper, lower, series, cap, ratio, tau, fc):
    executable = shutil.which("ngspice")
    if executable is None:
        raise RuntimeError("--spice requires ngspice")
    with tempfile.TemporaryDirectory(prefix="ulva-monitor-spice-") as td:
        work = Path(td)

        def run(name, supply, rail, commands):
            circuit = work / (name + ".cir")
            output = work / (name + ".dat")
            circuit.write_text(
                f"""ULVA monitor / demonstration diode model only
Vinput vin 0 {supply}
Vrail rail 0 DC {rail}
R31 vin div {upper}
R32 div 0 {lower}
R33 div adc {series}
C16 adc 0 {cap}
Dlower 0 adc DEMO
Dupper adc rail DEMO
.model DEMO D(IS=1e-8 N=1 RS=1 CJO=10p)
.control
set wr_singlescale
set wr_vecnames
set numdgt=12
{commands.format(output=output)}
quit
.endc
.end
"""
            )
            log = work / (name + ".log")
            subprocess.run(
                [executable, "-n", "-b", "-o", str(log), str(circuit)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if not output.exists():
                raise RuntimeError(log.read_text())
            return [
                [float(v) for v in line.split()]
                for line in output.read_text().splitlines()[1:]
                if line.strip()
            ]

        dc = []
        for vin, rail in [(0, 3.3), (24, 3.3), (36, 3.3), (40, 3.3), (24, 0)]:
            row = run(
                f"dc-{vin}-{rail}",
                f"DC {vin}",
                rail,
                "op\nwrdata {output} v(adc) i(Vrail)",
            )[0]
            adc, injection = row[1:3]
            if rail > 0 and not math.isclose(adc, ratio * vin, abs_tol=0.001):
                raise AssertionError("Normal DC divider is incorrectly connected")
            if rail == 0 and not (0 < adc < 0.35 and injection > 80e-6):
                raise AssertionError(
                    "Upper-clamp direction/power-off injection does not match topology"
                )
            dc.append(
                {
                    "vin_v": vin,
                    "forced_3v3_v": rail,
                    "adc_v": adc,
                    "rail_injection_a": injection,
                }
            )
        ac = run(
            "ac",
            "DC 24 AC 1",
            3.3,
            "ac dec 500 1 100000\nlet gain = mag(v(adc))\nwrdata {output} gain",
        )
        target = ratio / math.sqrt(2)
        crossing = next(i for i in range(1, len(ac)) if ac[i][1] <= target)
        a, z = ac[crossing - 1], ac[crossing]
        simulated_fc = a[0] + (z[0] - a[0]) * (a[1] - target) / (a[1] - z[1])
        if not math.isclose(simulated_fc, fc, rel_tol=0.01):
            raise AssertionError("SPICE RC corner differs from exported R/C values")
        tran = run(
            "step",
            "PULSE(0 24 1m 1n 1n 20m 40m)",
            3.3,
            "tran 1u 10m\nwrdata {output} v(adc)",
        )
        time_5tau = 0.001 + 5 * tau
        sample = min(tran, key=lambda row: abs(row[0] - time_5tau))
        expected = 24 * ratio * (1 - math.exp(-5))
        if not math.isclose(sample[1], expected, abs_tol=0.002):
            raise AssertionError("SPICE settling differs from exported R/C values")
        return {
            "result": "PASS",
            "simulator": "ngspice",
            "diode_model": "Demonstration only: IS=1e-8, N=1, RS=1, CJO=10p. Not HJC manufacturer/model fit or temperature bounds.",
            "dc_cases": dc,
            "rc_fc_hz": simulated_fc,
            "step_5tau_time_s": sample[0],
            "step_5tau_adc_v": sample[1],
            "scope": "Nominal resistor/capacitor behavior and diode polarity. Forced zero rail confirms a backfeed path; actual off-rail voltage/MCU state is not modeled.",
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("netlist", type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--spice", action="store_true")
    args = ap.parse_args()
    xml = ET.parse(args.netlist).getroot()
    components = {c.get("ref"): c for c in xml.findall("./components/comp")}
    upper, lower, series, cap = [
        value(components[ref].findtext("value")) for ref in ["R31", "R32", "R33", "C16"]
    ]
    ratio = lower / (upper + lower)
    rth = upper * lower / (upper + lower) + series
    tau = rth * cap
    fc = 1 / (2 * math.pi * tau)
    tolerance = 0.01  # Selected divider resistors' BOM/datasheet tolerance.
    low_ratio = (
        lower * (1 - tolerance) / (upper * (1 + tolerance) + lower * (1 - tolerance))
    )
    high_ratio = (
        lower * (1 + tolerance) / (upper * (1 - tolerance) + lower * (1 + tolerance))
    )
    if not (ratio * 36 < 3.3 and 40**2 * upper / (upper + lower) ** 2 < 0.1):
        raise AssertionError("Divider headroom/resistor dissipation is insufficient")
    report = {
        "result": "PASS",
        "netlist_sha256": hashlib.sha256(args.netlist.read_bytes()).hexdigest(),
        "values": {
            "upper_ohm": upper,
            "lower_ohm": lower,
            "series_ohm": series,
            "filter_f": cap,
        },
        "ratio": ratio,
        "nominal_adc_v": {str(v): v * ratio for v in [0, 24, 36, 40]},
        "divider_24v_a": 24 / (upper + lower),
        "adc_source_ohm": rth,
        "tau_s": tau,
        "fc_hz": fc,
        "settling_5tau_s": 5 * tau,
        "divider_1pct_24v_adc_range_v": [24 * low_ratio, 24 * high_ratio],
        "input_error_v_per_net_leakage_1ua": 1e-6 * rth / ratio,
        "upper_resistor_40v_w": 40**2 * upper / (upper + lower) ** 2,
        "24v_off_power_branch_source_upper_bound_a": 24 / upper,
        "physical_tests_performed": False,
        "limits": "40V is a divider calculation, not a board input rating. ADC calibration/sampling, diode leakage/temperature, transients and unpowered DevKit behavior require physical tests.",
        "spice": (
            simulate(upper, lower, series, cap, ratio, tau, fc)
            if args.spice
            else {"performed": False}
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "result": report["result"],
                "fc_hz": fc,
                "spice": report["spice"].get("result", "not requested"),
                "report": str(args.report),
            }
        )
    )


if __name__ == "__main__":
    main()
