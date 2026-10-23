# Third-party notices

The project uses symbols, embedded footprints and 3D model data from the
[KiCad libraries](https://www.kicad.org/libraries/), maintained by the KiCad
library contributors. These libraries use CC BY-SA 4.0 with an exception for
electronic designs and their generated files. See the
[KiCad library license and exception](https://www.kicad.org/libraries/license/).
The exported 3D scene includes geometry derived from these libraries. The Ulva
MIT license does not replace the license of upstream library data.

The 3D viewer and exporter use [Three.js](https://threejs.org/) 0.170.0 under
the MIT license. The bundled modules retain the upstream
[copyright and license notice](docs/3d/vendor/LICENSE.txt).

The VRML loader includes [Chevrotain](https://github.com/Chevrotain/chevrotain)
9.0.1 under [Apache License 2.0](docs/3d/vendor/chevrotain-LICENSE.txt), including
[regexp-to-ast](https://github.com/bd82/regexp-to-ast) 0.5.0 under the
[MIT license](docs/3d/vendor/regexp-to-ast-LICENSE.txt), copyright 2018 Shahar Soel.
See the [vendor manifest](docs/3d/vendor/README.md) for sources and local changes.

The illustrative ESP32-C5 DevKit model uses mechanical dimensions published by
[Espressif](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html#related-documents).
It is an original approximation, not a manufacturer-provided assembly model.

KiCad and ESP-IDF are installed separately and retain their respective
licenses. Manufacturer datasheets referenced in component properties are
external documents and are not included under the Ulva MIT license.
