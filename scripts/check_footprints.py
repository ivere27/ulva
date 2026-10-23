#!/usr/bin/env python3
"""Check footprint loading and symbol/pad numbering using an exported KiCad XML netlist.

Run with the Python interpreter shipped with KiCad (pcbnew must be importable):
  python3 scripts/check_footprints.py build/controller.xml --project-dir .

This checks library existence and pin numbers, not physical fit, net topology, or PCB DRC.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--system-footprints",
        type=Path,
        default=Path(
            os.environ.get("KICAD9_FOOTPRINT_DIR", "/usr/share/kicad/footprints")
        ),
    )
    args = parser.parse_args()
    try:
        import pcbnew
    except ImportError:
        parser.error(
            "pcbnew is unavailable; use the Python interpreter supplied with KiCad."
        )
    xml = ET.parse(args.netlist).getroot()
    symbol_pins = {
        (part.attrib["lib"], part.attrib["part"]): {
            pin.attrib["num"] for pin in part.findall("./pins/pin")
        }
        for part in xml.findall("./libparts/libpart")
    }
    issues = []
    checked = 0
    for component in xml.findall("./components/comp"):
        ref = component.attrib["ref"]
        footprint_id = component.findtext("footprint") or ""
        if ":" not in footprint_id:
            issues.append(
                {
                    "ref": ref,
                    "error": "missing_or_invalid_footprint",
                    "footprint": footprint_id,
                }
            )
            continue
        library_name, footprint_name = footprint_id.split(":", 1)
        local_library = args.project_dir / (library_name + ".pretty")
        library = (
            local_library
            if local_library.is_dir()
            else args.system_footprints / (library_name + ".pretty")
        )
        try:
            footprint = pcbnew.FootprintLoad(str(library), footprint_name)
        except Exception as error:
            issues.append(
                {
                    "ref": ref,
                    "error": "footprint_load_failed",
                    "footprint": footprint_id,
                    "detail": str(error),
                }
            )
            continue
        if footprint is None:
            issues.append(
                {"ref": ref, "error": "footprint_not_found", "footprint": footprint_id}
            )
            continue
        source = component.find("libsource")
        key = (
            (source.attrib["lib"], source.attrib["part"])
            if source is not None
            else None
        )
        if key not in symbol_pins:
            issues.append({"ref": ref, "error": "symbol_pin_definition_missing"})
            continue
        # Ignore unnumbered mechanical/NPTH pads; repeated same-number pads are allowed.
        pads = {pad.GetNumber() for pad in footprint.Pads() if pad.GetNumber()}
        expected = symbol_pins[key]
        if pads != expected:
            issues.append(
                {
                    "ref": ref,
                    "error": "pin_pad_number_mismatch",
                    "footprint": footprint_id,
                    "missing_pads": sorted(expected - pads),
                    "extra_pads": sorted(pads - expected),
                }
            )
        checked += 1
    result = {
        "components": len(xml.findall("./components/comp")),
        "checked": checked,
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
