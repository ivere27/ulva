# Order preparation

`prepare_orders.py` creates an offline selector and supplier upload files from
the current schematic and PCB. It does not create a cart, submit an order or
make a payment. It never substitutes parts from the Markdown BOM.

The [Orders tab](https://ivere27.github.io/ulva/#orders) contains the published
selector. It also works offline when opening `docs/index.html` directly, without
selecting any data files. Its embedded data reflects the last generated snapshot.

Use Python 3.10 or later with KiCad 9's `kicad-cli` on `PATH` and its `pcbnew`
Python module available to that interpreter. The first run exports a netlist
and placements from a temporary CAD snapshot. Later runs reuse a local cache
only when all CAD inputs and cached exports still match their recorded hashes.

From the repository root:

```sh
python3 tools/prepare_orders.py --boards 5
```

Open `build/orders/index.html` locally. Edit the board count and check either
PCBA or loose LCSC parts per reference; the choices cannot overlap. Uncheck
parts already on hand. Download the selection ZIP or individual files.

To update the shared viewer from this checkout's current CAD:

```sh
python3 tools/prepare_orders.py --boards 5 --update-docs
python3 scripts/export_viewer_info.py
```

`--update-docs` writes `docs/orders/index.html` after checking the source hashes.
CSV, selection and provenance files remain in `build/orders/` and can also be
downloaded from the selector. A matching fabrication ZIP is copied to
`docs/orders/` as a separate download when generated with `--gerbers` or already
present in the build output.

For a small initial assembly followed by optional upgrades, use the BOM's
[additional parts by stage](../docs/bom.md#minimal-bring-up-guide-additional-parts-by-stage).
It lists the carrier parts and external modules needed for each function, with
a workflow for placing a later loose-parts order.

- PCBA defaults include only fresh, identity-verified Basic or Preferred parts
  whose schematic ownership is `Assembly=JLC PCBA SMT` and PCB footprint is SMT.
- Verified Extended SMT parts can be selected explicitly. Unknown or stale tier
  evidence cannot be selected for PCBA. Schematic tier labels alone do not count
  as verification.
- Other valid schematic LCSC codes default to loose parts. A confirmed identity
  mismatch blocks both routes and appears in the manual list. Missing codes
  appear in that list too; no supplier number is guessed.
- DNP, excluded BOM entries and PCB features are not ordered. Original values,
  MPNs, assembly properties and catalog evidence remain visible per reference.

The generated files are:

| File | Contents |
| --- | --- |
| `jlc-bom.csv`, `jlc-cpl.csv` | The exact same selected reference set, one board |
| `lcsc-import.csv` | Exact LCSC codes grouped with board-count multiplied quantities |
| `manual-parts.csv` | Unresolved or blocked parts, original MPNs and required quantities |
| `selection.json` | Editable choices and source/model identity |
| `provenance.json` | CAD hashes, catalog evidence, original properties and selection |

JLC BOM and CPL are per board; select the same board quantity in the supplier's
order flow. LCSC quantities exclude spares, stock, MOQ and pack multiples.
Map **LCSC Part Number** and **Quantity** in the [LCSC BOM uploader](https://www.lcsc.com/bom),
then review matches and packing quantities. Review KiCad rotations and pin 1 in
the JLCPCB assembly preview. Tier labels do not establish a price or waived fee.

A saved browser selection can be checked and exported again:

```sh
python3 tools/prepare_orders.py --selection path/to/selection.json
python3 tools/prepare_orders.py --check-source build/orders/provenance.json
```

Selections from different CAD or catalog/eligibility data are rejected. A local
HTML file cannot detect subsequent CAD edits, so regenerate or check the source
before upload. The browser blocks exports after verified tier evidence expires.
CSV fields resembling spreadsheet formulas are rejected rather than rewritten.

To also generate a source-matched bare-board Gerber/drill ZIP:

```sh
python3 tools/prepare_orders.py --boards 5 --gerbers
```

This refills zones in a disposable snapshot and runs native DRC with schematic parity before writing
`build/orders/fabrication-gerbers.zip` and its provenance. It uses the project's auxiliary origin and records both the original and filled
PCB hashes; it never modifies authoritative CAD. The Gerber ZIP is separate
from the selection ZIP. Resolve any CAD/DRC issues before exporting. Prototype electrical, thermal and
mechanical qualification remains a separate task.

## Catalog updates

The included `parts-catalog.json` records exact MPN identity, tier, official
source URLs and UTC verification times. Preparation itself is offline; evidence
older than 30 days is treated as unknown. Refresh the catalog separately:

```sh
python3 tools/refresh_catalog.py
# After generating provenance for new/changed schematic parts:
python3 tools/refresh_catalog.py --provenance build/orders/provenance.json
python3 tools/prepare_orders.py --boards 5
```

A reviewed alternative can be supplied with `--catalog path/to/catalog.json`.
The schema is `{"schema_version":1,"parts":{"C123":{...}}}`. Each entry contains:

```json
{
  "tier": "basic",
  "verified": true,
  "identity_verified": true,
  "mpn": "EXACT-SCHEMATIC-MPN",
  "manufacturer": "Manufacturer",
  "package": "Package",
  "checked_at": "2026-10-21T09:00:00Z",
  "source_url": "https://jlcpcb.com/partdetail/..."
}
```

Valid tiers are `basic`, `preferred`, `extended` and `unknown`. PCBA eligibility
requires an official HTTPS JLCPCB source, a fresh timestamp, both verification
flags and an exact MPN match. A missing default catalog yields unknown tiers;
an explicitly supplied nonexistent catalog is an error. `blocked:true` or
`identity_verified:false` prevents ordering that code. `--max-catalog-age-days`
changes the explicit freshness policy. Supplier identity, availability and
assembly compatibility should be rechecked before placing the actual order.

## Tests

Run the order selection and consolidation unit tests:

```sh
python3 -m unittest discover -s tools
```
