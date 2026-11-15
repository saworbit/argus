# The improvement loop

[Back to the lab workflow](lab-workflow.md) | [The lab spine](lab-spine.md)

How a change to the bot gets from an idea to an installed build, which
instrument answers which question, and where a human is still the only
referee. Every instrument named here exists; each links to what it can and
cannot say.

## The objective decides what better means

`tools/lab_objective.json` orders four tiers: never visibly broken, fair, a
real threat at skill 1, moves like a person. A change is judged on the tier
it claims to move, and a hard-gate failure rejects it whatever else it
improves. Until the objective is signed off its goal targets are proposals;
`argus_lab.py state` says which.

## Every question is a claim

A defect, a hypothesis or a rule goes into `tools/lab_claims.json` with the
evidence for it and, for a hypothesis, what would refute it. A reverted change
goes in the graveyard with the numbers that convicted it, so it is not tried
again. [The lab spine](lab-spine.md#adding-a-claim) has the fields.

## Climb only as far as the claim needs

Cheapest first; a rung that refutes the change stops the climb.

| Rung | Instrument | Settles | Cannot settle |
| --- | --- | --- | --- |
| 1 | Static checks, navmesh audit, directed reach (`argus_lab.py pyramid`) | broken graphs, unreachable items, stale artefacts | anything about play |
| 2 | Fixtures and benchmark tasks | a specific behaviour, deterministically | how often it matters in a match |
| 3 | [Fixed-clock ladder](fixed-clock.md) (`argus-mcp seeds`) | a movement or economy change, quickly, on maps where the clock is accepted | metrics listed as its limits there, and anything human |
| 4 | Wall-clock band (`experiment`, `argus-mcp match`) | the same, at the lab's own rate; the tapes a ship decision needs | anything human |
| 5 | [Stand-in human](stand-in.md) (`argus-mcp standin`) | the direction of a threat change, before a session is spent, where calibrated | how a person feels about it |
| 6 | Human session with marks, then the [session gallery](session-gallery.md) | threat, fairness and feel | nothing the objective asks; it is the referee |

`argus_lab.py pyramid --maps M --through 5 --dry-run` prints the plan for a
map, including how many tapes each metric needs and whether rungs 3 and 5 are
trustworthy there (`tools/lab_instruments.json`, below).

A rung is trusted only where it was validated, and the record says where:
`tools/lab_instruments.json` lists, per map, whether the fixed clock was
accepted and which metrics are its limits, and whether the stand-in passed
dose response and level. `argus_lab.py state` prints it, `argus_ci.py lab`
validates it, and the pyramid plans rungs 3 and 5 from it.

## One build a cycle

Several changes may merge in a cycle, but one install closes it, so every
session belongs to exactly one build. Every tape names its build
(`ARGUS build <id>`), so a session is credited by its own stamp rather than by
merge times, and a binary run from a scratch folder is never mistaken for an
install.

1. Pick the claim the objective most needs, from `argus_lab.py state`.
2. Change, then climb the rungs above as far as the claim needs.
3. Merge; at the end of the cycle, install once (`ship`) and smoke it.
4. Play: at least one session on a goal map at skill 1, binding `mark`.
5. `harvest_session.py` scores it and prints its review; `argus_gallery.py`
   cuts the marked and suspect moments for a ruling.
6. Rulings and review findings become claims, and the next cycle starts.

## What a session needs from the player

- The launch command in [the telemetry guide](telemetry.md#record-and-harvest-a-human-session),
  which records the demo the gallery cuts from.
- `bind m mark`, and a press whenever a bot looks wrong. Marks change nothing
  in play.
- Three answers when it ends: did they feel dangerous, did they look human,
  did anything look broken.
- Two minutes on the gallery's rulings.

## Running several sessions of work at once

One coordinating session owns the queue, the claims and the engine. Work that
writes code goes to its own worktree, one writer per set of files (two changes
to `src/argus.qc` collide in its source manifest). Every match takes a lease
on its run directory, so two runs can never share a tape, and fixed-clock
lanes take their own ports. Merges go one at a time, with `gh pr update-branch`
after each, because branch protection holds a pull request that is behind.
