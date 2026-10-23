import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

const $ = id => document.getElementById(id);
const viewport = $('viewport');
const localFileMode = location.protocol === 'file:';
if (document.body.classList.contains('embedded')) {
  document.querySelector('.view-tools').append($('toggle-parts'));
}
const mobile = matchMedia('(max-width: 760px)');
const natural = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });
const parts = new Map();
let renderer, scene, camera, controls, assembly;
let center, radius = 1, upAxis = 'Z', loadingGeneration = 0, request;
let renderPending = false;
let downloadURLs = [];

function showParts(open) {
  document.body.dataset.partsOpen = String(open);
  $('toggle-parts').setAttribute('aria-expanded', String(open));
  if (renderer) requestAnimationFrame(resize);
}
$('toggle-parts').onclick = () => showParts(document.body.dataset.partsOpen !== 'true');
$('close-parts').onclick = () => { showParts(false); $('toggle-parts').focus(); };
mobile.addEventListener('change', () => showParts(!mobile.matches));
showParts(!mobile.matches);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && mobile.matches) showParts(false);
});

function loading(message) {
  $('loading-panel').hidden = false;
  $('load-title').textContent = 'Loading assembly';
  $('load-status').textContent = message;
  $('load-status').classList.remove('error');
  $('retry-load').hidden = true;
  $('open-files').hidden = false;
  viewport.setAttribute('aria-busy', 'true');
}

function failure(message) {
  $('loading-panel').hidden = false;
  $('load-title').textContent = 'Assembly not loaded';
  $('load-status').textContent = message;
  $('load-status').classList.add('error');
  $('retry-load').hidden = localFileMode;
  $('open-files').hidden = false;
  viewport.setAttribute('aria-busy', 'false');
  if (!assembly) $('visible-count').textContent = 'Unable to load assembly';
}

function validateManifest(value) {
  if (!value || value.schema !== 1 || !value.board ||
      !/^[a-z0-9_.-]+\.glb$/i.test(value.board.file || '') ||
      !Array.isArray(value.components) || !value.components.length) {
    throw Error('The parts data is invalid. Open the matching assembly.json and board.glb files.');
  }
  const ids = new Set(), nodes = new Set();
  for (const component of value.components) {
    if (!component || typeof component.id !== 'string' || !component.id ||
        typeof component.node !== 'string' || !component.node ||
        typeof component.label !== 'string' || !['carrier', 'module'].includes(component.kind) ||
        ids.has(component.id) || nodes.has(component.node)) {
      throw Error('The parts data has missing or duplicate component names.');
    }
    ids.add(component.id); nodes.add(component.node);
  }
  if (value.upAxis && !['Y', 'Z'].includes(value.upAxis)) throw Error('Unsupported board orientation.');
  return value;
}

function verifyEmbeddedGLB(buffer) {
  if (buffer.byteLength < 20) throw Error('The model file is incomplete.');
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2 ||
      view.getUint32(8, true) !== buffer.byteLength || view.getUint32(16, true) !== 0x4e4f534a) {
    throw Error('Open a complete GLB model exported with this assembly.');
  }
  const length = view.getUint32(12, true);
  if (length > buffer.byteLength - 20) throw Error('The model file is incomplete.');
  const content = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 20, length)));
  for (const item of [...(content.buffers || []), ...(content.images || [])]) {
    if (item.uri && (typeof item.uri !== 'string' || !item.uri.startsWith('data:'))) {
      throw Error('The model requires additional files. Use the self-contained board.glb export.');
    }
  }
}

async function verifyHash(buffer, value) {
  if (!value.board.sha256) return;
  if (!/^[a-f0-9]{64}$/i.test(value.board.sha256)) throw Error('The model verification hash is invalid.');
  if (!globalThis.crypto?.subtle) throw Error('This browser cannot verify the model hash. Use a current browser with SHA-256 support.');
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  const hex = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
  if (hex !== value.board.sha256.toLowerCase()) throw Error('The model does not match the parts data. Open both files from the same export.');
}

