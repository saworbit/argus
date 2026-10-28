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

---

### 10. `argus_humanness.py`
Map-matched movement distance between bot tracks and human reference tracks, read from ordinary `ARGLOG` telemetry rather than demo entity angles.
- **Usage**:
  ```bash
  python tools/argus_humanness.py runs/candidate.log
  python tools/argus_humanness.py --profile runs/ab_dm4_*.log
  python tools/argus_humanness.py --human
  python tools/argus_humanness.py --help
  ```
- **Behavior**:
  - Scores eight distribution features per bot track against same-map human tracks and reports a normalised empirical Wasserstein distance scaled by the human interquartile range. Lower is closer.
  - `--profile` adds SIGNED per-feature gaps. The scored distance is unsigned by construction: it says a feature is wrong without saying which way, which is the one thing a behaviour change needs.
  - `--human` lists the reference corpus; `--reference` overrides it.
  - Human and bot positions share cadence and precision, and bot tracks are not PVS-culled.
- **Exit Code**: `0` on success or `--help`. The score is evidence, never a quality gate, and the corpus carries a known bias: every human track was recorded hunting bots.

---

### 11. `argus_gait.py`
Attributes a tape's stationary windows to a deliberate pause or to something else.
- **Usage**:
  ```bash
  python tools/argus_gait.py runs/my_session.log
  python tools/argus_gait.py runs/*.log --max-hold 8 --attribute-sec 4
  python tools/argus_gait.py --help
  ```
- **Behavior**:
  - Freeze windows come from the shared `argus_tape.freeze_windows`, aligned with `MatchTape::freezes` in the Rust lab parser.
  - A window is credited to a hesitation only when that bot's own `ARGUS <name> hesitate <heard|junction|settle>` marker sits just before it. A window with no marker near it is the pre-existing fight-pin class ([#322](https://github.com/saworbit/argus/issues/322)).
  - A freeze count alone cannot separate the two, and both laddered maps produce long fight-pin freezes on unchanged code.
- **Exit Code**: `0` when no stationary window is attributable to a chosen pause that outlasted its own hold or took damage, `1` when one is.

---

### 12. `argus_voidprobe.py`
Offline hull-0 read of a shipped navigation graph, for the two questions the runtime's point-resolution probes cannot answer.
- **Usage**:
  ```bash
  python tools/argus_voidprobe.py dm4
  python tools/argus_voidprobe.py dm4 dm2 dm3 dm6 --clearance
  python tools/argus_voidprobe.py dm4 --reach 52 --format json
  python tools/argus_voidprobe.py --help
  ```
- **Behavior**:
  - Reproduces `Argus_MoveHazard`'s 280-unit floor test for eight headings from every waypoint, and for the directions it would veto as void, reports what actually lies underneath and how far down.
  - `--clearance` audits each waypoint's cardinal elbow room against navgen's own 5a2 seat-shift bar, so a shipped graph can be checked without regenerating it.
  - Measured on the shipped graphs: no probe direction from any waypoint finds lava underfoot, every void dm4 and dm2 veto bottoms out in lava while dm3's and dm6's bottom out in stone or water, and 7 per cent of dm4 and dm2 waypoints sit within 24 units of a wall.
- **Inputs**: `maps_local/<map>.bsp` and `src/argus_nav_<map>.qc.json`; maps missing either are skipped with a note.
- **Exit Code**: `0` on success or `--help`.

---

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

### Behaviour, perception, plan and muzzle contracts

```text
python -m pip install -r tools/requirements-perception-cohort.txt
python -m unittest discover -s tools -p "test_behaviour*.py"
python -m unittest discover -s tools -p "test_perception*.py"
python tools/test_muzzle_fixture.py
python tools/test_tactic_fixture.py
python tools/test_review_outputs.py
python tools/test_plan_progress.py
python tools/test_offset_entry.py
python tools/test_muzzle_combat.py
python tools/test_button_physical.py
python tools/test_door_actuator.py
python tools/test_private_fixtures.py
```

