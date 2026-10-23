#!/usr/bin/env python3
"""Export the flat controller BOM from a KiCad XML netlist.

The BOM intentionally keeps one row per schematic reference, including DNP
options and mechanical holes, so its row count can be checked against PCB and
mechanical validation reports.
"""

import argparse
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def natural_reference(reference: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([^0-9]+)([0-9]+)(.*)", reference)
    if not match:
        return reference, -1, ""
    return match.group(1), int(match.group(2)), match.group(3)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("netlist", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--expect-count", type=int)
args = parser.parse_args()

root = ET.parse(args.netlist).getroot()
components = root.findall("./components/comp")
if args.expect_count is not None and len(components) != args.expect_count:
    raise SystemExit(
        f"Expected {args.expect_count} components, found {len(components)}"
    )

references = [component.get("ref", "") for component in components]
if not all(references) or len(set(references)) != len(references):
    raise SystemExit("Component references are blank or duplicated")

rows = []
for component in sorted(
    components, key=lambda item: natural_reference(item.get("ref", ""))
):
    fields = {
        field.get("name", ""): field.text or ""
        for field in component.findall("./fields/field")
    }
    properties = {
        prop.get("name", ""): prop.get("value", "")
        for prop in component.findall("./property")
    }
    if "exclude_from_bom" in properties:
        continue
    rows.append(
        {
            "Reference": component.get("ref", ""),
            "Value": component.findtext("value", default=""),
            "Footprint": component.findtext("footprint", default=""),
            "MPN": fields.get("MPN", properties.get("MPN", "")),
            "Manufacturer": fields.get(
                "Manufacturer", properties.get("Manufacturer", "")
            ),
            "LCSC": fields.get("LCSC", properties.get("LCSC", "")),
            "JLCPCB_Library": fields.get(
                "JLCPCB_Library", properties.get("JLCPCB_Library", "")
            ),
            "Assembly": fields.get("Assembly", properties.get("Assembly", "")),
            "Fuse_MPN": fields.get("Fuse_MPN", properties.get("Fuse_MPN", "")),
            "DNP": "yes" if "dnp" in properties else "no",
            "Datasheet": component.findtext("datasheet", default="")
            or fields.get("Datasheet", ""),
            "Design note": fields.get("Design_Note", properties.get("Design_Note", "")),
        }
    )

args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"BOM: {len(rows)} references -> {args.output}")
