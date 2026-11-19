# Played navigation elbow ladders

The control is main at `0ea1317`. The candidate adds the engine-probed
elbows on dm4 and e1m2. Both arms use the same dm2 graph. All 32 valid
tapes were recorded at the played rate and verified against the registered
build and graph. [Registration](https://github.com/saworbit/argus/issues/907#issuecomment-7001442246) · [Provenance correction](https://github.com/saworbit/argus/issues/907#issuecomment-7001558676)

| Map | Pairs | Stalls | Engagements | Lava deaths | Freezes | Hard gates |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| dm4 | 8 | 8 to 7.5 | 66.5 to 62.5 | 3.5 to 2 | 0 to 0 | Parity |
| dm2 | 5 | 27 to 30 | 33 to 38 | 0 to 0 | 0 to 0 | Parity |
| e1m2 | 3 | 38 to 19 | 12 to 18 | 0 to 0 | 0 to 0 | Parity |

The table uses the native control and candidate band medians.
Mean dm4 lava deaths per tape went from 3.25 to 2.5.
The registered lava gate passed with a mean change of -0.75 against the allowed increase of 2.1.

On e1m2, median route failures went from 5 to 4, and goals went from 8 to 10.
The goal pickup advisory compared representative tapes and flagged -41.2%. Door-related stall hotspots appeared three times in each arm's briefs.
The measured scope is this targeted splice.

The floor audit fell from 20 to 5 on dm4 and 41 to 30 on e1m2.
The native mill passed all 52 legs added to the two maps.
[Builds, tape hashes and gate results](../../runs/issue907-elbows-played.results.json)
