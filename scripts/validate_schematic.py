#!/usr/bin/env python3
"""Check exported KiCad nets against the controller interface requirements.

Input is KiCad's exported XML netlist. Run after ERC.
This catches critical rail aliasing that KiCad can classify as a warning, and
checks physical pin numbers against the external devices' interface contracts.
"""
import argparse
import collections
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument("netlist", type=Path)
ap.add_argument("--report", type=Path)
a = ap.parse_args()
r = ET.parse(a.netlist).getroot()
components = {c.get("ref"): c for c in r.findall("./components/comp")}
net_by_pin = {}
names = {}
for net in r.findall("./nets/net"):
    code = net.get("code")
    names[code] = net.get("name").removeprefix("/")
    for pin in net.findall("node"):
        key = (pin.get("ref"), pin.get("pin"))
        if key in net_by_pin:
            raise AssertionError(f"Duplicate pin in netlist: {key}")
        net_by_pin[key] = code
checks = []


def require(ok, message):
    if not ok:
        raise AssertionError(message)
    checks.append(message)


def net(ref, pin):
    key = (ref, str(pin))
    require(key in net_by_pin, f"Required physical pin {ref}.{pin} is missing")
    return names[net_by_pin[key]]


def mapping(ref, expected):
    for p, want in expected.items():
        got = net(ref, p)
        require(got == want, f"{ref}.{p}: expected {want}, got {got}")


def value(ref, expected):
    require(ref in components, f"Required component {ref} is missing")
    actual = components[ref].findtext("value")
    require(actual == expected, f"{ref} value {actual} / required {expected}")


def nc(ref, pin):
    require(net(ref, pin).startswith("unconnected-"), f"{ref}.{pin} must be NC")


# Exact inventory for the current circuit.
expected_counts = {
    "AE": 1,
    "C": 16,
    "D": 7,
    "F": 3,
    "H": 8,
    "J": 27,
    "JP": 2,
    "K": 1,
    "L": 1,
    "NT": 1,
    "Q": 2,
    "R": 33,
    "SW": 4,
    "TP": 0,
    "U": 4,
}
expected_refs = {
    f"{prefix}{i}"
    for prefix, count in expected_counts.items()
    for i in range(1, count + 1)
}
expected_refs.add("TP2")
expected_refs -= {"C2", "F1", "R7", "R9", "R10"}
require(
    set(components) == expected_refs,
    "Physical component inventory matches the current circuit; no missing or extra references",
)
mapping("C1", {1: "3V3", 2: "GND"})
value("C1", "100nF")

# Official ESP32-C5-DevKitC-1 v1.2 PSRAM header numbers, J1/J3.
# Bus0 uses LP-I2C fixed GPIO2/3; bus1 uses HP-I2C GPIO9/10. GPIO15 is unavailable with PSRAM.
mapping(
    "J6",
    {
        1: "3V3",
        3: "I2C0_SDA",
        4: "I2C0_SCL",
        5: "RTC_INT_N",
        6: "UI_BUTTON_ADC",
        7: "CFG_ADC",
        8: "CAN2_TX",
        9: "CAN2_RX",
        10: "I2C1_SDA",
        11: "I2C1_SCL",
        12: "RF433_RX",
        13: "ZONE_ENABLE",
        14: "EXP_5V",
        15: "GND",
    },
)
mapping(
    "J7",
    {
        1: "GND",
        4: "CAN_TX",
        5: "CAN_RX",
        8: "UI_PIEZO_PWM",
        9: "VIN24_ADC",
        12: "GND",
        15: "GND",
    },
)
for p in (2, 16):
    nc("J6", p)
for p in (2, 3, 6, 7, 10, 11, 13, 14, 16):
    nc("J7", p)
# TX24/RX23 drive the native CAN FD transceiver U3.
# RGB27, native USB13/14, UART11/12 and BOOT28 retain DevKit functions.
official_gpio = {
    "J6": {3: 2, 4: 3, 5: 0, 6: 1, 7: 6, 8: 7, 9: 8, 10: 9, 11: 10, 12: 26, 13: 25},
    "J7": {2: 11, 3: 12, 4: 24, 5: 23, 7: 27, 8: 4, 9: 5, 11: 28, 13: 14, 14: 13},
}
for rr, gpios in official_gpio.items():
    part = components[rr].find("libsource")
    expected_part = "C5_DevKitC1_" + ("Left" if rr == "J6" else "Right")
    require(
        part.get("lib") == "Ulva" and part.get("part") == expected_part,
        rr + " uses the C5 v1.2 PSRAM socket symbol",
    )
    pins = {
        p.get("num"): p.get("name")
        for p in r.findall(
            f"./libparts/libpart[@lib='Ulva'][@part='{expected_part}']/pins/pin"
        )
    }
    for pin, gpio in gpios.items():
        require(
            pins[str(pin)].split("/")[0] == f"GPIO{gpio}",
            f"{rr}.{pin} is physical C5 GPIO{gpio}",
        )
