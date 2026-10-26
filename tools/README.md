# Argus Developer Tools

This directory contains standalone command-line tools for navigation generation, match analysis, session harvesting, and graph reach validation.

For agent development, use the [native lab workflow](../docs/lab-workflow.md)
before choosing a standalone tool. Current development-source status and
recorded validation are in [behaviour diagnostics](../docs/behaviour-diagnostics.md#current-development-status).

---

## Tool Index

### 1. `analyze_match.py`
Plots BSP wireframe geometry, player telemetry trajectories, A/B match panels, and combat/hazard deaths.
- **Usage**:
  ```bash
  python tools/analyze_match.py <map.bsp> <logA> [logB] <out.png> [nav.json]
  python tools/analyze_match.py --help
  ```
- **Inputs**:
  - `map.bsp`: BSP29 level file used for hull-0 lava/slime point contents classification and wireframe overlay.
  - `logA`: Primary match log with `ARGLOG` / `ARGEVT` telemetry.
  - `logB` *(optional)*: Secondary match log for side-by-side A/B comparison.
  - `out.png`: Target output plot image.
  - `nav.json` *(optional)*: Navigation graph json (`argus_nav_<map>.qc.json`) to overlay waypoints and links.
- **Exit Code**: `0` on success or `--help`, `1` on invalid arguments or missing input files.

---

### 2. `argus_reach.py`
Directed-reach audit for shipped navigation graphs using spawn-point BFS traversals.
- **Usage**:
  ```bash
  python tools/argus_reach.py [map ...]
  python tools/argus_reach.py --help
  ```
- **Behavior**:
  - Without arguments, audits every map that has both `maps_local/<map>.bsp` and `src/argus_nav_<map>.qc.json`.
  - Calculates directed forward reach from each spawn across all edges (`walk`, `jump`, `tele`, `rj`, `lift`, `swim`, `train`, `sprint`) and ungated edges.
- **Exit Code**:
  - `0`: All spawn points meet the $\ge 60\%$ directed reach threshold.
  - `1`: Any spawn point has $< 60\%$ reach (7h gate failure), an explicitly requested map is missing, or zero maps were audited.

---

### 3. `argus_review.py`
Tape review battery for automated playtest inspections and stuck-bot forensics.
- **Usage**:
  ```bash
  python tools/argus_review.py summary <log>
  python tools/argus_review.py deaths <log>
  python tools/argus_review.py region <log> <bot|all> <x0> <x1> <y0> <y1>
  python tools/argus_review.py rides <log>
  python tools/argus_review.py --help
  ```
- **Commands**:
  - `summary`: Event totals, first goal acquisition, per-bot combat stats, and freeze detection (velocity $< 20\text{ u/s}$ within $32\text{ u}$ Euclidean radius for $6+\text{ s}$, aligned with `MatchTape::freezes` in Rust lab parser).
  - `deaths`: Chronological list of deaths with the victim's preceding 14 telemetry samples.
  - `region`: Trace bot trajectories and interleaved events strictly within bounding coordinates.
  - `rides`: Train and lift transition audit, deck crossings, and bridge fall tracking (dm2 geometry).
- **Exit Code**: `0` on success or `--help`, `1` on missing arguments or invalid command.

---

### 4. `argus_navgen.py`
Offline BSP29 hull 1 clipnode parser and waypoint/link compiler. Generates `src/argus_nav_<map>.qc` and `src/argus_nav_<map>.qc.json`.
- **Usage**:
  ```bash
  python tools/argus_navgen.py <map.bsp> <mapname> <out.qc> <out.png> [--no-dispatcher] [--no-rj] [--grid <n>] [--register]
  python tools/argus_navgen.py <map.bsp> <mapname> <shipped.qc> <unused.png> --reanalyze-tactics
  python tools/argus_navgen.py --help
  ```
- **Options**:
  - `--no-dispatcher`: Suppress generation of the per-map `Argus_Nav_Spawn` function (recommended when using `argus_nav_dispatch.qc`).
  - `--no-rj`: Suppress rocket-jump link exploration.
  - `--grid <n>`: Override base waypoint sampling grid spacing.
  - `--register`: Wire the generated file into `src/progs.src` and update `src/argus_nav_dispatch.qc`. The output filename must be `argus_nav_<mapname>.qc`; custom names are refused before generation.
  - `--reanalyze-tactics`: Recompute static exposure and nearest hidden ordinary-walk targets in an existing shipped QC/JSON pair without changing graph topology or typed movement data.

---

### 5. `harvest_session.py`
Ingests a live human or bot play session from `qconsole.log` and `.dem` recordings into the `runs/` archive.
- **Usage**:
  ```bash
  python tools/harvest_session.py [--tag <build_tag>] [--dry-run]
  python tools/harvest_session.py --help
  ```
- **Outputs**:
  - Stamped log: `runs/shane_<map>_<date>[_<tag>].log`
  - Paired demo: `runs/demos/shane_<map>_<date>[_<tag>].dem`

---

### 6. `pak_extract.py`
Minimal id PAK archive inspector and file extractor.
- **Usage**:
  ```bash
  python tools/pak_extract.py <pak> [<pak> ...] --list
  python tools/pak_extract.py <pak> [<pak> ...] --out <dir> <name> [<name> ...]
  python tools/pak_extract.py --help
  ```

---

### 7. `test_tools_cli.py`
Unit test runner validating command-line interfaces, exit codes, and error formatting across the tools suite.
- **Run**:
  ```bash
  python tools/test_tools_cli.py
  ```

---

### 8. `setup_rig.sh`
Automated Linux test rig environment bootstrap script (Ubuntu/Debian). Builds `fteqcc` from upstream source, fetches LibreQuake free assets, sets up the QuakeSpasm headless harness, and runs a baseline smoke test.
- **Usage**:
  ```bash
  ./tools/setup_rig.sh
  ```
- **Requirements**: Supports root or non-root execution via `sudo`.

---

### 9. `tactic_review.py`
Summarizes ordinary-session tactical entry diagnostics and applied difficulty
using the shared tape reader.
- **Usage**:
  ```bash
  python tools/tactic_review.py runs/my_session.log
  python tools/tactic_review.py --help
  ```
- **Output**: JSON containing map, per-bot evaluation ticks and tactical phase
  counts, plus applied difficulty records. Entry ticks are throttled checks,
  not independent encounters. Legacy tapes without diagnostics have unknown
  opportunity counts; ordinary-session `return_hits` is always `null`.
- **Validation**: `python tools/test_tactic_review.py` exercises legacy tapes,
  multiword names and separation of checks, shots and applied aim share.

Bot POV recording, PNG capture and video export use the Rust lab CLI:

```text
argus-mcp record-pov my_pov 1 8
argus-mcp capture-demo my_pov 0.5 12 0.1
argus-mcp capture-video my_pov 0.5 2.4 0.5
```

The recorder joins an existing lab match. Video export requires FFmpeg with
`libvpx-vp9` on PATH and writes a silent lossless VP9 WebM; PNG capture needs
no encoder. The video example samples 2.4 source seconds and plays them over
4.8 seconds at half speed. See [rendered POV evidence](argus_mcp/README.md#rendered-pov-evidence)
for asset requirements, verification and bounds.

### Behaviour, perception and muzzle contracts

```text
python -m pip install -r tools/requirements-perception-cohort.txt
python -m unittest discover -s tools -p "test_behaviour*.py"
python -m unittest discover -s tools -p "test_perception*.py"
python tools/test_muzzle_fixture.py
python tools/test_tactic_fixture.py
python tools/test_review_outputs.py
```

These commands exercise Python contracts without launching a cohort or engine.
The muzzle suite and local review-output contracts run in the fast workflow.
`check_muzzle_fixture.py` exposes `check(text)` and `audit(source)` for Python
callers; it has no CLI. The private `fixtures/muzzle_clearance.qc` is excluded
from production and emits `MFIX` under a quarantining `BHVRPL begin` marker.

`health_inventory_parked.py` verifies the active source against a declared
manifest, reverses only allowlisted amendments in memory, then reconstructs
the historical health/inventory candidate for static checks. Passing those
candidate checks does not mean step 1b is active in normal play.

`verify_muzzle_clearance.py`, `investigate_health_stalls.py` and
`prepare_blind_perception.py` are retained one-shot study drivers. They are not
argument-parsing CLIs and require their original local snapshots/fresh output
names. Do not run them with `--help`, overwrite their evidence, or treat them
as clean-checkout setup commands. See the [focused-check runbook](../docs/lab-workflow.md#focused-checks-without-deployment).
The reusable blind-review HTML template is `blind_perception_review.html`;
generated clips and answer keys stay local and outside Git staging.
