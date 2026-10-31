# e1m6 docking and continuing-route decisions

[Machine-readable evidence](../runs/e1m6-decisions.results.json) |
[Earlier mover investigation](mover-intelligence.md) |
[Water/action execution](e1m5-encounters.md)

## Decision failure and repair

The unchanged controller boards e1m6's upper platform but releases its ride
hold when the exit comes within 40 units of its height. The slab is still
moving. At the top, the walking hazard guard repeatedly deflects around the
exit seam instead of crossing it. The bot circles on the slab, reaches its
lift deadline and discards the continuing route. This reproduces at played
cadence; the 100 ms control already succeeds. Static directed reach alone
does not establish that the controller can execute this transfer.

The repair keeps the ride hold while the bot is actually grounded on a
moving platform. At the dock, a blocked step can become a jump only if the
existing gravity-aware arc test predicts a dry, shallow landing on the
routed exit's floor. The heading must be within 30 degrees of the exit,
horizontal distance 64 through 220 units, speed 100 through 330 units per
second and height difference at most 48 units. The predicted landing must
approach the exit by at least 16 units. A refusal changes neither the route
nor its jump cooldown. A successful launch releases ride ownership to
airborne route control; it retains the route until ordinary arrival handling
installs the next edge. Exit forecasting is skipped outside a lift action.

The implementation has no map-name branch, graph edits, horizontal launch
impulse or score/band changes. It reuses the current physical speed and
jump/gravity model. Ride ownership requires current ground support, so a
stale `groundentity` reference while airborne cannot hold a bot still.

## Physical witnesses

The private fixture places one bot at the boarding point, assigns a later
goal and then leaves movement to production routing and physics. The e1m6
start is `625 1425 24`, exit `529 1393 344`, and later goal
`433 1297 208`. The dm3 task is a separate positive transfer control.
Success now requires boarding, dry static-floor landing near the exit,
advancement to a different route node, continuous original task ownership,
survival and zero forced relocation. Landing beside the exit alone is
insufficient. A later node alone is also insufficient if no landing occurred.

`MTRACE` records support, mover phase, velocity and route state every half
second. The observer audit rejects actor/world mutations and steering after
setup. The receipt parser rejects missing/duplicate results, inconsistent
completion, wrong map and wrong measured cadence. `BHVRPL` keeps these
private trials out of ordinary gameplay bands.

The exact final fixture is used unchanged on both sources and both rates.
Earlier landing-only trials and an overly strict requirement that the next
edge carry no lift tag are retained separately. The latter rejected dm3 even
as it continued successfully onto another lift-tagged edge; it is a rejected
test criterion, not evidence that dm3's controller failed. No earlier trial
is pooled into the final ordinary-match cohorts.

## Comparison protocol

The baseline is main `8ddcd57773cc0f8f323f092ee8341797a5b084ff` with decision
source SHA256 `2af83d97ca0c5a21225beea25d13d1b7ad46100b6a6d6d7e3222b6279ef376f2`.
First candidate decision source is
`cf36fd384065159a3d8ac874ef553dd36469f58a65e6f1611b9faddc0397a8ee`;
it is rejected below. The final source has a separate identity.
The ordinary program is frozen per arm; private fixtures compile separately.
The evidence records every program, source, graph, fixture and raw identity.
Historical health/inventory fixture definitions remain recoverable exactly
through the updated reverse amendment.

The initial comparison registers two 60-second skill-2 matches per arm on
dm3, dm6, lqdm2, e1m1, e1m2, e1m5, e1m6 and e1m7. A separate confirmation
stratum registers four more 60-second repeats on both e1m6 and dm3 before
their initial candidate pair finishes. Its purpose is to check the physical
repair and the earlier rejected prototype's dm3 warning. Both focal maps
are retained regardless of outcome. All maps use measured played cadence.
Engagements are the registered primary throughout; severe freezes still veto
and stalls, pickups, damage and recoveries remain reported. No null gate
or secondary metric is retuned after a result.

## Results

### Rejected first candidate