require(
    len({g for ps in official_gpio.values() for g in ps.values()}) == 21,
    "All 21 exposed PSRAM-variant GPIOs have unique assignments/reservations",
)
require(
    {pin for pin, code in net_by_pin.items() if code == net_by_pin[("J7", "2")]}
    == {("J7", "2")},
    "GPIO11 remains unused by the carrier for DevKit UART TX",
)
mapping("TP2", {1: "GND"})
mapping("J5", {1: "UI_PIEZO", 4: "GND"})
nc("J5", 2)
nc("J5", 3)
mapping("R26", {1: "UI_PIEZO_PWM", 2: "UI_PIEZO"})
value("R26", "1k")
require(
    components["J5"].findtext("footprint")
    == "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "J5 is a four-position vertical male header for the two end contacts",
)
require(
    {pin for rr, pin in net_by_pin if rr == "J5"} == {"1", "2", "3", "4"},
    "J5 has four physical positions, with only pins 1 and 4 connected",
)
require(
    components["R26"].findtext("footprint") == "Resistor_SMD:R_0603_1608Metric"
    and components["R26"].findtext("./fields/field[@name='MPN']") == "0603WAF1001T5E",
    "Piezo series resistor reuses the existing 1k 0603 part",
)
for ref, signal in [
    ("SW2", "UI_BUTTON_ADC"),
    ("SW3", "UI_BUTTON_OK"),
    ("SW4", "UI_BUTTON_DOWN"),
]:
    mapping(ref, {1: signal, 2: "GND"})
    value(ref, "TS-1187A-B-A-B")
    require(
        components[ref].findtext("footprint") == "Ulva:SW_XKB_TS-1187A_5.1x5.1mm",
        "Button footprint follows selected XKB drawing",
    )
    require(
        components[ref].findtext("./fields/field[@name='LCSC']") == "C318884",
        "Button BOM uses C318884",
    )
# Three buttons share one calibrated ADC input; the taps form a series ladder.
for rr, val, pins, mpn, lcsc in [
    ("R12", "10k", {1: "3V3", 2: "UI_BUTTON_ADC"}, "0603WAF1002T5E", "C25804"),
    (
        "R13",
        "4.7k",
        {1: "UI_BUTTON_ADC", 2: "UI_BUTTON_OK"},
        "0603WAF4701T5E",
        "C23162",
    ),
    (
        "R14",
        "10k",
        {1: "UI_BUTTON_OK", 2: "UI_BUTTON_DOWN"},
        "0603WAF1002T5E",
        "C25804",
    ),
]:
    mapping(rr, pins)
    value(rr, val)
    require(
        components[rr].findtext("footprint") == "Resistor_SMD:R_0603_1608Metric"
        and components[rr].findtext("./fields/field[@name='MPN']") == mpn
        and components[rr].findtext("./fields/field[@name='LCSC']") == lcsc,
        rr + ": button ladder uses the specified 1% 0603 part",
    )
mapping("C15", {1: "UI_BUTTON_ADC", 2: "GND"})
value("C15", "100nF")
require(
    components["C15"].findtext("footprint") == "Capacitor_SMD:C_0603_1608Metric"
    and components["C15"].findtext("./fields/field[@name='MPN']") == "CC0603KRX7R9BB104"
    and components["C15"].findtext("./fields/field[@name='LCSC']") == "C14663",
    "C15 reuses the 100nF X7R 50V 0603 capacitor",
)
for signal, pins in {
    "UI_BUTTON_ADC": {
        ("J6", "6"),
        ("R12", "2"),
        ("R13", "1"),
        ("SW2", "1"),
        ("C15", "1"),
    },
    "UI_BUTTON_OK": {("R13", "2"), ("R14", "1"), ("SW3", "1")},
    "UI_BUTTON_DOWN": {("R14", "2"), ("SW4", "1")},
}.items():
    require(
        {pin for pin, code in net_by_pin.items() if names[code] == signal} == pins,
        signal + ": exact button ladder tap membership",
    )
for pin in ["7"]:
    require(
        {node for node, code in net_by_pin.items() if code == net_by_pin[("J7", pin)]}
        == {("J7", pin)},
        "J7." + pin + ": RGB27 reserved; no carrier connection",
    )

# HJC BAT54S manufacturer diagram: 1=A, 3=series junction, 2=K.
# The clamp and storage capacitor must be after the series resistor, with
# the divider returning to logic GND rather than the switched DC return.
for rr, val, pins, mpn, lcsc in [
    ("R31", "150k", {1: "VIN_24V", 2: "VIN24_DIV"}, "0603WAF1503T5E", "C22807"),
    ("R32", "10k", {1: "VIN24_DIV", 2: "GND"}, "0603WAF1002T5E", "C25804"),
    ("R33", "1k", {1: "VIN24_DIV", 2: "VIN24_ADC"}, "0603WAF1001T5E", "C21190"),
]:
    mapping(rr, pins)
    value(rr, val)
    require(
        components[rr].findtext("footprint") == "Resistor_SMD:R_0603_1608Metric"
        and components[rr].findtext("./fields/field[@name='MPN']") == mpn
        and components[rr].findtext("./fields/field[@name='LCSC']") == lcsc
        and components[rr].findtext("./fields/field[@name='JLCPCB_Library']")
        == "Basic",
        rr + ": specified 1% Basic resistor for the 24V monitor",
    )
mapping("C16", {1: "VIN24_ADC", 2: "GND"})
value("C16", "100nF")
require(
    components["C16"].findtext("footprint") == "Capacitor_SMD:C_0603_1608Metric"
    and components["C16"].findtext("./fields/field[@name='MPN']") == "CC0603KRX7R9BB104"
    and components["C16"].findtext("./fields/field[@name='LCSC']") == "C14663",
    "C16: X7R 50V storage/filter capacitor on the protected ADC node",
)
mapping("D7", {1: "GND", 2: "3V3", 3: "VIN24_ADC"})
value("D7", "BAT54S")
require(
    components["D7"].findtext("footprint") == "Package_TO_SOT_SMD:SOT-23"
    and components["D7"].findtext("./fields/field[@name='MPN']") == "BAT54S"
    and components["D7"].findtext("./fields/field[@name='Manufacturer']")
    == "hongjiacheng"
    and components["D7"].findtext("./fields/field[@name='LCSC']") == "C7420333"
    and components["D7"].findtext("./fields/field[@name='JLCPCB_Library']")
    == "Preferred Extended",
    "D7: selected HJC BAT54S SOT-23 and JLC Preferred Extended sourcing",
)
for signal, pins in {
    "VIN24_DIV": {("R31", "2"), ("R32", "1"), ("R33", "1")},
    "VIN24_ADC": {("R33", "2"), ("C16", "1"), ("D7", "3"), ("J7", "9")},
}.items():
    require(
        {pin for pin, code in net_by_pin.items() if names[code] == signal} == pins,
        signal + ": exact monitor node membership; no divider/series bypass",
    )
