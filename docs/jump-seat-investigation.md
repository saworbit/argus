# Rejected legacy jump-seat experiment

[Issue #719](https://github.com/saworbit/argus/issues/719) |
[Receipts and source patches](../runs/jump-seat-v1.results.json)

The strict source-anchor audit identifies a modeled launch. It does not
certify the crossing or explain every engine refusal. The current e1m5
route from node 19 at (-1303,2185,24) to node 28 at (-1079,2185,24)
fails in private native controls at played and 100 ms cadence. The bot
loses its continuing goal after failing to cross. Later spike-trap deaths
occur after that loss and do not explain the initial failure.

A private candidate moves only the graph source to (-1271,2185,24)
before execution. It retains the original player seed, goal, link type,
physics and eighteen-second bound. The modeled launch becomes 72 units
from the source instead of 104, inside the strict 96-unit limit.
It still fails at both cadences. The played candidate loses ownership
and later dies. The 100 ms candidate retains ownership but times out at
18.1 seconds with the checkpoint still unreached.

The destination has conflicting geometric evidence. Both the engine and
the offline render-hull classifier return solid at that point; an engine
point trace starts solid and remains all-solid. A temporary body with the
subject's actual bounds succeeds at an engine zero-step walk there.
The player clip hull also marks the destination empty. These facts do not
prove a usable route, and the point result alone does not prove the body
cannot fit. The local BSP exactly matches maps/e1m5.bsp in the engine's
base PAK.

The unchanged dm3 flagged hop also fails in a played-cadence control.
No complete four-map study, feasible route positive control, accepted
re-seating, ordinary-match comparison or graph adoption is claimed.
This source-only candidate is insufficient. A different physical route or
approach design must be proven before changing the shipped topology.
The existing directed bridges, source-anchor bar and entity allowance
remain unchanged.

The source patches and frozen one-off driver preserve the exact private
setup. Production routing and physics own movement after initial placement.
The observer only reads the subject until stopping a completed measurement.
Native briefs, raw tapes and source, fixture and program hashes remain in
the receipt. All seven routes failed; none is relabeled as an accepted
candidate.

This investigation remains draft evidence. #719 stays open, and
[the mega-return graph adoption](https://github.com/saworbit/argus/issues/636)
still depends on resolving it.
