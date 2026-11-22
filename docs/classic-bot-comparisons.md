# Classic bot comparisons

[Architecture](architecture.md) | [Lab workflow](lab-workflow.md)

## Compare recorded movement

Run `argus-mcp classic-replay suite.json` on protocol 15 demos recorded on the
same map with matching engine, rules and observer setup. The command reads
the demos offline and prints a JSON scorecard. Paths are relative to the
manifest. Use `argus-mcp demo <stem>` to inspect player-model entity numbers
and confirm the subject and opponent in playback. Set each bot's version
and actual skill setting separately.

```json
{
  "map": "dm4",
  "engine": "QuakeSpasm 0.96.3, protocol 15",
  "rules": "deathmatch 1, skill set per mod, two bots, 5 minute limit",
  "perspective": "fixed observer at the same seat in both recordings",
  "recordings": [
    {"demo": "argus.dem", "bot": "Argus", "version": "build-id", "skill": "skill 1", "subject_entity": 12, "opponent_entity": 13},
    {"demo": "reaper.dem", "bot": "Reaper", "version": "v0.5", "skill": "documented mod setting", "subject_entity": 9, "opponent_entity": 10}
  ]
}
```

Read each observation in the order of the manifest. The report includes the
demo hash, recorded time, observed time, distance, sustained pauses and time
both entities were recorded within 256 units. Compare observed exposure
alongside each count. An entity can be absent from the demo while it is out
of the recorder's visibility. Proximity measures co-observation, and combat
or route claims still need their own evidence. Use the existing Argus gates
for Argus match telemetry.

## Capabilities

