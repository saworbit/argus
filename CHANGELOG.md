# Changelog

Changes to bot behaviour, navigation and the lab, newest first. Each entry
describes the result and links to its implementation or detailed evidence.

[Recent changes](#main-updates) |
[Versioned builds](#versioned-builds) |
[Earlier builds](#earlier-builds) |
[Full historical notes](docs/changelog-history.md) |
[How to update this log](#maintaining-this-log)

| Status | What to use |
|---|---|
| Development source | Main as of 2026-11-15 is installed; the human-play check ([#610](https://github.com/saworbit/argus/issues/610)) and the parked step 1b gate ([#583](https://github.com/saworbit/argus/issues/583)) remain open |
| Latest gameplay update | 2026-11-15: build `004b4ff9ddf7` installed (tape identity, the fixed-clock seed and session marks; no change to play); see Unreleased |
| Gameplay binary | `game/argus/progs.dat` and `engine/argus/progs.dat`; MD5 `5FD814CC448AF8FBA7BFB16CD29062BC` |
| Last explicitly numbered build | v4.21, 2026-09-16; subsequent changes are recorded by merge date below |
| Lab version | 0.32; [operator guide and version history](tools/argus_mcp/README.md#versions) |

Main-update dates are UTC merge dates. Numbered builds retain their recorded
build dates. A merged change does not imply a new numbered release, and a
passing botmatch does not establish better human play.

## Main updates

### Unreleased

#### Added

- The fixed lab clock is accepted on dm3 and e1m7 at 14.25 ms
  ([#854](https://github.com/saworbit/argus/issues/854)), under an amendment
  registered before its fixed tapes. Its wall-clock arm is the control tapes
  of other ladders of the same build, which is weaker than a control recorded
  for the purpose, and the doc says so. Limits: stalls, deaths and routefails
  on dm3, where lava is untested because neither arm had a lava death; stalls,
  lava and world deaths and routefails on e1m7. `tools/lab_instruments.json`
  carries both maps and the 64 tapes are in `runs/` under the amendment's
  names.
- `python tools/health_inventory_parked.py --amend <name> --base <rev>
  --scope "<text>"` writes the reverse patch and manifest entries that every
  edit to `src/argus.qc` needs, a comment-only one included
  ([#871](https://github.com/saworbit/argus/issues/871)). It refuses a base
  whose text does not match the current pin, re-pins any changed active
  function, replays the chain to the frozen step1b text before writing, and
  says whether the edit changed only comments and layout. Given the
  revisions either side of 5787b7a it reproduces that commit's hand-written
  patch and manifest byte for byte. CONTRIBUTING.md now points at it instead
  of the manual steps.

- `python tools/argus_lab_mutants.py` makes the lab spine's mutation check
  reproducible ([#824](https://github.com/saworbit/argus/issues/824)). It
  breaks each of 67 guards in `tools/argus_lab.py` in turn, in memory only,
  runs `tools/test_argus_lab.py` against each and reports every guard caught
  or missed. A row whose original text no longer names exactly one place in
  the spine stops the run before any suite starts. Its first run missed 10
  guards, among them a gate with no bound, a goal target with low above
  high, a session off a goal map and a sweep whose failure got worse; each
  now has a test, and all 67 are caught. Fast CI checks the table and the
  harness only; run the whole table before a change to the spine merges
  ([the mutation check](docs/lab-spine.md#the-mutation-check)).

- Add lab scenarios: purpose-built micro-maps that isolate one bot behaviour
  ([lab scenarios](docs/lab-scenarios.md)). `lab_request` (MCP, which also
  accepts the request as a JSON string) and `argus-mcp lab-request
  <request.json>` take a structured request (named regions, entities placed
  by region name, brush and entity budgets, `claim_tier: isolation`), and
  `tools/lab_mapgen.py` writes a plain-text `.map` and a generated texture
  WAD, compiles a BSP29 with the pinned ericw-tools 0.18.1 (`python
  tools/lab_mapgen.py tools --install` verifies the release's SHA-256) and
  writes a manifest with counts, region adjacency, hashes and navgen
  readiness. The map then takes the stock road: the lab's `nav_generate`, the
  mill and the first-registration gate, and the scenario is recorded in
  `tools/lab_instruments.json`.

- `tools/argus_guard_replica.py --overhead GRAPH.qc.json [--region X0 X1 Y0
  Y1 Z0 Z1]` scores the overhead-target primary per tape, and the same counts
  plus routed seconds inside a box
  ([#868](https://github.com/saworbit/argus/issues/868)). On the recorded
  tapes it reproduces `runs/dm4-overhead-target.results.json` tape for tape:
  means 15.75 and 11.62 (dm4ov2 control and candidate) and 12.12 and 12.75
  (dm4ov3), and in the room under the walkway jump 0.88 and 3.38 events a
  tape (dm4ov2) and 2.62 and 1.00 (dm4ov3), with every routed-seconds figure.
  The recorded reading took only the waypoint closest in bearing to the wish,
  not any in the 8 degree cone the protocol's wording admits; counting any
  gives 718 events on those 32 tapes against 418.

- `match_run` takes `seeds`, so an agent can run the fixed lab clock through
  the MCP server ([#853](https://github.com/saworbit/argus/issues/853)). It
  is refused on any map where `tools/lab_instruments.json` does not record
  the clock as accepted (dm4 and dm2 today). One seed returns the usual
  result; up to ten run one after another on one engine as
  `<run_name>_s<seed>` and report like `argus-mcp seeds`. Both name the
  clock, its 14.25 ms frame, the seeds and the map's limits, and a
  `match_stop`, shutdown or Task cancel ends the whole ladder. No tool was
  added: the surface is 25,446 bytes against its 25,500 bound.

- A lab-map result supports an isolation-tier claim only: `argus_ci.py lab`
  fails a supported or fixed claim that names a stock map without citing a
  tape recorded on it, or that cites a lab tape without naming the lab map
  ([promotion rule](docs/lab-scenarios.md#the-promotion-rule)).

- `lab_request` refuses registration while a standable floor at least 32u
  wide seats no waypoint within 64u above it, unless the request marks the
  region `off_graph`; `tools/lab_mapgen.py coverage <request>` runs the same
  check. Both drymix maps had registered with a run-off ledge the graph never
  seated, which carried a third to over half of their re-entries, while every
  dm4 re-entry happens on the graph
  ([findings](docs/lab-scenarios.md#lab_drymix2-and-the-coverage-gate)).

- Add a water layer and a time layer to the clip-hull navmesh
  ([#791](https://github.com/saworbit/argus/issues/791)). `--audit` now reads
  exact swim volumes (hull-1 origins in hull-0 water, split where the eyes
  leave it), their exits onto the floor mesh by navgen's lip rules, and the
  air each pool asks for at an assumed 300 u/s against the 12 s of air, and
  cross-checks the shipped swim links: dm3 1 confirmed and 3 reached on foot
  from the trench sill, e1m2 8 of 8, e1m1 15 of 15. `--air` now grades the
  ledges beside every plat, door and train at each of its positions, with
  the times stock QC holds it there; beside dm2's sliding floor panels `*1`
  and `*2` it finds 55 and 38 danger ledges while they are open and none
  while they are shut. The floor mesh and every existing line of output are
  unchanged
  ([details](docs/navmesh-experiment.md#the-water-layer)).

- Add `tools/argus_guard_replica.py`, which replays the physics brink guard
  offline from a `scratch1 697` tape and names the branch behind each
  deflection (wall, lava, void, run-off landing). Of dm4's routed
  re-entries, 47 per cent are walls, 36 lava, 6 voids and 2.5 the run-off
  landing test, while on the first three lab maps 97 to 98 per cent are lava,
  because a generated slab over open air turns a buried probe into a lava
  veto ([findings](docs/lab-scenarios.md#what-deflects-routed-bots-dm4-against-the-lab-maps)).

- Seven scenarios are recorded in `labmaps/`, six registered:
  `lab_voidcorner` (a 64u walkway ring over lava with four tight corners),
  `lab_drymix` and `lab_drymix2` (dm4's mix of lethal and dry-drop lips;
  neither matched it), `lab_wallmix` (the first whose walls the guard reads
  as walls, at 20 per cent walls against dm4's 47), and `lab_dropwall` and
  `lab_dropwall2` (dm4's walkway over a room: the open room let bots fight
  instead of route, and the bays restored routing without the mechanism).
  `lab_jumpgap` is recorded and not registered: the mill refused its jump
  links at a 128u and a 96u gap.

- Evidence and limits: play is unchanged. Five changes were laddered on these
  maps and dm4 under registered protocols, and none shipped. The route elbow
  and an early turn at hazard corners were refuted on `lab_voidcorner`. The
  brink turn cut route-steer deflection episodes 23 per cent there and held
  on dm4 without the benefit. A hazard check for routed steering after a
  deflection cut that flicker a fifth there and changed nothing on dm4. A
  grounded re-plan for a steering point overhead behind solid, aimed at dm4's
  largest wall cluster (bots that miss the staged walkway jump and land in
  the room below), did not move dm4's overhead-target re-entries in its
  second or third version and is refuted
  ([corners](docs/lab-scenarios.md#the-first-scenario-lab_voidcorner),
  [overhead target](docs/lab-scenarios.md#the-overhead-target-lab_dropwall-lab_dropwall2-and-lab_jumpgap)).

- `argus-mcp probelinks <map> --confirm` walks every first-attempt failure once
  more at the end of the sweep and convicts only a second failure; on a
  micro-map the roster stands on the walkway the puppet is walking, and two
  sweeps of one graph convicted different links. `nav_sync::register_maps`
  registers named maps alone, because `nav_sync_dispatch` stops at the first
  experimental graph on disk (e1m3).

- Briefs of tapes recorded with `scratch1 697` carry
  `movement.deflection_causes` (brink-deflection episodes by the steering cause
  that led into each) and `movement.brink_encounters` (episodes under 250 ms
  apart merged, by what started each encounter), which the throttled `hazards`
  count cannot say.

- Add the fixed lab clock: `argus-mcp seeds <map> <count> <stem>` and
  `argus-mcp match ... --seed N` run matches at the wall-clock lab's measured
  14.25 ms frame about six times faster than real time per engine, on up to
  eight engines at once, and a given progs, map and seed repeat line for line,
  so a freeze or a death can be replayed by its seed. Stock engine settings
  only (`host_framerate`, `sys_ticrate 0.001`, `host_maxfps 1000`,
  `timelimit`); the seed reaches QC as `saved4`. Validated per map against a
  registered protocol: 13.9 ms failed on dm4 (more lava deaths and
  routefails than the wall clock), and 14.25 ms passed a registered
  confirmation on fresh seeds on dm4 and dm2, with lava, world deaths and
  routefails (and dm4 stalls) as limits; average speed could not be measured
  because the corpus does not carry it
  ([details](docs/fixed-clock.md), [#843](https://github.com/saworbit/argus/issues/843)).

- Stamp a build identity into every tape (#823). `src/argus_build.qc` holds a
  hash of the QC source with comments and layout removed, so a comment-only
  change keeps the stamp and the compiled bytes. Every match prints
  `ARGUS build <id>` and `ARGUS clock ...`, compile and `ship` refresh the
  stamp, `argus_ci.py stamp` fails while it is stale, briefs carry the build,
  clock and marks, the spine credits a session to the install carrying its
  stamp, and the skeptic reports arms on different builds, clocks or frames
  and voids an arm holding one fixed-clock seed and build twice.

- Add session marks: `bind m mark` (impulse 200, handed to every client as an
  alias) writes `ARGUS mark` with the time, where the player stood and looked,
  and the bot in sight nearest their view. It works while dead, says
  "not saved" without `+developer 1`, and changes nothing in play. `review`
  and `triage` list each mark with the bot's state and events around it
  ([controls](docs/controls.md#session-marks)).

- Add the session gallery, `tools/argus_gallery.py`: it picks a session's
  marks, freezes under fire, unforced world deaths and long freezes, cuts a
  six-second clip of each from the demo, and serves a local page that records
  rulings. Clips stay machine-local ([details](docs/session-gallery.md)).

- Add the stand-in human, `argus-mcp standin`: a puppet that follows a route a
  person ran (from the demo's full-rate track), rejoins it over the nav graph,
  reacts in 0.25 s with a capped, noisy aim, strafes at the human reversal
  rate and refuses lava. Its registered calibration on dm4 failed dose
  response (bot kills on it did not rise with bot skill, Spearman 0.13,
  because its time in sight of bots ran 0 to 2608 ticks between matches), so
  it does not screen threat claims yet ([details](docs/stand-in.md),
  [#842](https://github.com/saworbit/argus/issues/842)).

- Add `tools/lab_instruments.json`, where the fixed clock and the stand-in may
  be trusted, read by `argus_lab.py state`, validated by `argus_ci.py lab`,
  and used by `pyramid` (`--through 5` plans the stand-in rung); and
  [the improvement loop](docs/improvement-loop.md), which says which
  instrument answers which question.

- Cover triggered capture's camera cut in CI. The cut logic now runs against
  a small camera trait, and a scripted camera checks that a cut waits for the
  view to leave the previous bot, that each intermediate cut lands before the
  next press, and that a name the camera cannot track is refused after one
  lap. The only test of this path used to need an engine
  ([#809](https://github.com/saworbit/argus/issues/809)).

- Add `argus_ci.py suites`, part of `all`, which fails when a `tools/test_*.py`
  suite runs in no workflow. It counts a suite as run when a workflow names it,
  a `discover -p` pattern matches it, or a running suite calls it through
  `run_tool`. All 55 suites run today; the five named in the issue run
  through `test_tools_cli.py`
  ([#803](https://github.com/saworbit/argus/issues/803)).

- Add an air layer to the clip-hull navmesh audit: fly a player body off
  every ledge at walk, run and running-jump speeds and record where it
  lands, counting walls, doors and plats at their spawn positions. Against
  tapes, with every ordinary second of movement as the base rate, lava
  entries cross the ledges it flags far more often than ordinary moves do:
  e1m7 94.4 against 8.3 per cent, dm4 74.7 against 15.5, e1m8 49.0 against
  12.5, and the report splits run-offs from deliberate jumps. Its drop-link
  check is not supported by the tapes and is reported as such. Audit
  tooling only; no bot or graph change
  ([#771](https://github.com/saworbit/argus/pull/771),
  [details](docs/navmesh-experiment.md#the-air-layer)).

- Reproduce the dm4 under-fire freeze from the cover-hop cohort in the real
  engine. A player passing on the pit floor below nudged the bot into the
  walkway wall on both the candidate and its unchanged control, so the cover
  guard did not cause it. The body-height fixture keeps a dm4 regression,
  which current main passes at both cadences
  ([#723](https://github.com/saworbit/argus/issues/723),
  [details](docs/body-height-investigation.md#the-dm4-walkway-pin)).

- Add the lab spine, `tools/argus_lab.py`, which joins the corpus,
  scorecard, baselines, benchmark suites, puppet verdicts and measurement
  limits with a written objective (`tools/lab_objective.json`, a draft until
  signed off) and a claims ledger (`tools/lab_claims.json`: open defects with
  map cells, fixed cells with dates and measured allowances, the graveyard of
  refused changes). `state` generates the session brief from that evidence,
  `session` and `review` score human sessions against the objective,
  `skeptic` audits a comparison before it is read, `triage` names the claim
  behind a tape's trouble, `pyramid` runs the cheap evidence tiers first, and
  `night` is an unattended census that alerts only on what got worse.
  `argus_ci.py lab` validates the objective and the claims in CI
  ([guide](docs/lab-spine.md), [#818](https://github.com/saworbit/argus/pull/818)).

- `argus_lab.py stale` found, on its first run, six maps whose baselines were
  recorded at 19 Hz, eight whose baselines ran a graph that no longer ships
  (all before the 2026-11-13 link repair; e1m5's from a 155-seat graph where
  195 now ship), and a dm4 benchmark suite pinned to an old graph. A tape's
  graph is read from git history, not from its `ARGNAV` banner, which changed
  meaning at #716.

- The skeptic recounts lava from map contents at each death, because the
  corpus still counts lava below z -300 and reads 0 on dm2 and e1m7 (#816).
  It reads each metric against the larger of the documented and the observed
  spread, and voids comparisons across tick classes, maps or tape kinds.

- Triage judges each fixed claim's cell against an allowance measured on the
  archive, which gives zero regression flags across every bot tape in
  `runs/`. Measuring it showed the dm3 quad-court pinch was not fixed by the
  2026-08-28 remint, as the record said: the 20 tapes between the remint and
  the 2026-09-13 regeneration held a median of 10 stalls in the cell, and the
  246 since hold 0.

- Evidence: 65 tests on built fixtures (`tools/test_argus_lab.py`, in fast
  CI), and every one of 56 deliberately broken guards fails a test. Four
  independent review rounds found about 47 defects, all fixed; the fourth
  found three.

- Limits: goal targets stay proposals until the objective is signed off.
  Tapes do not name their build, so session attribution uses merge times and
  the skeptic cannot see a build confound
  ([#823](https://github.com/saworbit/argus/issues/823)). What the first run
  found stale is filed: baselines
  ([#819](https://github.com/saworbit/argus/issues/819)), the dm4 benchmark
  pin ([#820](https://github.com/saworbit/argus/issues/820)), refused links
  still shipping ([#821](https://github.com/saworbit/argus/issues/821)) and
  the measurement limits
  ([#822](https://github.com/saworbit/argus/issues/822)). The mutation check
  is not yet committed
  ([#824](https://github.com/saworbit/argus/issues/824)).

- The human scorecard gains `bot_world_unforced`: bot world deaths that no
  damage led into, so a bot walking or jumping off a ledge into lava no
  longer counts the same as one knocked in. A death is unforced when the bot
  lost no health in the 3 s before it reached lava or slime, read from the
  map's hull-0 contents; without a machine-local BSP the column is blank.
  Across the 75 committed session tapes, 107 of 164 bot world deaths were
  unforced, and the 2026-11-14 dm4 session reads 2 of 3, matching its
  review. Existing scorecard values are unchanged. A hit landing in the same
  half second as the entry still reads as unforced
  ([#815](https://github.com/saworbit/argus/pull/815)).

- `argus_ci.py refuted` also reads the machine-local CLAUDE.md when it is
  present, and says the brief was not checked when it is absent, as in CI
  ([#766](https://github.com/saworbit/argus/issues/766)).

- Seed `tools/refuted_claims.json` with seven more refuted rules: dm2 water,
  dm6 movers, colormap bot colours, splash against walls, grenades at the
  feet, the strafe re-roll as the reversal cause, and re-fitting the played
  aim spring ([#767](https://github.com/saworbit/argus/issues/767)).

- Run the navmesh repair and air layer suites in fast CI ([#787](https://github.com/saworbit/argus/issues/787)).

- Start a bot's-eye recording when something happens instead of at a fixed
  time. `argus-mcp watch-pov`, and `bot_capture_pov_frame` with `on`, join the
  lab match as a camera, tail its console and cut to the first bot that
  stalls, stands still, emits a chosen marker or produces a burst of them
  (`stall`, `still:3`, `flip:3`). They then record and render frames, with
  the lead-up when the camera was already watching that bot. The MCP form
  waits a fixed 60 s; the CLI takes `--wait` up to 110 s. Lab tooling only;
  no bot or graph change
  ([#795](https://github.com/saworbit/argus/pull/795),
  [details](tools/argus_mcp/README.md#triggered-capture)).

- Add navgen `--seat-links`, which adds seats and walks to a shipped graph
  from a coordinate sidecar (`src/argus_nav_<map>.seats.json`) without a
  regeneration. Every index and slot is kept, every walk must pass
  `beeline_ok`, cuts retire only walks whose far end stays reachable, and a
  rerun changes nothing ([#772](https://github.com/saworbit/argus/pull/772)).

- Add `argus_ci.py refuted` to the blocking invariant battery. It fails when
  tracked text restates a rule listed in `tools/refuted_claims.json` as
  current, so one correction reaches every copy. It is seeded with the three
  refuted tick-rate claims, and the guide copies #669 found would have failed
  it ([#764](https://github.com/saworbit/argus/issues/764),
  [#765](https://github.com/saworbit/argus/pull/765)).

- Add the Argus brand: the faceted A mark, the wordmark, the palette and the
  chamfer motif, with a guide in [docs/brand](docs/brand/README.md). The README
  opens on a banner that follows the reader's light or dark theme, carries its
  badges in the palette, states the hard constraints as chamfered stat tiles,
  shows the shipped dm2 graph in the lab's link colours in place of the stale
  162-node `docs/media/nav_dm2.png`, and signs off with the mark. The lab GUI
  shows the mark as its tab icon, and a 1280 x 640 social preview is ready for
  the repository settings. `tools/brand` regenerates every asset from the
  mark's parameters and the nav figure from the shipped graph. No gameplay,
  telemetry or lab behaviour changes.

- Require actual landing and continuous task ownership in private mover
  fixtures, with read-only phase traces and rejection of observer steering.
  See the [e1m6 investigation](docs/e1m6-decisions.md).

- Add native water-route and action-decision witnesses at played and 100 ms
  cadence, including physical failures and supported-wait controls. Compile
  all 21 maintained private fixture variants in CI.
- Preserve bounded, engine-proven navigation seats through validated sidecars.
  Regenerate e1m5's moat escape without manual changes to generated QC.

- Reassess opponents during an ongoing fight using recent hostile damage
  and visible powerup cues. Keep a focus margin, bounded decision clocks,
  reaction delay and the original item goal. Record switches separately
  from initial engagements. See the [decision controls and map study](docs/combat-attention.md).
- Add controlled target-decision checks at played and 100 ms cadence, retain
  the unchanged-source failures, and compile the twentieth private fixture
  variant in CI. Keep retreat and secondary-threat state consistent on a switch.

- Add frozen-source multi-map evaluation, route-distance audits and private
  recovery/continuing-route transfer fixtures. Preserve controls, rejected
  candidates and raw tape identities. See the [routing](docs/map-intelligence.md),
  [recovery](docs/freeze-recovery.md) and [mover](docs/mover-intelligence.md) studies.

- Recover from combat wall pins with checked movement feedback and recent
  hostile damage as a cue for the existing bounded rescue. Retain aim/fire,
  mover ownership and destination checks. The final 22-match candidate has
  zero freezes under fire across eight maps, versus one in unchanged controls;
  other warnings remain. Development source only; no deployment.

- Check tracked documentation paths, heading fragments and explicit HTML
  anchors with `argus_ci.py links`, included in the blocking invariant battery.
  Synchronise the focused local test list with all fast-CI suites (#611, #614).

- Compile all maintained private QuakeC fixture families in CI using their
  native staging helpers and the pinned compiler, with fresh outputs and
  retained failure logs. No engine or game assets are required (#604).

- Add `tools/argus_voidprobe.py`, which reads two things about a shipped
  graph that the runtime's point-resolution probes cannot: what lies under the
  voids the hazard guard vetoes, and how much elbow room each waypoint has
  against navgen's own seat-shift bar. Two gait changes were built on guesses
  about the first and a third was about to be built on a guess about the
  second. On the shipped graphs: no probe direction from any waypoint finds
  lava underfoot, every void dm4 and dm2 veto bottoms out in lava while dm3's
  and dm6's bottom out in stone or water, and 7 per cent of dm4 and dm2
  waypoints sit within 24 units of a wall - against which only 6 and 15 per
  cent of wall slides occur, so wall scraping is diffuse rather than seated.
  dm3's 25 zero-empty-cardinal seats were subsequently classified as water,
  rather than boxed-in walls; seven dm3 seats have solid cardinal samples.

- Quantify what the human reference corpus costs as a comparison: every human
  track was recorded hunting bots, while candidate tapes are bot-versus-bot.
  Comparing the human, the bots in those same sessions and the bots in a
  botmatch puts roughly a fifth of the dm2 local-dwell gap on match
  configuration and four fifths on the bot, with gyration unchanged by the
  human's presence. The gaps are mostly real bot properties.

- Record four refused gait changes with their reasons, so none is tried
  again. A gentler 30 degree deflection rung cut hazard-attributed heading
  swings and raised wall-slide ones to compensate, taking the metric it
  targeted the wrong way and stalls from a median of 8 to 21: the churn is not
  the deflection step size, it is that the bot is pressed against geometry at
  all. Stamping the lethal void improved dm4's gait gap to +1.752 and cost
  dm2's the same trade as the first cautious-gait trigger, because every void
  either map vetoes has lava under it, so the signal stops discriminating. A
  flatter distance curve for an unhurried bot made its errands shorter rather
  than longer, worsened the dwell it targeted and cut engagements 28-45 to 17:
  the distance curve is not the cause of local dwell. The fourth, re-seating
  waypoints off walls, was refuted by measurement before any code was written.
  [Post-mortems](docs/behaviour-diagnostics.md#refused-a-gentler-first-rung-in-the-deflection-fan).

- Report signed per-feature gaps from `tools/argus_humanness.py --profile`.
  The scored distance is unsigned and says a feature is wrong without saying
  which way, which is the one thing a behaviour change needs.

- Add `tools/argus_gait.py`, which attributes stationary windows to a chosen
  pause or to something else. A freeze count alone cannot tell them apart, and
  both laddered maps produce long fight-pin freezes on unchanged code.

- Document private plan/offset fixture records, reproducible CLI options and
  acceptance limits. Separate current development status from earlier
  parked-state evidence and supplied game binaries.

- Recognise failed navigation plans using goal-relative progress and reached
  waypoints, then choose alternatives through the existing selector. Add
  repeatable decision and physical-escape fixtures. Development source only;
  supplied binaries remain unchanged. [Checks and limits](docs/behaviour-diagnostics.md#shared-failed-plan-recognition).

- Add private ordinary-rocket clearance checks using real BSP geometry and
  stock firing: 14 checks, with legacy and uncapped negative controls. See
  [the verification contract](docs/behaviour-diagnostics.md#ordinary-rocket-muzzle-clearance).

- Add opt-in passive behaviour diagnostics and an acknowledged isolated
  observer suite. Step 0 alone preserves perception and tactical decisions. See
  [the diagnostic contract](docs/behaviour-diagnostics.md).

- Record staged asset digests and FFmpeg build/settings in capture manifests,
  isolate staged bytes and reject changed inputs (#572). Check VP9 encoding
  before rendering or creating capture output (#573).

- Replace the parked POV capture with bounded real-engine PNGs, record
  acknowledged bot POVs and fixture opponent-eye demos, and retain visual
  evidence separately from tactical counts and human feel (#517).

- Record tactical evaluation stages and actual cognition/aim tiers for human
  review (#517, #527). Keep the adaptive aim share at 0.35 and distinguish
  evaluation ticks, shot acknowledgements and unmeasured return hits.

- Cover failed-life avoidance after GOAP weapon substitution, repeated picks,
  typed-hop cancellation and both shared-queue ownership paths in the real
  engine on dm4 and dm2 (#530).

#### Changed

- navgen seats a deathmatch spawn that stands on a solid brush entity
  ([#783](https://github.com/saworbit/argus/issues/783)). A spawn whose first
  floor is a brush top at its spawn position, more than a step above any
  world floor there, gets a seat on that top after the late link passes,
  joined only by up to four one-way exits. An exit is kept only when the
  runtime's brink guard passes the run to the pad's edge at run and walk
  speed (the `argus_guard_replica` replica, which now takes the map's
  gravity) and the flight off the edge lands dry, on no brush entity, within
  a step of the target's height, with 48u of floor beyond and a walk from
  there to the target. The 7h report now names every deathmatch spawn more
  than 64u from a seat. The short drops onto e1m7's walkways beside the pads
  are refused, because the guard deflects them at speed and a run lands on
  the walkway's far lip. A fresh e1m7 regeneration lacks the 41 lake seats
  `--repair-links` kept, so the new `--seat-spawn-pads` mode applies the same
  rules to a shipped graph: seats and link calls are appended, a rerun
  changes nothing, and a pad it cannot seat refuses the splice with nothing
  written. Applied to the shipped e1m7 graph: the four z 280 pads gain seats
  n204 to n207, 1u from their spawns, with nine exits, each running east or
  west off a pad; every deathmatch spawn is within 46u of a seat, and every
  other spawn still reaches the same 139 nodes (66 per cent of 208, from 68
  per cent of 204, because nothing enters a pad). dm4, dm2 and e1m3
  regenerate byte for byte as on main.
- `tools/argus_bsp.py` is now the one Python BSP29 reader
  ([#814](https://github.com/saworbit/argus/issues/814)). Its `Bsp` class
  checks the header once and serves navgen, the navmesh and its graph, the
  pointfile overlays, the analyzer and nav preview wireframe, the reach audit,
  the map gate and the lab map compiler, and it holds the one `check_bottom`
  and the one water-surface probe. A file that is not BSP29 now raises the
  same `ValueError` from all of them, under `python -O` too, where the two
  `assert` checks used to vanish; `tools/test_argus_bsp.py` holds that in both
  modes. The water probe keeps navgen's 320u ceiling rather than the
  pointfile's 512u, because 320u decides which swim links exist and the
  surface overlay is there to show what navgen saw. `argus_nav_preview.py` no
  longer imports the `analyze_match.py` script. Regenerating with the original
  and the changed navgen gave byte-identical QC, JSON, output and exit codes
  on dm2, dm4, dm6, e1m1, e1m3, e1m4, e1m7, e1m8 and the six registered lab
  maps, while dm3, e1m2, e1m5, e1m6 and lqdm2 refused at the same jump anchor
  check with identical output both times, and the six graph-preserving modes
  matched on dm3, dm4, e1m1, e1m2 and e1m7.

- navgen's reachability knit (section 7g2) has three last-resort stitches
  for a pocket its walk, jump, drop and dive stitches leave stranded
  ([#623](https://github.com/saworbit/argus/issues/623),
  [#624](https://github.com/saworbit/argus/issues/624)). A swim stitch joins
  two underwater seats both ways when a player box fits through water
  between them. A bank stitch walks a dry seat into the water and vaults
  back out onto a lip up to 44u above the surface, which it finds itself:
  7d's surface probe stops 320u above a seat, so a seat on a deeper floor
  saw a surface that is not there. A deep-drop stitch lets a pocket holding
  the seat nearest a deathmatch spawn or live pickup escape by a fall of up
  to 240u, past DROPMAX's 200 but short of falling damage (264u at gravity
  800) and inside the runtime's 280u floor probe. On e1m4 a flooded
  courtyard and a 504u deep lake had cut the south of the map and the start
  building's shore off from the rest, leaving six of nine spawns 527 to 860u
  from the graph; now all nine are within 142u, pickups reachable from every
  spawn rise from 21 to 50 of 58 and the map gate's reasons fall from 117 to
  49, at 186 waypoints and 576 of 600 edicts. On e1m3 the super nailgun's
  ledge escapes by a 216u fall, so the weapon is no longer 209u from the
  graph: 53 of 55 pickups, 17 reasons, 177 waypoints and 597 of 600 edicts.
  Both maps stay unregistered. e1m3's super shotgun shelf is climbed by 24
  to 32u risers on 16u treads that SV_CheckBottom refuses as seats, so only
  a rocket jump reaches it. e1m4's other eight pickups sit behind a
  two-button secret door, in a walled room behind a trigger-lowered door, on
  a trigger-started train and in an air pocket under the lake, and nine of
  its eleven teleporter links name teleporters that fire only for 0.2 s
  after a trigger. Regenerating with the original and the changed navgen
  gave byte-identical QC, JSON, preview receipts and logs on dm2, dm4, dm6,
  e1m1, e1m7, e1m8 and the six registered lab maps, and identical refusals
  at the jump anchor check on dm3, e1m2, e1m5, e1m6 and lqdm2.

- A full navgen regeneration applies `src/argus_nav_<map>.seats.json`
  ([#778](https://github.com/saworbit/argus/issues/778)). Only `--seat-links`
  read it before, so regenerating dm3 dropped its five elbow seats and
  sixteen walks into the red armour's south upper area and re-minted the
  n45 to n40 diagonal the sidecar cuts, which carried the origin 119u over a
  346u drop. Section 7g2e now appends the seats at their exact positions,
  joined only by the sidecar's walks, adds the walks under `beeline_ok` and
  the 340u limit, keeps them first at the slot clamp, and applies the cuts
  under the same reachability guard. An entry that cannot apply refuses the
  regeneration before anything is written, and a second regeneration is
  byte-identical. No shipped graph changes: dm3 is the only map with the
  sidecar, and its fresh regeneration is still refused by the #719 jump
  anchor.

- Evidence: with that one anchor check stubbed in a scratch harness, a dm3
  regeneration reproduces the shipped graph's 249 nodes in order and its
  regions exactly, with both elbow routes and without the diagonal. The 12
  and 3 remaining edge differences are the separate `--repair-links` and
  jump-link cases a regeneration without the sidecar also shows (14 and 19).

- Trim rationale four lab tool descriptions repeated from the guides, and a
  stale tape count, reclaiming tool-surface headroom from 3 bytes to 262.
  `bot_capture_pov_frame` spends part of it on `wait_sec` (5 to 110, default
  60) for live `on` recordings, which the CLI `watch-pov --wait` already had
  ([#808](https://github.com/saworbit/argus/issues/808)).

- Re-pin `benchmarks/dm4_navigation.json` to the shipped dm4 graph
  (`561c3ede`). Every task still starts and ends on a node and keeps a route;
  `pit_east_to_green` and `pit_center_to_east` lost a gated shortcut in the
  #770 repair, so their routes are one hop longer than before
  ([#820](https://github.com/saworbit/argus/issues/820)).

- Start each lab engine on Windows one priority class above normal. On
  2026-11-13 a CPU-heavy job beside a ladder pushed every tape to
  `dedicated_fast`; the same engines raised to AboveNormal by hand stayed in
  the listen class with full game time. Linux still relies on the tick-class
  check ([#786](https://github.com/saworbit/argus/issues/786)).

- `harvest_session.py` now reads each harvested session against the lab
  objective and claims after scoring it: hard gates, whether it counts for a
  goal verdict, and any new or regressed trouble. `argus_reach.py` honours
  `ARGUS_MAPS`, so it runs from a worktree against the main checkout's
  machine-local BSPs ([#818](https://github.com/saworbit/argus/pull/818)).

- Open CONTRIBUTING's lab tick-rate rule with the rate, about 70 frames a
  second and not 10, so a preview that shows only its opening no longer
  stops before the correction. A new rule asks that a commit or PR refuting
  an earlier rule name that rule in its title: the change that refuted the
  10 Hz rule ([#336](https://github.com/saworbit/argus/pull/336)) never
  mentions it, so a history search for the rule finds the commit that
  taught it and not the one that disproved it. The PR template's
  refuted-rules item says the same. Documentation only
  ([#796](https://github.com/saworbit/argus/pull/796)).

- Install main as the gameplay binary, MD5
  `ED8926C1F3F0E4A5D6F591F905516638`. It is the first install since
  2026-10-22 ([#566](https://github.com/saworbit/argus/pull/566)), so players
  now get every source change merged since then: the human gait, combat
  target reassessment, route actions and recovery, docked lift exits, the
  body nudge and cover-hop guards, the shallow-lava and climb repairs, the
  dm3 red armour route and the e1m7 lava run-off fix
  ([#793](https://github.com/saworbit/argus/pull/793)).

- Smoke evidence for that install: 75 s dedicated matches at the played
  rate, skill 1, on dm4, e1m7 and dm3, with no engine or progs errors and no
  freezes (`runs/smoke_deploy_ed8926c1_*.log`). This shows the build loads
  and plays; it is not an A/B result and says nothing about human play. The
  rerelease client was not checked.

- Add the first human session on that install, a 176 s dm4 tape at skill 1
  (`runs/shane_dm4_2026-11-14_ed8926.log`), with its scorecard row. Bots had
  no freezes or route failures, and the gait check finds no attributable
  failure. The behaviour guide records why one tape cannot separate the
  installed gait from earlier builds; the feel verdict and a dm2 session for
  [#610](https://github.com/saworbit/argus/issues/610) are still open.

- Record in the behaviour guide a probe of fast bot movement. Two thirds or
  more of grounded frames above 400 u/s come from bots turning at the full
  320 deg/s turn rate, which is stock Quake physics; the brink deflection
  accounts for 6 to 10 per cent, and none of nine probe-tape lava deaths
  followed self-made overspeed. Follow-ups: the missing stock edge and wall
  friction ([#794](https://github.com/saworbit/argus/issues/794)), and a stall
  jump whose landing check misses the heading it then flies
  ([#797](https://github.com/saworbit/argus/issues/797)).

- Correct the behaviour guide's status lines, which still called the gait,
  observation, muzzle and plan work uninstalled after #793, and the step 1b
  manifest's status string.

- Index the navmesh audit, its air layer and the mesh-derived graph in the
  developer tools guide, with navgen's `--repair-links` mode, and link the
  navmesh follow-ups from the experiment's limits: CI coverage for its
  tests, floors the extractor misses under 31 dry seats, e1m8's uncovered
  spawns, the mesh graph beyond dm4, and swim and mover layers
  ([#787](https://github.com/saworbit/argus/issues/787),
  [#788](https://github.com/saworbit/argus/issues/788),
  [#789](https://github.com/saworbit/argus/issues/789),
  [#790](https://github.com/saworbit/argus/issues/790),
  [#791](https://github.com/saworbit/argus/issues/791)).

- Record the ranked reversal causes and two refused responses in the
  behaviour guide, and document the manifest step every `src/argus.qc` edit
  needs. Link the follow-ups from the body-nudge, cover-hop and dm4 pin work
  ([#697](https://github.com/saworbit/argus/issues/697), [#754](https://github.com/saworbit/argus/issues/754), [#755](https://github.com/saworbit/argus/issues/755),
  [#756](https://github.com/saworbit/argus/issues/756), [#757](https://github.com/saworbit/argus/issues/757)).

- Synchronize lab runbooks with current fixture families and observer layouts.
  Clarify the closed body-clearance prototype and retain its same-floor hull
  failures as a separate follow-up
  ([#747](https://github.com/saworbit/argus/issues/747)).

- The lab guide and the lab workflow describe three recent fixes: the source
  fingerprint reads CRLF as LF, a band gate card names the tapes its rows
  compare, and a runner with no lab binary stops and says where to build one
  ([#777](https://github.com/saworbit/argus/issues/777), [#757](https://github.com/saworbit/argus/issues/757), [#768](https://github.com/saworbit/argus/issues/768)).

- `argus-mcp probelinks` reports a verdict for every link it probes
  (`passed`, `failed` or `teleport_failed`) in sweep order, beside the
  eight-entry passed sample. It also reads the graph and records verdicts
  under `ARGUS_SRC`, so a sweep run from a worktree no longer writes into the
  main checkout ([#781](https://github.com/saworbit/argus/issues/781)).

- Track portable agent rules in AGENTS.md while keeping local handoffs ignored,
  so rule corrections reach every checkout (#672).

- Draw each navigation link type the same way in the navgen PNG, the
  `analyze_match.py` plots and the lab GUI, from one table in
  `tools/argus_linkstyle.py`. Jumps were red in the PNG and blue in the GUI,
  rocket jumps magenta and orange, and teleports purple and fuchsia. Each type
  now keeps one hue with a dash, so colour-blind readers can still tell walk
  from drop. Amber now means a drop of more than one step, matching the lab's
  own rule, instead of any one-way link. The GUI legend lists node colours and
  is drawn from the same table, and a test keeps the GUI and Python copies
  equal. See [the brand guide](docs/brand/README.md#navigation-link-colours).

- `argus_ci.py links` also checks the `src`, `srcset` and `href` paths in
  raw HTML inside Markdown, so a broken `<picture>` source such as the
  README banner fails CI like a broken Markdown image already did.

- Return the tracked tree to zero en dashes and em dashes, which the
  editorial rule requires and the 2026-08-29 sweep had achieved. Eleven had
  crept back into the changelog, the recovery study and the co-op spec. The
  invariant battery does not check for them, tracked in
  [#674](https://github.com/saworbit/argus/issues/674).

- Correct the contributor and agent guidance on the lab tick rate. The
  frametime 0.1 rule they taught was refuted in lab 0.26: 0.1 was `ftos`
  printing a 0.05 s frame to one decimal, and every match has run at
  `+sys_ticrate 0.0139` since. The pull request checklist, the core rules in
  the contributor guide and its manual dedicated example are updated, and a
  deliberate 100 ms study arm is now named as a chosen second cadence rather
  than the lab default. Records of trials actually run at 100 ms are
  unchanged. `tools/setup_rig.sh` still omits the flag, tracked in
  [#669](https://github.com/saworbit/argus/issues/669).

- Document lift-to-flight ownership, continuing-route receipt fields and
  current reproduction commands across the architecture, telemetry and lab
  guides. Distinguish the runtime landing forecast from the fixture's dry
  world-floor landing requirement.
  Track missing negative engine controls and stronger forward-handoff proof
  in [#646](https://github.com/saworbit/argus/issues/646) and
  [#647](https://github.com/saworbit/argus/issues/647).

- Synchronise root status, contributor checks, the tool index, telemetry and
  runbooks with the broader-map studies and 19 private fixture variants.
  Track remaining map, movement, reporting and test-coverage gaps in
  [#622-#629](docs/mover-intelligence.md#tracked-follow-ups).

- Prefer shorter geometric distances among routes with the same fewest-link
  count; shopping and route installation share the settled distance tree.
  Refine sampling within reduced node caps and exclude uncompiled graphs
  from the study report's runtime navigation coverage.

- Synchronise the changelog status row, architecture notes, telemetry
  grammar, agent command table and lab runbook with the gait work, and
  record its follow-ups: the unreachable hazard hold (#607), dm3's air-only
  cardinal outlier (#608, subsequently classified as water), the duplicated hull-0 classifier behind an
  unimportable analyser (#609), the human session the measurement cannot
  replace (#610) and the missing documentation link check (#611).

- Give bots a human gait: pauses they choose, with a reason, and a slower
  approach beside lava or slime. Map-matched movement distance improves on
  both laddered maps - dm4 median 1.321 to 1.022, dm2 1.278 to 1.008 with the
  four-a-side arms fully disjoint - at parity or better on stalls,
  engagements, lava, route failures and freezes. New `ARGUS <name> hesitate`
  marker, counted in briefs. Development source only; supplied binaries
  unchanged, and no human session has played against it.
  [Measurement, refusals and limits](docs/behaviour-diagnostics.md#human-gait-hesitation-and-cautious-liquid-approach).

- Synchronise current status, private verification commands, control gates and
  fixture telemetry across the README, contribution guide and lab runbooks
  after #597, #598, #599, #601 and #603. Preserve historical evidence and
  the unresolved gameplay warning; supplied binaries are unchanged.
  Record the missing private-fixture compile gate as follow-up #604.

- Reactivate health/inventory perception step 1b in development at the user's
  request. Fresh dm2/dm4 controlled trials pass 44 information-boundary checks;
  the earlier dm4 gameplay warning remains unresolved. No deployment or cohorts.

- Earlier investigation: retained step 1a and parked health/inventory step 1b
  after a bounded dm4 investigation could not isolate its regression warning.
  Preserve the candidate as a patch; incoming-projectile perception stays on
  hold. [Current status](docs/behaviour-diagnostics.md#current-development-status).

- Record a short blind step 1a/shipped comparison with fixed viewing windows
  and pre-reveal scores. The low-confidence results show no demonstrated
  skill gain; retain step 1a for fair information use and prior checks.
  [Review and limits](docs/behaviour-diagnostics.md#blind-comparison-of-step-1a-and-shipped-matches).

- Complete a separate pre-registered dm2 lava-death holdout: 256 pairs,
  512 valid matches, with two timing-invalid attempts retained under technical
  amendments. Control/candidate lava deaths are 48/50; the registered
  +0.10/minute non-inferiority rule passes, including both rejected-attempt
  sensitivities. The earlier increase is consistent with sampling noise.
  Preserve all timing disruptions and limits. No QC changes or deployment;
  health/inventory and projectile perception remain on hold. See
  [the protocol](docs/perception-lava-cohort-protocol.json) and
  [results](docs/behaviour-diagnostics.md#separate-dm2-lava-holdout-2026-10-25-complete).

- Complete a frozen 128-pair dm2 engagement holdout with unchanged step1a
  and control binaries: 256 valid real-time matches, no exclusions or interim
  decisions. Engagement-rate practical equivalence passes the registered
  +/-2/minute margin; the earlier sharp drop is consistent with noise.
  Retain an exploratory increase in lava deaths (20 to 45) for separate
  validation. No deployment or further perception changes. See
  [the protocol](docs/perception-engagement-cohort-protocol.json) and
  [results and limits](docs/behaviour-diagnostics.md#larger-dm2-engagement-holdout-2026-10-25-complete).

- Implement perception step 1a in source: ordinary combat uses cached visual
  position, velocity, movement and powerup cues, with bounded prediction.
  Unseen damage cannot create a sighting; target reuse clears observations.
  Preserve weapon-callback trace results around the new visibility check.
  The final candidate passes 320 directed engine checks; restoring the old
  combat/pain bodies fails all four positive-control cases. Enemy-health,
  hidden-inventory and projectile-recognition changes remain deferred. See
  [the contract and validation](docs/behaviour-diagnostics.md#perception-step-1a).
  Shipped binaries remain unchanged.

- Complete a larger pre-registered real-time diagnostic cohort: 128 on/off
  pairs per map, 512 valid matches, with unchanged +/-2 goals/minute bounds.
  Goal-rate and mean-frame equivalence pass on dm2 and dm4, including a
  retained first-attempt sensitivity after one exposure-invalid match.
  Diagnostics add about 6 CPU ms per wall second; the earlier goal deficit is
  consistent with sampling noise. This completed step 0 before the user
  resumed perception implementation. See
  [the protocol](docs/behaviour-goal-cohort-protocol.json) and
  [the results](docs/behaviour-equivalence-results.md).

- Clarify staged MCP reconnects, capture provenance fields and current VP9
  preflight prerequisites and pipe timeout limits (#577, #578).

- Update the lab's locked Tokio dependency to 1.53.3 (#575).

- Document the video CLI in the recording guides and tool index, explain its
  playback units and public result fields, and state the current asset-identity
  (#572) and encoder-preflight (#573) limits.

- Synchronize tactical diagnostics, rendered POV limits, camera behaviour and
  blocking Python CI documentation. Track capture notification leakage (#567),
  bounded video export (#568) and missing mod PAK staging (#569).

- Require the tested rmcp 3.5.1 minimum (#534), explain dashboard subscription
  refreshes in the resource description (#536), and make probe enforce build
  authority and the shared compile deadline (#546).

- Run the Python navigation, tape and playability suites as blocking CI steps
  (#525). Pin LibreQuake asset checksums and include them in the cache key
  (#554). Enable private vulnerability reporting and Dependabot alerts (#553).

- Share tape sample, map, event, death and role readers across Python tools
  (#542, #543, #544). Preserve spaced names in pointfile events, exclude lab
  instruments from human trails, and align Rust's repeated whitespace handling
  with Python (#538).

#### Fixed

- Triggered POV capture no longer depends on the engine writing
  `qconsole.log` in the run directory
  ([#810](https://github.com/saworbit/argus/issues/810)). Where that file is
  absent, `bot_capture_pov_frame` with `on` tails the match controller's
  captured stdout, which carries the same console lines, and the
  `watch-pov` CLI refuses with the path it expected and asks for `--log`.
  Covered by a unit test; not yet run on the Linux rig.
- A bot no longer stands at a lift that can never come, or pushes into a door
  leaf that only a button opens
  ([#628](https://github.com/saworbit/argus/issues/628),
  [#643](https://github.com/saworbit/argus/issues/643)). A plat with a
  targetname spawns raised and inert until its button fires (e1m5's *2, button
  *3); the lift wait read it as on its way and stood still for the full 8 s
  give-up, and now gives up at once. Stock LinkDoors copies a pair's
  targetname onto the master only, so the leaf a bot meets could read as
  touch-open (e1m6's *20 beside *7, "This door is opened elsewhere");
  `Argus_DoorMaster` makes the touch-open test and the opener search use the
  master. Played-rate pairs, five a side: e1m5 freezes 2.4 to 0 a tape, mover
  waits at the pad 17 to 0, goals 23.6 to 30.6; e1m6 seconds pinned at the
  door face 58.7 to 10.7 over five tapes. Every gate reads no detectable
  effect, and dm4, with no such door or plat, replays its fixed-clock seeds
  identically.

- A routed bot switches early to its next waypoint only while floor runs under
  the straight line to it
  ([#775](https://github.com/saworbit/argus/issues/775)): the side traces
  refused only walls, so on a void-edged walkway a bot 48u short of a
  mid-corner elbow could head across open air. Parity on dm4 and dm3 (three
  played-rate pairs each) and lab_voidcorner (five); the original fall was not
  reproduced, because #772 re-seated dm3's elbows.

- The bot ground physics gains stock edge friction and wall friction
  ([#794](https://github.com/saworbit/argus/issues/794)): friction doubles
  (cvar `edgefriction`) when nothing lies 34u below a point 16u ahead at the
  feet, and a wall slide facing within 60 degrees of head-on keeps 1 + d of its
  speed along the wall, as `SV_UserFriction` and `SV_WallFriction` do for
  players. Ground samples over 400 u/s fall on dm4 from 5.57 to 4.96 per cent
  (edge) and 4.68 (wall), with separate ten-seed ladders at parity on dm4 and
  dm2 and played-rate pairs of both together at parity (three on dm4, five on
  dm2).

- Reachability jumps fire only where a jump helps, and a stall jump is
  checked on the flight it will fly
  ([#774](https://github.com/saworbit/argus/issues/774),
  [#782](https://github.com/saworbit/argus/issues/782),
  [#797](https://github.com/saworbit/argus/issues/797)). Both reachability
  branches fired at any steering point 24u or more above within 80u. On dry
  feet a jump now waits for a riser taller than a step within 32u along the
  line, so ordinary stairs are walked, and is refused above
  `Argus_JumpApex` plus a step, where no jump climbs. The stall jump is
  tagged, checked along the post-turn heading with the 30 u/s that NQ air
  acceleration can add along one wish, and the flight is held on that
  heading. A refusal is no longer logged for a bot already in lava or
  slime. In a liquid both keep the old rule: applying the new one there
  left bots burning on the dm4 pit floor in the first candidate.

- Evidence: jump events halve (dm4 187 to 93, dm2 2,148 to 1,144 over 30
  fixed-clock seeds, e1m7 185 to 30). dm3's n55 to n45 stairs go from 14
  jumps to 2, both stall jumps, and none from routed steering; e1m7
  low-floor jumps go from 175 to 23. Against main every gate reads no
  detectable effect: 30 fixed-clock seeds a side on dm4 and dm2 (lava 1.9
  to 2.1 and 0.9 to 1.0), ten on e1m7, and three played-rate pairs each on
  dm4, dm3 and e1m7.

- `tools/argus_gait.py` no longer files a bot parked at a mover pad as the
  wedge class ([#628](https://github.com/saworbit/argus/issues/628)). A lift
  or train hop parks the bot with `ar_liftwait`, friction only and no marker,
  so the e1m5 window the issue quotes (Romero, 6.0 s from t=33.1 in
  `broad_mhb_e1m5_2`) read as "pre-existing" although the tape shows the hop
  planned at t=31.0 and the 8 s pad give-up at t=39.1. A window that opens
  inside the bot's own hop is now a `mover wait`, with the verb that closed
  the hop and whether the bot boarded; one that runs on more than a second
  past its hop's close or bound is a `mover overrun`, so a hold that outlives
  the controller's own give-up is not hidden either. A hesitation marker
  keeps first claim, and neither class fails the exit status. All three e1m5
  windows on record (`broad_mhb_e1m5_2`, `broad_ecu_e1m5_2` and the
  `broad_ecpin5` trace) now read `lift hop ... closed by abandon, never
  boarded`. The waits themselves are not fixed here: they are at e1m5's
  targeted plat (`func_plat *2`, targetname `t2`), which stays raised and
  inert until its button fires.
- The box test samples the player hull's real 16u corners, and the unstick
  test calls a bot embedded when its hull, not just its origin, is in solid
  ([#755](https://github.com/saworbit/argus/issues/755),
  [#756](https://github.com/saworbit/argus/issues/756)). At 15u a spot whose
  hull clipped a wall by up to a unit passed, so the catchup warp, the
  unstick destination, the airborne body nudge and the tactic path samples
  could approve a place every engine move then left in solid. A hull that
  clipped a wall with a clear origin waited for the slower stall, hurt or
  fight rescues: Joe Rogan held dm4 '12.8 -272.9 -72' for six seconds. The
  embedded test reads solid only, so water and lava do not count, and
  `pointcontents` cannot see movers, so a plat, door or train never trips
  it.

- Evidence: replayed against hull 0, both reported spots (dm4
  '12.8 -272.9 -72' and dm3 '335.1 125.9 -200') pass at 15u and are refused
  at 16u, and a hull flush against the dm4 wall stays clear. Ten fixed-clock
  seeds a map against main read identical on dm4 and dm2 (cover moved by
  0.1), so the path is rare in ordinary play. A real-engine fixture that
  places a hull on the dm4 spot was not built.

- The step1b amend helper's test no longer pins the newest amendment's
  name, which made it fail on the first real edit to `src/argus.qc` after
  it landed. It checks that the manifest it was given is unchanged, and
  takes the duplicate case from the manifest itself
  ([#871](https://github.com/saworbit/argus/issues/871)).
- Say why each shipped seat stands on no navmesh fragment
  ([#788](https://github.com/saworbit/argus/issues/788)). The dry ones
  were not floors the extractor lost: every one stands on a hull-1 face
  too steep to stand on (normal z 0.24 to 0.66), which the mesh leaves out
  under the FL_ONGROUND rule, and with that cut lowered the extractor finds
  a face under each within 0.1u. `argus_navmesh.py --audit` now splits its
  off-mesh line into liquid seats the repair keeps, steep faces with the
  distance to the nearest fragment, no world floor within 30u, seats inside
  the world, and dry seats with no fragment and no reason. Dry off-mesh
  seats before, and dry seats with no fragment and no reason after: e1m8
  25 to 0, e1m3 5 to 0, e1m7 3 to 0, e1m2 2 to 0, lqdm2 1 to 0, all 36
  now reported as steep; dm2, dm3, dm4, dm6, e1m1, e1m4, e1m5, e1m6 and
  the six lab maps 0 to 0.

- Stop the lab's Rust tests leaving directories in `%TEMP%`
  ([#861](https://github.com/saworbit/argus/issues/861)). The console
  injection and network client tests leaked one each on every run with an
  engine present, and the two backup tests, the fingerprint test and the
  stop-match test leaked one whenever they failed. All six now use
  `test_support::TestDir`, which removes its directory on drop, so a panic
  cleans up too. Before the change a run of the two engine tests left two new
  directories; after it, a run in which one of them failed left none.

- Keep the lab's Rust suite green on a loaded machine (#836). Three fixed
  waits in the lab itself are now bounds on a condition: `stop` waits up to
  5 s for a killed engine to exit instead of 200 ms, so it no longer reports
  a dying engine as running; shutdown gives aborted tasks 10 s, not 2 s, to
  release the run gate; and the Windows console helper may take 15 s to
  start, not 5. The six tests named on the issue, and five more of the same
  kind, wait on conditions with deadlines instead of fixed sleeps, and the
  real-engine tests now hold the live-match test lock, because their matches
  wrote the live state the fake-match server tests assert on. Three full
  parallel runs passed 437 of 437 with a busy loop on every core.

- Classify lava by hull-0 contents in `measure`'s null-pair gate audit and
  stopping-rule audit, as its limits table already did. Both read dm2 and
  e1m7 lava as zero on every tape; the dm2 null pairs now read their real
  lava (0 to 8), none convicts, and the stopping-rule audit gains one reject
  in the regenerated limits doc. A test now covers the listen-class arm
  filter (#835).

- Name the arm and both halves when the stopping-rule audit accepts a null.
  The e1m6 stall accept at the listen-class sigma is #324's seven-tape
  candidate arm, whose own spread (28.2) exceeds the pooled 21.0; the larger
  baked sigma stays, with that evidence beside it (#834).

- Count a human death as a bot kill in the brief's human scorecard only when a
  bot is the killer. A self-splash used to count, so the 16 September dm4
  session read eight bot kills where the bots got six (#844).

- Print `avg_speed` in `argus-mcp corpus` tables. The index already carried
  it, but a tape the index lacks reached the fixed-clock validation without
  it (#843).

- Carry build and clock confounds into the Rust compare, band and experiment
  verdicts, as the skeptic already does: different builds or engine clocks
  between or inside arms are reported, and an arm holding one fixed-clock seed
  and build twice is refused (#852).

- Refuse a second match on a live run's name or a held port before it spawns
  anything (#832). Every match takes a lease on `runs/<run>/`, and a reused
  directory's old log is cleared before the engine starts, so a rerun cannot
  read its predecessor's tape; the port probe also binds the hostname address
  QuakeSpasm binds.

- Let capture start up to 900 s into a demo (it stopped at 120 s), with a
  render deadline that grows with the seek.

- Resolve `ARGUS_LAB` to an absolute path in the lab spine: Windows could not
  launch a relative one once the child had its own environment, so the
  corpus silently returned nothing.

- Name the real cause when the Windows console-inject tests fail. They spawn
  `target/debug/argus-mcp.exe`, which `cargo test --lib` does not build, so a
  fresh target directory failed with a bare os error 2 at any thread count.
  The error now names the missing binary or a helper built from other source
  and says to run `cargo build --bin argus-mcp`, and CONTRIBUTING builds the
  CLI before the lib tests. With the CLI current, the full parallel lib run
  passes 405 of 405
  ([#805](https://github.com/saworbit/argus/issues/805)).

- Give the lab server's git children a 30-second deadline, as the Python
  helpers already have: plain calls are killed and reported as timed out, the
  `cat-file --batch` history reader has a watchdog, and `mill` and argument
  completion run their history walks on the blocking pool instead of holding
  an async worker for as long as git takes
  ([#813](https://github.com/saworbit/argus/issues/813)).

- Confirm each step of `argus-mcp benchmark` in the server log instead of
  sleeping 150 ms: every console line ends with an echoed marker and is resent
  until it lands, opponents are removed one at a time while more than one bot
  remains, and placement and goal are confirmed together by the task bot's
  route from the task start to the task goal, placing again up to four times.
  A task that never starts is reported incomplete with a `note`. The dm3 suite had
  scored 0 of 4 because a late console line made the goal impulse place the
  bot again ([#776](https://github.com/saworbit/argus/issues/776)).

- Classify lava deaths in `argus-mcp corpus` by hull-0 contents when the map's
  BSP is on hand, as briefs and `compare_runs` already do. The corpus used the
  retired z < -300 rule, so dm2 (lava near z -35) and e1m7 (near z -30) read
  0 lava on every tape. CLASSIFICATION BOUNDARY: corpus, `measure` and
  `corpus what=changes` lava figures for dm2, e1m7 and dm4 are not comparable
  with earlier outputs. The index's context schema is bumped, so a cached
  index written under the old rule is re-parsed
  ([#816](https://github.com/saworbit/argus/issues/816)).

- Read the working-tree graph revision, its sidecars and their mtimes from
  `ARGUS_SRC`, and its history from the repository that holds it. Run from a
  worktree with `ARGUS_ROOT` at the main checkout, `mill what=revisions` and
  `argus://graph-revisions/<map>` used to describe the main checkout's graph
  ([#804](https://github.com/saworbit/argus/issues/804)).

- Print capture manifests' scheduled seconds as exact playback steps (2.8,
  not 2.8000000000000003) by counting whole 0.05 s steps and dividing once
  ([#811](https://github.com/saworbit/argus/issues/811)).

- Retry the GUI rendering test's headless browser once when it stalls, kill
  the browser's whole process tree on a timeout, and fail a second stall with
  the browser's stderr from both attempts. The first launch on the CI runner
  had hung for the full 25 s with no output while the page work takes a few
  seconds ([#817](https://github.com/saworbit/argus/issues/817)).

- Escape the `Argus_Nav_Spawn_<map>` placeholder in the lab's rustdoc, and
  build rustdoc with warnings denied in the fast workflow so the next one
  fails its pull request ([#806](https://github.com/saworbit/argus/issues/806)).

- Stop routing bots into shallow lava and up impossible vertical "walks".
  navgen tested liquid 48u above the floor, so 70 seats across six maps stood
  in lava or slime that burns at the feet, and it passed any zero-length link
  whatever the height, minting 15 climbs of 128 to 192u. navgen now tests the
  feet and refuses a zero-length rise; a new `--repair-links` mode cut both
  classes from nine shipped graphs without a regeneration, keeping liquid
  only as a seat's last way out. Matched dm4, e1m7, dm3 and e1m8 ladders stay
  at parity: dm4 lava entries fall 40 to 24, and dm3 stops choosing a red
  armour that bots picked 70 times in 157 tapes and never reached. e1m7's
  lava deaths are falls off its upper walkways and do not move. Found by a
  new exact navmesh audit read from the BSP's player clip hull
  ([#770](https://github.com/saworbit/argus/pull/770),
  [details](docs/navmesh-experiment.md)).

- Check that a baked combat cover hop is still a live, untyped link from its
  node, with no deliberate drop, before a retreating bot steers along it.
  Every shipped graph already meets this, so current matches are unchanged;
  the guard covers future regenerations
  ([#652](https://github.com/saworbit/argus/issues/652)).

- Separate same-floor body nudges on a hull axis and let the engine refuse a
  spot the player hull cannot fit, so a nudge no longer clips a wall or
  leaves two players overlapping on a diagonal. Matched dm3 and dm4 matches
  stay at parity
  ([#747](https://github.com/saworbit/argus/issues/747),
  [details](docs/body-nudge-investigation.md)).

- Check every muzzle combat witness predicate and retain strict receipt
  rejection under optimized Python
  ([#745](https://github.com/saworbit/argus/issues/745)).

- Keep health and observation evidence, frozen-source and private-input
  guards active under optimized Python
  ([#742](https://github.com/saworbit/argus/issues/742)).

- Require vertical body overlap before nudging or sidestepping another
  player. Prevent the reproduced dry e1m6 and dm3 pins caused by players
  on other floors; retain separate task and broader-match gates
  ([#642](https://github.com/saworbit/argus/issues/642),
  [#644](https://github.com/saworbit/argus/issues/644)).

- Preserve weapon-free swim exits when the generator also finds a rocket
  link for the same pair. Record the private mega-return proof while graph
  adoption remains blocked by the legacy jump anchor
  ([#636](https://github.com/saworbit/argus/issues/636),
  [#719](https://github.com/saworbit/argus/issues/719)).

- Name the missing lab binary. The study runners now stop with the path they
  tried and the two ways to provide a lab, instead of a bare
  FileNotFoundError from subprocess ([#768](https://github.com/saworbit/argus/issues/768)).

- Correct two `src/argus.qc` comments that still said dm2 has pools. Its only
  liquid is lava, settled on 2026-08-18. Comments only: the compiled
  progs.dat is byte-identical ([#767](https://github.com/saworbit/argus/issues/767)).

- Let routed bots walk into dm3's south upper area, which holds the red
  armour. Removing two impossible climbs (#770) had stranded its 22 seats;
  five elbow seats and sixteen walks that navgen's beeline test accepts now
  join it to the mainland, and the walk that crossed 119u of open air at the
  top is retired. Reach from the worst spawn rises from 89 to 98 per cent
  ([#772](https://github.com/saworbit/argus/pull/772)).

- Evidence for the dm3 route: the engine walked all sixteen new legs twice;
  matched dm3 ladders stay at stall parity (listen class, 5 against 5 and 5
  against 11); bots chose the armour 28 times in 15 tapes against 0 and
  entered the area in 6. Controlled acceptance on dm3 only, not human play
  ([details](docs/navmesh-experiment.md#seating-dm3s-south-upper-area)).

- Limitation: no bot reached dm3's armour platform at skill 2; a skill-1
  diagnostic put one across it. Bots reach the top walkway airborne after a
  stair hop the runtime fires whenever the next seat is over 24u up, and at
  skill 2 the router prefers an existing sprint across the top gap. Both are
  open runtime work.

- Judge where a bot running off a ledge lands, not only the floor under its
  hazard probe. On e1m7 the guard approved run-offs whose probe found the
  island, the floor under the deathmatch spawn pads or the deathmatch lava
  bridge, and run speed carried bots 200 to 240 units past them into the
  lava lake: 28 of 43 lava deaths in six full-rate tapes
  ([#773](https://github.com/saworbit/argus/pull/773),
  [details](docs/e1m7-lava-investigation.md)).

- Drop a jump that would land in lava. The other 15 e1m7 lava deaths were
  jumps at the lake edge: the fighting reachability jump fired under a
  walkway seat 160 units overhead, and the predictive gap jump judged its
  landing at chest height and let steering bend its flight. Reachability,
  stall, escort and gap jumps now trace the arc at the feet first, and a
  gap jump holds its launch line until it lands
  ([#773](https://github.com/saworbit/argus/pull/773),
  [details](docs/e1m7-lava-investigation.md#the-jump-change)).

- Evidence: five interleaved e1m7 tapes a side with lava deaths registered
  read parity (median 3 to 2, P(improve) 0.56), while two full-rate
  candidate tapes held no upper-floor run-off against 4.7 a tape before.
  dm4 holds stall parity over six tapes against eight earlier controls of
  the same build. Smoke and controlled parity only; no human play.

- Evidence for the jump check: ten interleaved e1m7 tapes a side against the
  run-off build, lava deaths registered, read parity overall but lava deaths
  fall 25 to 14 (median 3 to 1.5, improvement CI +0.2 to +2.2, P(improve)
  0.77); stalls and engagements unchanged. The frag gap between bots widened
  (median 6 to 10.5) and is unexplained. dm4 logs about one veto a tape and
  holds stall parity. Controlled parity only; no human play.

- Correct three `src/argus.qc` comments that still gave the refuted
  frametime 0.1 lab rate as measured fact: the swim drag block, the aim tremor
  guard and the tremor clock field. Comments only; the compiled program is
  byte-identical. The swim constant was calibrated to that wrong rate, and
  whether to restore its original feel is left to
  [#761](https://github.com/saworbit/argus/issues/761)
  ([#762](https://github.com/saworbit/argus/issues/762),
  [#765](https://github.com/saworbit/argus/pull/765)).

- Evaluate every mover-observer retention and dryness clause and qualify
  older field claims separately from physical handoff evidence
  ([#735](https://github.com/saworbit/argus/issues/735)).

- Refuse legacy water-route ramp experiments before staging or engine launch
  when the selected source graph lacks their required seats
  ([#736](https://github.com/saworbit/argus/issues/736)).

- Evaluate both water-route ownership identities and distinguish corrected
  layout-2 receipts from historical task-only markers
  ([#733](https://github.com/saworbit/argus/issues/733)).
  Let accepted route checks return without reading a missing rejection field.

- Check co-op allies along the limited barrel direction and disable speculative
  rockets in co-op while respecting facing and muzzle-clearance gates
  ([#655](https://github.com/saworbit/argus/issues/655)).

- Keep plan-proof input, source and output guards active under optimized Python
  ([#728](https://github.com/saworbit/argus/issues/728)).

- Clarify persistent hazard-deflection memory and its reset paths without
  changing steering ([#607](https://github.com/saworbit/argus/issues/607)).

- Share the stall ownership predicate so stationary typed actions can release
  failed goals, while moving item-clock orbits clear isolated failure history
  ([#649](https://github.com/saworbit/argus/issues/649), [#650](https://github.com/saworbit/argus/issues/650)).
  Preserve the frozen health/inventory source through an explicit reverse amendment.

- Apply requested lab skill before loading the map so the initial roster uses
  the declared difficulty ([#726](https://github.com/saworbit/argus/issues/726)).

- Measure full-rate movement reversals in native demo briefs and add passive
  steering markers with finalized engine poses for the open movement study
  ([#697](https://github.com/saworbit/argus/issues/697)).
  Retain the frozen health/inventory definitions through a reverse amendment.

- Require observed exit-node consumption, the planned successor and a dry
  world-floor landing in private mover receipts. Preserve the weaker v1 evidence
  and reject node-only oracle controls ([#647](https://github.com/saworbit/argus/issues/647)).

- Restore the chase camera basis after failed flyby sweeps and bound its
  position blend at slow frame rates ([#654](https://github.com/saworbit/argus/issues/654)).

- Add private engine controls for obstructed, mismatched-floor and undocked
  mover forecasts, with real water depth kept separate from dry landing proof
  ([#646](https://github.com/saworbit/argus/issues/646)).

- Read CRLF as LF in the lab's source fingerprint, so a worktree and the main
  checkout of one commit report the same identity and a worktree compare is
  no longer refused as a stale lab
  ([#777](https://github.com/saworbit/argus/issues/777)).

- Say on a band gate card that its rows compare the median-stall tape of each
  arm while the verdict uses every tape, so a red row under a green verdict
  is not read as a failed gate
  ([#757](https://github.com/saworbit/argus/issues/757)).

- Reject resolved jump launches outside the runtime's strict 96-unit source
  anchor before generation or profiling publishes artifacts. Add a read-only,
  hash-stamped audit for existing jump links (#665).

- Bind navigation coverage to frozen compile and tape receipts, distinguish
  on-disk registration from the tested build, and withhold runtime claims
  when provenance is unknown. Keep study report checks active under optimized
  Python (#625).

- Count emitted navigation links in ARGNAV banners and enforce QC/JSON edge
  and cover-hop agreement. Reconcile all 13 graph pairs and rebake dm4 hints
  after removing its phantom walk edge (#666, #653).

- Preserve configuration, argument, missing-target and internal failure kinds
  across MCP tools, prompts and resources, with actionable JSON hints (#689).

- Share each controller's typed UDP port with its clients, expose side ports
  on connected CLI helpers, and refuse an occupied port before launch (#690).
- Refuse dot, hidden and trailing-dot run names before creating a directory,
  and declare `match_command` as the trusted raw console escape hatch (#663).

- Isolate Windows console injection in a bounded helper process so parallel
  live commands cannot detach the lab or swap its standard handles (#659).

- Bound Python helper lifetimes, yield the async worker while they run, and
  publish staged nav, registration and plot outputs only after success (#683).
- Apply six-percent chamfers with complete inset borders to GUI panels,
  buttons, pills and canvas frames at normal and doubled display scale (#677).

- Check the GUI's inline favicon against its source SVG in fast CI and
  document the manual full-brand reproduction check (#678).

- Render GUI server fields as text and bind dynamic edge clicks without
  parsing data as markup or JavaScript (#660).

- Resolve relative lab config paths at load, confine generated outputs and backup
  restores, preflight restores with rollback, and trust fresh preview receipts
  instead of printed path spelling, with boundary help kept within the tool
  schema budget (#692, #684, #661, #680).
- Share private fixture staging, protected installs, named single-map tape
  reads and measured cadence checks across study runners (#685).

- Use one QC/SRC identity in new Python receipts, preserve existing source
  hash ordering, and distinguish whole-tree audits and native legacy MD5
  identities from the shared `source_sha256` field (#687).

- Use one platform-aware study lab resolver for MCP, CLI calls and receipt
  hashes, with explicit request deadlines and bounded CLI cleanup (#686).

- Share QC-safe map names across lab entry points (#688), count every typed
  family in runtime slot admission and refuse typed overflow (#664), and use
  the cached graph representation for overlays while exposing unavailable
  map-item data in graph views (#691).

- Keep parsing client messages after NetQuake keepalives, report malformed
  `svc_bad` streams explicitly, and retain later prints and entity updates
  from the same packet (#658).

- Match the engine's door-lip default for explicit zero values (#668), reject
  proven anchors that collide on one fine sample before writing navigation
  (#694), and remove two unused, uncallable jump wrappers (#667).

- Keep proof and study validation active under optimized Python (#681), refuse
  the backups root before creating plan-test output (#651), and close failed
  lab sessions without replacing the original error or skipping binary
  restoration (#695).

- Draw every typed link family in navigation previews, with dashed swim links
  distinct from solid door links (#675). Render shipped graphs with
  `--render-only` without regenerating navigation (#676), and give the Omicron
  roster four distinct track and death-marker colours (#698).

- Run navigation tactics and Rust integration tests in fast CI, preserve
  option-like PR titles and line-buffer smoke output (#670). Enforce the
  dash rule on tracked prose and sources (#674), and stop accepting false
  setext anchors after lists, quotes, headings and separators (#696).

- Preserve Quake console text with bronze bytes (#657), split CRLF tapes at
  exact level boundaries (#662), attribute plain markers independently of
  bot names (#693), and refuse gameplay comparisons when any tape records a
  failed map spawn (#656).

- Colour `analyze_match.py` trajectory tracks by roster slot. The table was
  keyed by the retired names Reap, Omi and Zeus, so Carmack, Romero and Joe
  Rogan all drew black and could not be told apart.

- Keep an actually supported bot aboard a moving lift through docking.
  Cross a dock seam only after checking the jump's landing at current
  speed, preserving the continuing route. Repair the reproduced e1m6 exit
  failure without a map-specific runtime branch or navigation edits.

- Report optional navigation preview freshness separately from QC/JSON
  generation. Bind previews to their graph and image hashes, and withhold
  stale images from native results and the wizard when plotting is skipped
  or fails (#638).

- Carry the registered study primary into per-tape native comparison cards.
  Retain input identities and native vetoes, reject incompatible baselines
  before starting matches, and gate these contracts in fast CI (#629).

- Execute affordable route actions when several typed links share endpoints.
  Preserve underwater depth, supported arrivals and required transitions
  when an item becomes visible. Complete planned swim exits and low hurdles.
- Replan actions that stop approaching their route seat. Keep deliberate
  waits and jump setup, and require lift rides to approach their landing
  rather than renewing recovery on a crush/reverse cycle. See the [e1m5 investigation](docs/e1m5-encounters.md).

- Quarantine new and historical recovery/transfer fixture tapes from native
  match comparisons and default bot-corpus queries, invalidating older cached
  classifications without changing raw tapes or numeric metrics (#626).

- Run the navigation-budget, map-report, recovery-receipt and mover-receipt
  suites as blocking fast-CI checks, with matching contributor and lab guidance
  (#627).

- Preserve the historical health-perception fixture boundary after recovery
  changes with an exact reverse amendment; retain active function checks and
  rejection of undeclared source edits.

- Keep navigation infrastructure and synthetic platform pads inside Quake's
  entity allowance. The experimental e1m3 graph now fits within 600 edicts;
  e1m3/e1m4 still fail playability gates and remain unregistered.

- Enforce severe-freeze vetoes across every candidate tape in a repeated-run
  comparison, including tapes outside the displayed representative.

- Synchronise the contributor guide with the pinned Rust toolchain, strict
  Clippy check and CI compilation of all 19 maintained private fixture variants.

- Keep the lab dependency update compatible with strict Clippy by boxing the
  Unix child handle. Update locked rmcp to 3.7.0, rmcp-macros to 3.8.0 and Tokio
  to 1.54.1 (#620).

- Correct the dm3 clearance interpretation: 25 zero-empty-cardinal seats and
  all 100 of their probes are water, not solid walls. Preserve the graph and
  distinguish the air-only navgen bar from runtime movement clearance (#608).

- Make `analyze_match.py` import-safe and share its hull-0 contents reader
  with the void probe. Existing CLI behavior and the no-BSP lava-death
  classification fallback are unchanged (#609).

- Retain nearby opening-door ownership until the slab finishes, with one
  bounded eight-second opening phase and unchanged remote/past-door handling
  (#602). Add shipped-speed physical deadline and premature-release controls
  for #589. Retain the unsupported motor override as an explicit diagnostic,
  outside the default gate (#593).

- Deliver engine-confirmed floor-button touches for walking bots, resolve
  physical openers behind relays and wait for actual button activation. Add
  private physical/control fixtures; normal e1m2 goal contact is verified,
  while the historical motor override is retained as a diagnostic outside
  automatic acceptance (#600, #589, #593).

- Verify ordinary rocket clearance through the actual combat trigger, retaining
  movement and checking real ammo/projectile emission against a negative
  control. Record the existing embedded-muzzle limit without changing gameplay
  or installed binaries (#584).

- Enforce the offset-entry case 3 negative control and retain invalid receipts
  before rejecting them (#594). Add repeatable private muzzle and active
  health/inventory verification with current-source snapshots, declared
  controls and unchanged installed binaries on success or failure (#586, #595).

- Resolve game-directory reports against the base directory (#590), report
  unsupported camera signon protocols (#591), and exclude `labcamera` from
  bot and human statistics in both tape readers (#592).

- Require a landed, laterally clear entry before ordinary flat-walk waypoint
  handoff, including the apex shortcut (#593). Preserve typed/height-changing
  links and the 48-unit arrival radius. Account for validated apex transitions
  as plan progress. Development source only; physical evidence is recorded
  in the behaviour diagnostics guide.

- Keep progressing detours alive, reject repeated waypoint cycles as progress,
  and rest failed co-op fetches before retrying without blocking a new subject
  or another bot (#589). Preserve combat and fixed-task deadlines. Controlled
  decision, physical co-op retry and supported-speed deadline controls pass.
  The unsupported motor override remains diagnostic only (#593); development
  source only, supplied binaries unchanged.

- Run muzzle-clearance and local review-output contracts in fast CI. Keep
  generated review media and frozen local study tapes out of Git staging,
  retaining tape checksums separately (#585, #587).

- Check the actual ordinary rocket firing direction against nearby geometry,
  capped at aim-point distance so an opponent's backdrop does not veto a
  clear shot. Preserve movement, other weapons and the tactical 240-unit
  probe/abort rule. This is a development-source change; supplied binaries
  remain unchanged. [Evidence](runs/muzzle1_clearance.results.json).

- Investigate diagnostic overhead with fixed-input original-source controls;
  batch snapshot output, retain frame-time precision, fix rounded-timestamp
  validation and synthetic lifecycle-fixture residue, and quarantine controlled
  tapes from ordinary match bands. Controlled equivalence passed; the initial
  real-time goal-rate cohort was inconclusive. See
  [the evidence and limits](docs/behaviour-equivalence-results.md).

- Escape protocol and map filename placeholders in Rust documentation (#579).

- Bound FFmpeg preflight pipe I/O and use a built-in PNG instead of lavfi
  to verify VP9 before capture (#577, #578).

- Keep capture acknowledgements out of rendered frames while preserving the
  console log (#567). Stage mod PAKs with their original search precedence
  (#569). Export bounded POV clips with explicit playback speed and verified
  decoded frame order/timing; FFmpeg remains optional for PNG capture (#568).

- Hide the tracked bot from its own POV by selecting its protocol view
  entity. Hide the observer body while active and restore its render index
  and view entity on camera exit (#565).

- Sequence tactical trials with console and engine acknowledgements, unique
  IDs and bounded cleanup (#516). Observe real owned rockets independently
  of ammo changes for unlimited-ammo fixture acceptance (#529). Complete
  both 15-trial map suites at played cadence and measured 10 Hz (#515).

- Use the standard player hull for both teleport camera cuts and tactical
  trigger avoidance, including its 32-unit upper reach (#548).

- Refuse the Omicron roster rename in deathmatch and co-op, including when
  the roster key is armed. Keep the plain single-player toggle (#552).

- Build cartograph overlays with the nav reader and report malformed graphs
  instead of drawing partial links. Share the walkable step height (#545).

- Preserve quoted strings while checking navigation registration in Rust and
  Python (#523), reject noninteger graph endpoints (#524), and refuse custom
  QC filenames with `--register` before any files change (#537).

#### Maintenance

- Machine-local study tapes no longer need a `.gitignore` line per ladder
  stem ([#872](https://github.com/saworbit/argus/issues/872)). A run named
  `study_<stem>_...` is covered, tape and navigation receipt, by one rule on
  every branch, so a branch's tapes are no longer trackable on main until its
  ignore lines merge, the gap through which a `git clean` deleted 197 of
  them. The new `argus_ci.py localtapes` check fails when a results file in
  `runs/` says its tapes are machine-local but Git would track one of them;
  it passes on the 14 existing records. The older lines for 22 stems stay, so
  recorded run names still hold.

- `cargo deny` ignores RUSTSEC-2026-0543, the notice that `chrono` is
  unmaintained. No upgrade exists, and `rmcp` and `schemars` depend on it as
  well as the lab, so the policy records why it is ignored and when to look
  again (`tools/argus_mcp/deny.toml`,
  [#870](https://github.com/saworbit/argus/issues/870)).

- Read average speed on the fixed-clock confirmation tapes
  ([#863](https://github.com/saworbit/argus/issues/863)). It was registered
  with the validation but the corpus did not carry it when the verdicts were
  made. Read afterwards on the same tapes, it is equivalent on both maps:
  dm4 212.2 against 209.4 u/s (90 per cent interval -6.7 to +1.0, margin
  63.7) and dm2 182.9 against 183.7 (-9.5 to +11.0, margin 54.9). Neither
  verdict and no limit changes. `docs/fixed-clock.md` and
  `tools/lab_instruments.json` record it as read after the verdicts.

- Explain the project in the README. A new section says what Argus is, which
  rules all of its code follows and how a map file becomes a measured match.
  Five Mermaid diagrams show the main data flows: the build, play and measure
  stages, one server frame, the navigation pipeline, one lab experiment and
  the improvement cycle. A telemetry sample comes from the dm4 smoke tape of
  the supplied build. Two stale statements are corrected: the development
  status said the recent behaviour work was not installed, but the
  2026-11-15 install shipped it, and the map table now lists the six
  registered episode-one maps. The status paragraphs become two tables that
  keep every link. The prose follows ASD-STE100 Simplified Technical English
  where it fits.

- Bring the guides in line with #834, #835, #844, #846 and #852: the lab
  operator guide names the repeated-seed refusal, the confounds the Rust
  verdicts now report and the audits' lava rule, the fixed-clock and lab spine
  guides say which instruments see clock and build confounds, the stand-in
  guide drops its scorecard caveat, and AGENTS.md names the hashed CI copy of
  the frozen perception pins.

- Clear 35 of the 37 pyflakes findings in `tools/` and widen the `python
  critical lint` gate from Ruff's critical set to all of pyflakes. The other
  two sit in `verify_muzzle_clearance.py`, whose hash a results file records,
  so `ruff.toml` exempts it rather than editing it. The two unused variables
  in navgen's `beeline_ok` were leftovers of reverted attempts; a dm2
  regeneration is byte-identical before and after (#850).

- Record the repository settings applied with the GitHub hardening, which
  live outside Git: `main` now accepts changes only through pull requests
  and requires seven checks (`repo invariants`, `lab test suite (rust)`,
  `workflow lint`, `config schemas`, `python critical lint`, `shell lint`
  and `dependency review`) on an up-to-date branch, with no approvals
  needed and the admin bypass kept. A ruleset stops `v*` release tags being
  deleted or moved. Dependabot security updates and the Update branch
  button are on; the empty wiki is off. CONTRIBUTING.md now lists the
  checks, gives the CI test commands (the `--lib` form it taught missed the
  integration tests) and adds a release runbook; AGENTS.md carries the
  workflow and frozen-input rules
  ([#845](https://github.com/saworbit/argus/pull/845)).

- Add the repository metadata a public project is expected to carry: an
  `.editorconfig` that matches `.gitattributes`, `CODEOWNERS`, a
  `CITATION.cff` behind GitHub's "Cite this repository" button, linguist rules
  that collapse generated nav graphs and tapes in pull request diffs, and
  ignore rules for editor, Python cache and credential files. The issue forms
  ask for the Argus build and how the session ran, as `SUPPORT.md` already
  did, and the template links no longer point at a file that is not in the
  repository. Pull requests are labelled by path so the generated release
  notes group them. The `dashes` check now reads workflows, manifests and
  repository metadata too, not only prose and sources ([#838](https://github.com/saworbit/argus/pull/838)).

- Add a `release` workflow: pushing a `v*` tag builds `progs.dat` from that
  tag with the pinned compiler, packages it as earlier releases were shipped,
  attests the zip's build provenance and opens a draft release for the notes
  to be written before publishing. The fteqcc pin now lives once, in
  `.github/actions/build-progs`, shared by the compile gate and the release
  ([#838](https://github.com/saworbit/argus/pull/838)).

- Type-check the lab on Windows in CI. Its console injection, job objects and
  pipe handling sit behind `cfg(windows)`, which the Linux job never compiled;
  a `windows` workflow now runs strict Clippy on every target whenever the lab
  changes. It does not run the suite, whose Windows inject tests need an
  engine ([#838](https://github.com/saworbit/argus/pull/838)).

- File the loose bullets that sat between Main updates and Unreleased under
  their categories, and merge the repeated category headings, so each one
  appears once. Every bullet keeps its wording and links
  ([#769](https://github.com/saworbit/argus/issues/769)).

- Refresh the measurement limits and persist the tape index. `measure` now
  uses only listen-class arms for any map that has them, names each sigma's
  tick class in a new last column, and classifies lava by hull-0 contents
  as #816 did for the corpus. The superseded listen-class baseline bands stay
  in the noise corpus as ladder arms. Each baked sigma keeps the larger of its
  old value and the new one, because a lower e1m6 stall sigma let the stopping
  rule accept a null. `runs/tape_index.tsv` is rebuilt with hull-0 lava and
  the current context schema, so queries stop re-parsing every tape
  ([#822](https://github.com/saworbit/argus/issues/822)).

- Re-baseline every map in `runs/baselines.json` on main at the played rate,
  skill 2, 185 s: five tapes for dm2 and three each for dm3, dm4, dm6, e1m1,
  e1m2, e1m5, e1m6, e1m7 and lqdm2, all listen class. Six of those maps had
  baselines recorded at about 19 Hz, so verdicts against them were void, and
  every map's baseline ran a graph from before the #770 link repair. One
  e1m1 tape whose game clock ran 3 per cent slow under load was replaced, and
  e1m7 was run again after two drivers started it in the same run
  directories and cut the head off its tapes
  ([#819](https://github.com/saworbit/argus/issues/819)).

- Move the lab's lockfile off the yanked `yoke-derive` 0.8.3 to 0.8.4, a
  transitive dependency through `rmcp` and `url`, so `cargo install --locked`
  stops warning about it ([#807](https://github.com/saworbit/argus/issues/807)).

#### Security

- Fuzz the lab's three parsers of outside input: the protocol 15 demo
  reader, the BSP and PAK reader and the ARGLOG tape parser. Three cargo-fuzz
  targets in `tools/argus_mcp/fuzz` run weekly and by hand from a nightly
  `fuzz` workflow, seeded from committed tapes, LibreQuake's free maps and
  synthesised demos, never id Software content. A bounded mutation test
  carries the same never panic, never spin contract in the stable suite, and
  on its first run it found two defects, now fixed with regression tests: a
  PAK whose directory held a negative offset overflowed the bounds arithmetic,
  and a demo whose view yaw neared the float limit spun the aim-rate wrap
  forever, because subtracting 360 from such a value changes nothing
  ([#849](https://github.com/saworbit/argus/issues/849)).

- Install every Python package CI uses from a hash-locked file in
  `.github/requirements/` with `pip install --require-hashes`, transitive
  dependencies included. The perception copy must name exactly the frozen
  study pins, which stay byte-identical, and `argus_ci.py pins` fails on
  drift or on an install without hashes. Dependabot keeps the lint tools
  current and ignores numpy and scipy (#846).

- Pin every GitHub Action to a full commit SHA, stop checkouts persisting
  the job token, move workflow expressions out of shell scripts, give every
  job a timeout, and cancel superseded runs on pull requests only, so each
  main commit keeps its result. A new `lint` workflow gates every pull request
  on actionlint, a zizmor workflow security audit, schema checks for the
  Dependabot, issue form, discussion and citation files, critical Python
  lint and ShellCheck. CodeQL analyses the Rust lab, the Python tools, the GUI
  and the workflows; OpenSSF Scorecard publishes a score; dependency review
  checks every pull request; and `cargo deny` checks the lab's advisories,
  licences and sources weekly and on every manifest change. Dependabot now
  waits a week before proposing a new release
  ([#838](https://github.com/saworbit/argus/pull/838)).

- Stop Dependabot proposing bumps to
  `tools/requirements-perception-cohort.txt`. Its SHA-256 is registered in
  the engagement and lava cohort protocols and asserted before a cohort
  runs, so a bump would break reproduction of both studies; #838 had added
  a pip updater that opened one within minutes. The updater now ignores
  every dependency, security updates included, and an advisory against a
  pin still raises a Dependabot alert for a deliberate decision
  ([#840](https://github.com/saworbit/argus/pull/840)).

- Attach each release's signed provenance attestation as a release asset,
  `argus-<tag>.zip.sigstore.json`, beside the zip and its checksum, so the
  package can be verified offline. GitHub kept the attestation but not as a
  file, and OpenSSF Scorecard scored Signed-Releases at 0 for it
  ([#840](https://github.com/saworbit/argus/pull/840)).

- Check the local wizard Host header on GET requests as well as POST, so
  a DNS-rebinding page cannot read local paths or map data (#551).

- Require separate server-console keys for A/B snapshots and probe teleports;
  consume the A/B key after use. Update both lab callers and add a real-engine
  permission regression (#533). Document the tactical fixture's live-state
  changes and six-second bot freeze on shared servers (#540).

### 2026-10-22

**Added**

- **Combat:** Romero can fire a rocket, walk behind full-body cover and return
  from another angle on two authored routes in dm4 and dm2. Eligibility is
  limited to roster slot 1 at base skill 1 with a suitable loadout and safe
  approach. Normal reaction and aim error still apply.
  [#531](https://github.com/saworbit/argus/pull/531)

**Fixed**

- **Movement:** Tactical travel suppresses incompatible route jumps and drops,
  rejects unsafe incoming momentum, and brakes for up to 0.5 seconds when
  handing movement back. Emergency dodge and retreat can interrupt the handoff.
  [#531](https://github.com/saworbit/argus/pull/531)
- **Navigation:** Cancelling a search releases both its shared queue and the
  bot's shopping state. Failed-life avoidance runs after prerequisite weapon
  selection, and route cancellation clears pending jump/climb/drop state.
  [#531](https://github.com/saworbit/argus/pull/531)
- **Fixture reliability:** Overlapping trials are refused, temporary entity
  state is restored, and the stationary target no longer carries phantom
  knockback velocity. Damage checks exclude later ordinary-combat rockets.
  [#531](https://github.com/saworbit/argus/pull/531)

**Validation and remaining work**

- Passed **44 controlled trials** across dm4/dm2 at played cadence and 10 Hz,
  including 12/12 damaging stationary returns; 114 Python and 271 Rust tests
  passed. Normal smoke matches returned parity. The slow suite covers a
  focused subset of interruption cases.
  [Results and reproduction](docs/attack-cover-return.md#validation-record)
- Human frequency/readability, a reusable trial runner, unlimited-ammo shot
  observation and a dedicated goal-veto regression were follow-ups at this checkpoint.
  [Limits and issue links](docs/attack-cover-return.md#validation-record)
- The separate 0.60 adaptive-aim experiment remains deferred; the current
  share is 0.35. [#527](https://github.com/saworbit/argus/issues/527)

**Documentation**

- Put installation, everyday controls and the lab loop first in the README.
  Added focused control, lab, recording and architecture guides; aligned the
  plain-text quick start and support page. Clarified listen slots, roster
  permission, skill timing and camera actions.
  [#535](https://github.com/saworbit/argus/pull/535)
- Reorganised this log by date and change type, restored the missing v4.20
  and v4.21 build entries, and indexed earlier releases. Detailed historical
  notes and measurements are preserved in the [archive](docs/changelog-history.md).
  [#532](https://github.com/saworbit/argus/pull/532)

### 2026-10-21

**Fixed**

- **Reports:** Track names containing event words such as `lift` or `death`
  are parsed correctly. Python and Rust agree on samples and freeze counts;
  tactical phases and abort reasons are reported separately from hits.
  [#521](https://github.com/saworbit/argus/pull/521),
  [#522](https://github.com/saworbit/argus/pull/522)
- **Navigation tools:** Readers agree on link types, count door-only routes,
  and require both build registrations before calling a map registered.
  Invalid or cyclic BSP collision trees return solid.
  [#519](https://github.com/saworbit/argus/pull/519)
- **Benchmarks:** A task completed after its game-time budget is recorded as
  late, with its elapsed time retained, rather than counted as a success.
  [#518](https://github.com/saworbit/argus/pull/518)
- **Live lab:** Progress values strictly increase. Resource subscriptions
  detect meaningful match/session changes without repeatedly parsing the
  entire growing log. [#513](https://github.com/saworbit/argus/pull/513)

**Maintenance**

- Updated lab dependencies and adapted configuration handling to their types.
  [#509](https://github.com/saworbit/argus/pull/509)
- Documented shared navigation and report contracts, including their scoped
  parity checks. [#526](https://github.com/saworbit/argus/pull/526)

### 2026-09-21

**Added**

- **Repeatable measurements:** Fixed navigation benchmarks pin the graph and
  test declared routes. Within-match A/B runs compare two bots per arm and
  swap roster assignments to control for personality.
  [#497](https://github.com/saworbit/argus/pull/497),
  [#498](https://github.com/saworbit/argus/pull/498)
- **Movement comparison:** Compare bot movement with human references from the
  same map. Mixed-map sessions use only their dominant telemetry segment.
  [#494](https://github.com/saworbit/argus/pull/494),
  [#496](https://github.com/saworbit/argus/pull/496)
- **Background match tasks:** Compatible MCP clients can poll and cancel
  `match_run` tasks. Cancellation stops only that run's engine child and waits
  for finalisation. Older clients retain synchronous calls. Completed results
  expire after their retention window; lifecycle tests cover transport,
  shutdown and successor isolation.
  [#486](https://github.com/saworbit/argus/pull/486),
  [#487](https://github.com/saworbit/argus/pull/487),
  [#488](https://github.com/saworbit/argus/pull/488),
  [#489](https://github.com/saworbit/argus/pull/489),
  [#492](https://github.com/saworbit/argus/pull/492),
  [#493](https://github.com/saworbit/argus/pull/493)
- **Input discovery:** MCP catalogs expose map, run and baseline values;
  function/constant names complete from the current source index. An ambiguous
  default baseline can request a map from a supporting client.
  [#476](https://github.com/saworbit/argus/pull/476),
  [#477](https://github.com/saworbit/argus/pull/477),
  [#478](https://github.com/saworbit/argus/pull/478)

**Fixed**

- **Verdict safety:** Lab 0.30 identifies its build and checkout, and refuses
  quality verdicts when they disagree. Install the current server and restart
  the connected client to activate this protection; an older running server
  cannot enforce the new guard.
  [#500](https://github.com/saworbit/argus/pull/500)

### 2026-09-20

**Added**

- **Lab integration:** Long calls report progress, live resources publish
  changes, and core briefing tools return structured JSON/CSV. Tool safety
  annotations, operating prompts and name completion expose the existing
  workflow to MCP clients.
  [#455](https://github.com/saworbit/argus/pull/455),
  [#464](https://github.com/saworbit/argus/pull/464),
  [#467](https://github.com/saworbit/argus/pull/467),
  [#468](https://github.com/saworbit/argus/pull/468),
  [#474](https://github.com/saworbit/argus/pull/474),
  [#475](https://github.com/saworbit/argus/pull/475)
- **Graph history:** The mill identifies exact graph revisions, diffs and
  engine probe verdicts. [#445](https://github.com/saworbit/argus/pull/445)
- **Goal selection:** Bots remember one failed long item run after respawning
  and can choose a nearby fight or supplies instead of repeating it.
  [#436](https://github.com/saworbit/argus/pull/436)

**Fixed**

- **Short-match comparisons:** Baseline counts scale to candidate duration
  while preserving each source tape's duration for coverage calculations.
  Empty candidate lists are rejected.
  [#439](https://github.com/saworbit/argus/pull/439),
  [#442](https://github.com/saworbit/argus/pull/442),
  [#443](https://github.com/saworbit/argus/pull/443)
- **Lab installation:** The installed server lives outside Cargo's cleanable
  build directory. Migration and source-build CLI tests prevent stale binary
  paths from silently taking over.
  [#430](https://github.com/saworbit/argus/pull/430),
  [#432](https://github.com/saworbit/argus/pull/432),
  [#434](https://github.com/saworbit/argus/pull/434),
  [#444](https://github.com/saworbit/argus/pull/444)

**Maintenance**

- Pinned blocking CI to Ubuntu 24.04, enforced LF in committed text and added
  strict Clippy checks. Added parser/reach invariants and isolated Git test
  fixtures so parallel tests do not collide.
  [#447](https://github.com/saworbit/argus/pull/447),
  [#449](https://github.com/saworbit/argus/pull/449),
  [#451](https://github.com/saworbit/argus/pull/451),
  [#456](https://github.com/saworbit/argus/pull/456),
  [#459](https://github.com/saworbit/argus/pull/459),
  [#460](https://github.com/saworbit/argus/pull/460)

### 2026-09-19

**Changed**

- **Routing:** Bots share temporary warnings about recently failed places;
  item scoring uses the route they can walk. Protective powerups permit only
  the hazard step they cover, and graphs include static cover/exposure data.
  [#410](https://github.com/saworbit/argus/pull/410),
  [#411](https://github.com/saworbit/argus/pull/411),
  [#413](https://github.com/saworbit/argus/pull/413),
  [#414](https://github.com/saworbit/argus/pull/414)

**Fixed**

- **Map generation:** Over-budget graphs are refused before registration, and
  new maps must pass directed reach and real-engine link checks.
  [#421](https://github.com/saworbit/argus/pull/421),
  [#422](https://github.com/saworbit/argus/pull/422)
- **Tick classification:** Normal played-rate sampling jitter no longer splits
  equivalent tapes into different tick classes.
  [#415](https://github.com/saworbit/argus/pull/415)

### 2026-09-17

**Changed**

- **Combat:** Decisions account for the enemy's weapon, distance, height,
  splash hazards and nearby threats. Each bot has a continuous skill value;
  adaptive changes affect cognition more strongly than raw aim.
  [#408](https://github.com/saworbit/argus/pull/408),
  [#409](https://github.com/saworbit/argus/pull/409)
- **Jump approach:** Plain jump links carry a graph-validated approach speed
  based on their gap and landing runway. Unsupported cases retain the
  conservative launch gate. [#405](https://github.com/saworbit/argus/pull/405)

**Maintenance**

- Split CI into fast invariants and compilation/smoke checks. PR checks refuse
  an empty changed-file list rather than skipping evidence checks silently.
  [#401](https://github.com/saworbit/argus/pull/401),
  [#404](https://github.com/saworbit/argus/pull/404)

### 2026-09-16

- **Gameplay builds:** Shipped the wall-slide and typed-jump changes as v4.20
  and v4.21. See the build ledger below for their exact identities.
- **Combat and navigation:** Trace predicted rocket impact points before
  firing, and use typed door crossings on e1m5 and e1m6.
  [#391](https://github.com/saworbit/argus/pull/391),
  [#392](https://github.com/saworbit/argus/pull/392)
- **Lab and reports:** Added corpus queries, smaller responses, statistical
  intervals and stopping rules. The [detailed notes](docs/changelog-history.md#unreleased)
  retain the measurements, limits and rejected runtime collision approach.
  [#393](https://github.com/saworbit/argus/pull/393),
  [#394](https://github.com/saworbit/argus/pull/394),
  [#395](https://github.com/saworbit/argus/pull/395)

## Versioned builds

These are historical binary identities, not the current gameplay binary.

| Build | Date | Main change | Binary MD5 | Record |
|---|---|---|---|---|
| v4.21 | 2026-09-16 | Jump from the authored takeoff, align with the link and steer toward the landing | `E0A63B4D52ECB517BB6D6F814642CBA7` | [Ship #400](https://github.com/saworbit/argus/pull/400) |
| v4.20 | 2026-09-16 | Slide along walls while grounded | `923A233D328D07FE1E1CF878DB152898` | [Ship #398](https://github.com/saworbit/argus/pull/398) |
| v4.19 | 2026-09-16 | Remove the dm4 jump link that could not be crossed in its authored direction | `4A691E3CFCADE7EF2CA476955B44CBA7` | [Detailed notes](docs/changelog-history.md#v4-19) |
| v4.18 | 2026-09-16 | Stabilise aim across frame rates and keep firing when blocked at close range | `DE6E4B629B408F1EAE8E0274A1C1B66B` | [Detailed notes](docs/changelog-history.md#v4-18) |

The old log grouped later notes beneath v4.18 and did not identify individual
v4.10-v4.17 release boundaries. That material remains in the
[archive](docs/changelog-history.md#v4-18); no dates or build numbers have been
invented to fill the gap. Early tick-rate claims were corrected later:
the lab now requests the played rate, and verification measures actual cadence.

## Earlier builds

Each build links to its original notes, including evidence and reversions.
Ranges are kept where the original record grouped several builds together.

| Build / update | Recorded date | What changed |
|---|---|---|
| [v4.09](docs/changelog-history.md#v4-09) | 2026-09-05 | Fixed co-op collisions, embedding, repeated route failures and water exits; added forensic tools. |
| [v4.08](docs/changelog-history.md#v4-08) | 2026-09-03 | Cached nearby navigation and item lookups; improved lift pads, pickup claims and roster controls. |
| [v4.07](docs/changelog-history.md#v4-07) | 2026-08-29 | Audited frame-dependent movement. Its tick-rate interpretation was corrected in later notes. |
| [v4.06](docs/changelog-history.md#v4-06) | 2026-08-29 | Restored pickup chat when bots take a dropped Quad, not just the pedestal item. |
| [v4.05](docs/changelog-history.md#v4-05) | 2026-08-29 | Batched weapon, camera, combat, perception, economy and swimming fixes from v3.98 onward. |
| [v3.97](docs/changelog-history.md#v3-97) | 2026-08-28 | Fixed fourth-bot roster naming and completed the remaining tracker fixes. |
| [v3.96](docs/changelog-history.md#v3-96) | 2026-08-28 | Added engine-proven entry links to dm3 islets. |
| [v3.95](docs/changelog-history.md#v3-95) | 2026-08-28 | Fixed teleporter exit coasting, lightning depth and other tracked correctness defects. |
| [v3.94](docs/changelog-history.md#v3-94) | 2026-08-28 | Blended aim-offset changes to reduce abrupt angular flicks. |
| [v3.93](docs/changelog-history.md#v3-93) | 2026-08-28 | Added the run-up discipline needed to execute sprint-jump links. |
| [v3.92](docs/changelog-history.md#v3-92) | 2026-08-28 | Regenerated lqdm2 navigation with the modern graph pipeline. |
| [v3.91](docs/changelog-history.md#v3-91) | 2026-08-28 | Added post-kill spawn watching and resolved the first issue-tracker sweep. |
| [v3.90](docs/changelog-history.md#v3-90) | 2026-08-28 | Retyped the blocked dm2 grate-room crossings as jumps after engine probes. |
| [v3.89](docs/changelog-history.md#v3-89) | 2026-08-28 | Rebuilt dm6 navigation and repaired lab installation/configuration gaps. |
| [v3.88](docs/changelog-history.md#v3-88) | 2026-08-28 | Rebuilt dm2 navigation and restored lab operation after an audit. |
| [v3.87](docs/changelog-history.md#v3-87) | 2026-08-28 | Improved item seats, jump connections and vault behaviour from session feedback. |
| [v3.86](docs/changelog-history.md#v3-86) | 2026-08-28 | Introduced real-engine link probing and repaired a navigation pinch point. |
| [v3.85 + lab 0.22](docs/changelog-history.md#v3-85-lab-0-22) | 2026-08-28 | Added the protocol-15 puppet client for observing, walking and testing links. |
| [v3.84](docs/changelog-history.md#v3-84) | 2026-08-28 | Added human-trace link candidates and dm3 improvements; retained rejected experiments. |
| [v3.83](docs/changelog-history.md#v3-83) | 2026-08-28 | Required physical evidence before treating a bot as trapped. |
| [v3.82](docs/changelog-history.md#v3-82) | 2026-08-27 | Fixed wading-bank vaults and other dm3 session defects. |
| [v3.81](docs/changelog-history.md#v3-81) | 2026-08-27 | Reduced invisible-player glimpses and corrected movement/powerup handling. |
| [v3.80](docs/changelog-history.md#v3-80) | 2026-08-27 | Repaired dm3 directed connectivity, water routes and trapped spawn regions. |
| [v3.79](docs/changelog-history.md#v3-79) | 2026-08-27 | Enabled opponent-goal prediction and corner pre-fire at default skill 1. |
| [v3.78](docs/changelog-history.md#v3-78) | 2026-08-27 | Added one speculative corner rocket while pursuing a vanished opponent. |
| [v3.75-v3.77](docs/changelog-history.md#v3-75-v3-77) | 2026-08-27 | Added opponent-goal prediction, interception and related pursuit behaviour. |
| [v3.74](docs/changelog-history.md#v3-74) | 2026-08-27 | Added goal-decision traces and bounded unattended lab controls. |
| [Lab 0.21](docs/changelog-history.md#lab-0-21) | 2026-08-27 | Added staged-build warnings, harvest guards, paired-demo review and install helpers. |
| [Stack sweep](docs/changelog-history.md#stack-sweep) | 2026-08-27 | Fixed Windows console injection and extended demo/event inspection. |
| [Lab pipeline](docs/changelog-history.md#lab-pipeline) | 2026-08-26 to 2026-08-27 | Added demo ingestion, directed-reach audits and richer match briefs. |
| [v3.73](docs/changelog-history.md#v3-73) | 2026-08-26 | Used rocket splash to push grounded opponents toward nearby hazards. |
| [v3.72](docs/changelog-history.md#v3-72) | 2026-08-26 | Bent retreats toward reachable supplies and recorded human death events. |
| [v3.71](docs/changelog-history.md#v3-71) | 2026-08-21 | Added the optional classic-bot roster homage. |
| [v3.70](docs/changelog-history.md#v3-70) | 2026-08-21 | Reverted a regressed dm2 graph and added directed-reach checks. |
| [v3.69](docs/changelog-history.md#v3-69) | 2026-08-21 | Added high-ground responses and graph-authored sprint jumps. |
| [v3.68](docs/changelog-history.md#v3-68) | 2026-08-21 | Added cooldowns for repeatedly failing movement pads. |
| [v3.67](docs/changelog-history.md#v3-67) | 2026-08-20 | Added deliberate movement over drop lips. |
| [v3.66](docs/changelog-history.md#v3-66) | 2026-08-20 | Added pre-positioning at major items and human telemetry tracks. |
| [v3.65](docs/changelog-history.md#v3-65) | 2026-08-20 | Made long freezes and mover boarding visible to quality checks. |
| [v3.64](docs/changelog-history.md#v3-64) | 2026-08-20 | Fixed the west train boarding pad and combat-aware waits. |
| [v3.59-v3.63](docs/changelog-history.md#v3-59-v3-63) | 2026-08-20 | Added mid-fight item grabs, pickup hearing, gap prediction and shared routes. |
| [v3.58](docs/changelog-history.md#v3-58) | 2026-08-20 | Expanded major-item influence to encourage map-wide control circuits. |
| [v3.57](docs/changelog-history.md#v3-57) | 2026-08-20 | Made retreat seek actual cover rather than distance alone. |
| [v3.55-v3.56](docs/changelog-history.md#v3-55-v3-56) | 2026-08-20 | Scaled brink probes with speed and moved lift pads outside swept columns. |
| [v3.51-v3.53](docs/changelog-history.md#v3-51-v3-53) | 2026-08-19/20 | Improved lift waits, weapon hearing and spectator invisibility. |
| [v3.48-v3.50](docs/changelog-history.md#v3-48-v3-50) | 2026-08-19 | Added item clocks and missile dodging; fixed lift entity detection. |
| [v3.42-v3.47](docs/changelog-history.md#v3-42-v3-47) | 2026-08-19 | Fixed dm2 grates, stairs, doors, goal shelving and train boarding. |
| [v3.38-v3.41](docs/changelog-history.md#v3-38-v3-41) | 2026-08-19 | Added combat memory, corridor sampling and gunfire investigation. |
| [v3.36-v3.37](docs/changelog-history.md#v3-36-v3-37) | 2026-08-19 | Added typed doors, stable roster personalities and names with spaces. |
| [v3.27-v3.35](docs/changelog-history.md#v3-27-v3-35) | 2026-08-18/19 | Added spring aim, hearing, vendettas, denial and dm2 navigation fixes. |
| [v3.24-v3.26](docs/changelog-history.md#v3-24-v3-26) | 2026-08-18 | Removed bot autoaim; honoured invisibility, timelimits and player damage rules. |
| [v3.20-v3.22](docs/changelog-history.md#v3-20-v3-22) | 2026-08-18 | Added typed water exits, lift rides and rocket-jump entry links. |
| [v3.16-v3.19](docs/changelog-history.md#v3-16-v3-19) | 2026-08-17/18 | Introduced utility goals, prerequisite planning, projectile lead and hazard steering. |
| [v3.9-v3.15](docs/changelog-history.md#v3-9-v3-15) | 2026-08-17 | Added skill personalities, pursuit, chat, roster controls and baked skins. |
| [v3.2-v3.8](docs/changelog-history.md#v3-2-v3-8) | 2026-08-14/17 | Fixed weapon firing, pickups, death behaviour and stock-player physics parity. |
| [v3.1](docs/changelog-history.md#v3-1) | 2026-08-14 | Fixed human detection, scoreboard crashes and frequent dm4 lava deaths. |

## Maintaining this log

- Add a dated section at the top of **Main updates**, using the UTC merge
  date. Put new work under **Added**, **Changed**, **Fixed**, **Removed** or
  **Maintenance**; omit empty categories.
- Write one concrete result per bullet, name the affected component, and link
  the PR. Describe what a player or lab operator can now observe.
- Put test evidence and remaining limitations in separate bullets. State
  whether results establish smoke parity, controlled acceptance or human play
  quality; retain failed/reverted attempts in the detailed record.
- Add a numbered build to the ledger only when that build actually ships.
  Record its date, binary identity and source/PR reference. Lab versions
  continue in the operator guide.
- Keep logs, raw measurements and long investigations in linked documents.
  Preserve existing historical entries and anchors when moving material.
