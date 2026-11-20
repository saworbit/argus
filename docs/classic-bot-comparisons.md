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
| Omicron | Uses pickup sounds to locate opponents and can pursue through the waypoint graph. [Release notes](https://mrelusive.com/oldprojects/obots/skorpion/obots102/OBOTS.HTM) · [Sound model](https://mrelusive.com/oldprojects/obots/ObotDoc/sampling.htm) | Argus can take one safe waypoint leg around a corner towards a last confirmed sighting or a nearby, fresh shot. Longer pursuit routes remain open. |
| Reaper | The original Reaper learned maps during play. The Reaper-derived MRE adds weapon-specific sound investigation and adapts weapon preferences from past results. [Polge's archived v0.5 readme](https://github.com/Jason2Brownlee/QuakeBotArchive/blob/main/research/essays/b23_reaper.md#reaper-bot-v05) · [MRE source and feature notes](https://github.com/saworbit/mre) | Argus assesses heard gunfire using its own health and armour, distinguishes pickups from weapons, and gives a fresh shot priority. It uses an offline graph and a local recovery layer when it has no useful route. |
| FrikBot X | Uses player firing routines and reduced weapon switching in its v0.06 changes. Its dynamic waypoints and waypoint files support roaming and authored routes. [Source and release notes](https://code.nephatrine.net/QuakeArchive/frikbot/src/branch/master/frikbot) | Argus hears the actual stock firing routine, including a fallback shot or a continuing nail or lightning burst. An active lightning burst can continue through small changes in range. Wider weapon-selection comparisons need cases with several viable loaded weapons. |
| Frogbot | Scores paths with estimated time to the item and precomputes escape destinations. [Frogbot v2 technical notes](https://github.com/DrLex0/quake-frogbots/blob/master/doc/TechNotes.md) | Argus checks live cover during retreats and weighs nearby supplies against distance. Confirmed portals inform pickup respawn timing. The next idle graph frame applies observations of distinct portals used during a search. Mover arrival and travel time for route ordering remain open. [Argus route model](map-intelligence.md#timing-pickups-through-teleporters) |

## Combat trials

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
zero freezes under fire and zero rescue warps. The train boarding claim
remains open. [dm2 train boarding issue](https://github.com/saworbit/argus/issues/1003)
[Decision checks and match receipts](../runs/audio-adaptation.results.json)

## Comparison method

Controlled native fixtures exercise the production armour touch, attack
and respawn reset alongside the ordinary weapon selector. The early combat
screen used the retreat supply build as its control. The two ten-round
screens used the previous development build named in each study. All three
used skill 1.

The private decisions still need a maintained runner with a fixture marker.
Further gameplay cases cover switching among several loaded weapons and
pursuit around more than one corner.
[Fixture runner and quarantine](https://github.com/saworbit/argus/issues/1004),
[loaded weapon selection](https://github.com/saworbit/argus/issues/1005),
[multi-corner pursuit](https://github.com/saworbit/argus/issues/1007)

A cross-bot replay comparison needs the same maps, rules and recording
perspective, with each bot's version and skill recorded.
[Replay comparison issue](https://github.com/saworbit/argus/issues/998)