These commands exercise Python contracts without launching a cohort or engine.
The muzzle suite and local review-output contracts run in the fast workflow.
The plan evidence oracle runs there too. For authorised native decision and
physical-escape checks, use `python tools/verify_plan_progress.py --output
backups/plan-check-1`; choose a new output directory. It uses private source
and asset copies and never writes installed game files. `--help` is read-only;
`--mode contract` or `--mode physical` selects part of its fixed fixture suite.
`--mode edges` covers co-op retry/rest, long detours, waypoint cycles and
deadline ownership with injected controller state on dm2/e1m2.
`--mode physical-edges --physical-part coop` runs the separate real co-op
retry fixture; `--physical-part normal` checks the completing e1m2 route.
The separate `mover`, `mover-control` and `mover-release` parts check the
shipped-speed real-door witness, deadline-disabled control and premature-release
control. Run each separately with fresh output paths for bounded experiments.
The default physical gate excludes the historical motor override; explicit
`half`/`deadline-control` selectors retain it as a diagnostic, not a supported
navigation-speed setting. The full schedule stops on failure.
`check_muzzle_fixture.py` exposes `check(text)` and `audit(source)` for Python
callers; it has no CLI. The private `fixtures/muzzle_clearance.qc` is excluded
from production and emits `MFIX` under a quarantining `BHVRPL begin` marker.

`health_inventory_parked.py` verifies the active source against a declared
manifest, reverses allowlisted opening-door, button/door, offset-entry,
active-health, plan and muzzle
amendments in memory, then reconstructs
the historical health/inventory candidate for static checks. Those historical
checks alone do not establish the behaviour of a current build.

Step 1b is now reactivated in development. The manifest additionally verifies
the actual active function hashes; reverse patches retain the frozen historical
parked/candidate definitions without altering the checked-in source.
`python tools/verify_offset_entry.py --output backups/<new-directory>` runs
four small physical entry cases plus an old-handoff policy control, using
private native builds. `--variants current` limits it to the fixed source;
`--cases 3` isolates the recorded airborne offset. The source/trajectory audit
and evidence parser run in fast CI through `tools/test_offset_entry.py`.
Its `old_handoff` airborne-offset case 3 must fail. Unexpected passes,
current-case failures and malformed receipts fail automatically, with invalid
receipts retained. Other old-policy cases remain diagnostic. CLI defaults and case meanings are in the
[focused runbook](../docs/lab-workflow.md#focused-checks-without-deployment).

The fresh 44 active step 1b native checks used local private drivers retained
under `backups/offset-entry-20261027/`. They are evidence, not a clean-checkout
command. `run_health_fixture.py` still depends on historical snapshots and
temporarily stages `engine/argus/progs.dat`; do not treat it as a no-install
replacement. Use the maintained driver instead:

```text
python tools/verify_private_fixtures.py --help
python tools/verify_private_fixtures.py health --output backups/health-check-1 --prefix health_check_1
```

It uses private source/assets/binaries/runs and checks protected files after
success or failure. Choose new output directories and prefixes. Replace `health`
with `muzzle`, `combat`, `button` or `door` for the corresponding contracts and
declared controls. These checks launch no gameplay cohort and do not install
binaries. See [native fixture choices](../docs/lab-workflow.md#focused-checks-without-deployment).


Compile-only CI also checks all 17 maintained variants across `muzzle`,
`combat`, `health`, `button`, `door`, `plan` and `offset`. It reuses the native
verifiers' staging helpers, including extracted production decision wrappers:

```text
python tools/compile_private_fixtures.py --help
python tools/compile_private_fixtures.py --compiler <pinned-fteqcc> --family door --output backups/door-compile-1
```

Use the FTEQCC revision pinned in `.github/workflows/compile.yml`. Omit
`--family` to compile every family serially. Supply a new output directory;
existing evidence is refused. Each variant must produce a fresh id-format
`progs.dat` and the compiler's id-format finish line. Source/compiler/binary
hashes, logs and failure receipts remain in that directory. This needs no
lab connection, engine, BSPs or historical snapshots and never installs a
binary. It proves compilation only; native trials still determine fixture
outcomes. CI runs it when sources, fixtures or Python staging helpers change.

`verify_muzzle_clearance.py`, `investigate_health_stalls.py` and
`prepare_blind_perception.py` are retained one-shot study drivers. They are not
argument-parsing CLIs and require their original local snapshots/fresh output
names. Do not run them with `--help`, overwrite their evidence, or treat them
as clean-checkout setup commands. See the [focused-check runbook](../docs/lab-workflow.md#focused-checks-without-deployment).
The reusable blind-review HTML template is `blind_perception_review.html`;
generated clips and answer keys stay local and outside Git staging.
