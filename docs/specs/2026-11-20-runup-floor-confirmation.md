# Staged jump run-up floor check

On dm4, bots lining up the jump from n111 to n115 can run off the walkway
and continue steering for the jump from the room below. The run-up now
refuses a drop of more than one step while a grounded bot lines up an
ordinary staged jump in phase -1 or 1. The charge and airborne motion use
their existing checks.

The [registered comparison](https://github.com/saworbit/argus/issues/867#issuecomment-7023490893)
used 24 dm4 pairs at the played rate and a five-pair dm2 guard rung, skill 2
and 185 seconds per tape. Both arms used the shipped graphs. The control
build was `1129a18536ba` and the candidate was `efe96adc21bb`. All 58 tapes
passed the map, build, graph and cadence checks.

The dm4 room spans x 690 to 1060, y -700 to -390 and z -160 to -90.
Routed time there averaged 18.32 seconds on the control and 5.73 on the
candidate. The reduction of 12.59 seconds exceeds the registered
8.82-second detection limit. Room overhead-target wall re-entries fell
from 7.54 to 0.04 per tape.

| Map | Guard | Control mean | Candidate mean | Detection limit |
| --- | --- | ---: | ---: | ---: |
| dm4 | Stalls | 6.54 | 8.58 | 4.61 |
| dm4 | Lava deaths | 2.25 | 2.08 | 1.21 |
| dm4 | World deaths | 2.25 | 2.08 | 0.88 |
| dm4 | Freezes | 0.00 | 0.04 | 0.57 |
| dm4 | Goal pickups | 22.92 | 20.38 | 4.11 |
| dm2 | Stalls | 26.60 | 20.60 | 34.71 |
| dm2 | Lava deaths | 0.40 | 1.00 | 2.44 |
| dm2 | World deaths | 0.40 | 1.00 | 2.44 |
| dm2 | Freezes | 0.80 | 0.00 | 1.59 |
| dm2 | Goal pickups | 9.20 | 12.00 | 5.14 |

All five guards held on both maps. The [earlier eight-pair result](2026-11-18-runup-floor-protocol.md)
is retained as recorded.

The QuakeSpasm fixture starts a player hull at n111 and confirms there is
dry floor 128 units below its probe. The control allows the step in both
run-up phases. The candidate vetoes those two cases. The charge, ordinary
movement, airborne and level-floor cases remain allowed.

```text
python tools/verify_runup_floor.py --output backups/runup-floor-check --prefix runup_floor_check
```

[Per-tape readings and identities](../../runs/runup-floor-confirmation.results.json).