function initializeRenderer() {
  if (renderer) return;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    throw Error('WebGL is unavailable. Try a browser with hardware graphics enabled.');
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.35;
  renderer.domElement.setAttribute('aria-label', '3D Ulva board. Drag to orbit, scroll to zoom, right-drag to pan.');
  renderer.domElement.tabIndex = 0;
  viewport.prepend(renderer.domElement);
  scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xf3f7ff, 0x6b7770, 2.5));
  const key = new THREE.DirectionalLight(0xfff4e5, 3.2);
  key.position.set(1, -1, 2); scene.add(key);
  const fill = new THREE.DirectionalLight(0xd4eaff, 1.8);
  fill.position.set(-1, 1, -1); scene.add(fill);
  camera = new THREE.PerspectiveCamera(38, 1, 0.001, 1000);
  camera.up.set(0, 0, 1);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.screenSpacePanning = true;
  controls.addEventListener('change', scheduleRender);
  controls.listenToKeyEvents(renderer.domElement);
  new ResizeObserver(resize).observe(viewport);
  renderer.domElement.addEventListener('webglcontextlost', event => {
    event.preventDefault(); failure('The graphics context was interrupted. Reload this page to restore the model.');
  });
}

function disposeModel(model) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  model.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of Array.isArray(object.material) ? object.material : object.material ? [object.material] : []) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  for (const item of [...geometries, ...materials, ...textures]) item.dispose();
}

async function mount(value, buffer, generation) {
  verifyEmbeddedGLB(buffer);
  await verifyHash(buffer, value);
  if (generation !== loadingGeneration) return;
  const loader = new GLTFLoader();
  const gltf = await loader.parseAsync(buffer, '');
  if (generation !== loadingGeneration) { disposeModel(gltf.scene); return; }
  const model = gltf.scene;
  try {
    const objects = new Map();
    model.traverse(object => {
      if (!object.name) return;
      if (!objects.has(object.name)) objects.set(object.name, []);
      objects.get(object.name).push(object);
    });
    const mapped = value.components.map(component => {
      const matches = objects.get(component.node);
      if (!matches || matches.length !== 1) throw Error(`The model cannot identify ${component.id}. Open a matching model and parts file.`);
      return [component, matches[0]];
    });
    initializeRenderer();
    model.updateMatrixWorld(true);
    // A module attached to a socket in CAD must still have its own visibility.
    for (const [, object] of mapped) if (object.parent !== model) model.attach(object);
    const extent = new THREE.Box3().setFromObject(model);
    if (extent.isEmpty()) throw Error('The model contains no visible geometry.');
    const sphere = extent.getBoundingSphere(new THREE.Sphere());
    if (!(sphere.radius > 0) || !Number.isFinite(sphere.radius)) throw Error('The model dimensions are invalid.');
    if (assembly) { scene.remove(assembly); disposeModel(assembly); }
    assembly = model; center = sphere.center; radius = sphere.radius;
    upAxis = value.upAxis || 'Z';
    scene.add(assembly); parts.clear();
    for (const [component, object] of mapped) {
      object.visible = component.defaultVisible !== false;
      parts.set(component.id, { ...component, object, input: null, row: null });
    }
    controls.dispose();
    camera.up.set(0, upAxis === 'Y' ? 1 : 0, upAxis === 'Z' ? 1 : 0);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false; controls.screenSpacePanning = true;
    controls.minDistance = radius * 0.08; controls.maxDistance = radius * 20;
    controls.addEventListener('change', scheduleRender);
    controls.listenToKeyEvents(renderer.domElement);
    buildParts(); resize(); setView('isometric');
    document.querySelectorAll('[data-view],#reset-view,#part-search,#kind-filter').forEach(node => node.disabled = false);
    $('loading-panel').hidden = true; $('gesture-hint').hidden = false;
    $('gesture-hint').textContent = mobile.matches ? 'Drag to orbit · Pinch to zoom · Two fingers to pan' : 'Drag to orbit · Scroll to zoom · Right-drag to pan';
    viewport.setAttribute('aria-busy', 'false'); viewport.dataset.ready = 'true';
    for (const url of downloadURLs) URL.revokeObjectURL(url);
    downloadURLs = [URL.createObjectURL(new Blob([buffer], { type: 'model/gltf-binary' })),
      URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + '\n'], { type: 'application/json' }))];
    $('download-model').href = downloadURLs[0]; $('download-model').download = value.board.file;
    $('download-parts').href = downloadURLs[1]; $('download-parts').download = 'assembly.json';
    updateCounts(); scheduleRender();
  } catch (error) {
    if (model !== assembly) disposeModel(model);
    throw error;
  }
}

