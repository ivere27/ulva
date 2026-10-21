#!/usr/bin/env python3
"""Refresh the reviewed parts catalog from JLCPCB's public component search.

This queries a read-only search endpoint. It does not log in, add cart items,
request quotes or place orders. Use --provenance to include the current CAD's
part numbers after generating an order selector.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request


ENDPOINT = (
    "https://jlcpcb.com/api/overseas-pcb-order/v1/"
    "shoppingCart/smtGood/selectSmtComponentList/v2"
)
DEFAULT_CATALOG = Path(__file__).resolve().with_name("parts-catalog.json")


def approved_parts(catalog, provenance=None):
    """Use explicit identifiers only; never guess a substitute from a value."""
    if not isinstance(catalog, dict) or not isinstance(catalog.get("parts"), dict):
        raise ValueError("Catalog needs a parts object keyed by LCSC code")
    if provenance is None:
        return {code: {entry.get("mpn", "").strip()}
                for code, entry in catalog.get("parts", {}).items()
                if re.fullmatch(r"C\d+", code) and isinstance(entry, dict)}
    if not isinstance(provenance, dict) or not isinstance(provenance.get("parts"), list):
        raise ValueError("Provenance needs a parts list")
    result = {}
    for row in provenance.get("parts", []):
        if not isinstance(row, dict):
            raise ValueError("Provenance parts must be objects")
        code = str(row.get("lcsc", "")).strip()
        if re.fullmatch(r"C\d+", code):
            result.setdefault(code, set()).add(str(row.get("mpn", "")).strip())
    return result


def classify(entry):
    """A missing promotional flag is not evidence that a part is Extended."""
    kind = entry.get("componentLibraryType")
    preferred = entry.get("preferredComponentFlag")
    if kind == "base":
        return "basic"
    if kind == "expand" and preferred is True:
        return "preferred"
    if kind == "expand" and preferred is False:
        return "extended"
    return "unknown"


def parse_result(payload, code, expected_mpns):
    if not isinstance(payload, dict):
        raise ValueError("Component search response must be an object")
    data = payload.get("data", {})
    if payload.get("code") != 200 or not isinstance(data, dict):
        raise ValueError("Component search did not return a successful result")
    page = data.get("componentPageInfo", {})
    entries = page.get("list", []) if isinstance(page, dict) else []
    if not isinstance(entries, list):
        raise ValueError("Component search result list is missing")
    exact = [entry for entry in entries
             if isinstance(entry, dict) and entry.get("componentCode") == code]
    if len(exact) != 1:
        raise ValueError("Component search did not return one exact LCSC code")
    entry = exact[0]
    mpn = str(entry.get("componentModelEn", "")).strip()
    expected = {value.casefold() for value in expected_mpns if value}
    identity = bool(mpn and len(expected) == 1 and mpn.casefold() in expected)
    tier = classify(entry)
    result = {
        "tier": tier,
        "verified": tier != "unknown",
        "identity_verified": identity,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://jlcpcb.com/partdetail/" + code,
        "tier_source_url": ENDPOINT,
        "tier_request": {"keyword": code, "currentPage": 1, "pageSize": 10},
        "mpn": mpn,
        "manufacturer": entry.get("componentBrandEn", ""),
        "package": entry.get("componentSpecificationEn", ""),
    }
    if not identity:
        result.update(blocked=True, identity_note="Exact schematic MPN match required")
    if tier == "unknown":
        result["tier_note"] = "Official search omitted a supported tier or promotion flag"
    stock = entry.get("stockCount")
    if isinstance(stock, int) and not isinstance(stock, bool) and stock >= 0:
        result["jlcpcb_stock_at_check"] = stock
    return result


def fetch_part(code, expected_mpns):
    query = {"keyword": code, "currentPage": 1, "pageSize": 10}
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Ulva-BOM/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    return parse_result(payload, code, expected_mpns)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--provenance", type=Path,
                        help="Current order selector's provenance.json; includes new CAD parts")
    parser.add_argument("--output", type=Path, help="Default: update the input catalog")
    args = parser.parse_args(argv)
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        provenance = (json.loads(args.provenance.read_text(encoding="utf-8"))
                      if args.provenance else None)
        expected = approved_parts(catalog, provenance)
        if not expected:
            raise ValueError("No explicit LCSC codes found")
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))

    parts = {}
    failures = []
    for index, code in enumerate(sorted(expected, key=lambda value: int(value[1:]))):
        if index:
            time.sleep(0.5)
        try:
            entry = fetch_part(code, expected[code])
        except (OSError, ValueError, TypeError, urllib.error.URLError) as error:
            entry = {
                "tier": "unknown", "verified": False, "identity_verified": False,
                "blocked": True, "checked_at": datetime.now(timezone.utc).isoformat(),
                "source_url": "https://jlcpcb.com/partdetail/" + code,
                "mpn": next(iter(expected[code])) if len(expected[code]) == 1 else "",
                "error": str(error),
            }
        parts[code] = entry
        if not entry["verified"] or not entry["identity_verified"]:
            failures.append(code)
        print(f"{code}: {entry['tier']}; identity {'matched' if entry['identity_verified'] else 'unverified'}")

    result = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": "JLCPCB tier and exact MPN snapshot. JLCPCB stock is separate from LCSC stock; "
                 "check pricing, stock, purchase multiples and shipping at checkout.",
        "parts": parts,
    }
    output = args.output or args.catalog
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"Catalog: {len(parts)} codes; {len(failures)} need review. No orders were placed.")
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
