#!/usr/bin/env python3
"""Prepare offline JLCPCB/LCSC selection files from the current Ulva CAD.

This tool never contacts suppliers or places orders. KiCad reads only a private
snapshot; unchanged exports are reused from a hash-checked local cache.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1
CAD_NAME = 'ulva_controller'
DEFAULT_SOURCE = ROOT
TIERS = {'basic', 'preferred', 'extended', 'unknown'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stable_hash(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def source_files(source):
    paths = sorted(set(source.glob('*.kicad_sch')) | set(source.glob('*.kicad_sym')) |
                   set(source.glob('*.kicad_pcb')) | set(source.glob('*.kicad_pro')) |
                   set(source.glob('*.kicad_dru')) | set(source.glob('*.pretty/*.kicad_mod')) |
                   {source / 'fp-lib-table', source / 'sym-lib-table'})
    required = {source / f'{CAD_NAME}.{ext}' for ext in ('kicad_sch', 'kicad_pcb', 'kicad_pro')}
    if not required <= set(paths):
        raise ValueError('Source must contain the Ulva schematic, PCB and project')
    result = {}
    for path in paths:
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != source.parent):
            raise ValueError(f'Symlink source file is not supported: {path}')
        if path.is_file():
            result[path.relative_to(source).as_posix()] = path.read_bytes()
    if not required <= {source / name for name in result}:
        raise ValueError('Required CAD input is missing')
    return result


def check_source(source, receipt):
    actual = {name: sha(data) for name, data in source_files(source).items()}
    if actual != receipt['source_files_sha256']:
        raise ValueError('CAD source changed: regenerate the selector before exporting this selection')


def runtime(*args):
    if not shutil.which('kicad-cli'):
        raise ValueError('KiCad 9 kicad-cli must be on PATH; run with Python that can import pcbnew')
    return [str(arg) for arg in args]


def extract_pcb(board_path, output):
    """Executed in KiCad Python; one read-only LoadBoard, no SaveBoard."""
    import pcbnew as p
    board = p.LoadBoard(str(board_path))
    origin = board.GetDesignSettings().GetAuxOrigin()
    rows = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in rows:
            raise ValueError(f'Duplicate PCB reference: {ref}')
        rows[ref] = {
            'value': fp.GetValue(), 'footprint': str(fp.GetFPID().GetLibItemName()),
            'smd': bool(fp.GetAttributes() & p.FP_SMD),
            'mechanical': bool(list(fp.Pads())) and all(pad.GetAttribute() == p.PAD_ATTRIB_NPTH for pad in fp.Pads()),
            'dnp': fp.IsDNP(), 'excluded': fp.IsExcludedFromBOM(),
            'position': {'Designator': ref, 'Mid X': f'{p.ToMM(fp.GetPosition().x-origin.x):.4f}mm',
                         'Mid Y': f'{p.ToMM(origin.y-fp.GetPosition().y):.4f}mm',
                         'Layer': 'Bottom' if fp.IsFlipped() else 'Top',
                         'Rotation': f'{fp.GetOrientationDegrees()%360:.2f}'},
        }
    output.write_text(json.dumps(rows, indent=2) + '\n')


def cached_inputs(source, cache):
    files = source_files(source)
    hashes = {name: sha(data) for name, data in files.items()}
    receipt = {'schema_version': SCHEMA, 'source_files_sha256': hashes,
               'source_digest': stable_hash(hashes), 'exporter_sha256': sha(Path(__file__).read_bytes())}
    cache.mkdir(parents=True, exist_ok=True)
    manifest = cache / 'manifest.json'
    if manifest.exists():
        old = json.loads(manifest.read_text())
        if old.get('source_digest') == receipt['source_digest'] and old.get('exporter_sha256') == receipt['exporter_sha256'] and all(
            (cache / name).is_file() and sha((cache / name).read_bytes()) == digest
            for name, digest in old.get('artifacts_sha256', {}).items()
        ) and set(old.get('artifacts_sha256', {})) == {'controller.xml', 'positions.json'}:
            check_source(source, receipt)
            return ET.parse(cache / 'controller.xml').getroot(), json.loads((cache / 'positions.json').read_text()), old
    with tempfile.TemporaryDirectory(prefix='order-snapshot-', dir=cache) as temporary:
        work = Path(temporary)
        for name, data in files.items():
            dest = work / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        subprocess.run(runtime('kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                               '-o', work / 'controller.xml', work / f'{CAD_NAME}.kicad_sch'), check=True)
        subprocess.run(runtime(sys.executable, Path(__file__).resolve(), '--extract-pcb',
                               work / f'{CAD_NAME}.kicad_pcb', work / 'positions.json'), check=True)
        for name, data in files.items():
            if (work / name).read_bytes() != data:
                raise ValueError(f'KiCad unexpectedly modified snapshot input: {name}')
        check_source(source, receipt)
        for name in ('controller.xml', 'positions.json'):
            shutil.copyfile(work / name, cache / name)
    receipt['exported_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    receipt['artifacts_sha256'] = {name: sha((cache / name).read_bytes()) for name in ('controller.xml', 'positions.json')}
    manifest.write_text(json.dumps(receipt, indent=2) + '\n')
    return ET.parse(cache / 'controller.xml').getroot(), json.loads((cache / 'positions.json').read_text()), receipt




def refill_pcb(board_path):
    """Isolated worker: one LoadBoard/SaveBoard, disposable snapshot only."""
    import pcbnew as p
    project = board_path.with_suffix('.kicad_pro')
    before = project.read_bytes()
    board = p.LoadBoard(str(board_path))
    board.BuildConnectivity()
    if p.ZONE_FILLER(board).Fill(board.Zones()) is False:
        raise ValueError('KiCad zone refill failed; fabrication export stopped')
    if p.SaveBoard(str(board_path), board) is False:
        raise ValueError('KiCad snapshot save failed; fabrication export stopped')
    if project.read_bytes() != before:
        raise ValueError('KiCad modified the snapshot project during zone refill')


def export_gerbers(source, output, receipt):
    """Validate and export the same read-only source snapshot as the selection."""
    check_source(source, receipt)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fabrication-', dir=output / 'cache') as temporary:
        work = Path(temporary)
        for name, data in source_files(source).items():
            dest = work / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        board = work / f'{CAD_NAME}.kicad_pcb'
        subprocess.run(runtime(sys.executable, Path(__file__).resolve(), '--refill-pcb', board), check=True)
        filled_pcb_sha256 = sha(board.read_bytes())
        drc = work / 'drc.json'
        subprocess.run(runtime('kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                               '--all-track-errors', '--exit-code-violations', '--format', 'json',
                               '-o', drc, board), check=True)
        report = json.loads(drc.read_text())
        if report.get('violations') or report.get('unconnected_items'):
            raise ValueError('Resolve DRC findings before exporting the fabrication package')
        fab = work / 'gerbers'
        fab.mkdir()
        subprocess.run(runtime('kicad-cli', 'pcb', 'export', 'gerbers', '--layers',
                               'F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts',
                               '--use-drill-file-origin', '--subtract-soldermask',
                               '-o', str(fab) + '/', board), check=True)
        subprocess.run(runtime('kicad-cli', 'pcb', 'export', 'drill', '--format', 'excellon',
                               '--excellon-units', 'mm', '--excellon-separate-th',
                               '--excellon-oval-format', 'route', '--drill-origin', 'plot',
                               '-o', str(fab) + '/', board), check=True)
        check_source(source, receipt)
        target = output / 'fabrication-gerbers.zip'
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(fab.iterdir()):
                archive.write(path, path.name)
        shutil.copyfile(drc, output / 'fabrication-drc.json')
    result = {'file': target.name, 'sha256': sha(target.read_bytes()), 'source_digest': receipt['source_digest'],
              'drc_violations': 0, 'drc_unconnected': 0, 'zones_refilled_in_snapshot': True,
              'source_pcb_sha256': receipt['source_files_sha256'][f'{CAD_NAME}.kicad_pcb'],
              'filled_pcb_sha256': filled_pcb_sha256,
              'note': 'Bare-board Gerbers and drills; assembly BOM/CPL are separate. Zones are refilled only in the disposable snapshot; authoritative CAD stays unchanged.'}
    (output / 'fabrication-provenance.json').write_text(json.dumps(result, indent=2) + '\n')
    return result



def verified_tier(entry, now, max_age_days):
    """Fail closed for incomplete, stale, future, or nonofficial evidence."""
    tier = entry.get('tier', 'unknown').lower()
    if tier not in TIERS:
        raise ValueError(f'Invalid tier: {tier}')
    try:
        checked = dt.datetime.fromisoformat(entry.get('checked_at', '').replace('Z', '+00:00'))
        age = (now - checked).total_seconds() / 86400
        url = urlparse(entry.get('source_url', ''))
        official = url.scheme == 'https' and (url.hostname == 'jlcpcb.com' or (url.hostname or '').endswith('.jlcpcb.com'))
        valid = (entry.get('verified') is True and entry.get('identity_verified') is True and
                 0 <= age <= max_age_days and official)
    except (ValueError, TypeError):
        valid = False
    return tier if valid else 'unknown'


def natural(ref):
    return re.sub(r'\d+', lambda m: m[0].zfill(8), ref)


def make_model(xml, positions, catalog, receipt, boards, max_age_days, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if catalog.get('schema_version') != SCHEMA or not isinstance(catalog.get('parts'), dict):
        raise ValueError('Catalog needs schema_version=1 and parts keyed by exact LCSC number')
    comps = xml.findall('./components/comp')
    refs = [c.get('ref') for c in comps]
    if not all(refs) or len(refs) != len(set(refs)) or set(refs) != set(positions):
        raise ValueError('Schematic and PCB reference sets must match exactly, without duplicates')
    rows = []
    for component in sorted(comps, key=lambda c: natural(c.get('ref'))):
        ref = component.get('ref')
        props = {f.get('name'): f.text or '' for f in component.findall('./fields/field')}
        flags = {f.get('name'): f.get('value', '') for f in component.findall('./property')}
        properties = flags | props
        value = component.findtext('value', '')
        footprint = component.findtext('footprint', '')
        pcb = positions[ref]
        if pcb['value'] != value or pcb['footprint'] != footprint.split(':')[-1]:
            raise ValueError(f'Schematic/PCB value or footprint mismatch: {ref}')
        lcsc = properties.get('LCSC', '').strip()
        mpn = properties.get('MPN', '')
        evidence = catalog['parts'].get(lcsc, {})
        tier = verified_tier(evidence, now, max_age_days)
        identity_blocked = evidence.get('blocked') is True or evidence.get('identity_verified') is False
        # An asserted catalog match must also identify this exact schematic MPN.
        if evidence.get('identity_verified') is True and (not mpn or evidence.get('mpn', '').casefold() != mpn.casefold()):
            identity_blocked = True
        valid_code = bool(re.fullmatch(r'C[1-9][0-9]*', lcsc))
        dnp = 'dnp' in flags or pcb['dnp']
        no_part = ('exclude_from_bom' in flags or pcb['excluded'] or
                   properties.get('Assembly') == 'PCB copper; no purchased part' or
                   footprint.startswith('MountingHole:') or pcb.get('mechanical', False) or ref.startswith('TP'))
        assembly = properties.get('Assembly', '')
        purchasable = not dnp and not no_part
        loose = purchasable and valid_code and not identity_blocked
        pcba = loose and pcb['smd'] and assembly == 'JLC PCBA SMT' and tier in {'basic', 'preferred', 'extended'}
        default = 'pcba' if pcba and tier in {'basic', 'preferred'} else 'loose' if loose else 'none'
        reason = ('Not fitted (DNP)' if dnp else 'PCB feature; no purchased part' if no_part else
                  'Catalog identity conflict / blocked part' if identity_blocked else
                  'No valid schematic LCSC code; source manually' if not valid_code else
                  'Tier evidence unknown or stale; loose parts only' if tier == 'unknown' else
                  'Manual assembly ownership' if not pcba else 'Verified ' + tier)
        rows.append({'ref': ref, 'value': value, 'footprint': footprint, 'mpn': mpn,
                     'manufacturer': properties.get('Manufacturer', ''), 'lcsc': lcsc,
                     'assembly': assembly, 'schematic_tier': properties.get('JLCPCB_Library', ''),
                     'tier': tier, 'evidence': evidence, 'properties': properties,
                     'datasheet': component.findtext('datasheet', ''),
                     'dnp': dnp, 'no_part': no_part, 'pcba_allowed': pcba,
                     'loose_allowed': loose, 'default': default, 'reason': reason,
                     'manual': purchasable and not loose, 'position': pcb['position']})
    result = {'schema_version': SCHEMA, 'generated_at': now.isoformat(), 'boards': boards,
              'source_digest': receipt['source_digest'], 'source_files_sha256': receipt['source_files_sha256'],
              'catalog_sha256': stable_hash(catalog), 'catalog_max_age_days': max_age_days, 'rows': rows,
              'cpl_note': 'KiCad angles; confirm supplier library orientation and pin 1 in the assembly preview.',
              'quantity_note': 'BOM/CPL describe one board. Loose and manual quantities are multiplied by board count; MOQ, pack multiples, stock, spares and fees are not included.'}
    result['model_digest'] = stable_hash({k: v for k, v in result.items() if k not in {'generated_at', 'boards'}})
    return result


def selection_for(model):
    return {'schema_version': SCHEMA, 'source_digest': model['source_digest'],
            'model_digest': model['model_digest'], 'boards': model['boards'],
            'choices': {r['ref']: r['default'] for r in model['rows']}}


def validate_selection(model, selection):
    if selection.get('schema_version') != SCHEMA or selection.get('source_digest') != model['source_digest'] or selection.get('model_digest') != model['model_digest']:
        raise ValueError('Selection belongs to different CAD, catalog or eligibility data; regenerate/review it')
    boards = selection.get('boards')
    if type(boards) is not int or not 1 <= boards <= 100000:
        raise ValueError('Board count must be an integer from 1 to 100000')
    choices = selection.get('choices', {})
    if set(choices) != {r['ref'] for r in model['rows']}:
        raise ValueError('Selection must include each reference exactly once')
    for row in model['rows']:
        mode = choices[row['ref']]
        if not isinstance(mode, str) or mode not in {'none', 'pcba', 'loose'} or (mode != 'none' and not row[mode + '_allowed']):
            raise ValueError(f'Ineligible or invalid selection for {row["ref"]}: {mode}')
    return choices, boards


def csv_text(headers, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(headers)
    for row in rows:
        for value in row:
            text = str(value)
            numeric = re.fullmatch(r'-?\d+(?:\.\d+)?(?:mm)?', text)
            if (text and ord(text[0]) < 32) or (re.match(r'^\s*[=+@-]', text) and not numeric):
                raise ValueError('CSV text could be interpreted as a spreadsheet formula; correct the CAD field before exporting')
        writer.writerow(row)
    return stream.getvalue()


def output_files(model, selection):
    choices, boards = validate_selection(model, selection)
    assembled = [r for r in model['rows'] if choices[r['ref']] == 'pcba']
    loose = {}
    for row in model['rows']:
        if choices[row['ref']] == 'loose':
            loose.setdefault(row['lcsc'], []).append(row)
    bom = [[r['value'], r['ref'], r['footprint'].split(':')[-1], r['lcsc']] for r in assembled]
    cpl_headers = ['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation']
    cpl = [[r['position'][key] for key in cpl_headers] for r in assembled]
    assert {r[1] for r in bom} == {r[0] for r in cpl}
    files = {
        'jlc-bom.csv': csv_text(['Comment', 'Designator', 'Footprint', 'LCSC Part #'], bom),
        'jlc-cpl.csv': csv_text(cpl_headers, cpl),
        'lcsc-import.csv': csv_text(['LCSC Part Number', 'Quantity', 'References', 'MPN', 'Value'],
            [[code, len(rows)*boards, ','.join(r['ref'] for r in rows),
              ' | '.join(dict.fromkeys(r['mpn'] for r in rows)), ' | '.join(dict.fromkeys(r['value'] for r in rows))]
             for code, rows in sorted(loose.items())]),
        'manual-parts.csv': csv_text(['Reference', 'Value', 'MPN', 'Manufacturer', 'Footprint', 'Quantity', 'Reason'],
            [[r['ref'], r['value'], r['mpn'], r['manufacturer'], r['footprint'], boards, r['reason']]
             for r in model['rows'] if r['manual']]),
        'selection.json': json.dumps(selection, indent=2) + '\n',
        'provenance.json': json.dumps({k: v for k, v in model.items() if k != 'rows'} | {
            'selected_board_count': boards, 'pcba_references': [r['ref'] for r in assembled],
            'loose_references': [r['ref'] for r in model['rows'] if choices[r['ref']] == 'loose'],
            'parts': model['rows']}, indent=2) + '\n',
    }
    return files



def html_payload(value):
    """Keep JSON data exact while preventing HTML script termination."""
    return json.dumps(value, ensure_ascii=True).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/orders')
    parser.add_argument('--catalog', type=Path, help='Verified catalog JSON (default: tools/parts-catalog.json; missing default means unknown)')
    parser.add_argument('--gerbers', action='store_true', help='Run native DRC and also export a matching Gerber/drill ZIP')
    parser.add_argument('--update-docs', action='store_true',
                        help='Publish the generated selector to the shared viewer Orders tab')
    parser.add_argument('--boards', type=int, default=5, help='Initial editable board count (default: 5)')
    parser.add_argument('--max-catalog-age-days', type=int, default=30)
    parser.add_argument('--selection', type=Path, help='Saved selector JSON to validate and export')
    parser.add_argument('--check-source', type=Path, help='Check current CAD against a provenance JSON and exit')
    parser.add_argument('--refill-pcb', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--extract-pcb', nargs=2, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.refill_pcb:
        refill_pcb(args.refill_pcb)
        return
    if args.extract_pcb:
        extract_pcb(*args.extract_pcb)
        return
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if args.update_docs and source != ROOT.resolve():
        parser.error('--update-docs requires this checkout\'s authoritative CAD')
    if output == source or (source in output.parents and source / 'build' not in output.parents):
        parser.error('Output/cache must be under source/build or outside the source checkout')
    if not 1 <= args.boards <= 100000 or args.max_catalog_age_days < 0:
        parser.error('Invalid board count or catalog age')
    if args.check_source:
        check_source(source, json.loads(args.check_source.read_text()))
        print('Current CAD matches the saved provenance.')
        return
    catalog_path = args.catalog or Path(__file__).with_name('parts-catalog.json')
    if args.catalog and not catalog_path.is_file():
        raise ValueError(f'Catalog does not exist: {catalog_path}')
    catalog = json.loads(catalog_path.read_text()) if catalog_path.is_file() else {'schema_version': SCHEMA, 'parts': {}}
    xml, positions, receipt = cached_inputs(source, output / 'cache')
    model = make_model(xml, positions, catalog, receipt, args.boards, args.max_catalog_age_days)
    if args.gerbers:
        model['fabrication'] = export_gerbers(source, output, receipt)
    elif (output / 'fabrication-provenance.json').is_file():
        fabrication = json.loads((output / 'fabrication-provenance.json').read_text())
        bundle = output / 'fabrication-gerbers.zip'
        if fabrication.get('source_digest') != receipt['source_digest'] or fabrication.get('file') != bundle.name or not bundle.is_file() or sha(bundle.read_bytes()) != fabrication.get('sha256'):
            raise ValueError('Existing fabrication bundle is stale or modified; regenerate with --gerbers or use a new output directory')
        model['fabrication'] = fabrication
    selection = json.loads(args.selection.read_text()) if args.selection else selection_for(model)
    files = output_files(model, selection)
    check_source(source, receipt)
    output.mkdir(parents=True, exist_ok=True)
    # JSON is data, never executable markup; escape script delimiters and HTML.
    payload = html_payload({'model': model, 'selection': selection})
    template = (Path(__file__).with_name('order_selector.html')).read_text()
    files['index.html'] = template.replace('__ORDER_DATA__', payload)
    for name, content in files.items():
        (output / name).write_text(content, encoding='utf-8')
    if args.update_docs:
        check_source(source, receipt)
        destination = ROOT / 'docs/orders'
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'index.html').write_text(files['index.html'], encoding='utf-8')
        if model.get('fabrication'):
            shutil.copyfile(output / 'fabrication-gerbers.zip', destination / 'fabrication-gerbers.zip')
        else:
            (destination / 'fabrication-gerbers.zip').unlink(missing_ok=True)
        check_source(source, receipt)
    counts = {mode: list(selection['choices'].values()).count(mode) for mode in ('pcba', 'loose', 'none')}
    print(json.dumps({'output': str(output), 'references': len(model['rows']), 'boards': selection['boards'],
                      'selected': counts, 'source_digest': model['source_digest']}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, ET.ParseError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Order preparation failed: {error}')