function resize() {
  if (!renderer || !camera) return;
  const width = viewport.clientWidth, height = viewport.clientHeight;
  if (!width || !height) return;
  renderer.setSize(width, height, false);
  camera.aspect = width / height; camera.updateProjectionMatrix(); scheduleRender();
}

function scheduleRender() {
  if (renderPending || !renderer) return;
  renderPending = true;
  requestAnimationFrame(() => {
    renderPending = false;
    if (assembly) {
      // Keep copper and mask surfaces distinct without clipping close inspection.
      const distance = camera.position.distanceTo(center);
      const orbitDistance = camera.position.distanceTo(controls.target);
      camera.near = Math.max(distance - radius * 1.5, orbitDistance / 100, radius / 100000);
      camera.far = Math.max(distance + radius * 1.5, radius * 2);
      camera.updateProjectionMatrix();
    }
    renderer.render(scene, camera);
  });
}

function setView(view) {
  if (!assembly) return;
  const vertical = THREE.MathUtils.degToRad(camera.fov / 2);
  const horizontal = Math.atan(Math.tan(vertical) * camera.aspect);
  const distance = radius / Math.sin(Math.min(vertical, horizontal)) * 1.12;
  let direction;
  if (upAxis === 'Z') direction = view === 'top' ? [0, -.0001, 1] : view === 'bottom' ? [0, -.0001, -1] : [1, -1.35, 1.35];
  else direction = view === 'top' ? [0, 1, .0001] : view === 'bottom' ? [0, -1, .0001] : [1, 1.35, 1.35];
  camera.position.copy(center).add(new THREE.Vector3(...direction).normalize().multiplyScalar(distance));
  camera.near = Math.max(distance - radius * 1.5, radius / 100000);
  camera.far = Math.max(distance + radius * 1.5, radius * 2);
  camera.updateProjectionMatrix(); controls.target.copy(center); controls.update();
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  scheduleRender();
}

function updateCounts() {
  const counts = { carrier: [0, 0], module: [0, 0] };
  for (const part of parts.values()) {
    counts[part.kind][1]++;
    if (part.object.visible) counts[part.kind][0]++;
    if (part.input) part.input.checked = part.object.visible;
  }
  for (const [kind, [shown, total]] of Object.entries(counts)) {
    const label = document.querySelector(`[data-group-count="${kind}"]`);
    if (label) label.textContent = `${shown} / ${total} visible`;
  }
  $('visible-count').textContent = `Carrier ${counts.carrier[0]}/${counts.carrier[1]} · Modules ${counts.module[0]}/${counts.module[1]}`;
  scheduleRender();
}

function setGroup(kind, visible) {
  for (const part of parts.values()) if (part.kind === kind) part.object.visible = visible;
  updateCounts();
}

function buildParts() {
  $('part-groups').replaceChildren();
  for (const [kind, title] of [['module', 'Plug-in modules'], ['carrier', 'Carrier components']]) {
    const section = document.createElement('section'); section.className = 'part-group'; section.dataset.kind = kind;
    const heading = document.createElement('div'); heading.className = 'group-heading';
    const h3 = document.createElement('h3'); h3.textContent = title;
    const count = document.createElement('span'); count.className = 'group-count'; count.dataset.groupCount = kind;
    heading.append(h3, count); section.append(heading);
    const actions = document.createElement('div'); actions.className = 'group-actions';
    for (const [visible, label] of [[true, 'Show all'], [false, 'Hide all']]) {
      const button = document.createElement('button'); button.textContent = label;
      button.dataset.groupAction = `${kind}-${visible ? 'show' : 'hide'}`;
      button.setAttribute('aria-label', `${label} ${kind === 'carrier' ? 'carrier components' : 'plug-in modules'}`);
      button.onclick = () => setGroup(kind, visible); actions.append(button);
    }
    section.append(actions);
    const list = document.createElement('div'); list.className = 'part-list';
    for (const part of [...parts.values()].filter(p => p.kind === kind).sort((a, b) => natural.compare(a.id, b.id))) {
      const row = document.createElement('label'); row.className = 'part-row'; row.dataset.part = part.id;
      const input = document.createElement('input'); input.type = 'checkbox'; input.checked = part.object.visible;
      input.dataset.part = part.id; input.setAttribute('aria-label', `${part.id}: ${part.label}`);
      const copy = document.createElement('span'); copy.className = 'part-copy';
      const name = document.createElement('span'); name.className = 'part-name';
      const ref = document.createElement('span'); ref.className = 'part-ref';
      ref.textContent = kind === 'module' ? part.label : part.id;
      name.append(ref);
      if (part.approximate) { const badge = document.createElement('span'); badge.className = 'approx'; badge.textContent = 'Approx.'; name.append(badge); }
      copy.append(name);
      if (kind === 'carrier') { const detail = document.createElement('span'); detail.className = 'part-label'; detail.textContent = part.label; copy.append(detail); }
      input.onchange = () => { part.object.visible = input.checked; updateCounts(); };
      row.append(input, copy); list.append(row); part.input = input; part.row = row;
    }
    section.append(list); $('part-groups').append(section);
  }
  filterParts();
}