| Map | Matches per arm | Engagements, control -> candidate | Stalls | Consumed goals | Forced recoveries, total |
|---|---:|---:|---:|---:|---:|
| dm3 | 6 | 5.67 -> 6.00 | 3.00 -> 7.33 | 5.33 -> 3.67 | 0 -> 1 |
| dm6 | 2 | 15.50 -> 17.50 | 1.00 -> 6.50 | 10.00 -> 9.50 | 0 -> 0 |
| lqdm2 | 2 | 14.50 -> 11.00 | 3.00 -> 1.00 | 8.00 -> 5.50 | 0 -> 0 |
| e1m1 | 2 | 2.00 -> 4.00 | 9.00 -> 6.00 | 3.00 -> 4.00 | 0 -> 0 |
| e1m2 | 2 | 1.00 -> 6.50 | 6.50 -> 2.00 | 4.00 -> 4.00 | 0 -> 0 |
| e1m5 | 2 | 7.00 -> 9.00 | 10.50 -> 4.00 | 6.50 -> 7.00 | 0 -> 0 |
| e1m6 | 6 | 9.17 -> 7.33 | 15.67 -> 12.83 | 2.17 -> 2.83 | 0 -> 0 |
| e1m7 | 2 | 30.00 -> 30.00 | 0.00 -> 0.50 | 5.50 -> 5.50 | 0 -> 0 |

The initial e1m6 pair improved engagements, but confirmation did not. The
combined e1m6 mean falls from 9.17 to 7.33 engagements, while stalls improve
from 15.67 to 12.83 and consumed goals rise from 2.17 to 2.83. dm3 stalls
rise from 3.0 to 7.33, with a native IQM improvement interval entirely worse
(-7.8 to -1.0) and one forced recovery. The engagement-primary cards still
pass. This candidate is rejected: those cards do not erase the movement
warning. All 84 tapes remain in the [initial evidence](../runs/e1m6-dock-initial.results.json).

### Revised transfer handoff

The revised controller checks action ownership before calling the exit
forecaster and releases the lift flag on the verified launch. A jump is
then owned by airborne route control rather than by the platform ride. The
physical test still requires an actual landing and continuing-route handoff.
This addresses a real phase transition; the earlier candidate is not renamed
or pooled into the replacement.

The replacement comparison registers six matches on each focal map and two
on each other map. It reuses every unchanged-source control from both earlier
strata, selected before the replacement runs. The evidence preserves original
run names, source/binary hashes, repeat numbers and the subset projection
used by the native comparison driver. All 24 replacement matches use one
frozen ordinary program and the same duration, skill, cadence and primary.
The runner caps repeats at five, so each six-repeat focal set uses two fixed
three-repeat batches with the corresponding first/last three controls.

The final comparison contains 24 frozen controls and 24 replacement matches.
The focal maps have six repeats per arm; other maps have two. Values below
are arithmetic means per 60-second match except recovery totals.

| Map | Matches per arm | Engagements, control -> candidate | Stalls | Consumed goals | Forced recoveries, total |
|---|---:|---:|---:|---:|---:|
| dm3 | 6 | 5.67 -> 8.83 | 3.00 -> 5.17 | 5.33 -> 4.50 | 0 -> 1 |
| dm6 | 2 | 15.50 -> 15.00 | 1.00 -> 5.50 | 10.00 -> 7.00 | 0 -> 0 |
| lqdm2 | 2 | 14.50 -> 17.00 | 3.00 -> 0.50 | 8.00 -> 5.00 | 0 -> 0 |
| e1m1 | 2 | 2.00 -> 1.50 | 9.00 -> 12.00 | 3.00 -> 2.00 | 0 -> 0 |
| e1m2 | 2 | 1.00 -> 3.50 | 6.50 -> 8.00 | 4.00 -> 1.00 | 0 -> 0 |
| e1m5 | 2 | 7.00 -> 8.00 | 10.50 -> 11.00 | 6.50 -> 8.50 | 0 -> 0 |
| e1m6 | 6 | 9.17 -> 11.50 | 15.67 -> 8.67 | 2.17 -> 4.33 | 0 -> 1 |
| e1m7 | 2 | 30.00 -> 35.00 | 0.00 -> 0.00 | 5.50 -> 4.50 | 0 -> 0 |