for rr in ["R31", "R32", "R33", "C16", "D7"]:
    require(
        components[rr].findtext("./fields/field[@name='Assembly']") == "JLC PCBA SMT",
        rr + ": included in outsourced SMT BOM/CPL",
    )
require(
    not {"UI_UP_N", "UI_OK_N", "UI_DOWN_N"} & set(names.values()),
    "Buttons have no separate digital GPIO nets",
)

for signal, pins in {
    "UI_PIEZO_PWM": {("J7", "8"), ("R26", "1")},
    "UI_PIEZO": {("R26", "2"), ("J5", "1")},
}.items():
    require(
        {pin for pin, code in net_by_pin.items() if names[code] == signal} == pins,
        signal + ": exact series path; no resistor bypass or power-rail connection",
    )
require(
    not {"UI_BUZZER", "UI_RGB_BUZZ"} & set(names.values()),
    "No active-buzzer or shared RGB/piezo nets",
)

# Boot configuration: two independent SPST contacts, pairs 1-4 and 2-3.
mapping("SW1", {1: "CFG_SW1_N", 2: "CFG_SW2_N", 3: "GND", 4: "GND"})
config_symbol = components["SW1"].find("libsource")
require(
    config_symbol is not None
    and config_symbol.get("lib") == "Switch"
    and config_symbol.get("part") == "SW_DIP_x02",
    "SW1 must contain two independent normally-open SPST configuration contacts",
)
value("SW1", "206-2ST")
require(
    components["SW1"].findtext("./fields/field[@name='MPN']") == "206-2ST",
    "SW1 must use the selected CTS two-position DIP switch",
)
require(
    components["SW1"].findtext("footprint")
    == "Button_Switch_THT:SW_DIP_SPSTx02_Slide_9.78x7.26mm_W7.62mm_P2.54mm",
    "SW1 must use the CTS 206 two-position body and DIP pad geometry",
)
for i, (pull, weight, resistance, mpn, lcsc) in enumerate(
    [
        ("R5", "R27", "10k", "0603WAF1002T5E", "C25804"),
        ("R6", "R28", "20k", "0603WAF2002T5E", "C4184"),
    ],
    start=1,
):
    signal = f"CFG_SW{i}_N"
    mapping(pull, {1: "3V3", 2: signal})
    value(pull, "1k")
    mapping(weight, {1: signal, 2: "CFG_ADC"})
    value(weight, resistance)
    require(
        {pin for pin, code in net_by_pin.items() if names[code] == signal}
        == {("SW1", str(i)), (pull, "2"), (weight, "1")},
        signal
        + ": independent grounded DIP contact, 1k pull-up and weighted ADC branch",
    )
    for rr, expected_mpn, expected_lcsc in [
        (pull, "0603WAF1001T5E", "C21190"),
        (weight, mpn, lcsc),
    ]:
        require(
            components[rr].findtext("footprint") == "Resistor_SMD:R_0603_1608Metric"
            and components[rr].findtext("./fields/field[@name='MPN']") == expected_mpn
            and components[rr].findtext("./fields/field[@name='LCSC']")
            == expected_lcsc,
            rr + ": selected 1% 0603 resistor and matching BOM number",
        )
mapping("C12", {1: "CFG_ADC", 2: "GND"})
value("C12", "100nF")
require(
    components["C12"].findtext("footprint") == "Capacitor_SMD:C_0603_1608Metric"
    and components["C12"].findtext("./fields/field[@name='MPN']")
    == "CC0603KRX7R9BB104",
    "C12 uses the existing 100nF X7R 50V 0603 capacitor",
)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "CFG_ADC"}
    == {("J6", "7"), ("R27", "2"), ("R28", "2"), ("C12", "1")},
    "Only GPIO6 ADC1_CH5 reads the weighted DIP voltage; no direct switch or supply bypass",
)
require(
    not {"CFG0_N", "CFG1_N"} & set(names.values()),
    "DIP switches do not use separate GPIO input nets",
)
# RTC alarm and RF receiver have independent GPIOs; no selection links.
mapping("R8", {1: "3V3", 2: "RTC_INT_N"})
value("R8", "10k")
mapping("J2", {5: "RTC_INT_N"})
mapping("R11", {1: "RF433_DO", 2: "RF433_RX"})
value("R11", "1k")
for ref in ("J4", "AE1", "R11"):
    require(
        components[ref].find("./property[@name='dnp']") is None,
        ref + " RF hardware is fitted independently of RTC",
    )
require(
    not {"CFG2_N", "CFG3_N", "GPIO23_IN"} & set(names.values()),
    "No unsupported DIP or shared GPIO23 nets",
)
for name, expected in {
    "RTC_INT_N": {("J6", "5"), ("J2", "5"), ("R8", "2")},
    "RF433_RX": {("J6", "12"), ("R11", "2")},
}.items():
    require(
        {pin for pin, code in net_by_pin.items() if names[code] == name} == expected,
        name + " has only its dedicated GPIO and interface connections",
    )