| Reference | Behaviour to compare | Argus status |
| --- | --- | --- |
| Omicron | Uses pickup sounds to locate opponents and can pursue through the waypoint graph. [Release notes](https://mrelusive.com/oldprojects/obots/skorpion/obots102/OBOTS.HTM) · [Sound model](https://mrelusive.com/oldprojects/obots/ObotDoc/sampling.htm) | Argus keeps two decaying opponent bearings and can take a checked waypoint leg towards a confirmed sighting or nearby shot. Effective stack and the opponent's recent pressure affect whether it retreats. |
| Reaper | The original Reaper learned maps during play. The Reaper-derived MRE adds weapon-specific sound investigation and adapts weapon preferences from past results. [Polge's archived v0.5 readme](https://github.com/Jason2Brownlee/QuakeBotArchive/blob/main/research/essays/b23_reaper.md#reaper-bot-v05) · [MRE source and feature notes](https://github.com/saworbit/mre) | On a BSP without a registered graph, Argus learns directed links from traversals. It distinguishes pickups from actual weapon fire and retains the more useful cue for pursuit. |
| FrikBot X | Uses player firing routines and reduced weapon switching in its v0.06 changes. Its dynamic waypoints and waypoint files support roaming and authored routes. [Source and release notes](https://code.nephatrine.net/QuakeArchive/frikbot/src/branch/master/frikbot) | Argus has dedicated lift, train, door and swim route actions. It infers those link types from live movement as well as using registered links. Actual firing and water state constrain weapon switching. |
| Frogbot | Scores paths with estimated time to the item and precomputes escape destinations. [Frogbot v2 technical notes](https://github.com/DrLex0/quake-frogbots/blob/master/doc/TechNotes.md) | Argus times nearby major respawns, incorporates observed portal travel and can gain speed through air acceleration on a checked runway. Mover travel time for item ordering remains open. [Argus route model](map-intelligence.md#timing-pickups-through-teleporters) |

## Combat trials

Repeat the neutral pickup, stock weapon fallback, corner investigation, combat
pickup expiry and two-portal cases with the private verifier.

```text
python tools/verify_adaptation.py --output backups/adaptation-check --prefix adaptation_check
```

The runner keeps the source and binary hashes and the native tape receipts for
dm2 and dm6. It also runs an ordinary dm6 arm and checks that comparing it with
the controlled dm6 tape refuses a gameplay verdict.

Loaded-switch cases use both stock maps. The super nailgun fires below the
230-unit splash boundary, then its animation stops as the bot selects rockets
above the boundary. Repeated crossings keep those choices. Depleted nails
select a firing super shotgun, and an unavailable rocket launcher leaves room
for the grenade launcher. An expired lightning burst selects rockets outside
the start range. Entering deep water cancels a live burst before the super
shotgun fires. All seven cases passed on both maps, so the policy stays as it is.

Pickup sounds previously inherited the weapon bit of the player who took
the item. An armour pickup could make a listener react as though it heard a
rocket or lightning attack. The first candidate took weapon cues from actual shots,
cleared remembered audio on respawn and allowed an equipped lightning gun
to hold out to 520 units. It passed the decision fixtures and exceeded the
played-rate stationary limit with a 12.1-second dm2 train wait. Follow-up
played-rate runs put the maximum at 9.1 seconds for the same candidate.

The isolated 520-unit weapon change recorded a 9.1-second freeze under
fire and a rescue warp on dm4. Both versions were set aside.

The retained change keeps the normal 480-unit selection range and extends
the release range to 500 units during an active burst. Empty cells and
unsafe water conditions still require an immediate weapon change. It passed
18 weapon checks on dm2 and dm3, including idle and expired bursts at the
original boundary. No bot froze or used a rescue warp in the six candidate
played-rate matches on dm3 and dm4. The short played-rate screen found
more engagements on dm4 and more goal pickups on dm3. Both changes were
within the detection limits of the fixed-seed screen. The candidate also
completed smoke matches on dm6 and e1m7.
[Fixtures and match results](../runs/classic-combat.results.json)

## Ten adaptability rounds

The control was `551c48049913`, which includes the earlier retreat supply,
lightning burst and teleporter timing changes. The combined build
`d6d11aafc80d` passed all 37 native decision checks on dm2, dm3 and dm6.
The control passed 16. Both arms used the same scene, item and target
positions in each fixture.

| Round | Decision or check | Result |
| --- | --- | --- |
| 1 | Direct pursuit checks the wall and floor along the line to the last confirmed position. | Passed on dm2 and dm6. |
| 2 | A blocked visual pursuit can take one short, ordinary waypoint leg with a clear opening to that position. | Passed on dm2 and dm6. |
| 3 | A pursuit detour yields to committed mover traversal, air control, a retreat and lower skill. The detour uses the sighting for steering and keeps speculative fire on the direct path. | Passed on dm2 and dm6. |
| 4 | A wall blocks a combat pickup diversion. | The bot chose the reachable health box over armour behind a wall on dm2. |
| 5 | A combat pickup gets a 1.5-second attempt. An expired target still present goes on cooldown and the bot can choose an alternative. | Passed on dm2 and dm3. |
| 6 | A fresh life clears pickup commitments and their clocks. Losing the combat target clears the current commitment. | Passed on dm2 and dm3. |
| 7 | Combat pickup ranking gives distance a cost. | The nearer health box beat more distant red armour on dm2 and dm3. |
| 8 | Active invulnerability prevents or ends low-stack retreat. | Passed on dm2 and dm3. The unprotected low-stack case still retreated. |
| 9 | A successful unconditional warp observed during a graph search is held for the next idle frame. | Passed on dm3 and dm6. The active search kept its previous estimate. |
| 10 | Screen the combined build on a stock rotation and repeat the dm4 lava comparison on fresh tapes. | 12 matched-seed tapes, 26 played-rate tapes and two smoke maps completed. |

Matched-seed dm3 and dm4 matches screened engagements, pickups and coverage.
Played-rate comparisons used three 60-second matches per arm on dm2, dm4 and
dm6, followed by four fresh 90-second dm4 matches per arm. The first dm4
screen recorded four candidate lava deaths and zero in the control. The
follow-up recorded one and two respectively. Both differences fell within
the lab's detection limits. The 13 played-rate candidate matches recorded
no freezes or rescue warps. dm3 and e1m7 also passed the smoke matrix.
These checks establish the decision changes and leave match-level gains
and direct comparisons with the reference bots unresolved.
[Decision checks and match receipts](../runs/ten-bot-rounds.results.json)

## Ten hearing and route-learning rounds

The control was `d6d11aafc80d`. The new build `d2a1ad76e9b2` passed
63 of 63 native decision checks on dm2, dm3 and dm6. The control passed 33.

| Round | Behaviour | Native check |
| --- | --- | --- |
| 1 | Keep pickups audible with a neutral weapon cue. | An actual armour touch supplies location and time on all three maps. |
| 2 | Classify the attack that fired. | A one-shell super shotgun and a one-nail super nailgun produce the single-shotgun and nailgun cues respectively. |
| 3 | Hear continuing nail fire. | The live animation emits a cue when it spends nails. An empty frame stays silent. |
| 4 | Follow the stock lightning sound cadence. | The start sound and an audible sustained frame register. The intervening frame leaves the cue alone. |
| 5 | Discard previous-life hearing. | A respawn clears the position, source, time and weapon cue. Peripheral acquisition requires a recorded sound time. |
| 6 | Give gunfire a short priority over loot. | A pickup preserves a shot less than 0.6 seconds old and replaces an older cue. |
| 7 | Investigate a nearby shot around a corner. | A fresh shot in the dm2 and dm6 corner scenes permits a safe waypoint leg while old shots, pickup sounds, warmup skill and committed movers decline it. |
| 8 | Finish a sound approach and resume the goal. | Arrival consumes the movement cue on dm2 and dm6. The remembered sound remains available for looking and the existing item goal is preserved during investigation. |
| 9 | Learn distinct portals used during one search. | On dm3 and dm6 both live links update when the search clears. Repeat uses and conditional gates leave the in-flight estimates alone. |
| 10 | Screen the combined build, with a longer dm2 repeat. | Matched-seed dm3 and dm4, played-rate dm2, dm4 and dm6, and smoke matches on dm3 and e1m7. |

The stock screen comprised 12 fixed-seed tapes, 24 played-rate tapes and
two smoke matches. The fixed dm4 screen recorded higher coverage, from
233.3 to 255.0 on average against a 20.0 detection limit. The played-rate
dm4 difference was within its detection limit. Across the played-rate
screens, changes in engagements, pickups, stalls and lava deaths were
within their detection limits.

The three fresh 120-second dm2 matches per arm reproduced the long wait
behind the earlier trial. Both builds recorded one freeze during a missed
train. The longest was 12.7 seconds in the control and 11.1 seconds in
the candidate. The control hop closed by deadline and the candidate hop
closed by abandon, with neither bot boarding. The candidate recorded
zero freezes under fire and zero rescue warps. The later train fix bounded
the displaced waits. [dm2 train boarding issue](https://github.com/saworbit/argus/issues/1003)
[Decision checks and match receipts](../runs/audio-adaptation.results.json)

## Map-agnostic adaptation pre-mortem

1. Reaper and FrikBot can roam using waypoints learned during play. Argus
   follows typed routes where a graph is registered. On a map without one,
   shopping has no start node and the bot falls back to wandering. Nearby
   pickups are the first test of whether bounded live geometry can improve
   that behaviour without spending edicts on speculative nodes.
2. Omicron uses observed and heard activity to locate opponents. Argus
   already ranks items by need and times their actual respawns, but its
   denial bonus uses opponents' live positions even when they are hidden.
   Treat fresh sightings and shots as evidence with a short expiry.
3. Frogbot prioritises estimated travel time in item routes. In combat,
   Argus already leads projectiles, compensates gravity and checks splash
   clearance. Its rocket and nail lead assumed the opponent stayed at the
   same range during flight. Measure the effect of correcting that
   estimate before revisiting grenade arcs or the splash constraints.

Any runtime graph must fit under the 600-edict cap and must not publish
routes before traversal proves them. Geometry checks for local shopping
need a fixed budget and a rescan interval. Changing a pickup each frame
would interfere with route ownership, so keep the current claim and
completion rules. Aim changes must preserve the final muzzle and movement
guards. Played cadence is observable in native receipts. It cannot
attribute CPU time to a QuakeC routine.

## Map-agnostic adaptation results

The candidate uses direct, checked approaches to live items on maps
without a registered graph in deathmatch 1. Each scan tests up to six
approaches within 240 units. It prioritises a usable weapon when unarmed,
shares the existing item claim and leaves an unsuccessful approach on
the bot's existing cooldown. Shopping resumes as the bot explores.
This extends first-load pickup behaviour. Multi-room navigation using
learned links remains open.

Two 40-second matches per arm and map ran at skill 2 and played cadence.
Both maps passed the native stall-parity gate. Pickups below count only
successful touches of the bot's selected goal.

| Map | Verified goal pickups, control to candidate | Mean stalls, control to candidate |
| --- | ---: | ---: |
| dm1 | 0 to 6 | 2.0 to 0.5 |
| dm5 | 0 to 8 | 13.0 to 10.5 |

The four candidate matches recorded no freezes, rescue warps or world
deaths. Smoke matches on start, e1m3 and e1m7 checked that the build ran
on further geometry. The private adaptation suite passed 77 checks
across dm2 and dm6. The added checks cover lead for closing, receding
and crossing targets, the expiry of denial evidence, and neutral
teleporter exit sounds that yield to recent shots.

On registered graphs, three 60-second matches per arm and map passed
the stall-parity gate on dm2, dm4 and dm6. Control build `9ca6ea0341b3`
and candidate `b46571398dc3` both ran at skill 2 and played cadence.

| Map | Verified goal pickups | Mean stalls | Mean speed (u/s) | Bot kills |
| --- | ---: | ---: | ---: | ---: |
| dm2 | 13 to 14 | 10.7 to 9.7 | 226 to 209 | 7 to 7 |
| dm4 | 27 to 28 | 1.3 to 2.3 | 232 to 221 | 19 to 22 |
| dm6 | 42 to 51 | 1.0 to 3.0 | 253 to 255 | 19 to 11 |

The nine candidate matches recorded no freezes or rescue warps. They
recorded two world deaths against zero in the control, including one
classified as lava on dm4. These short self-play bands leave a general
gain in fighting efficiency or movement speed unverified.

Two 120-second skill-1 dm4 stand-in matches per build estimated a
difference of +1.84 bot kills per minute in sight. The 95 per cent
interval was -36.41 to +40.08, so the threat direction is inconclusive.
Matched results against the classic bots are still needed.
[Classic replay suite](https://github.com/saworbit/argus/issues/1079)

## Runtime navigation and duel decisions

Three bottlenecks drove this pass. A BSP without a registered graph left
bots repeatedly trying direct lines to blocked items. Fixed weapon bands
and torso lead left damage on the table near lips and on uneven floors.
Single-cue attention and current-item utility made it easy to miss a
second opponent or a major pickup about to return. These are the areas
where the runtime adaptation of Reaper, movement coverage of FrikBot,
stack decisions of Omicron and movement and item control of Frogbot are
the relevant benchmarks.

The main risks were exhausting edicts when exploration kept adding seats,
spending the frame on geometry queries, and changing goals or weapons
more often than a bot could execute them. Sampling is throttled, query
distance is bounded, and graph growth stops while the route queue is
working. Item scans have a cooldown and respect claims. Weapon scoring
favours the currently firing gun when its score is close, and an unsafe
explosive shot temporarily suppresses that choice.

Maps without a registered graph can learn one from bot and player
movement. Existing maps can exercise the same learner with developer
`scratch3 641` before the map loads. A grounded position becomes a seat
after the actor moves far enough to warrant a new one. Three clearance
rays and floor samples validate ordinary walks. Airborne transitions can
produce directed jump and drop links. The learner also accepts a live
unconditional warp, an observed mover ride, a dry exit from water and
recent door or button activation as traversal evidence.

The graph uses the existing route queue and item claims. It limits
itself to 104 seats, keeps room below the 600-edict budget and waits
until the queue is idle before adding links. Failed route actions
temporarily block the observed edge. The current walk and jump
recovery remains available. A learnt grenade-assisted escape and
replacement of seats in a full graph remain open.

On a dry, checked straightaway, a short hop retains horizontal velocity
and steers just off perpendicular to gain speed through air acceleration.
The launch requires a checked runway and overhead clearance. Route
actions, water, combat and deliberate waits have priority over these
hops. The ammo and range scorer uses actual own inventory, recent
damage to a visibly tracked target and the predicted blast position.
The blast guard computes armour absorption and health damage before
ordinary firing. A bouncing grenade can still land somewhere other
than the predicted impact.

Bots keep two recent opponent bearings in existing player edicts.
Confirmed sightings, audible activity and the location of the damage
inflictor refresh those bearings. A bearing can turn the bot towards
a threat. Firing still needs the visibility and muzzle checks. A major
pickup keeps the stock item's respawn schedule. The healthy bot can
interrupt a minor direct errand for a nearby major that will return
in three to five seconds, if its own path and the claim check pass.
This uses the actual armour and powerup intervals for the mod, including
Megahealth's delayed timer after decay.

`tools/report_architecture.py` reads accepted major pickups and actual
self-damage from the tape. In counterbalanced trials, major item share
uses the combined pickups of both arms as the denominator. A missing
share means neither arm picked up the item. Engine host timing measures
whole-server pacing, including the timing of the harness. Per-routine
QuakeC CPU cost remains unmeasured.

### Graphless checks

The held-out `lab_jumpgap` BSP has no dispatched graph. The release build
reported at least 64 seats on each first load, with 94 and 96 live edicts
at those samples. The tapes witnessed walk links and a directed drop.
They did not witness a crossing of the gap. The native fixture proves
the directed drop and a real trigger warp in controlled placements.
Lift, train and door inference still need witnessed route completion on
an unregistered stock or custom BSP.

The first combined build failed the dm5 stall-parity gate with 32 stalls
across two 40-second tapes, against 10 for the control. Most of the
failures were in water. Holding a clear swim heading and taking a checked
direct pickup before requesting a learned route brought the follow-up to
15 stalls. The selected native gate passed on that dm5 follow-up.

### Counterbalanced dm6 trial

The native `within-ab` runner swaps which two of four slots use the new
duel policy and holds the graph, item logic and program binary fixed.
Cross-arm kills are its primary outcome. Kills and deaths in the table
also include same-arm fights and self deaths. The control here is the
paired policy path inside the release binary. The independent match
ladder below uses `121c714` as its control.

| Pair | Candidate vs control cross-arm kills | Candidate vs control K/D | Candidate minus control speed (u/s) | Candidate vs control self-damage (HP) |
| --- | ---: | ---: | ---: | ---: |
| Release pair 1 | 17 to 5 | 22/10 to 12/24 | -13.3 | 54 to 37 |
| Release pair 2 | 4 to 15 | 13/24 to 21/10 | -0.3 | 84 to 13 |
| Four 95-second matches | 21 to 20 | 35/34 to 33/34 | -6.8 | 138 to 50 |

The two pairs' 95 per cent log-strength intervals were 0.20 to 2.12 and
-2.29 to -0.19. The direction reversed on the same binary. Earlier
90- and 120-second pairs on development builds finished 9 to 10 and 13
to 13. The evidence leaves a sustained dm6 combat advantage unproven.

Across the four release matches, the candidate took 7 of 10 red armours
(70%), 4 of 8 Megahealths (50%) and 10 of 23 rocket launchers (43%). It took
one of two lightning guns. Neither side took yellow armour or Quad. No
bot pre-empted a goal through the new contest policy in these dm6 tapes.
The fixture demonstrates the decision under controlled placement.

### Independent match ladder

The control was `121c714` with pickup and damage receipts added. The
release build was `c03df079392d`. Each arm ran two 40-second skill 2
matches per map on QuakeSpasm 0.97.0 at a requested 0.0139-second tick.
The columns report control to release, and the totals describe all bots
in each match. Major pickup entries are accepted touches in RA, YA, MH,
RL, Quad order. Head-to-head item shares use the counterbalanced results
above.

| Map | Kills/deaths | Mean speed (u/s) | Stalls | Goal pickups | World deaths | Self-damage (HP) | Major pickups |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dm1 | 5/5 to 7/7 | 247.9 to 267.7 | 4 to 1 | 17 to 16 | 0 to 0 | 0 to 0 | 0/0/0/0/0 to 0/0/0/0/0 |
| dm2 | 0/0 to 3/3 | 219.7 to 219.3 | 14 to 12 | 7 to 7 | 0 to 0 | 0 to 0 | 0/3/0/2/0 to 0/2/0/0/0 |
| dm4 | 7/8 to 10/10 | 223.1 to 240.8 | 2 to 0 | 10 to 11 | 1 to 0 | 140 to 203 | 2/0/2/6/0 to 1/0/2/4/0 |
| dm5 | 6/6 to 6/6 | 185.1 to 156.9 | 10 to 18 | 17 to 8 | 0 to 0 | 0 to 0 | 0/2/0/0/0 to 0/2/0/0/0 |
| dm6 | 9/9 to 8/8 | 257.1 to 263.0 | 5 to 0 | 19 to 22 | 0 to 0 | 0 to 36 | 1/0/1/5/0 to 4/0/2/5/0 |
| lab_jumpgap | 21/21 to 18/18 | 273.7 to 278.1 | 0 to 2 | 23 to 12 | 0 to 0 | 0 to 0 | 0/0/0/0/0 to 0/0/0/0/0 |

All six comparisons passed the selected native stall-parity gate. The
raw dm5 stall flag still fired. Its median of nine was inside the
control band of zero to twelve, and the speed and pickup losses make
water traversal a remaining weakness. The release tapes recorded 21
momentum hops, zero freezes, and zero world deaths. Per-tape server
frame p95 was 15 to 16 ms in both arms. The largest frame was 114 ms in
the control and 66 ms in the release arm. These are short match samples
under the same nominal dedicated cadence.

The NetQuake build compiled with zero warnings. The adaptation fixture
passed 46 checks each on dm2 and dm6. The tactical suite passed 15 cases
each on dm2 and dm4. The private muzzle, combat, button, door and health
checks also passed. These checks establish behaviour within Argus.
Matched recordings against Reaper, Omicron, FrikBot and Frogbot remain
necessary to establish relative performance.

### Ordinary pickups through timed switches

The last switch fix in [#1084](https://github.com/saworbit/argus/pull/1084)
allows for the turn into the switch approach and honours a confirmed touch
at the deadline. A full-rate diagnostic took 1.534 seconds from switch
selection to confirmed departure, beyond the previous 1.3-second budget.

Nine ordinary 60-second, skill-2 dm5 matches from stock spawns on build
`dde73b1bd8b9` recorded 10 accepted rocket launcher touches across all nine
matches. Against nine matches on `7288ada99e93`, first post-switch stalls
fell from one to zero and total stalls fell from 60 to 53. The median stayed
at six and passed the native stall-parity gate. Three e1m4 matches per arm
also passed stall parity, with medians of three and four. Weapon engagements
on e1m4 were an advisory flag, with medians of one and zero.

The lesson from the final ladder is specific to the switch approach and
departure. The dm5 armour approach clustered more stalls in the candidate
and remains under investigation. The final sample is an automated stock-map
check, with human play and matched classic-bot comparisons still open.
[Armour approach follow-up](https://github.com/saworbit/argus/issues/1083) |
[Matched recordings](https://github.com/saworbit/argus/issues/1079)

## Two-leg pursuit evaluation

`tools/verify_pursuit_two_leg.py` builds a private program with the current
one-leg search and an optional two-leg fallback. The fallback takes the
existing cue and uses ordinary links with dry floor, clear traces and a
350u total path limit. The fixture seats the actual bot on stock geometry
and runs the production noise and movement code until the cue releases.
An old cue, a novice bot and a committed train hop each decline steering.

On dm2, the one-leg control declined the occluded cue. The fallback
steered the bot for about 1.3 seconds, reached within 80u of the cue and
released steering. Every sample kept the original goal and dry feet.
Both arms declined the scripted dm4 case.

Two ordinary cohorts each recorded two 90-second pairs per map at 14 ms
frame intervals. Neither dm2 cohort exercised the search. The control had
zero rapid flip runs there and the candidate had one across both cohorts.
On dm4, control and candidate counts were five and two in the first cohort
and five and three in the repeat. One pursuit episode in each cohort
exercised the fallback, with five and thirteen search calls respectively.
Neither episode had a rapid flip for the pursuing bot in the measured
window. The sampled episodes are too few for a gameplay adoption verdict.
The prototype stays in the private verifier.
[Two-leg evaluation](https://github.com/saworbit/argus/issues/1007)

Run the verifier with `--output backups/pursuit_trial --prefix pursuit_trial`.
Add `--played` to record the longer match pairs with bot and time markers.
The output retains the build, source and tape identities.

## Learned graph knitting and the dodge side

### Bottlenecks

1. Learned graphs starve on first load. On dm1 and dm5 the learned
   graph reached its fixed 104-seat ceiling within about 40 seconds, at
   about 170 of 600 edicts, and learned nothing more for the rest of the
   match. Before that, links joined only consecutive seats along one
   actor's path, and an item could end a route only when a seat already
   sat within 72 units of it. Bots spent 70 to 90 per cent of their
   samples wandering, against 22 per cent on the registered dm4 graph.
   FrikBot and Reaper avoid this by linking each dropped waypoint to the
   waypoints around it.
   [Learned graph issue](https://github.com/saworbit/argus/issues/1093)
2. The missile dodge steps across the shot. Both dodge loops tried the
   side left of the shot first and kept it whenever it was clear, so a
   bot standing right of the track stepped into the blast. The grenade
   loop's own comment said to step away from its track. The fix is
   proven by fixture and not yet adopted (below).
   [Dodge issue](https://github.com/saworbit/argus/issues/1094)
3. The lab cannot see the interpreter budget. Every bot runs inside one
   `StartFrame` call. id's interpreter stops a call after 100000
   statements, and QuakeSpasm allows 16777216, so a frame that would end
   a server on the original engine passes every lab gate.
   [Runaway limit issue](https://github.com/saworbit/argus/issues/1091)

The previous pass already covers the remaining items in the brief:
closing-range lead, gravity on airborne targets, lead clipping at walls,
foot splash and grenade loft (`Argus_Combat`), effective-stack retreat
and cover legs, respawn clocks for majors (`Argus_GoalOK`,
`Argus_MajorTiming`), sound and damage bearings (`Argus_ThreatMark`),
momentum hops on checked runways and rocket-jump links. Their
graveyards (range fighting, pit-adjacent fear, unhurried shopping) are
recorded beside the code and were not retried.

### Pre-mortem

- Edicts. A larger learned graph could crowd out projectiles, gibs and
  backpacks. The existing guard refuses a seat once 456 edicts are
  allocated, and the new ceiling of 224 seats matches the size of the
  authored graphs the router already runs.
- Frame budget. Each new loop has a fixed bound per frame: one knit
  with at most eight neighbour tests, and at most six item seat scans.
  Nothing measures statements per call yet, so the bounds are the
  safeguard (#1091).
- False links. A knitted link passes `Argus_LiveWalk` in its own
  direction, the same test that already mints a traversed seat's reverse
  link. Wet seats are left to traversal. A link that fails a route is
  cooled by `Argus_LiveNavReject` as before.
- Slot starvation. Typed evidence (drop, jump, portal, mover, door,
  swim) comes only from traversal, so knitting stops at six of a seat's
  eight link slots.
- Oscillation. More links give more alternative routes. The router
  still takes the fewest hops and plans only at goal selection, so a
  denser graph does not change goals between frames.
- Dodge near brinks. Both sides already pass the same hazard and
  clearance probes; only the order changes. It is gated at skill 2 and
  up so the skill 1 dodge that the human sessions calibrated is
  unchanged.

### What changed

`Argus_LiveKnit` links each new seat to up to eight nearby seats on the
same level, one direction at a time, when `Argus_LiveWalk` passes. The
seat ceiling is `AL_SEAT_CAP` (224), still behind the 456-edict guard.
`Argus_LiveItemSeat` scans at most six unseated items a frame.
`ARGUS live graph status seats <n> links <n> items_seated <n> of <n>`
reports the graph every ten seconds on any map running the learner.

The dodge fix is on the local branch `feat/dodge-away-from-track`, not
on this one, until a longer ladder clears it (results below).
`Argus_DodgeAway` there chooses the first dodge side from the sign of
the bot's lateral offset from the shot's track, at skill 2 and up and
only beyond 4 units from the track. Both dodge loops keep their
fallback.

A third candidate was laddered and dropped: seating a nearby unseated
item from the actor's seat. It made more items routable and lowered
goal-to-touch conversion on five of six maps (dm1 0.57 and 0.68 to
0.42 and 0.40), with no gain in total pickups.

### Results

All arms ran at skill 2, 90 seconds, at the played rate (every tape
listen class), on `run_map_intelligence.py` private game directories,
against `origin/main` at `e7433e3` unless noted. Two tapes per arm and
map unless noted. Every native band card below read parity.

Graphless stock maps, knit, ceiling and scan budget only. Batch 1 ran
against the earlier base `31b4663`, batch 2 against `e7433e3`; each
cell is control to knit.

| Map | Batch | Verified pickups | Total pickups | Routes | Stalls | Kills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dm1 | 1 | 20.5 to 24.5 | 30.0 to 36.5 | 36.5 to 48.5 | 5.5 to 2.0 | 6 to 10 |
| dm1 | 2 | 23.0 to 13.0 | 39.0 to 29.5 | 43 to 39 | 2.0 to 2.5 | 11 to 8.5 |
| dm5 | 1 | 15.5 to 15.5 | 36.0 to 28.5 | 16 to 23.5 | 13 to 10.5 | 5.5 to 7.5 |
| dm5 | 2 | 14.5 to 14.5 | 30.0 to 30.5 | 18 to 34.5 | 10 to 9.5 | 4.5 to 4 |
| e1m3 | 1 | 13 to 18.5 | 17.0 to 20.0 | 19 to 22.5 | 2.5 to 5.5 | 4 to 2 |
| e1m3 | 2 | 21.5 to 15.5 | 24.0 to 15.5 | 35 to 17 | 12 to 4.5 | 3 to 2 |
| e1m4 | 1 | 4 to 3.5 | 4.0 to 3.5 | 3.5 to 5 | 3.5 to 4.5 | 0 to 0 |
| e1m4 | 2 | 4 to 4 | 4.5 to 4.0 | 9.5 to 3.5 | 2 to 3 | 1.5 to 0.5 |

The two batches disagree in direction on dm1 and e1m3, and the
control-to-control spread between them (e1m3 13 against 21.5) is as
large as any difference. Pooled over four tapes per arm, verified
pickups are dm1 21.75 to 18.75, dm5 15.0 to 15.0, e1m3 17.25 to 17.0
and e1m4 4.0 to 3.75: parity. The graph grew past the old ceiling in
all 35 candidate tapes (107 to 212 seats at 90 seconds, against 104
by about 40 seconds).

The learned graph on dm4 and dm6, with `--cvar scratch3=641` so the
same geometry can be judged against the authored graph:

| Map and arm | Tapes | Verified pickups | Routed goals picked up | Stalls | Kills |
| --- | ---: | ---: | --- | ---: | ---: |
| dm4 control | 2 | 23.0 | 6/20, 6/31 | 1.5 | 10.5 |
| dm4 knit only | 2 | 30.0 | 15/35, 14/23 | 3.0 | 6.0 |
| dm6 control | 5 | 30.8 | 49/143 (34%) | 1.0 | 6.4 |
| dm6 knit only | 2 | 22.5 | 21/67 (31%) | 3.0 | 5.5 |
| dm6 knit, item seats, dodge | 5 | 26.6 | 73/194 (38%) | 4.0 | 6.4 |

On dm4 the knit roughly doubled the routed errands that ended in a
pickup. On dm6 the candidate routed a third more often and finished a
slightly larger share of routed errands, but took fewer direct pickups
on the way, so its total fell. The first two tapes of every dm6
candidate arm read low (22 and 23) before three replicas returned 27,
29 and 32 against control's 31, 28 and 29.

The knit removes the ceiling that froze the learned graph and connects
its chains, and no native card failed it. A gain in self-play pickups,
kills or stalls is not established: it reads better on learned dm4,
slightly worse on learned dm6 and at parity on the graphless maps, at
two to five 90-second tapes per arm. Two limits apply to every row. In
self-play the item supply is shared, so better routing can move a
pickup from one bot to another without adding one. And 90 seconds is
too short for the ceiling, which costs the control most in the minutes
after it binds.

The dodge, on the registered graphs where the learned graph never
runs, so only the dodge differs. Means per tape, control to dodge:

| Map | Tapes | Verified pickups | Stalls | Kills | World deaths | Freezes | Self-damage outside rocket jumps (HP) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dm2 | 8 | 8.5 to 8.6 | 17.4 to 15.5 | 3.5 to 4.0 | 0.6 to 0.4 | 0.4 to 0.1 | 10.0 to 7.8 |
| dm4 | 5 | 11.4 to 15.2 | 4.8 to 3.8 | 9.4 to 8.8 | 0.4 to 1.0 | 0 to 0 | 25.2 to 25.2 |
| dm6 | 2 | 21.5 to 21.5 | 1.5 to 2.0 | 7.5 to 5.5 | 0 to 0 | 0 to 0 | 30.5 to 50.5 |

dm2 shows why its tapes are read in fives: after five tapes the dodge
arm's stalls ran 18.8 against 12.8, and the next three ran 8, 10 and 12
against control's 27, 25 and 23. The screen registered before reading
the pool still failed twice. dm4 world deaths were 5 against 2, all at
the lava pit floor after route, abandon and cover-retreat events, and
one dm2 tape held an 11.6-second freeze under fire at the chronic
(2002 -1109 344) deck cell, where control froze for 6.7 seconds.
Neither is attributed to the dodge, which is not logged as an event,
but neither is excluded, so the change waits for a longer ladder. In
self-play every bot gets the better dodge, so kills cannot show an
individual gain, and the counterbalanced runner cannot isolate one
feature from the earlier `Argus_Advanced ()` package (#1092). The
fixture establishes the decision itself: 52 checks pass on dm2 and
dm6, and the previous code fails both right-of-track cases.

### Still open

- A full graph, and water. 224 seats were not reached in 90 seconds;
  seat recycling for long matches on large maps is unbuilt, and wet
  seats are never knitted, so dm5 and e1m4 still spend 73 to 92 per
  cent of their samples wandering.
  [Recycling and water issue](https://github.com/saworbit/argus/issues/1096)
- No brief reads the learned graph, which is why the 104-seat freeze
  went unnoticed.
  [Learned graph brief issue](https://github.com/saworbit/argus/issues/1095)
- Routed errands that are replaced before pickup on tight maps such as
  dm6, and longer matches than 90 seconds.
- Statements per `StartFrame` call (#1091), a within-ab trial scoped to
  one feature (#1092), and matched recordings against the classic bots
  (#1079).

## Comparison method

Controlled native fixtures exercise the production armour touch, attack
and respawn reset alongside the ordinary weapon selector. The early combat
screen used the retreat supply build as its control. The two ten-round
screens used the previous development build named in each study. All three
used skill 1.

The private decision runner marks its tapes so the gameplay gates refuse
them. It also covers switching among several loaded weapons.
[Fixture runner and quarantine](https://github.com/saworbit/argus/issues/1004),
[loaded weapon selection](https://github.com/saworbit/argus/issues/1005)

A cross-bot replay comparison needs the same maps, rules and recording
perspective, with each bot's version and skill recorded.
[Replay comparison issue](https://github.com/saworbit/argus/issues/998)
