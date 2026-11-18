# Argus Developer Tools

Navigation names use the lab's shared rule: trim and lowercase, then
`[a-z0-9_]{1,32}`, excluding `dispatch`. `argus_navgen.py` refuses invalid
names before opening a BSP or output. Generation counts unique destinations
across all typed families, preserves typed routes when pruning walks and
refuses typed overflow before writing. `test_nav_contracts.py` checks the
name cases shared with Rust and the eight-slot contract.

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

`analyze_match.py` is safe to import without running its CLI or loading plotting
libraries. It and `argus_voidprobe.py` use the shared hull-0 reader in
`argus_bsp.py`. The analyzer alone retains the no-BSP `z < -300` death fallback;
with a BSP, lava/slime contents at the death origin or 24 units below remain
authoritative. The void probe still requires a readable BSP.

Each bot track keeps its roster slot's colour (Carmack, Romero, Joe Rogan and
Mr Elusive, or the same slots under their older names), so one bot matches
across A/B panels; a player outside the roster draws in neutral ink. The nav
overlay uses the shared link styles in `argus_linkstyle.py`.
The Omicron roster puts Mr Elusive in slot 1; the normal roster puts him in
slot 3. Each panel selects its roster from the names in that tape.

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
  - `ARGUS_MAPS` overrides the BSP folder, as it does for the lab, so a worktree can point at the main checkout's `maps_local/`.
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
  python tools/argus_navgen.py <map.bsp> <mapname> <shipped.qc> <unused.png> --repair-links
  python tools/argus_navgen.py <map.bsp> <mapname> <shipped.qc> <unused.png> --seat-links src/argus_nav_<map>.seats.json
  python tools/argus_navgen.py <map.bsp> <mapname> <shipped.qc> <out.png> --render-only
  python tools/argus_navgen.py --help
  ```
- **Options**:
  - `--render-only`: Render the existing QC/JSON graph into a PNG and freshness receipt. No navigation, tactics or registration file is changed. Cannot be combined with generation options; plotting failure returns a nonzero status.
  - `--no-dispatcher`: Suppress generation of the per-map `Argus_Nav_Spawn` function (recommended when using `argus_nav_dispatch.qc`).
  - `--no-rj`: Suppress rocket-jump link exploration.
  - `--grid <n>`: Override base waypoint sampling grid spacing.
  - `--register`: Wire the generated file into `src/progs.src` and update `src/argus_nav_dispatch.qc`. The output filename must be `argus_nav_<mapname>.qc`; custom names are refused before generation.
  - `--reanalyze-tactics`: Recompute static exposure and nearest hidden ordinary-walk targets in an existing shipped QC/JSON pair without changing graph topology or typed movement data.
  - `--repair-links`: Keep a shipped graph's nodes and link slot order and cut two classes of link: a zero-length "walk" that rises past an 18-unit step, and a link from a dry seat into a seat whose feet stand in lava or slime (or a walk that wades it). A cut liquid link stays when it is a dry seat's only ungated way to the mainland, and seats already in liquid keep their links out. Rebakes regions and tactics; a second run changes nothing. Applied to nine shipped graphs in [#770](https://github.com/saworbit/argus/pull/770).
  - `--seat-links <seats.json>`: Add seats and walks to a shipped pair from a coordinate sidecar (`src/argus_nav_<map>.seats.json`: `seats`, `walks` and optional `cuts` as origins). New seats and link calls are appended, so no index or slot moves. It refuses a seat that is not a dry standable origin, a walk that `beeline_ok` refuses or that exceeds 340u, a ninth slot, and a cut whose far end would become unreachable. Reruns change nothing; regions and tactics are rebaked. A full regeneration applies the same sidecar after its late link passes (section 7g2e): seats are appended at their exact positions and joined only by the sidecar's walks, and an entry that cannot apply refuses the regeneration before anything is written. On void-edged walkways, place elbow seats so that a bot switching to its next waypoint 48u early stays over floor (see [the dm3 case](../docs/navmesh-experiment.md#seating-dm3s-south-upper-area)).
  - `--help` lists the other topology-preserving modes (`--retype-doors`, `--reprofile-jumps`, `--audit-jump-anchors`, `--reconcile-artifacts`).
- **Input checks**: Door travel uses the engine's 8-unit lip default for both missing and explicit zero values. Proven seat nominations must resolve to distinct fine samples; a collision stops generation before any QC or graph JSON is replaced.
- **Preview freshness**: Plotting is optional. Missing matplotlib, plot failures or an empty render leave QC/JSON generation successful and invalidate the preview receipt. `<out.png>.json` records `nav-preview-v1`, `generated` and MD5 hashes of the QC, graph JSON and successful PNG. Native results expose `preview_generated`; the wizard and image attachments require matching hashes. An old PNG can remain on disk, but is unavailable as a current preview. Images without a matching receipt are also unavailable. `test_nav_preview.py` and the developer CLI suite cover this without game execution.
- **Preview styling**: Link colours and dashes come from `argus_linkstyle.py`, the table the lab GUI also draws from: walk green, drop amber dashed, jump red dotted, rocket jump magenta dash-dot, teleport dark long dash, refused jump dark red dashed with an X at the far end. A drop is a plain link that descends more than one 18-unit step, so a one-way link at one level draws as a walk. See the [brand guide](../docs/brand/README.md#navigation-link-colours).

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
  - Reproduces `Argus_MoveHazard`'s 280-unit floor test for eight headings from every waypoint, and for the directions it would veto as void, reports what actually lies underneath and how far down. It does not reproduce the run-off landing test (`Argus_DropLandHazard`, [#773](https://github.com/saworbit/argus/pull/773)), which depends on the bot's speed, so a heading it reports as a safe drop can still be refused at run speed.
  - `--clearance` audits each waypoint's cardinal elbow room against navgen's own 5a2 seat-shift bar, so a shipped graph can be checked without regenerating it.
  - That bar counts only empty contents as open. Water also scores nonempty: dm3's 25 zero-open seats have 100 water samples and no solid samples. The output is not a player-hull collision verdict.
  - Measured on the shipped graphs: no probe direction from any waypoint finds lava underfoot, every void dm4 and dm2 veto bottoms out in lava while dm3's and dm6's bottom out in stone or water, and 7 per cent of dm4 and dm2 waypoints sit within 24 units of a wall.
- **Inputs**: `maps_local/<map>.bsp` and `src/argus_nav_<map>.qc.json`; maps missing either are skipped with a note.
- **Exit Code**: `0` on success or `--help`.

### 13. `brand/`
Regenerates every file in `docs/brand` (mark, wordmark, banners, social preview, favicon) from the mark's parameters in `brand/build.py`.
- **Usage**:
  ```bash
  npm install --prefix tools/brand
  python tools/brand/dist.py
  node tools/brand/raster.js
  ```
- **Requirements**: Python with fontTools, and Node.js for the pinned `@ibm/plex` font package and `@resvg/resvg-js` rasteriser. Neither is needed to play, build or run the lab. `node_modules` stays ignored.
- **Behavior**: `dist.py` writes the SVGs and `raster.js` the two PNGs. Output is deterministic: a rerun reproduces the committed files byte for byte. The lab GUI inlines its own copy of `docs/brand/favicon.svg`, so update both together; no test catches that drift yet ([#678](https://github.com/saworbit/argus/issues/678)). See the [brand guide](../docs/brand/README.md).

### 14. `argus_navmesh.py`
Exact navigation mesh read from a BSP's player clip hull (hull 1), with an audit of a shipped graph and an air layer for falls and jumps. Experimental audit tooling; it changes no graph. See [the navmesh experiment](../docs/navmesh-experiment.md).
- **Usage**:
  ```bash
  python tools/argus_navmesh.py maps_local/dm4.bsp --audit
  python tools/argus_navmesh.py maps_local/dm4.bsp --png dm4_mesh.png --nav src/argus_nav_dm4.qc.json
  python tools/argus_navmesh.py maps_local/e1m7.bsp --air --tapes runs/<tape>.log [...] --air-png e1m7_air.png
  python tools/argus_navmesh.py --help
  ```
- **Options**:
  - `--audit`: Cross-examine the shipped graph (`src/argus_nav_<map>.qc.json`, or the file `--nav` names): seats whose feet stand in lava or slime, seats on no mesh fragment, rising zero-length walks, and plain links with no mesh walk or drop path. Each off-mesh seat gets a reason: in liquid (the lava seats `--repair-links` keeps on purpose), on a face too steep to stand on, no world floor within 30 units, inside the world, or dry with no fragment, the only one that would be an extractor miss ([#788](https://github.com/saworbit/argus/issues/788)).
  - `--air`: Fly a body off every ledge point, 16 units apart, at walk (240), run (320) and run turned 30 degrees either way, plus a running jump, and grade each point danger, risky, momentum or safe by where it lands. Gravity is 100 on e1m8 and 800 elsewhere; `--gravity` overrides it.
  - `--tapes <log> [...]`: With `--air`, test each lava entry's last second against the danger ledges, using every ordinary second of movement as the base rate, and split run-offs from entries that followed a jump event.
  - `--no-brushes`: With `--air`, fly through the world hull only. By default solid walls, doors, secret doors and plats count as boxes at their deathmatch spawn positions; trains are left out.
  - `--png`, `--air-png`, `--json`: Draw the mesh or the ledge verdicts, or write the fragments as JSON. Plotting needs matplotlib; the audit and air layer do not.
- **Inputs**: A BSP29 file, usually `maps_local/<map>.bsp` (machine-local).
- **Tests**: `test_navmesh_repair.py` and `test_navmesh_air.py`, both on built fixtures. They are not yet in fast CI ([#787](https://github.com/saworbit/argus/issues/787)).
- `argus_pointfile.py <map> --what mesh` draws the mesh outlines into a listen game. It has not been checked by eye.

### 15. `argus_navmesh_graph.py`
Experimental waypoint graph derived from the mesh. Typed links are inherited from the shipped graph with their exact seats, so only the walk graph is new. On dm4 it played at parity with navgen's graph ([ladder](../docs/navmesh-experiment.md#the-mesh-graph-ladder)); other maps are [#790](https://github.com/saworbit/argus/issues/790).
- **Usage**:
  ```bash
  python tools/argus_navmesh_graph.py dm4 OUTDIR [--max-seats N] [--radius R] [--min-clear C] [--prune P]
  python tools/argus_navmesh_graph.py --help
  ```
- **Behavior**: Seats control items, then covers the mesh roomiest first. It accepts a walk link only when a body following it stays on the mesh with world floor under its centre. `--max-seats` builds dense, then removes the most crowded seat only while every in-neighbour still reaches every out-neighbour within three hops. Run navgen's `--reanalyze-tactics` on the output pair to fill exposure and cover.
- **Output**: A QC and JSON pair in `OUTDIR`, named like the shipped pair (`argus_nav_<map>.qc` and `.qc.json`). Pass a scratch directory, not `src/`, unless you mean to replace the shipped graph.

### 16. `argus_lab.py`
The lab spine: joins the corpus, scorecard, baselines, benchmarks, verdict sidecars and limits with the objective (`lab_objective.json`) and claims ledger (`lab_claims.json`). See [the lab spine](../docs/lab-spine.md).
- **Usage**:
  ```bash
  python tools/argus_lab.py state
  python tools/argus_lab.py stale [--strict]
  python tools/argus_lab.py skeptic RUN ... --vs RUN ...
  python tools/argus_lab.py triage TAPE
  python tools/argus_lab.py --help
  ```
- **Behavior**: `stale` reports void and stale artefacts with fixes; `skeptic` voids or caveats a comparison and reads each metric against its detection limit; `triage` matches a tape's trouble to claim cells; `session` scores human sessions against the hard gates and goal targets; `pyramid` runs the cheap evidence tiers first.
- **Tests**: `test_argus_lab.py` on a built fixture tree; `argus_ci.py lab` validates the objective and claims.

### 17. `argus_build_stamp.py`
Writes the QC build identity (#823) into `src/argus_build.qc`: a hash of every file `progs.src` lists, with comments and layout removed, so a comment-only change keeps the stamp and the compiled bytes. Every match prints it as `ARGUS build <id>`, and the spine credits a session to the build its tape names.
- **Usage**:
  ```bash
  python tools/argus_build_stamp.py            # print the identity of src/
  python tools/argus_build_stamp.py --write    # rewrite argus_build.qc when stale
  python tools/argus_build_stamp.py --check    # exit 1 when stale (CI: argus_ci.py stamp)
  ```
- **Behavior**: the lab's compile and `ship` steps refresh the stamp themselves (`build_stamp.rs`, held to this tool by a parity test). After a hand edit under `src/`, run `--write` and commit the stamp with the change.
- **Tests**: `test_argus_build_stamp.py`.

### 18. `argus_gallery.py`
The session gallery: picks the moments of a session worth a ruling (marks, freezes under fire, unforced world deaths, long freezes), cuts a six-second clip of each from the paired demo and serves a local page for rulings. See [the session gallery](../docs/session-gallery.md).
- **Usage**:
  ```bash
  python tools/argus_gallery.py build <stem> [--dry-run]
  python tools/argus_gallery.py serve <stem>
  python tools/argus_gallery.py verdicts <stem>
  ```
- **Behavior**: clips are licensed-data renders and stay under `runs/demos/gallery/` (gitignored); the server listens on 127.0.0.1 and accepts rulings only from its own page.
- **Tests**: `test_argus_gallery.py`.

### 19. `argus_clock_validation.py`
Applies the registered fixed-clock criterion (`docs/specs/2026-11-15-fixed-clock-validation.md`) to a played arm and a fixed arm of tapes: per metric, Welch intervals for the difference against a margin of 30 per cent of the played mean or one event. See [the fixed lab clock](../docs/fixed-clock.md).
- **Usage**:
  ```bash
  python tools/argus_clock_validation.py --map dm4 --played-glob 'fxval_played_dm4_r*' --fixed-glob 'fxval_fixed_dm4_s*'
  ```
- **Behavior**: exits 0 when the map is accepted. Metrics come from `argus-mcp corpus`; a metric the corpus does not carry reads "not measured", never zero.

### 20. `argus_standin_calibration.py`
Applies the registered stand-in calibration (`docs/specs/2026-11-15-stand-in-calibration.md`) to tapes named `<stem>_k<skill>_<seed>`: dose response (Spearman between bot skill and bot kills on the stand-in, and a top-minus-bottom Welch interval) and level against a person's mean. See [the stand-in human](../docs/stand-in.md).
- **Usage**:
  ```bash
  python tools/argus_standin_calibration.py --glob 'standin_cal_dm4_k*' --person-mean 1.27
  ```
- **Behavior**: counts kills from `ARGEVT ... death` lines (a dedicated tape has no obituaries), taking a kill as a death whose killer is a bot by name; exits 0 when dose response passes.
- **Tests**: `test_argus_instrument_tools.py`, with `argus_clock_validation.py`.

### 21. `lab_mapgen.py`
Generates purpose-built lab micro-maps from a structured request: a plain-text Quake `.map` of axis-aligned brushes inside one sealed hull, a generated texture WAD, a BSP29 compiled by the pinned ericw-tools 0.18.1 under `lab_mapgen_profile.json`, and a manifest. The lab MCP's `lab_request` runs it, then the stock navgen, mill and registration path. See [lab scenarios](../docs/lab-scenarios.md).
- **Usage**:
  ```bash
  python tools/lab_mapgen.py tools --install
  python tools/lab_mapgen.py check labmaps/lab_voidcorner/request.json
  python tools/lab_mapgen.py build labmaps/lab_voidcorner/request.json
  ```
- **Behavior**: `check` validates the request and every budget without writing; `generate` writes the `.map` and WAD (deterministic, no tools needed); `compile` adds qbsp, vis and light; `build` also installs the BSP into `ARGUS_MAPS` and the engine game directory and writes `labmaps/<map>/manifest.json`; `record` folds navgen, mill and registration results into the manifest and the scenario into `lab_instruments.json`. A request error exits 2, a build error 1.
- **Coverage**: `python tools/lab_mapgen.py coverage <request.json>` lists the floor regions the generated graph seats no waypoint on; `lab_request` refuses registration while one is uncovered and not marked `off_graph` in the request.
- **Tests**: `test_lab_mapgen.py` (determinism, brush syntax and orientation, placement by region name, budgets, the WAD, the promotion rule, the coverage gate against the shipped lab_drymix graph; a real compile and navgen pass when ericw-tools is installed, and an engine load with `ARGUS_LAB_SMOKE_ENGINE=1`).

### 22. `argus_guard_replica.py`
Names the branch of the per-frame brink guard that deflected each routed bot, read offline from a full-rate ARGMOT tape (`scratch1 697`) and the map's hull-0 tree.
- **Usage**:
  ```bash
  python tools/argus_guard_replica.py dm4 runs/dm4fl_ctl_r1.log runs/dm4fl_ctl_r2.log
  python tools/argus_guard_replica.py lab_drymix runs/labdm_ctl_r1.log --json
  python tools/argus_guard_replica.py dm4 runs/dm4ov2_ctl_r*.log --overhead src/argus_nav_dm4.qc.json
  python tools/argus_guard_replica.py dm4 runs/dm4ov3_ctl_r*.log --overhead src/argus_nav_dm4.qc.json --region 690 1060 -700 -390 -160 -90
  python tools/argus_guard_replica.py --help
  ```
- **Behavior**:
  - Replays `Argus_Physics`'s guard: the velocity heading after one frame of friction and acceleration, the speed-scaled 32 to 52u probe, and every branch of `Argus_MoveHazard` including the bridge test, the stair rescue and the run-off landing test (`Argus_DropLandHazard`). Verdicts are `wall`, `lava`, `void`, `run_off_lava`, `run_off_void` or `none`.
  - Traces follow the engine's hull check: one that starts in solid and never leaves it returns fraction 1, and one that leaves it reports an impact at the next solid it enters. A probe buried in a 16u slab over open air therefore finds what lies under the slab.
  - Validates itself on the tape: route-led deflection starts are known vetoes (mode 2 route steering has no steering-side hazard check) and steady routed frames are known passes. Brush entities are invisible to it.
  - Measured on eight dm4 control tapes: recall 0.895, false vetoes 0.019; of 1369 re-entries, 47 per cent are wall vetoes, 36 lava, 6 void and 2.5 run-off ([results](../runs/dm4-reentry-guard.results.json)).
  - `--overhead GRAPH.qc.json` adds the overhead-target primary ([protocol](../docs/specs/2026-11-17-overhead-target-protocol.md)) per tape, with each tape's route-led starts, re-entries and wall re-entries beside it and the mean over the tapes. A wall re-entry counts when, from the pose and wish the guard replay uses (row k-1), the graph waypoint 24 to 340u away horizontally whose bearing lies closest to the wish is within 8 degrees of it, stands 64u or more above the bot's origin, and has solid on the straight line to it (a hull-0 sample every 8u, both ends excluded). The protocol's wording admits any waypoint in the cone, but the recorded reading took the closest in bearing only: that gives 418 events on the 32 dm4ov2 and dm4ov3 tapes, any waypoint in the cone 718.
  - `--region X0 X1 Y0 Y1 Z0 Z1` (needs `--overhead`) adds, per tape, the same counts for events whose row k-1 pose lies strictly inside the box, and the routed seconds spent there: the interval from each mode 2 row inside the box to the next row, summed over stays. A stay still open when the bot's rows end is left out, because the tape was cut inside it.
  - Reproduces `runs/dm4-overhead-target.results.json` tape for tape: overhead-target means 15.75 and 11.62 (dm4ov2 control and candidate) and 12.12 and 12.75 (dm4ov3), and with the box `690 1060 -700 -390 -160 -90` the room split, 0.88 and 3.38 events a tape (dm4ov2, `post_hoc`) and 2.62 and 1.00 (dm4ov3, `rungs.dm4_v3.room_split`), with every routed-seconds figure to its one decimal. It also reproduces the `lab_dropwall2` rung and the first dm4 pair, which the definition was not fitted on.
- **Inputs**: `ARGUS_MAPS/<map>.bsp` (default `maps_local/`), one or more tapes, and for `--overhead` the graph the tapes ran (`src/argus_nav_<map>.qc.json`; check the tape's `ARGNAV` line).
- **Exit Code**: `0` on success or `--help`, `2` when the BSP, a tape or the graph is missing or a flag is malformed.
- **Tests**: `test_tools_cli.py` (trace semantics, each verdict on synthetic geometry, the re-entry count from a synthetic tape; the overhead-target rule, including the closest-bearing choice, and the region's strict box and closed stays on a built fixture).

---

The fixed lab clock and the stand-in human are Rust lab CLI commands:

```text
argus-mcp seeds dm4 20 fx_dm4 --lanes 4 --skill 2
argus-mcp match dm4 185 fx_dm4_replay --seed 7919 --skill 2
argus-mcp standin dm4 185 standin_dm4_a --skill 1
```

`seeds` runs fixed-clock matches on several engines at once (the lab's
14.25 ms frame, about six times faster than real time per engine, and the same
match every time for one seed and build); see [the fixed lab clock](../docs/fixed-clock.md).
`standin` seats a puppet that plays like a person; see [the stand-in human](../docs/stand-in.md).

---

Bot POV recording, PNG capture and video export use the Rust lab CLI:

```text
argus-mcp record-pov my_pov 1 8
argus-mcp watch-pov my_stall --on stall,still --run <run_name>
argus-mcp capture-demo my_pov 0.5 12 0.1
argus-mcp capture-video my_pov 0.5 2.4 0.5
```

The recorder joins an existing lab match. `watch-pov` waits on that match's
console for the first bot to stall, stand still or emit a chosen marker, cuts
the camera to it, and renders frames; see
[triggered capture](argus_mcp/README.md#triggered-capture). Video export requires FFmpeg with
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
manifest, reverses allowlisted target-attention, recovery, opening-door,
button/door, offset-entry, active-health, plan and muzzle
amendments in memory, then reconstructs
the historical health/inventory candidate for static checks. Those historical
checks alone do not establish the behaviour of a current build.
`python tools/health_inventory_parked.py --amend <name> --base <rev> --scope
"<text>"` adds the reverse patch and manifest entries that any edit to
`src/argus.qc` needs (CONTRIBUTING.md, "Production source manifest").

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


Compile-only CI also checks all 20 maintained variants across `muzzle`,
`combat`, `health`, `button`, `door`, `plan`, `offset`, `freeze`, `mover` and `attention`. It reuses the native
verifiers' staging helpers, including extracted production decision wrappers:

```text
python tools/compile_private_fixtures.py --help
python tools/compile_private_fixtures.py --compiler <pinned-fteqcc> --family door --output backups/door-compile-1
```

Use the FTEQCC revision pinned in `.github/actions/build-progs/action.yml`. Omit
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

### Broader-map routing, recovery and mover studies

Use the [cross-map runbook](../docs/lab-workflow.md#cross-map-routing-evaluation)
for the native source build, existing lab configuration and private assets.
New output directories must be beneath `backups/`; use a fresh lowercase
letter/digit/underscore prefix for every engine attempt. Raw tapes are
append-once evidence. Installed gameplay binaries remain unchanged.

| Tool | Inputs and controls | Output / acceptance |
|---|---|---|
| `audit_route_distance.py` | `--maps`, `--gravity`, `--objective hops-distance` (default) or `distance`; optional `--output` | Offline generated-QC audit against an independent shortest-path oracle; no engine |
| `run_map_intelligence.py` | `--output`, `--prefix`; optional frozen `--source`, `--maps`, `--seconds` (10 to 185), `--repeats` (1 to 5), `--skill`, `--primary`, `--baseline`, `--ticrate`, `--port`, `--lab` | Compile once; protocol, named tapes and native briefs; default eight maps, 60 seconds, two repeats, skill 2 |
| `report_map_intelligence.py` | Control and candidate folders; optional `--output`, `--native-gates`, `--lab` | Verify tape hashes, summarise matched map/duration/skill/primary arms; complete both arms for registered-primary native band cards |
| `verify_route_distance.py` | `--output`, `--prefix`; optional `--source`, `--ticrate`, `--port`, `--lab`, `--compile-only`, `--expect-failure` | Native routing and shopping contracts; declared legacy control must fail |
| `verify_freeze_recovery.py` | `--output`, `--prefix`; optional `--source`, `--maps`, `--seat original\|corner\|south`, `--ticrate`, `--port` | Private physical recovery and guard receipts; control/source and seat determine expected checks |
| `verify_mover_transfer.py` | `--output`, `--prefix`; optional `--source`, `--maps e1m6,dm3`, `--control`, `--ticrate`, `--port` | Continuing-route transfer, safe launch, dry static-floor landing and zero rescue warps; `--control` retains an incomplete baseline |

The registered primaries are `stall_parity`, `engagements`, `lava_deaths` and
`freezes`. New per-tape `.compare.json` artifacts pass the frozen selection
to native `compare --primary` and retain `effective_primary`, input identities
and the verbatim `native_gate_card`. Incompatible baseline protocols fail
before output or matches start. Single-pair cards remain advisory; use the
report's final native band cards for the study judgment. Older artifacts are
unchanged, and severe freezes retain their independent veto. Cadence choices
are `.0139` and `.1`; measure actual frames rather than assuming the request
was honoured. Graph presence alone is not runtime navigation: the report
requires both frozen compilation-list and dispatcher registration.

Engine-free receipt and budget tests are `test_nav_budget.py`,
`test_map_intelligence_report.py`, `test_study_comparison.py`,
`test_freeze_recovery.py` and `test_mover_transfer.py`. All five block the fast
workflow using the same Python environment as the other contract suites. They need no engine, BSPs
or historical backups. The separate compile workflow includes the `freeze`
and `mover` families; native trials remain the physical verification layer.
See [the tracked study follow-ups](../docs/mover-intelligence.md#tracked-follow-ups)
for fixture quarantine and comparison-primary propagation.

`verify_target_attention.py` uses `--output`, `--prefix`, optional frozen
`--source`, `--maps`, `--ticrate`, `--port`, and explicit `--legacy-control`.
It checks production opponent decisions on dm6/lqdm2 by default, including
retreat ownership and information boundaries. Its tapes emit the recognised
quarantine marker. `test_target_attention.py` runs in fast CI; the `attention`
family is compiled by the private gate. See the [policy and evidence](../docs/combat-attention.md).
