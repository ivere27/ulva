#!/usr/bin/env node
/** Convert native KiCad VRML, retaining each component's exact placement. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { Group, Scene, Mesh, MeshStandardMaterial, Matrix4, Box3, Vector3 } from '../docs/3d/vendor/three.module.js';
import { VRMLLoader } from '../docs/3d/vendor/VRMLLoader.js';
import { GLTFExporter } from '../docs/3d/vendor/GLTFExporter.js';
import { mergeGeometries, mergeVertices } from '../docs/3d/vendor/BufferGeometryUtils.js';

// GLTFExporter uses this browser API for its binary Blob, even without textures.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then(result => {
      this.result = result;
      this.onloadend?.();
    }, error => { throw error; });
  }
};

const [input, mappingPath, output, reportPath] = process.argv.slice(2);
if (!reportPath) throw new Error('Usage: node convert_3d.mjs board.wrl model-map.json board.glb geometry.json');
const mapping = JSON.parse(await fs.readFile(mappingPath, 'utf8'));
const byFilename = new Map();
for (const entry of mapping) {
  if (!/^[A-Za-z0-9_-]+$/.test(entry.id)) throw new Error(`Unsafe component ID: ${entry.id}`);
  const name = path.parse(entry.path).name + '.wrl';
  if (byFilename.has(name)) throw new Error(`Duplicate native model filename: ${name}`);
  byFilename.set(name, entry.id);
}

const markerEntries = [];
let boardText = await fs.readFile(input, 'utf8');
// Native WorldInfo contains the local output path; it is not public metadata.
boardText = boardText.replace(/WorldInfo\s*\{[^}]*\}/g, '');
boardText = boardText.replace(/Inline\s*\{\s*url\s*"([^"\r\n]+)"\s*\}/g, (_, url) => {
  const name = path.posix.basename(url.replaceAll('\\', '/'));
  const id = byFilename.get(name);
  if (!id) throw new Error(`Native export includes an unmapped model: ${name}`);
  const modelPath = path.resolve(path.dirname(input), url);
  const exportRoot = path.resolve(path.dirname(input)) + path.sep;
  if (!modelPath.startsWith(exportRoot)) throw new Error('Model escapes native export directory');
  const marker = `ULVA_MODEL_${markerEntries.length}`;
  markerEntries.push({ marker, id, modelPath, filename: name });
  return `DEF ${marker} Group { children [] }`;
});
if (/\bInline\s*\{/.test(boardText)) throw new Error('Unsupported native Inline syntax');
if (markerEntries.length !== mapping.length) {
  throw new Error(`Native model count mismatch: ${markerEntries.length} != ${mapping.length}`);
}
if (new Set(markerEntries.map(x => x.filename)).size !== mapping.length) {
  throw new Error('Native export omitted or duplicated a component model');
}

// KiCad emits valid VRML numbers such as -0. and 18.; Three's lexer needs .0.
const normalizeNumbers = text => text.replace(/(?<![\w.])([-+]?\d+)\.(?=[\s,\]])/g, '$1.0');
const loader = new VRMLLoader();
const nativeScene = loader.parse(normalizeNumbers(boardText), '');
const scene = new Scene();
const assembly = new Group();
assembly.name = 'assembly';
scene.add(assembly);
const board = new Group();
board.name = 'board';
assembly.add(board);
board.add(nativeScene);
scene.updateMatrixWorld(true);
const components = new Map();
for (const entry of markerEntries) {
  const marker = nativeScene.getObjectByName(entry.marker);
  if (!marker || !marker.parent) throw new Error(`Native model marker missing: ${entry.marker}`);
  const transform = marker.parent;
  if (transform.children.length !== 1) throw new Error('Unexpected native model transform layout');
  const text = await fs.readFile(entry.modelPath, 'utf8');
  // The portable pipeline accepts only self-contained mesh models, never scripts/textures.
  if (/\b(?:Inline|ImageTexture|MovieTexture|Script)\s*\{/.test(text)) {
    throw new Error(`Model needs unsupported external resources: ${entry.filename}`);
  }
  const model = loader.parse(normalizeNumbers(text.replace(/WorldInfo\s*\{[^}]*\}/g, '')), '');
  let count = 0;
  model.traverse(item => { if (item.isMesh && item.geometry?.attributes.position?.count) count++; });
  if (!count) throw new Error(`Empty native model: ${entry.filename}`);
  marker.removeFromParent();
  transform.add(model);
  let component = components.get(entry.id);
  if (!component) {
    component = new Group();
    component.name = entry.id;
    component.userData.componentId = entry.id;
    assembly.add(component);
    components.set(entry.id, component);
  }
  // Native outer scale converts KiCad's internal VRML inches to millimeters.
  // attach preserves that transform while moving each model under its own ID.
  component.attach(transform);
}
// STEP tessellation creates thousands of tiny Shape nodes. Bake their exact
// native transforms and merge by material within each selectable component.
// No merge crosses a component boundary, so visibility remains independent.
scene.updateMatrixWorld(true);
let meshCount = 0;
let triangles = 0;
let boardMeshes = 0;
let maskColor;
board.traverse(item => {
  if (item.isMesh && item.material.transparent) maskColor = item.material.color.getHex();
});
let coveredCopperMaterials = 0;
for (const group of [board, ...components.values()]) {
  const inverse = group.matrixWorld.clone().invert();
  const batches = new Map();
  group.traverse(item => {
    if (!item.isMesh) return;
    if (Array.isArray(item.material)) throw new Error('Unexpected native multi-material mesh');
    const old = item.material;
    const geometry = item.geometry.clone().applyMatrix4(new Matrix4().multiplyMatrices(inverse, item.matrixWorld));
    const properties = {
      color: old.color.getHex(), emissive: old.emissive?.getHex() ?? 0, opacity: old.opacity,
      transparent: old.transparent, side: old.side, vertexColors: old.vertexColors,
      roughness: 0.65, metalness: 0,
    };
    // Native copper is gold even beneath the solder mask. At screen scale,
    // its dense tessellation can sparkle through the mask. Use the same green
    // for covered board copper; exposed pad tin and component metals retain
    // their native colors. This changes appearance only, never mesh positions.
    if (group === board && maskColor !== undefined && !old.transparent
        && old.color.r > old.color.g && old.color.g > old.color.b
        && old.color.r > old.color.b * 3) {
      properties.color = maskColor;
      coveredCopperMaterials++;
    }
    const key = JSON.stringify([properties, Object.keys(geometry.attributes).sort()]);
    if (!batches.has(key)) batches.set(key, { geometries: [], properties });
    // Native meshes may mix indexed and non-indexed geometry.
    batches.get(key).geometries.push(geometry.index ? geometry.toNonIndexed() : geometry);
  });
  group.clear();
  for (const { geometries, properties } of batches.values()) {
    const merged = mergeGeometries(geometries, false);
    if (!merged) throw new Error('Cannot merge native component geometry');
    const geometry = mergeVertices(merged, 1e-6);
    const mesh = new Mesh(geometry, new MeshStandardMaterial(properties));
    group.add(mesh);
    meshCount++;
    triangles += geometry.index.count / 3;
  }
  if (group === board) boardMeshes = batches.size;
}
if (!boardMeshes) throw new Error('Native board geometry is empty');
// glTF lengths are meters; Z remains the board normal (recorded in assembly.json).
assembly.scale.setScalar(0.001);
scene.updateMatrixWorld(true);
const bounds = new Box3().setFromObject(assembly);
const size = bounds.getSize(new Vector3());
if (![size.x, size.y, size.z].every(Number.isFinite) || size.x <= 0 || size.y <= 0 || size.z <= 0) {
  throw new Error('Invalid assembled geometry bounds');
}
const binary = await new GLTFExporter().parseAsync(scene, { binary: true, onlyVisible: false });
await fs.writeFile(output, Buffer.from(binary));
const report = {
  componentIds: [...components.keys()].sort(), meshCount, boardMeshes, triangles,
  displayStyle: { coveredCopper: 'solder-mask green', recoloredNativeMeshes: coveredCopperMaterials },
  boundsMeters: { min: bounds.min.toArray(), max: bounds.max.toArray() },
  componentBoundsMeters: Object.fromEntries([...components].map(([id, group]) => {
    const box = new Box3().setFromObject(group);
    return [id, { min: box.min.toArray(), max: box.max.toArray() }];
  })),
};
await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(`Converted ${components.size} selectable components, ${meshCount} meshes, ${Math.round(triangles)} triangles.`);
