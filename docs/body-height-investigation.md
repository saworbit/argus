# Body height and lower-room pins

[Native receipts](../runs/body-height-v1.results.json) |
[Private checks](../tools/argus_mcp/README.md#body-height-and-physical-exits)

The e1m6 rescue in #642 logs its destination at (-15,817,-232).
The preceding stationary samples are near (-160.1,833,-232). A private
replay from that position reproduces the rescue with no opponent present:
feet are dry, water depth is zero, there is no typed route action, and
map damage continues. This is not evidence for a swim change.

The reproduced entry starts with a valid lower body at (-157.1,833,-232)
and a valid player above at (-124.1,833,216). Both pass the engine's
zero-step body check. The old body-block function flattens their separation
and treats the upper player as an overlap. Its point-box check accepts
the nudge, but the real engine body check rejects the resulting position
at the exact pin. The dm3 counterpart moves a valid body from
(338.1,125.9,-200) into (335.1,125.9,-200), reproducing that lower-room pin.
The historical tapes do not isolate the instruction that created them;
these controlled tests establish a concrete way to enter both failures.

The narrow correction requires actual vertical bounds to overlap before
nudging or clearing another player's line. It uses both entities' bounds.
It leaves same-floor nudge and collision behavior in place. The wider
collision and diagonal-separation prototype in draft #734 remains separate.

The maintained native fixture gives these physical outcomes:

| Task | Old code, played / 100 ms | Height gate, played / 100 ms |
|---|---|---|
| dm3 continuing checkpoint | Fails at 3.0s / reaches at 0.9s after an invalid nudge | Reaches at 1.0s / 0.9s |
| e1m6 local physical exit | Fails at 3.0s / 3.1s with task lost | Clears 64 units at 0.3s / 0.2s with task retained |

Both corrected tasks finish alive, dry, grounded on world geometry,
continuous and without rescue. The played e1m6 exit retains 91 health after
real map damage; the slow exit retains 100. This does not claim an injury-free
route. An earlier longer launcher task still fails later at eighteen seconds
and remains distinct from the local escape proof.

Nineteen native checks per profile cover both initial body fits, entry,
continuity, task identity, above/below and firing cases, touching bounds,
and the same-floor control. The touching cases are synthetic contracts.
Their first rounded setup produced a real floor-epsilon overlap and failed;
the corrected setup touches the engine-fitted bounds exactly. The rejected
setup is retained. Disabling the production gate fails the new tests at
both cadences. Slow dm3 completion does not erase its invalid initial nudge.

The ordinary comparison is registered before execution: forty-two thirty-second
skill-2 matches, alternating frozen control and candidate programs. It covers
the original eight broader-study maps plus dm4. dm3, dm4 and e1m6 have three
matches per arm; each other map has two. Both unchanged native stall-parity
and engagement gates must pass, including the severe-freeze vetoes. All
registered tapes remain in the result; no outcome-selected repeats are added.
All eighteen native cards approve parity. Every ordinary tape has zero
freezes and zero under-fire freezes. The following are native medians per
thirty-second match, control / candidate:

| Map | Stalls | Engagement starts |
|---|---:|---:|
| dm3 | 1 / 1 | 2 / 4 |
| dm4 | 0 / 0 | 13 / 11 |
| e1m6 | 7 / 7 | 2 / 2 |
| dm6 | 1 / 0.5 | 11 / 7.5 |
| lqdm2 | 0 / 0.5 | 9.5 / 6 |
| e1m1 | 3.5 / 5 | 0 / 0 |
| e1m2 | 2.5 / 4.5 | 0 / 1 |
| e1m5 | 1.5 / 5 | 2 / 1 |
| e1m7 | 0 / 0 | 19.5 / 19.5 |

The activity declines are material limits. dm6 and lqdm2 engagement IQM
intervals are entirely worse despite remaining inside the registered bands.
The stall intervals on e1m1 and e1m5 are also entirely worse. Native cards
retain pickup and frag-spread flags. This supports the narrow controlled
pin prevention within the existing parity allowance; it does not establish
a general gameplay or combat improvement. There are only two or three
tapes per arm. The fixed schedule adds no favorable repeats, and no band
was changed to obtain approval.

No generated navigation or installed gameplay program changes. The historical
health/inventory sources remain recoverable through a separate reverse patch.
No additional health/inventory cohorts or human-play claims are made.
