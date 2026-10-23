# Viewer dependencies

These files are bundled so the viewer and exporter work without a CDN or npm
installation. Preserve the license files when copying this directory.

| Dependency | Version | License |
| --- | --- | --- |
| [Three.js](https://github.com/mrdoob/three.js/tree/r170) | 0.170.0 / r170 | [MIT](LICENSE.txt) |
| [Chevrotain](https://registry.npmjs.org/chevrotain/9.0.1) | 9.0.1 | [Apache-2.0](chevrotain-LICENSE.txt) |
| [regexp-to-ast](https://registry.npmjs.org/regexp-to-ast/0.5.0) | 0.5.0, included in the Chevrotain bundle | [MIT](regexp-to-ast-LICENSE.txt) |

All JavaScript files come from the Three.js **r170** release:

| Local file | Upstream path |
| --- | --- |
| `three.module.js` | `build/three.module.js` |
| `OrbitControls.js` | `examples/jsm/controls/OrbitControls.js` |
| `GLTFLoader.js` | `examples/jsm/loaders/GLTFLoader.js` |
| `GLTFExporter.js` | `examples/jsm/exporters/GLTFExporter.js` |
| `VRMLLoader.js` | `examples/jsm/loaders/VRMLLoader.js` |
| `BufferGeometryUtils.js` | `examples/jsm/utils/BufferGeometryUtils.js` |
| `chevrotain.module.min.js` | `examples/jsm/libs/chevrotain.module.min.js` |

Retrieve a source file at
`https://raw.githubusercontent.com/mrdoob/three.js/r170/<upstream-path>`.
The local Three.js helper files change import paths only:

- `three` → `./three.module.js`
- `../utils/BufferGeometryUtils.js` → `./BufferGeometryUtils.js`
- `../libs/chevrotain.module.min.js` → `./chevrotain.module.min.js`

`three.module.js` and `chevrotain.module.min.js` are unchanged upstream files.
`LICENSE.txt` comes from the Three.js release; the other two license files are
unchanged copies from the corresponding published npm packages.