# Interrupt externally fused transformer wire2 before the separate EACRET return.
# J15/J12 are parallel alternative inputs: connect only one to the single
# externally fused source. Wire1 and that fuse are outside this PCB; the
# netlist can verify the relay path, but not the installed source or fuse.
for ref in ("J15", "J12", "J16", "J17", "J13", "J14"):
    require(ref in components, f"Required AC screw terminal {ref} is missing")
    mapping(ref, {1: "AC2_IN"})
    require(
        {pin for rr, pin in net_by_pin if rr == ref} == {"1"},
        f"{ref} must have exactly one electrical terminal",
    )
    terminal_symbol = components[ref].find("libsource")
    require(
        terminal_symbol is not None
        and terminal_symbol.get("lib") == "Connector"
        and terminal_symbol.get("part") == "Screw_Terminal_01x01",
        f"{ref} must use the single-position screw-terminal symbol",
    )
    require(
        components[ref].findtext("./fields/field[@name='MPN']") == "360272",
        f"{ref} must use the selected single-position METZ CONNECT screw terminal",
    )
    require(
        components[ref].findtext("footprint")
        == "TerminalBlock_MetzConnect:TerminalBlock_MetzConnect_360272_1x01_Horizontal_ScrewM2.6",
        f"{ref} must use the selected single-position METZ CONNECT footprint",
    )
mapping("K1", {"A1": "EXP_5V", "A2": "AC_RELAY_LOW", "13": "AC2_IN", "14": "EACRET"})
value("K1", "HF46F/5-HS1")
require(
    components["K1"].findtext("footprint") == "Ulva:Relay_SPST_Hongfa_HF46F_HS1",
    "K1 must use the HF46F-HS1 footprint with project IEC coil/contact pad numbers",
)
require(
    components["K1"].findtext("./fields/field[@name='MPN']") == "HF46F/5-HS1",
    "K1 must use the specified 5V normally-open relay",
)
relay_symbol = components["K1"].find("libsource")
require(
    relay_symbol is not None
    and relay_symbol.get("lib") == "Relay"
    and relay_symbol.get("part") == "Relay_SPST-NO",
    "K1 symbol must represent a normally-open SPST mechanical contact",
)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "AC2_IN"}
    == {(r, "1") for r in ("J15", "J12", "J16", "J17", "J13", "J14")} | {("K1", "13")},
    "Externally fused transformer wire2 reaches only J15.1/J12.1 and the K1 contact input",
)
for ref, prefix, ac in [
    ("J8", "I2C0", True),
    ("J10", "I2C0", False),
    ("J9", "I2C1", True),
    ("J11", "I2C1", False),
]:
    mapping(ref, {7: prefix + "_SDA", 8: prefix + "_SCL", 9: "EXP_5V", 10: "GND"})
    for p in (5, 6) if ac else (3, 4):
        mapping(ref, {p: "EACRET" if ac else "DC_ZONE_RETURN"})
    for p in (1, 2, 3, 4) if ac else (1, 2, 5, 6):
        nc(ref, p)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "EACRET"}
    == {("K1", "14"), ("J8", "5"), ("J8", "6"), ("J9", "5"), ("J9", "6")},
    "EACRET connects only K1 and AC return pins; no added ground bond",
)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "DC_ZONE_RETURN"}
    == {("Q2", "3"), ("J10", "3"), ("J10", "4"), ("J11", "3"), ("J11", "4")},
    "DC_ZONE_RETURN connects only Q2 drain and DC return pins; no added ground bond",
)
require(
    len({net_by_pin[("J8", "5")], net_by_pin[("J10", "3")], net_by_pin[("J8", "10")]})
    == 3,
    "EACRET, DC_ZONE_RETURN and board GND are distinct nets",
)
for ac_ref, dc_ref in [("J8", "J10"), ("J9", "J11")]:
    require(
        all(
            net_by_pin[(ac_ref, p)] == net_by_pin[(dc_ref, p)]
            for p in ("7", "8", "9", "10")
        ),
        f"{ac_ref}/{dc_ref} share one I2C bus, power and fixed logic reference",
    )
require(
    net_by_pin[("J8", "7")] != net_by_pin[("J9", "7")]
    and net_by_pin[("J8", "8")] != net_by_pin[("J9", "8")],
    "I2C0 and I2C1 (HP) expansion buses remain electrically separate",
)
# GPIO25 drives both fail-off paths. The AC MOSFET sinks the relay coil current;
# the optocoupler operates a board-5V-powered, single-MOSFET DC command-return cut.
mapping("Q1", {1: "AC_RELAY_GATE", 2: "GND", 3: "AC_RELAY_LOW"})
value("Q1", "AO3400A")
require(
    components["Q1"].findtext("footprint") == "Package_TO_SOT_SMD:SOT-23",
    "Q1 must use the AO3400A SOT-23 gate/source/drain footprint",
)
require(
    components["Q1"].findtext("./fields/field[@name='MPN']") == "AO3400A",
    "Q1 must use the specified logic-level coil driver",
)
mapping("R17", {1: "ZONE_ENABLE", 2: "AC_RELAY_GATE"})
value("R17", "1k")
mapping("R15", {1: "ZONE_ENABLE", 2: "GND"})
value("R15", "10k")
mapping("D3", {1: "EXP_5V", 2: "AC_RELAY_LOW"})
value("D3", "1N4148W")
require(
    components["D3"].findtext("footprint") == "Diode_SMD:D_SOD-123",
    "D3 must use the specified coil-flyback diode footprint",
)
require(
    components["D3"].findtext("./fields/field[@name='MPN']") == "1N4148W"
    and components["D3"].findtext("./fields/field[@name='LCSC']") == "C81598",
    "D3 must use the specified coil-flyback diode",
)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "AC_RELAY_LOW"}
    == {("K1", "A2"), ("Q1", "3"), ("D3", "2")},
    "Relay coil low side reaches only the MOSFET drain and flyback diode anode",
)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "AC_RELAY_GATE"}
    == {("Q1", "1"), ("R17", "2")},
    "Relay gate reaches the shared R15 pull-down through R17",
)

