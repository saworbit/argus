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
| Latest gameplay update | 2026-10-22, [#531](https://github.com/saworbit/argus/pull/531): attack, cover and return on dm4/dm2 |
| Gameplay binary | `game/argus/progs.dat` and `engine/argus/progs.dat`; MD5 `1B17C38CE8053E713112CCF2D1EA4F7C` |
| Last explicitly numbered build | v4.21, 2026-09-16; subsequent changes are recorded by merge date below |
| Lab version | 0.30; [operator guide and version history](tools/argus_mcp/README.md#versions) |

Main-update dates are UTC merge dates. Numbered builds retain their recorded
build dates. A merged change does not imply a new numbered release, and a
passing botmatch does not establish better human play.

## Main updates

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
  observation and a dedicated goal-veto regression remain follow-ups.
  [Limits and issue links](docs/attack-cover-return.md#validation-record)
- The separate 0.60 adaptive-aim experiment remains deferred; the current
  share is 0.35. [#527](https://github.com/saworbit/argus/issues/527)

**Documentation**

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
