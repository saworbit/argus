# Recording and reading matches

[README](../README.md) | [Lab workflow](lab-workflow.md)

Use the lab's native briefs and comparisons for match metrics. The console
log records the whole map; a demo adds detailed observations within the
recording client's visible area.

Python review, scorecard, pointfile, humanness and tick tools share the sample,
map, event, death and role readers in `tools/argus_tape.py`. Known complete
names take precedence over words in the event vocabulary. Lab instruments
are excluded from human trails, and tapes without birth evidence do not
invent human tracks. Humanness scoring still requires birth evidence.

## Record and harvest a human session

With the mod installed, start a classic engine using these **engine arguments**:

```text
quakespasm -listen 8 -condebug -game argus +developer 1 +skill 1 +deathmatch 1 +record session dm4
```

Replace the executable as needed. `-condebug` saves console output,
`+developer 1` enables diagnostics, and `record session dm4` starts a demo
on dm4. `qconsole.log` is written in the process working directory; the demo
is written under the active game directory. This command starts a listen
game for human play, not a dedicated comparison arm.

Quit after playing. Before another engine launch, run from the repository
root:

```text
python tools/harvest_session.py --dry-run --tag my_session
python tools/harvest_session.py --tag my_session
```

The harvester looks for the freshest `qconsole.log` in the repository root
or `engine/`, and recent demos in `engine/argus/`. Playing elsewhere does not
change those search paths: preserve your external log/demo and put copies in
those input locations first. Inspect the dry run before moving anything.

The actual harvest moves inputs into `runs/<stem>.log` and
`runs/demos/<stem>.dem`, avoiding existing names, and updates the human
scorecard. Use the stem printed by the tool in subsequent calls.

For automated comparison matches, let `experiment` or `matrix_experiment`
launch the dedicated engine with the lab's rate/configuration controls.

## Read a saved session

**MCP calls**, using the harvested stem:

```text
brief_run log=my_run
see what=demo name=my_run
```

`my_run` is a placeholder for the actual run name, not necessarily the tag
passed to the harvester. For demo export use `see what=demo name=my_run:export`.
The terminal equivalent for a demo is `argus-mcp demo my_run`.

Demos contain positions, projectiles, view angles and kill messages at the
recording rate. They are PVS-culled: an off-screen bot is not a full-rate
track. Use the console tape for full-map event counts and quality gates.

## Log records and their meaning

```text
ARGLOG <name> t <time> pos '<x y z>' spd <speed> yaw <degrees> mode <mode>
       st <stalls> gl <goals> hp <health> frg <frags>
ARGEVT <name> goal <class>
ARGEVT <name> death <killer> pos '<x y z>' [thirdparty]
ARGEVT <name> tactic <phase-or-abort-reason>
ARGDBG <name> pick <class> u <utility> ...
```

This is a reading guide, not the complete closed event vocabulary. The Rust
parser and its QC-emitter audit define the accepted events; the
[operator guide](../tools/argus_mcp/README.md#tape-review-and-event-counts)
documents event counting and shared Python/Rust contracts.

| Record or field | What it establishes |
|---|---|
| `goal <class>` | A goal was selected, not that the item was taken |
| Sample `gl` | The consumed goal-pickup counter |
| `grab <class>` | A recorded pickup; separate from goal selections |
| Tactical `prepare` | The manoeuvre started, not that it completed |
| Tactical `returnshot` | A shot was acknowledged, not that it hit |
| `ARGDBG` | Optional decision scores; enabled by server `scratch1 1`, excluded from ordinary brief counts |

Names may contain spaces and event words. Parsers resolve full known track
names before interpreting verbs; older ambiguous rows without sample/spawn
context retain the legacy interpretation. Do not split names on whitespace.

Human and instrument tracks stay outside bot bands and freeze totals.
Freezes use speed under 20 u/s within a strict 32-unit XY circle for at least
six seconds, including the first sample. Multi-level tapes use the busiest
segment, with the last segment winning a tie. Lava deaths use BSP hull-0
contents; the `z < -300` rule is only a fallback when the BSP is absent.

## Plot or inspect a run

These **terminal commands** use a locally installed BSP and saved log:

```text
python tools/analyze_match.py maps_local/dm4.bsp runs/my_run.log runs/my_run.png src/argus_nav_dm4.qc.json
python tools/argus_pointfile.py dm4 --what swim
```

The plotter needs its Python plotting dependencies. Pointfile overlays are
viewed from a listen game with the engine's `pointfile` command. For live bot
fields, mover analysis, death regions and paired comparisons, follow the
[operator guide](../tools/argus_mcp/README.md#deeper-inspect).

For the bounded attack-cover-return behaviour, ordinary briefs report its
phases. The separate [fixture checker](attack-cover-return.md#engine-acceptance)
establishes controlled movement and first-return damage acceptance.