for ref in ("J18", "J19", "J20", "J21", "J22", "J23"):
    mapping(ref, {1: "DC_DRIVER_COM"})
    require(
        components[ref].findtext("footprint")
        == components["J25"].findtext("footprint"),
        ref + " uses the selected COM terminal",
    )
mapping("J25", {1: "POWER_0V"})
require(
    {pin for rr, pin in net_by_pin if rr == "J25"} == {"1"},
    "J25 has only the supply-negative pin",
)
require(
    components["J25"].findtext("footprint")
    == "TerminalBlock_MetzConnect:TerminalBlock_MetzConnect_360272_1x01_Horizontal_ScrewM2.6",
    "J25 uses the single-position supply-negative screw terminal",
)
require(
    components["J25"].findtext("./fields/field[@name='MPN']") == "360272",
    "J25 uses METZ CONNECT 360272",
)
mapping("R18", {1: "ZONE_ENABLE", 2: "DC_LED_A"})
value("R18", "330")
mapping("U1", {1: "DC_LED_A", 2: "GND", 3: "DC_GATE", 4: "DC_OPTO_C"})
value("U1", "LTV-817S-TA1-C")
require(
    components["U1"].findtext("footprint") == "Package_DIP:SMDIP-4_W9.53mm",
    "U1 must use the selected gull-wing SMDIP-4 footprint",
)
mapping("Q2", {1: "DC_GATE", 2: "DC_DRIVER_COM", 3: "DC_ZONE_RETURN"})
value("Q2", "AO3400A")
require(
    components["Q2"].findtext("footprint") == "Package_TO_SOT_SMD:SOT-23",
    "Q2 must use the selected AO3400A SOT-23 footprint",
)
mapping("D2", {1: "DC_DRIVER_COM", 3: "DC_GATE"})
nc("D2", 2)
value("D2", "BZX84C8V2")
for field, expected in {
    "Manufacturer": "hongjiacheng",
    "LCSC": "C22395522",
    "JLCPCB_Library": "Preferred Extended",
}.items():
    require(
        components["D2"].findtext(f"./fields/field[@name='{field}']") == expected,
        f"D2 {field} must match the selected C22395522, independently of Q2",
    )
mapping("R19", {1: "EXP_5V", 2: "DC_OPTO_C"})
value("R19", "10k")
mapping("R20", {1: "DC_GATE", 2: "DC_DRIVER_COM"})
value("R20", "47k")
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "DC_DRIVER_COM"}
    == {(r, "1") for r in ("J18", "J19", "J20", "J21", "J22", "J23")}
    | {("Q2", "2"), ("R20", "2"), ("D2", "1")},
    "DRIVER COM reaches only six command terminals, Q2 source and gate protection",
)
require(
    "DC_GATE_24V" not in names.values(), "No external positive DC gate supply remains"
)
require(
    net_by_pin[("J25", "1")] != net_by_pin[("J6", "15")],
    "POWER_0V and GND retain distinct net names at the explicitly checked NT1 copper bond",
)

# Independent native CAN FD channels share supply/ground only.
for prefix, u, j, d, f, term, pull, jp, c1, c2, tx, rx in [
    (
        "CAN",
        "U3",
        "J26",
        "D5",
        "F2",
        "R24",
        "R25",
        "JP1",
        "C10",
        "C11",
        ("J7", "4"),
        ("J7", "5"),
    ),
    (
        "CAN2",
        "U4",
        "J27",
        "D6",
        "F3",
        "R29",
        "R30",
        "JP2",
        "C13",
        "C14",
        ("J6", "8"),
        ("J6", "9"),
    ),
]:
    n = lambda suffix: prefix + "_" + suffix
    mapping(
        u,
        {
            1: n("TX"),
            2: "GND",
            3: "3V3",
            4: n("RX"),
            5: "GND",
            6: n("L"),
            7: n("H"),
            8: "GND",
        },
    )
    value(u, "TPT1334-SO1R")
    mapping(j, {1: n("24V"), 2: "POWER_0V", 3: n("H"), 4: n("L")})
    mapping(d, {1: n("H"), 2: n("L"), 3: "GND"})
    value(d, "PESD2CANFD24V-TR")
    mapping(f, {1: "VIN_24V", 2: n("24V")})
    value(f, "1.5A fast")
    mapping(term, {1: n("H"), 2: n("TERM")})
    value(term, "120")
    mapping(jp, {1: n("TERM"), 2: n("L")})
    value(jp, "TERM ON")
    mapping(pull, {1: "3V3", 2: n("TX")})
    value(pull, "10k")
    for rr, val in [(c1, "100nF"), (c2, "1uF")]:
        mapping(rr, {1: "3V3", 2: "GND"})
        value(rr, val)
    for suffix, want in {
        "TX": {tx, (u, "1"), (pull, "2")},
        "RX": {rx, (u, "4")},
        "H": {(u, "7"), (j, "3"), (d, "1"), (term, "1")},
        "L": {(u, "6"), (j, "4"), (d, "2"), (jp, "2")},
        "TERM": {(jp, "1"), (term, "2")},
        "24V": {(f, "2"), (j, "1")},
    }.items():
        require(
            {pin for pin, code in net_by_pin.items() if names[code] == n(suffix)}
            == want,
            n(suffix) + ": exact independent CAN endpoint connections",
        )
    for rr, mpn, lcsc in [
        (u, "TPT1334-SO1R", "C44859616"),
        (j, "XT30PW(2+2)-M.G.B", "C19268030"),
        (f, "046701.5NRHF", "C187608"),
        (d, "PESD2CANFD24V-TR", "C552486"),
        (term, "1206W4F1200T5E", "C17909"),
        (pull, "0603WAF1002T5E", "C25804"),
        (c1, "CC0603KRX7R9BB104", "C14663"),
        (c2, "CL10A105KB8NNNC", "C15849"),
    ]:
        require(
            components[rr].findtext("./fields/field[@name='MPN']") == mpn
            and components[rr].findtext("./fields/field[@name='LCSC']") == lcsc,
            rr + ": selected manufacturer part and LCSC code",
        )
    require(
        components[j].findtext("footprint") == "Ulva:AMASS_XT30PW_2plus2_M_Horizontal",
        j + ": four-pin AMASS footprint assignment",
    )
    require(
        components[u].findtext("footprint") == "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        u + ": selected SOP8 package",
    )
    require(
        components[jp].findtext("./fields/field[@name='Assembly']")
        == "PCB copper; no purchased part",
        jp + ": no purchased jumper required",
    )
