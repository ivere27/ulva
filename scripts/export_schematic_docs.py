#!/usr/bin/env python3
"""Export schematic SVG pages and a PDF from an unchanged KiCad 9 snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(text):
    stack = []; result = None
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text):
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            elif result is not None:
                raise ValueError('Multiple schematic roots')
            else:
                result = node
            stack.append(node)
        elif token == ')':
            if not stack:
                raise ValueError('Unbalanced schematic')
            stack.pop()
        else:
            if not stack:
                raise ValueError('Unexpected schematic token')
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack or not result or result[0] != 'kicad_sch':
        raise ValueError('Invalid schematic')
    return result


def children(node, key):
    return [value for value in node if isinstance(value, list) and value and value[0] == key]


def child(node, key, default=None):
    return next(iter(children(node, key)), default)


def sheet_details(main):
    documents = {}; sheets = []
    def document(path):
        if path not in documents:
            documents[path] = parse(path.read_text())
        return documents[path]
    root = document(main)
    root_page = child(child(child(root, 'sheet_instances'), 'path'), 'page')[1]
    root_uuid = child(root, 'uuid')[1]
    def visit(path, page, chain, ancestors):
        if path in ancestors:
            raise ValueError('Recursive schematic hierarchy')
        doc = document(path); title_block = child(doc, 'title_block', [])
        title = child(title_block, 'title', ['', path.stem])[1]
        sheets.append({'page': int(page), 'title': title, 'source': path})
        for sheet in children(doc, 'sheet'):
            props = {p[1]: p[2] for p in children(sheet, 'property')}
            filename = props.get('Sheetfile', props.get('Sheet file'))
            if not filename:
                raise ValueError('Sheet is missing its source filename')
            target = (path.parent / filename).resolve(strict=True)
            if not target.is_relative_to(main.parent):
                raise ValueError('Sheet source must remain inside the project directory')
            projects = children(child(sheet, 'instances', []), 'project')
            project = next((p for p in projects if p[1] == main.stem), None)
            instance = next((p for p in children(project or [], 'path') if p[1] == '/' + chain), None)
            if instance is None:
                raise ValueError(f'Cannot identify the page number for {target.name}')
            visit(target, child(instance, 'page')[1], chain + '/' + child(sheet, 'uuid')[1], ancestors | {path})
    visit(main, root_page, root_uuid, set())
    sheets.sort(key=lambda row: row['page'])
    if len({row['page'] for row in sheets}) != len(sheets):
        raise ValueError('Schematic page numbers must be unique')
    revision = child(child(root, 'title_block', []), 'rev', ['', ''])[1]
    return sheets, revision


def source_receipt(main, sheets):
    paths = {row['source'] for row in sheets}
    paths.update(main.parent.glob('*.kicad_sym'))
    for name in (main.with_suffix('.kicad_pro').name, 'sym-lib-table'):
        path = main.parent / name
        if path.is_file():
            paths.add(path)
    return {str(path.relative_to(main.parent)): sha(path) for path in sorted(paths)}


def ensure_unchanged(main, sheets, receipt):
    if source_receipt(main, sheets) != receipt:
        raise RuntimeError('Schematic sources changed during export; refusing publication')


def normalize_svg(source, destination, title):
    # ElementTree does not retrieve the native external SVG DTD. Re-serialization
    # drops that declaration and comments; retain all stroked text and geometry.
    tree = ET.parse(source); root = tree.getroot()
    for parent in root.iter():
        for node in list(parent):
            if node.tag == f'{{{SVG}}}metadata':
                parent.remove(node)
    heading = root.find(f'{{{SVG}}}title')
    if heading is not None:
        heading.text = title
    text = ET.tostring(root, encoding='unicode')
    if re.search(r'/home/|/Users/|file://|[A-Za-z]:\\Users\\', text):
        raise ValueError('Local filesystem path found in exported SVG')
    destination.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + text + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schematic', type=Path, default=ROOT / 'ulva_controller.kicad_sch')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/schematic-docs')
    parser.add_argument('--kicad-cli', default=os.environ.get('KICAD_CLI', 'kicad-cli'))
    parser.add_argument('--update-docs', action='store_true')
    args = parser.parse_args()
    source = args.schematic.resolve(strict=True); output = args.output.resolve()
    if source.is_relative_to(output) or output == (ROOT / 'docs/schematic').resolve():
        parser.error('Use a separate build output directory; --update-docs publishes the generated files')
    if args.update_docs and source != (ROOT / 'ulva_controller.kicad_sch').resolve():
        parser.error('--update-docs requires this checkout\'s authoritative schematic')
    version = subprocess.check_output([args.kicad_cli, 'version'], text=True).strip()
    if not version.startswith('9.'):
        parser.error('KiCad 9 is required')
    sheets, revision = sheet_details(source)
    receipt = source_receipt(source, sheets)
    aggregate = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='work-', dir=output) as temporary:
        work = Path(temporary); snapshot = work / 'source'; snapshot.mkdir()
        for name in receipt:
            destination = snapshot / name; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source.parent / name, destination)
        staged = snapshot / source.name; generated = work / 'generated'; generated.mkdir()
        # Export the complete hierarchy once. KiCad 9's single-page SVG mode
        # can select the root despite --pages; verify native title-block IDs.
        native = work / 'svg'; native.mkdir()
        subprocess.run([args.kicad_cli, 'sch', 'export', 'svg', '--output',
                        str(native) + os.sep, str(staged)], check=True)
        native_pages = {}
        for path in native.glob('*.svg'):
            root = ET.parse(path).getroot()
            descriptions = [node.text or '' for node in root.iter(f'{{{SVG}}}desc')]
            identity = next((re.fullmatch(r'Id: (\d+)/(\d+)', text) for text in descriptions
                             if re.fullmatch(r'Id: (\d+)/(\d+)', text)), None)
            if identity is None or int(identity[2]) != len(sheets):
                raise ValueError('Native SVG has an unexpected sheet identity')
            page = int(identity[1])
            if page in native_pages:
                raise ValueError('Native SVG export contains a duplicate page')
            native_pages[page] = (path, descriptions)
        if set(native_pages) != {row['page'] for row in sheets}:
            raise ValueError('Native SVG pages differ from the schematic hierarchy')
        entries = []
        for row in sheets:
            path, descriptions = native_pages[row['page']]
            native_file = next((text[6:] for text in descriptions if text.startswith('File: ')), None)
            native_title = next((text[7:] for text in descriptions if text.startswith('Title: ')), None)
            if native_title != row['title']:
                raise ValueError(f'Native page {row["page"]} has an unexpected title')
            if native_file != row['source'].name:
                raise ValueError(f'Native page {row["page"]} does not match its source file')
            name = f'page-{row["page"]:02d}.svg'
            normalize_svg(path, generated / name, row['title'])
            entries.append({'page': row['page'], 'title': row['title'], 'file': name,
                            'sha256': sha(generated / name)})
        pdf = generated / 'schematic.pdf'
        subprocess.run([args.kicad_cli, 'sch', 'export', 'pdf', '--exclude-pdf-metadata',
                        '--exclude-pdf-property-popups', '--output', str(pdf), str(staged)], check=True)
        data = pdf.read_bytes()
        if not data.startswith(b'%PDF-') or len(re.findall(rb'/Type\s*/Page\b', data)) != len(sheets):
            raise ValueError('Exported PDF page count does not match the schematic hierarchy')
        if re.search(rb'/home/|/Users/|file://|[A-Za-z]:\\Users\\', data):
            raise ValueError('Local filesystem path found in exported PDF')
        manifest = {'schema': 1, 'revision': revision, 'sourceSha256': aggregate,
                    'sources': receipt, 'pdf': {'file': pdf.name, 'sha256': sha(pdf)},
                    'sheets': entries, 'kicadVersion': version}
        content = json.dumps(manifest, indent=2, ensure_ascii=False)
        (generated / 'pages.js').write_text('window.ULVA_SCHEMATIC_PAGES = ' + content.replace('<', '\\u003c') + ';\n')
        ensure_unchanged(source, sheets, receipt)
        for path in generated.iterdir():
            shutil.copyfile(path, output / path.name)
        (output / 'pages.json').unlink(missing_ok=True)
        # Make the default ignored output directly viewable as well.
        for name in ('index.html', 'viewer.js', 'viewer.css'):
            shutil.copyfile(ROOT / 'docs/schematic' / name, output / name)
        if args.update_docs:
            ensure_unchanged(source, sheets, receipt)
            destination = ROOT / 'docs/schematic'; destination.mkdir(parents=True, exist_ok=True)
            for path in generated.iterdir():
                shutil.copyfile(path, destination / path.name)
            (destination / 'pages.json').unlink(missing_ok=True)
        ensure_unchanged(source, sheets, receipt)
    print(f'Exported {len(sheets)} SVG pages and schematic.pdf to {output}')
    print(f'Source SHA-256: {aggregate}; authoritative sources unchanged.')


if __name__ == '__main__':
    main()