function filterParts() {
  const query = $('part-search').value.trim().toLocaleLowerCase();
  const kind = $('kind-filter').value;
  let total = 0;
  for (const section of document.querySelectorAll('.part-group')) {
    let matches = 0;
    for (const part of parts.values()) {
      if (part.kind !== section.dataset.kind) continue;
      const visible = (kind === 'all' || kind === part.kind) && `${part.id} ${part.label}`.toLocaleLowerCase().includes(query);
      part.row.hidden = !visible; if (visible) matches++;
    }
    section.hidden = !matches; total += matches;
  }
  $('no-results').hidden = total !== 0;
}

function chooseLocalAssembly() {
  $('loading-panel').hidden = false;
  $('load-title').textContent = 'Open assembly files';
  $('load-status').textContent = 'Select assembly.json and its matching board.glb together. Both files stay on your device.';
  $('load-status').classList.remove('error');
  $('retry-load').hidden = true;
  $('open-files').hidden = false;
  viewport.setAttribute('aria-busy', 'false');
  if (!assembly) $('visible-count').textContent = 'Select assembly files';
}

async function fromNetwork() {
  if (localFileMode) { chooseLocalAssembly(); return; }
  const generation = ++loadingGeneration;
  request?.abort(); const controller = new AbortController(); request = controller;
  loading('Opening the board and its parts…');
  try {
    const response = await fetch('./assembly.json', { cache: 'no-cache', signal: controller.signal });
    if (!response.ok) throw Error(`Parts data could not be loaded (HTTP ${response.status}). Retry or open both local files.`);
    const value = validateManifest(await response.json());
    if (generation !== loadingGeneration) return;
    const model = await fetch('./' + value.board.file, { cache: 'no-cache', signal: controller.signal });
    if (!model.ok) throw Error(`The board model could not be loaded (HTTP ${model.status}). Retry or open both local files.`);
    await mount(value, await model.arrayBuffer(), generation);
  } catch (error) { if (generation === loadingGeneration) failure(error.message || 'Unable to load the assembly.'); }
}

$('open-files').onclick = () => $('assembly-files').click();
$('assembly-files').onchange = async event => {
  const files = [...event.target.files]; event.target.value = ''; if (!files.length) return;
  const generation = ++loadingGeneration; request?.abort(); loading('Opening the selected assembly files…');
  try {
    const json = files.find(file => file.name === 'assembly.json') || files.find(file => /\.json$/i.test(file.name));
    if (!json) throw Error('Select assembly.json and its matching board.glb together.');
    const value = validateManifest(JSON.parse(await json.text()));
    const model = files.find(file => file.name === value.board.file);
    if (!model) throw Error(`Select ${value.board.file} together with assembly.json.`);
    await mount(value, await model.arrayBuffer(), generation);
  } catch (error) { if (generation === loadingGeneration) failure(error.message || 'Unable to open these files.'); }
};
$('retry-load').onclick = fromNetwork;
$('part-search').addEventListener('input', filterParts);
$('kind-filter').addEventListener('change', filterParts);
document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => setView(button.dataset.view));
$('reset-view').onclick = () => setView('isometric');
if (localFileMode) chooseLocalAssembly();
else fromNetwork();
