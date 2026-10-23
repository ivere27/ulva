#!/usr/bin/env python3
"""Export a selectable 3D assembly without changing the authoritative KiCad files.

Requires KiCad 9 (pcbnew and kicad-cli) and Node.js 22+. Three.js and its loaders
are vendored in docs/3d/vendor. Model downloads are opt-in; later runs are offline.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_receipt(pcb):
    """Protect source CAD and project resources, including local visual models."""
    paths = {pcb}
    for suffix in ('.kicad_pro', '.kicad_dru'):
        sibling = pcb.with_suffix(suffix)
        if sibling.is_file():
            paths.add(sibling)
    for pattern in ('*.kicad_sch', '*.kicad_sym', '*.kicad_mod', '*.wrl', '*.step', '*.stp'):
        paths.update(pcb.parent.glob(pattern))
        for directory in ('lib', 'libs', 'library', 'libraries', 'models'):
            folder = pcb.parent / directory
            if folder.is_dir():
                paths.update(folder.rglob(pattern))
    for folder in pcb.parent.iterdir():
        if folder.is_dir() and folder.suffix in ('.pretty', '.3dshapes'):
            paths.update(path for path in folder.rglob('*') if path.is_file())
    for name in ('fp-lib-table', 'sym-lib-table'):
        if (pcb.parent / name).is_file():
            paths.add(pcb.parent / name)
    return {str(path.relative_to(pcb.parent)): sha(path) for path in sorted(paths)}


def check_source(pcb, receipt):
    if source_receipt(pcb) != receipt:
        raise RuntimeError('Source files changed during export; outputs were not published')


def run(*command):
    subprocess.run([str(arg) for arg in command], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcb', type=Path, default=ROOT / 'ulva_controller.kicad_pcb')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/3d')
    parser.add_argument('--model-dir', action='append', type=Path, default=[],
                        help='Additional KiCad 3D model library root (repeatable)')
    parser.add_argument('--download-models', action='store_true',
                        help='Download missing standard models from pinned KiCad 9.0.9 into build/3dmodels')
    parser.add_argument('--kicad-cli', default=os.environ.get('KICAD_CLI', 'kicad-cli'))
    parser.add_argument('--node', default='node')
    parser.add_argument('--update-docs', action='store_true',
                        help='Publish board.glb and assembly.json to docs/3d after checking source hashes')
    args = parser.parse_args()
    pcb = args.pcb.resolve(strict=True)
    output = args.output.resolve()
    if pcb.is_relative_to(output):
        parser.error('--output must be a build directory, not a source directory or its parent')
    if args.update_docs and pcb != (ROOT / 'ulva_controller.kicad_pcb').resolve():
        parser.error('--update-docs requires this checkout\'s authoritative PCB')
    if output == (ROOT / 'docs/3d').resolve():
        parser.error('Use --update-docs to publish, with a separate build output directory')
    receipt = source_receipt(pcb)
    version = subprocess.check_output([args.kicad_cli, 'version'], text=True).strip()
    if not version.startswith('9.'):
        parser.error('This exporter requires KiCad 9')
    node_version = subprocess.check_output([args.node, '--version'], text=True).strip()
    if int(node_version.lstrip('v').split('.')[0]) < 22:
        parser.error('Node.js 22 or later is required')
    try:
        from visual_models import prepare_models
    except ImportError as error:
        parser.error(f'Run with the Python environment containing KiCad pcbnew: {error}')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='work-', dir=output) as temporary:
        work = Path(temporary)
        prepared = prepare_models(pcb, work / 'prepared', args.model_dir, args.download_models)
        check_source(pcb, receipt)
        native = work / 'native'
        native.mkdir()
        vrml = native / 'board.wrl'
        # Native export converts STEP models to VRML and includes copper, masks,
        # silkscreen, holes and board edges. External model filenames preserve IDs.
        run(args.kicad_cli, 'pcb', 'export', 'vrml', '--force', '--units', 'mm',
            '--user-origin', '0x0mm', '--models-dir', 'models', '--models-relative',
            '--output', vrml, prepared['pcb'])
        mapping = work / 'model-map.json'
        mapping.write_text(json.dumps(prepared['model_entries'], indent=2) + '\n')
        glb = work / 'board.glb'
        geometry_path = work / 'geometry.json'
        run(args.node, ROOT / 'scripts/convert_3d.mjs', vrml, mapping, glb, geometry_path)
        geometry = json.loads(geometry_path.read_text())
        components = prepared['components']
        ids = [row['id'] for row in components]
        if len(ids) != len(set(ids)) or sorted(ids) != geometry['componentIds']:
            raise ValueError('GLB component IDs differ from the prepared assembly')
        if any(row.get('node') != row['id'] for row in components):
            raise ValueError('Component nodes must match their stable IDs')
        for row in components:
            row['boundsMeters'] = geometry['componentBoundsMeters'][row['id']]
        manifest = {
            'schema': 1,
            'sourcePcbSha256': receipt[pcb.name],
            'upAxis': 'Z',
            'units': 'meters',
            'board': {'file': 'board.glb', 'sha256': sha(glb), 'node': 'board'},
            'components': components,
            'boundsMeters': geometry['boundsMeters'],
            'assumptions': {
                'carrier': 'Generic KiCad package models and original approximations.',
                'boardDisplay': 'Covered copper is shaded solder-mask green for clear assembly viewing; pad tin and all geometry retain native data.',
                'modules': 'Original illustrative shapes; variants and 11 mm PCB underside height assumed; not fit verification.',
                'qualification': 'No connector, case, antenna, thermal, switch access or USB clearance qualification.',
                'devkitDimensionsSource': 'https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html',
            },
            'provenance': {
                'kicadVersion': version,
                'threeVersion': '0.170.0',
                'sourceFiles': receipt,
                'exporterSha256': sha(Path(__file__)),
                'converterSha256': sha(ROOT / 'scripts/convert_3d.mjs'),
                'visualModelsSha256': sha(ROOT / 'scripts/visual_models.py'),
                'preparedPcbPortableSha256': hashlib.sha256(
                    prepared['pcb'].read_bytes().replace(str(work).encode(), b'.')).hexdigest(),
                'models': [{'id': entry['id'], 'file': Path(entry['path']).name,
                            'sha256': sha(Path(entry['path']))} for entry in prepared['model_entries']],
                'meshCount': geometry['meshCount'],
                'triangleCount': int(geometry['triangles']),
            },
        }
        metadata = work / 'assembly.json'
        metadata.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        check_source(pcb, receipt)
        for name in ('board.glb', 'assembly.json'):
            shutil.copyfile(work / name, output / name)
        (output / 'geometry.json').write_text(json.dumps(geometry, indent=2) + '\n')
        if args.update_docs:
            destination = ROOT / 'docs/3d'
            destination.mkdir(parents=True, exist_ok=True)
            check_source(pcb, receipt)
            for name in ('board.glb', 'assembly.json'):
                shutil.copyfile(work / name, destination / name)
        check_source(pcb, receipt)
    print(f'Exported {len(ids)} selectable components: {output / "board.glb"}')
    print('Authoritative CAD and project resources are unchanged.')
    if args.update_docs:
        print('Updated docs/3d/board.glb and docs/3d/assembly.json.')


if __name__ == '__main__':
    main()
