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
| Development source | Water/action execution and lift-progress recovery restore e1m5 contact in the eight-map comparison; perception, target attention and earlier release gates remain in development; no deployment |
| Latest gameplay update | 2026-10-22, [#531](https://github.com/saworbit/argus/pull/531): attack, cover and return on dm4/dm2 |
| Gameplay binary | `game/argus/progs.dat` and `engine/argus/progs.dat`; MD5 `A3F7AA9428846DE7F7B327506F5F5D3D` |
| Last explicitly numbered build | v4.21, 2026-09-16; subsequent changes are recorded by merge date below |
| Lab version | 0.30; [operator guide and version history](tools/argus_mcp/README.md#versions) |

Main-update dates are UTC merge dates. Numbered builds retain their recorded
build dates. A merged change does not imply a new numbered release, and a
passing botmatch does not establish better human play.

## Main updates

### Unreleased

#### Added

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

- Synchronise root status, contributor checks, the tool index, telemetry and
  runbooks with the broader-map studies and 19 private fixture variants.
  Track remaining map, movement, reporting and test-coverage gaps in
  [#622–#629](docs/mover-intelligence.md#tracked-follow-ups).

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

#### Security

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
