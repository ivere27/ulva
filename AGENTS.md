# Project instructions

- Read `README.md` and `docs/hardware.md` before changing the design.
- Use English for documentation, code comments and tool output.
- Treat the KiCad sources as authoritative. Keep schematics, PCB and project
  libraries consistent, and use relative paths for project resources.
- For CAD changes, run relevant ERC and DRC checks. For firmware changes,
  follow the build instructions in `firmware/buttons_adc/README.md`.
- Report the checks performed and any limitations. File checks and simulations
  do not establish physical hardware validation.
- Regenerate `docs/images/` and `docs/routing/` from the matching
  board revision; do not edit generated images or viewer data by hand.
- Keep documentation concise. Exclude credentials, personal paths and local
  build output from version control.
- Preserve `LICENSE` and the upstream attribution in `NOTICE.md`.
- Create Git commits only when explicitly requested.
