#!/usr/bin/env python3
"""Record source and exported-file versions for the offline board viewer.

The commit is the checkout base at capture time, not an assertion that every
export was built from that commit. Each view retains its own source fingerprint.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'window.ULVA_VIEWER_INFO = '


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resource(relative):
    path = ROOT / 'docs' / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Invalid documentation resource name')
    return path


class EmbeddedData(HTMLParser):
    def __init__(self, element_id):
        super().__init__()
        self.element_id = element_id
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == self.element_id:
            self.active = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def embedded_json(path, element_id):
    parser = EmbeddedData(element_id)
    parser.feed(path.read_text())
    return json.loads(''.join(parser.parts))


def script_json(path, variable):
    text = path.read_text()
    prefix = f'window.{variable} = '
    if not text.startswith(prefix):
        raise ValueError('Unexpected generated metadata format')
    return json.loads(text[len(prefix):].strip().removesuffix(';'))


def git(*args):
    try:
        result = subprocess.run(['git', '--no-optional-locks', *args], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return None
    return result.stdout if result.returncode == 0 else None


def commit_info():
    checkout = git('rev-parse', '--show-toplevel')
    if checkout is None or Path(checkout.decode().strip()).resolve() != ROOT:
        return {'hash': None, 'short': None, 'sourceModified': None}
    head = git('rev-parse', '--verify', 'HEAD')
    if head is None:
        return {'hash': None, 'short': None, 'sourceModified': None}
    head = head.decode().strip()
    def design_path(name):
        path = Path(name)
        return ((path.name.startswith('ulva_') and path.suffix in
                 {'.kicad_pcb', '.kicad_pro', '.kicad_sch', '.kicad_dru'})
                or name in {'Ulva.kicad_sym', 'fp-lib-table', 'sym-lib-table'}
                or path.parts[0] in {'Ulva.pretty', 'Ulva.3dshapes'})

    sources = {path for path in ROOT.glob('ulva_*.kicad_*') if design_path(path.name)}
    sources.add(ROOT / 'Ulva.kicad_sym')
    for directory in ('Ulva.pretty', 'Ulva.3dshapes'):
        sources.update(path for path in (ROOT / directory).glob('*') if path.is_file())
    sources.update(ROOT / name for name in ('fp-lib-table', 'sym-lib-table'))
    tracked = git('ls-tree', '-r', '--name-only', head).decode().splitlines()
    sources.update(ROOT / name for name in tracked if design_path(name))
    modified = any(not path.is_file() or
                   git('show', f'{head}:{path.relative_to(ROOT).as_posix()}') != path.read_bytes()
                   for path in sources)
    return {'hash': head, 'short': head[:12], 'sourceModified': modified}


def collect():
    pcb = ROOT / 'ulva_controller.kicad_pcb'
    match = re.search(r'^\s*\(rev "([^"\n]+)"\)', pcb.read_text(), re.MULTILINE)
    if match is None:
        raise ValueError('The PCB title block is missing its revision')
    revision = match.group(1)
    current = sha(pcb)
    route = embedded_json(resource('routing/index.html'), 'board-data')
    model = json.loads(resource('3d/assembly.json').read_text())
    schematic = script_json(resource('schematic/pages.js'), 'ULVA_SCHEMATIC_PAGES')
    orders = embedded_json(resource('orders/index.html'), 'order-data')['model']
    pdf = 'schematic/' + schematic['pdf']['file']
    hashes = {
        'routing': sha(resource('routing/board.svg')),
        'model': sha(resource('3d/' + model['board']['file'])),
        'schematic': sha(resource(pdf)),
    }
    for name, expected in [('routing', route['board_svg_sha256']),
                            ('model', model['board']['sha256']),
                            ('schematic', schematic['pdf']['sha256'])]:
        if hashes[name] != expected:
            raise ValueError(f'The {name} export and its metadata do not match; regenerate them')
    for sheet in schematic['sheets']:
        if sha(resource('schematic/' + sheet['file'])) != sheet['sha256']:
            raise ValueError('A schematic SVG does not match pages.js')
    return {
        'schema': 1,
        'revision': revision,
        'commit': commit_info(),
        'currentSourcePcbSha256': current,
        'routing': {
            'revision': route['revision'],
            'sourcePcbSha256': route['sha256'],
            'file': 'routing/board.svg',
            'sha256': hashes['routing'],
            'indexSha256': sha(resource('routing/index.html')),
        },
        'model': {
            'revision': revision if model['sourcePcbSha256'] == current else None,
            'sourcePcbSha256': model['sourcePcbSha256'],
            'file': '3d/' + model['board']['file'],
            'sha256': hashes['model'],
            'metadataSha256': sha(resource('3d/assembly.json')),
        },
        'schematic': {
            'sourceSha256': schematic['sourceSha256'],
            'file': pdf,
            'sha256': hashes['schematic'],
            'pages': len(schematic['sheets']),
            'metadataSha256': sha(resource('schematic/pages.js')),
        },
        'orders': {
            'file': 'orders/index.html',
            'sha256': sha(resource('orders/index.html')),
            'sourceSha256': orders['source_digest'],
            'sourcePcbSha256': orders['source_files_sha256']['ulva_controller.kicad_pcb'],
            'catalogSha256': orders['catalog_sha256'],
            'modelSha256': orders['model_digest'],
            'generatedAt': orders['generated_at'],
        },
        'viewer': {
            'file': 'index.html',
            'sha256': sha(resource('index.html')),
            'bundleSha256': sha(resource('3d/viewer.bundle.js')),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Check recorded file versions without changing the captured commit')
    args = parser.parse_args()
    output = resource('viewer-info.js')
    metadata = collect()
    if args.check:
        text = output.read_text()
        start = text.index(PREFIX) + len(PREFIX)
        recorded = json.loads(text[start:].strip().removesuffix(';'))
        # A later documentation commit does not change an earlier export's provenance.
        recorded.pop('commit', None)
        metadata.pop('commit', None)
        if recorded != metadata:
            raise SystemExit('Viewer versions are stale. Run python3 scripts/export_viewer_info.py')
        print('Viewer source and exported-file versions are current.')
        return
    content = json.dumps(metadata, indent=2, ensure_ascii=True).replace('<', '\\u003c')
    output.write_text('// Generated by scripts/export_viewer_info.py.\n' + PREFIX + content + ';\n')
    print('Updated docs/viewer-info.js; source files are unchanged.')


if __name__ == '__main__':
    main()