All eight native engagement-primary cards pass as parity. Both focal
engagement IQM intervals cover zero: e1m6 -2.5 through +6.8, dm3 -0.2
through +6.5. These are directional changes, not statistically established
improvements. dm3's stall interval now covers zero (-6.2 through +1.5),
versus the entirely worse interval that rejected the first candidate.
Other means remain mixed, including higher dm6/e1m1/e1m2 stalls and fewer
pickups on several maps. The comparison does not establish a general win.

Every final ordinary match has zero native freezes and zero freezes under
fire. Gait attribution reports zero attributable failures. Two forced
recoveries remain, both outside the upper lift transfer: Carmack underwater
at `-15 817 -232` on e1m6 and Joe Rogan pursuing through `389 225 -200` on
dm3. The unchanged controls contain no rescues, so this study cannot claim
an overall reduction in rescue rate. These tapes remain failures to avoid
rescue, not successful physical transfers.

Remaining e1m6 work is tracked separately: [submerged recovery #642](https://github.com/saworbit/argus/issues/642)
and [lower-door recirculation #643](https://github.com/saworbit/argus/issues/643).
The [dm3 lower-room pin #644](https://github.com/saworbit/argus/issues/644)
is a separate observed rescue without lift activation.
The [e1m5 mega-return issue #636](https://github.com/saworbit/argus/issues/636)
also remains open.

The exact final static-world-floor fixture gives:

| Map / rate | Unchanged controller | Final controller | Checked jumps, final |
|---|---|---|---:|
| e1m6 / played, measured 14 through 16 ms | Fails at 18.0s, route lost | Completes at 3.9s, route retained | 1 |
| e1m6 / 100 ms | Completes at 3.0s | Completes at 2.7s | 0 |
| dm3 / played | Completes at 1.3s | Completes at 1.6s | 0 |
| dm3 / 100 ms | Completes at 1.1s | Completes at 1.3s | 0 |

Every final physical success is alive, dry, landed on world geometry,
advanced past the exit node and retains its original task without rescue.
Earlier revision trials also complete the e1m6 transfer at 3.7s played and
2.7s slow; fixture versions remain distinct. Final bank escape is 6.2s
played / 9.0s slow, and all 56 native decision contracts pass at both rates.
The original e1m5 mega-return task still fails after 18s and 14 handoffs;
its frozen baseline fails too. This remains the existing #636 checkpoint
issue, not a new dock-exit regression.

All 21 maintained private variants compile in id format against final
production source. The stricter mover fixture then compiles and executes
separately at both rates. The evidence retains 130 unique raw tapes,
including rejected candidates, preliminary test criteria, diagnostic failures,
smokes and final comparison tapes. The final ordinary program SHA256 is
`2b712713652bd86f072aba0974dee40bc01b603f88a73b13a14d49dfdeddd688`;
the unchanged ordinary control is
`1feb00a6b0605c9370128ac0de7ccb5e1bbd5f2a74a3a19739508f2a01b10437`.
Final decision source SHA256 is
`71cecc207e97c64d6b8efecceb44985c00b982f280a6447c5c381a6ac15050a3`.
The initial candidate's earlier source/program identities remain in its
separate evidence file; do not pool those matches into the replacement.


## Reproduction and limits

```text
python tools/verify_mover_transfer.py --output backups/<new-directory> --prefix <new_prefix>
python tools/verify_mover_transfer.py --output backups/<another-directory> --prefix <another_prefix> --ticrate .1
python tools/run_map_intelligence.py --source src --maps dm3,dm6,lqdm2,e1m1,e1m2,e1m5,e1m6,e1m7 --seconds 60 --repeats 2 --primary engagements --output backups/<study-directory> --prefix <study_prefix>
```

Use fresh output directories and prefixes. Use `--source` with a frozen
baseline source tree and `--control` to retain its physical outcome. The
ordinary comparison driver accepts `--baseline` only after that baseline
has a nonempty results file. Engine ports may be isolated, but compilers
must run serially. Use a freshly rebuilt native lab matching the checkout;
the connected server can remain stale across source changes.

Goal-selection events do not prove prize touches. Completing this transfer
does not prove quad control, full-map reachability or improved human play.
The supplied gameplay binaries remain MD5
`A3F7AA9428846DE7F7B327506F5F5D3D`; no installation is performed. Existing
health/inventory and human-play gates remain open.