require(
    len({net_by_pin[(u, p)] for u in ("U3", "U4") for p in ("1", "4", "6", "7")}) == 8,
    "Both CAN TX, RX, H and L sets remain distinct; no parallel-port wiring",
)


# 24V -> 5V logic supply, verified against SY8301ABC top-view pin numbers.
def power_net(base):
    matches = [
        name for name in names.values() if name == base or name.endswith("/" + base)
    ]
    require(len(matches) == 1, "Exactly one power net named " + base)
    return matches[0]


vin, bs, lx, raw, fb, div_top = [
    power_net(name)
    for name in ("VIN_24V", "BUCK_BS", "BUCK_LX", "BUCK_5V1", "BUCK_FB", "BUCK_DIV_TOP")
]
mapping("J24", {1: vin})
value("J24", "24V DC +")
mapping("NT1", {1: "POWER_0V", 2: "GND"})
require(
    components["NT1"].findtext("footprint") == "NetTie:NetTie-2_SMD_Pad2.0mm",
    "NT1 uses a copper-connected net-tie footprint, not an uninstalled jumper",
)
require(
    components["NT1"].find("./property[@name='exclude_from_bom']") is not None,
    "NT1 copper bond must not become a purchased component",
)
mapping("U2", {1: bs, 2: "GND", 3: fb, 4: vin, 5: vin, 6: lx})
value("U2", "SY8301ABC")
mapping("L1", {1: lx, 2: raw})
value("L1", "4.7uH")
mapping("D4", {1: "EXP_5V", 2: raw})
value("D4", "SS34")
for ref in ("C3", "C4", "C8", "C9"):
    mapping(ref, {1: vin, 2: "GND"})
    value(ref, "2.2uF / 50V")
mapping("C5", {1: bs, 2: lx})
value("C5", "100nF / 50V")
for ref in ("C6", "C7"):
    mapping(ref, {1: raw, 2: "GND"})
    value(ref, "47uF / 10V")
mapping("R21", {1: raw, 2: div_top})
value("R21", "51k")
mapping("R22", {1: div_top, 2: fb})
value("R22", "2.7k")
mapping("R23", {1: fb, 2: "GND"})
value("R23", "10k")
for name, expected in {
    vin: {
        ("F2", "1"),
        ("F3", "1"),
        ("J24", "1"),
        ("U2", "4"),
        ("U2", "5"),
        ("C3", "1"),
        ("C4", "1"),
        ("C8", "1"),
        ("C9", "1"),
        ("R31", "1"),
    },
    bs: {("U2", "1"), ("C5", "1")},
    lx: {("U2", "6"), ("C5", "2"), ("L1", "1")},
    raw: {("L1", "2"), ("C6", "1"), ("C7", "1"), ("R21", "1"), ("D4", "2")},
    div_top: {("R21", "2"), ("R22", "1")},
    fb: {("U2", "3"), ("R22", "2"), ("R23", "1")},
}.items():
    require(
        {pin for pin, code in net_by_pin.items() if names[code] == name} == expected,
        name + " has exactly the intended power-stage connections",
    )
for ref, mpn, code, category, assembly in [
    ("U2", "SY8301ABC", "C2927130", "Extended", "Manual SMT"),
    ("L1", "SWPA6045S4R7MT", "C78804", "Extended", "Manual SMT"),
    ("D4", "SS34", "C8678", "Basic", "JLC PCBA SMT"),
    ("C3", "CL31B225KBHNNNE", "C50254", "Basic", "JLC PCBA SMT"),
    ("C4", "CL31B225KBHNNNE", "C50254", "Basic", "JLC PCBA SMT"),
    ("C8", "CL31B225KBHNNNE", "C50254", "Basic", "JLC PCBA SMT"),
    ("C9", "CL31B225KBHNNNE", "C50254", "Basic", "JLC PCBA SMT"),
    ("C5", "CC0603KRX7R9BB104", "C14663", "Basic", "JLC PCBA SMT"),
    ("C6", "CL31A476MPHNNNE", "C96123", "Basic", "JLC PCBA SMT"),
    ("C7", "CL31A476MPHNNNE", "C96123", "Basic", "JLC PCBA SMT"),
    ("R21", "0603WAF5102T5E", "C23196", "Basic", "JLC PCBA SMT"),
    ("R22", "0603WAF2701T5E", "C13167", "Basic", "JLC PCBA SMT"),
    ("R23", "0603WAF1002T5E", "C25804", "Basic", "JLC PCBA SMT"),
]:
    for field, expected in {
        "MPN": mpn,
        "LCSC": code,
        "JLCPCB_Library": category,
        "Assembly": assembly,
    }.items():
        require(
            components[ref].findtext(f"./fields/field[@name='{field}']") == expected,
            f"{ref}: selected {field} is {expected}",
        )
