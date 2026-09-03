## Summary

<!-- Briefly describe the purpose and impact of this change. -->

## Type of Change

- [ ] **Bot AI / Logic** (GOAP goal scorer, combat, aim model, perception)
- [ ] **Movement / Physics** (hazard avoidance, jump mechanics, elevator/train handling)
- [ ] **Navigation / Maps** (navgen generator, graph links, sidecar probe data)
- [ ] **Lab MCP & Tooling** (Rust server, Python telemetry, visualization)
- [ ] **CI / Build System** (fteqcc compile, GitHub Actions, packaging)
- [ ] **Documentation** (README, guides, comments)

## Hard Project Constraints & Checklist

Please confirm your changes adhere to Argus engineering standards:

- [ ] **Vanilla QuakeC**: Code runs in standard NetQuake protocol 15, stays within 600 edicts, and uses no engine extensions or file I/O.
- [ ] **Generated Nav Integrity**: Generated map files (`src/argus_nav_<map>.qc`) are **not** hand-edited (generated via `tools/argus_navgen.py` or MCP `nav_generate`).
- [ ] **Frametime Calibration**: Any time-based physics or drag scales with `frametime` (calibrated against `frametime 0.1` lab rate).
- [ ] **Compilation**: Compiles cleanly with `fteqcc` (id format finish line verified).
- [ ] **Lab Tests**: `cargo test --manifest-path tools/argus_mcp/Cargo.toml --lib` passes without errors.
- [ ] **Directed Reach**: `python tools/argus_reach.py [map]` verified if modifying navigation.
- [ ] **Licensing**: QC code in `src/` complies with GPLv2; tooling in `tools/` complies with MIT.

## Telemetry / Verification

<!-- Describe how you verified this change (e.g. headless match run, telemetry log comparison, or live client observation). -->
