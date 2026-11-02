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
collision and diagonal-separation prototype in closed #734 was not adopted:
its dm4 combat-preservation comparison failed. The narrow height repair
superseded that proposal only for the reproduced different-floor entry.
The retained same-floor wall and diagonal-hull failures were tracked in
[#747](https://github.com/saworbit/argus/issues/747). They are not covered by
the height gate or the closed #642/#644 acceptance. The
[same-floor repair](body-nudge-investigation.md) fixes them separately.

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

## The dm4 walkway pin

[#723](https://github.com/saworbit/argus/issues/723) recorded a 6.1 s freeze
under fire at `13 -273 -72` in a cover-hop cohort tape. Those programs predate
the height gate. In the tape, Joe Rogan respawns at `-64 -232 -72`, and by
t 25.1 he holds at `12.8 -272.9 -72` with speed 0 for thirteen samples. At that
moment Carmack is on the pit floor at `-2.8 -240.5 -296`, 224 units below and
35.96 units away horizontally, which is the nudge radius. The south wall face
is at y -288.0 and the player hull reaches y -288.9, so every move starts in
solid. The body-height fixture now has a dm4 case seeded on that line:

| Program | Played | 100 ms |
|---|---|---|
| Cover-hop candidate from the tape | Nudged 12 units onto the recorded spot, pinned for 3.0 s, task lost | Not run |
| Unchanged cover-hop control | Same pin and position | Same nudge, then a 32-unit step clears the wall |
| Current main | No nudge, clears 64 units in 0.2 s | No nudge, clears 64 units in 0.1 s |

The unchanged control pins exactly like the candidate, so the cover guard did
not cause the freeze. The height gate removes the trigger, and the
[same-floor repair](body-nudge-investigation.md) refuses a hull that clips a
wall. Receipt: [runs/dm4-pin-v1.results.json](../runs/dm4-pin-v1.results.json).