require(
    components["J24"].findtext("footprint") == components["J25"].findtext("footprint")
    and components["J24"].findtext("./fields/field[@name='MPN']") == "360272",
    "New positive terminal uses the existing METZ360272 mechanical standard",
)
require(
    components["U2"].findtext("footprint")
    == "Package_TO_SOT_SMD:SOT-23-6_Handsoldering"
    and components["L1"].findtext("footprint") == "Ulva:L_Sunlord_SWPA6045_6x6mm",
    "U2/L1 use the selected hand-solderable footprints",
)
vraw = 0.8 * (1 + (51 + 2.7) / 10)
vraw_min = 0.8 * 0.99 * (1 + 53.7 * 0.99 / (10 * 1.01))
vraw_max = 0.8 * 1.01 * (1 + 53.7 * 1.01 / (10 * 0.99))
require(
    abs(vraw - 5.096) < 1e-9 and vraw_max <= 5.25 and vraw_min - 0.55 >= 4.4,
    "Nominal and 1% divider/FB tolerance leave the intended static 5V-rail range with D4",
)

# Direct expander I2C: logic stays pulled up to 3V3 while EVIN stays EXP_5V.
# Attached boards' pull-ups and input thresholds are external qualifications.
mapping("J1", {1: "3V3", 2: "I2C1_SDA", 3: "GND", 4: "I2C1_SCL"})
mapping("J2", {1: "3V3", 2: "GND", 3: "I2C0_SDA", 4: "I2C0_SCL"})
mapping("J3", {1: "GND", 2: "3V3", 3: "I2C0_SCL", 4: "I2C0_SDA"})
direct_i2c = {
    "I2C0_SDA": [
        ("J6", "3"),
        ("J2", "3"),
        ("J3", "4"),
        ("J8", "7"),
        ("J10", "7"),
        ("R1", "2"),
    ],
    "I2C0_SCL": [
        ("J6", "4"),
        ("J2", "4"),
        ("J3", "3"),
        ("J8", "8"),
        ("J10", "8"),
        ("R2", "2"),
    ],
    "I2C1_SDA": [("J6", "10"), ("J1", "2"), ("J9", "7"), ("J11", "7"), ("R3", "2")],
    "I2C1_SCL": [("J6", "11"), ("J1", "4"), ("J9", "8"), ("J11", "8"), ("R4", "2")],
}
for ref, nm in [
    ("R1", "I2C0_SDA"),
    ("R2", "I2C0_SCL"),
    ("R3", "I2C1_SDA"),
    ("R4", "I2C1_SCL"),
]:
    mapping(ref, {1: "3V3", 2: nm})
    value(ref, "4.7k")
require(
    not {"SW_I2C_SDA", "SW_I2C_SCL", "PROBE_3V3"} & set(names.values()),
    "No software I2C signals or dedicated probe supply",
)
for nm, pins in direct_i2c.items():
    require(
        len({net_by_pin[pin] for pin in pins}) == 1,
        nm
        + " directly joins its MCU pin, local devices, both expansion ports and 3V3 pull-up",
    )
direct_i2c_codes = {net_by_pin[pins[0]] for pins in direct_i2c.values()}
require(
    len(direct_i2c_codes) == 4,
    "The two direct I2C buses keep all four SDA/SCL conductors distinct",
)
for nm in ("EXP0_SDA_5V", "EXP0_SCL_5V", "EXP1_SDA_5V", "EXP1_SCL_5V"):
    require(
        nm not in names.values(), "No separate expander 5V signal net remains: " + nm
    )

# No buffered field interface or software I2C circuit is present.
# J1's local DHT20 and both direct expander buses remain checked above.
field_net_prefixes = (
    "FIELD_",
    "SWI2C_EXT_",
    "SW_I2C_EXT_",
    "SW-I2C-EXT",
    "MCU_EXT_",
    "J2_",
    "J15_",
)
remaining_field_nets = sorted(
    nm for nm in names.values() if nm.rsplit("/", 1)[-1].startswith(field_net_prefixes)
)
require(
    not remaining_field_nets,
    "No wired field-sensor supply or signal nets remain: "
    + ", ".join(remaining_field_nets),
)
# Shared buck/DevKit USB 5V distribution. The expansion load budget is an operating
# condition; the carrier has no onboard shared expansion current limiter.
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "EXP_5V"}
    == {
        ("J6", "14"),
        ("J8", "9"),
        ("J10", "9"),
        ("J9", "9"),
        ("J11", "9"),
        ("K1", "A1"),
        ("D3", "1"),
        ("R19", "1"),
        ("D4", "1"),
    },
    "D4-fed 5V rail joins DevKit, four expansion ports, relay coil and DC gate bias",
)
for nm in ("MCU_5V", "EXP_ILIM", "EXP_POWER_FAULT_N", "EXP_POWER_FAULT_GPIO"):
    require(nm not in names.values(), "No shared-limiter net: " + nm)
for forbidden in (
    "AC1_IN",
    "AC1_FUSED/GND",
    "J2_3V3",
    "DC_ZONE_RETURN0_IN",
    "DC_ZONE_RETURN1_IN",
    "DC_GATE0",
    "DC_GATE1",
    "AC_BUS_FUSED",
    "AC0_FUSED",
    "AC1_FUSED",
    "AC0_LED_A",
    "AC1_LED_A",
    "AC_COM0",
    "AC_COM1",
    "AC_HOT",
    "AC_FUSED",
    "AC_COM",
    "COIL_LOOP_IN",
    "COIL_LOOP_OUT",
    "COIL_LOOP_FUSED",
    "SSR_LED_SINK",
    "AC_LED_A",
    "AC2_FUSED",
    "SSR_BASE",
    "AC_PGATE",
    "AC_BUF_OUT",
    "AC_TRIAC_GATE",
):
    require(forbidden not in names.values(), "Obsolete net " + forbidden)
require(
    not any(n.startswith("unconnected-(K3-") for n in names.values()),
    "No obsolete K3 no-connect net remains",
)

# Catch rail aliasing and shorts through copper, fuses, or 0-ohm links.
short_graph = collections.defaultdict(set)
for ref, c in components.items():
    v = c.findtext("value", "").strip()
    if ref.startswith(("F", "NT")) or (ref.startswith("R") and v in ("0", "0R", "0Ω")):
        ns = [code for (rr, p), code in net_by_pin.items() if rr == ref]
        if len(ns) == 2:
            short_graph[ns[0]].add(ns[1])
            short_graph[ns[1]].add(ns[0])


def reachable(start, graph):
    seen = {start}
    stack = [start]
    while stack:
        for q in graph[stack.pop()] - seen:
            seen.add(q)
            stack.append(q)
    return seen


rail_pins = [("J6", 1), ("J6", 14), ("J6", 15), ("J15", 1), ("J24", 1)]
rail_codes = [net_by_pin[(rr, str(p))] for rr, p in rail_pins]
require(
    len(set(rail_codes)) == len(rail_codes),
    "Supply/domain nets must all remain distinct",
)
for i, c in enumerate(rail_codes):
    require(
        not (set(rail_codes[i + 1 :]) & reachable(c, short_graph)),
        "No rail/domain short through fuses or0ohm links: " + names[c],
    )
ground_reachable = reachable(net_by_pin[("J6", "15")], short_graph)
require(
    net_by_pin[("J18", "1")] not in ground_reachable,
    "No onboard copper/fuse/0-ohm bond from DRIVER COM to power or logic ground",
)
require(
    {pin for pin, code in net_by_pin.items() if names[code] == "POWER_0V"}
    == {("J25", "1"), ("J26", "2"), ("J27", "2"), ("NT1", "1")},
    "POWER_0V contains only input negative, CAN negative and the logic-ground bond",
)
require(
    net_by_pin[("J25", "1")] in ground_reachable,
    "The intentional NT1 copper bond returns buck current through J25",
)
require(
    net_by_pin[("J10", "3")] not in ground_reachable
    and net_by_pin[("J8", "5")] not in ground_reachable,
    "The supply-ground bond does not directly bypass DC_ZONE_RETURN or EACRET cutoff",
)
require(
    len({net_by_pin[pins[0]] for pins in direct_i2c.values()}) == 4,
    "Both hardware I2C buses have distinct SDA/SCL nets",
)
# Include nonzero resistor routes when checking the direct I2C pull-up voltage.
res_graph = collections.defaultdict(set)
for ref, c in components.items():
    if not ref.startswith(("R", "F")):
        continue
    ns = [code for (rr, p), code in net_by_pin.items() if rr == ref]
    if len(ns) == 2:
        res_graph[ns[0]].add(ns[1])
        res_graph[ns[1]].add(ns[0])
# Detect any added 5V pull-up, including a renamed resistor or series links.
# The carrier netlist cannot inspect pull-ups on attached external modules.
five_volt_rails = {net_by_pin[("J6", "14")]}
for nm, pins in direct_i2c.items():
    require(
        not (five_volt_rails & reachable(net_by_pin[pins[0]], res_graph)),
        "No passive pull-up or link from " + nm + " to a 5V supply",
    )
for ref, c in components.items():
    require(bool(c.findtext("footprint")), ref + " has physical footprint")
report = {
    "result": "PASS",
    "checks": len(checks),
    "physical_components": len(components),
    "design_status": "SCHEMATIC: ESP32-C5-DevKitC-1 v1.2 PSRAM. Two-position DIP through R5/R6 1k, R27 10k, R28 20k and C12 100nF into GPIO6 ADC1_CH5; CAN1 GPIO24/23, CAN2 GPIO7/8, UP/OK/DOWN share GPIO1 ADC1_CH0 via R12=10k, R13=4.7k, R14=10k and C15=100nF; GPIO5 ADC1_CH4 monitors24V through R31 150k/R32 10k, R33 1k, C16 100nF and HJC BAT54S D7; dedicated piezo GPIO4; RGB27 reserved. Independent CAN1 U3/J26 TX24/RX23 and CAN2 U4/J27 TX7/RX8, each with ESD, selectable120ohm and separate24V fuse; combined control-power output budget1A. PCB layout and routing are validated separately. RGB27 on DevKit only; dedicated GPIO4 passive piezo via R26 1k/J5 1x4 male; USB/UART/BOOT retained; RTC INT on GPIO0, enable on GPIO25, bus0 LP-I2C on GPIO2/3 and bus1 HP-I2C on GPIO9/10. POWER_0V (J25/CAN/NT1) is separate from six DRIVER COM terminals on the PCB; U1/Q2 gate drive requires an external common-negative reference. PCB and physical qualification are recorded separately.",
    "scope": "Exported net connectivity, pin contracts, passive fault paths; external fuse installation and physical EMC/thermal/motor behavior require separate qualification.",
}
if a.report:
    a.report.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
