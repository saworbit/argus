# The lab spine

[Back to the lab workflow](lab-workflow.md) |
[Operator guide](../tools/argus_mcp/README.md)

`tools/argus_lab.py` joins the lab's instruments into one loop. It adds no new
instrument and no second tape parser. It reads what the lab already keeps,
plus two hand-written files, and answers four questions: what is true now,
what is stale, what a new tape's trouble is, and whether a comparison can be
believed.

## What it reads

| Source | Written by | Used for |
|---|---|---|
| `tools/lab_objective.json` | hand, signed off by Shane | Priority tiers, hard gates, goal targets, measure labels, metric boundaries |
| `tools/lab_claims.json` | hand | Open defects and hypotheses, fixed cells, the graveyard, supported rules |
| `tools/refuted_claims.json` | hand | Imported as refuted rules, so they are not repeated in the claims |
| `runs/tape_index.tsv` | `argus-mcp corpus` | Per-tape metrics, tick class and kind for the skeptic |
| `runs/human_scorecard.tsv` | `argus_longi.py`, every harvest | Session gates and goal measures |
| `runs/baselines.json`, `benchmarks/*.json` | `baseline_set`, hand | What each verdict is measured against |
| `src/argus_nav_<map>.qc.json` and `.probe.json` | navgen, `probelinks` | Graph identity, refused links |
| `docs/specs/2026-09-16-lab-measurement-limits.md` | `argus-mcp measure` | Per-map sigma, so any tape count has a detection limit |
| `game/argus/progs.dat` history | git | Which build a session ran |

Raw artefacts stay the source of truth. When the skeptic needs a tape that
the corpus cache has not persisted, it asks `argus-mcp corpus` to parse it
rather than parsing metrics in Python.

In a worktree the machine-local BSPs, the lab binary and `.mcp.json` live in
the main checkout; the spine finds them there. `ARGUS_MAPS` and `ARGUS_LAB`
override both.

## Commands

From the repository root:

```text
python tools/argus_lab.py state
python tools/argus_lab.py stale
python tools/argus_lab.py session --last 5
python tools/argus_lab.py triage shane_dm4_2026-11-14_ed8926
python tools/argus_lab.py skeptic ab_dm4_shipctl1 ab_dm4_shipctl2 --vs ab_dm4_shipnew1 ab_dm4_shipnew2
python tools/argus_lab.py claims --check
python tools/argus_lab.py pyramid --maps dm4,dm2 --dry-run
python tools/argus_lab.py night
```

### `state`

The session brief, generated from the evidence instead of typed into a
handoff: the installed binary and whether the changelog agrees, whether the
objective is signed, the last five human sessions against the gates, the goal
verdict per goal map, every stale artefact, the open claims and the three
cheapest next steps. `--write PATH` saves it. Start a session here instead of
reading the history.

### `stale`

Artefacts whose inputs have moved, each with a fix:

- **void**: a verdict that depends on it cannot be trusted. A baseline recorded
  at 19 Hz is void, because verdicts against it compare two frame rates.
- **stale**: out of date. A baseline that ran a different graph (see graph
  identity below), a benchmark suite pinned to a graph that no longer ships, a link
  the puppet refused that still ships (matched within 24 units, navgen's own
  rule, for walk and jump verdicts), limits measured before many newer tapes,
  a session tape nobody scored.
- **info**: worth knowing. Verdicts whose endpoints a regeneration has
  outlived, source commits since the last install.

`--strict` exits 1 on any void or stale finding; `--json` prints the list.

### `session`

Scores human sessions against the objective's hard gates (engine errors,
freezes under fire, 10 s statues, unforced world deaths, rescue warps) and
goal measures (bot kills on the human per minute, the kill ratio). A session
counts towards a goal verdict only on a goal map, with a human in it, at the
calibration skill, over the minimum length and with the skill tier named in
the tape. Its build is the install in force at the tape's start time, from
its header, against commit times in the same local clock. A goal verdict
needs three such sessions on the installed build. `--json` writes an infinite
kill ratio (no bot kills on the human) as `"inf"`.

### `triage`

Clusters a tape's stalls, freezes and world deaths within 96 units, merging
piles until no two centres are that close, and matches each cluster to the
claims' map cells. A cell has a radius across the
floor and a vertical bound (`dz`, 56 units by default), so a fight on a
walkway does not land in the pit below it. With the map's BSP, world deaths
split into knock-ins and unforced deaths. Each cluster reads:

- **known**: an open claim covers it, or light trouble at a fixed cell.
- **new**: nothing does; consider a claim.
- **regression?**: heavy trouble in a fixed claim's cell, on a tape recorded
  after the fix, even when an open claim shares the cell. A fixed claim is
  judged over every point inside its cell, the unit its allowance is measured
  in, not cluster by cluster. Heavy means more unforced deaths, longer freezes
  or more events than the claim tolerates (no deaths, no freezes and four
  events by default). A fixed claim sets its allowance with
  `regression: {kinds, events, freeze_sec, deaths}`, where `kinds` names the
  trouble its fix addressed so trouble from another defect in the same cell
  does not count. It records the measured basis in `regression_basis`;
  tighten an allowance taken from pre-fix tapes once post-fix tapes exist.
- **on the fix day**: trouble at a fixed cell on the day of the fix, when the
  claim's `fixed_on` has no time to place the tape before or after it.
- **before the fix**: trouble at a fixed cell on a tape that predates the fix.

### `skeptic`

Lists every reason a comparison cannot be read at face value, before anyone
reads it. The first arm is the control.

- **Void**: the same tape in both arms or twice in one, tapes from different
  maps, human or fixture tapes, mixed or unknown tick classes, a stub tape
  with no duration, a run with no corpus row.
- **Confound**: the arms ran different graphs (see graph identity below) or
  skill tiers, or a metric crosses an emission boundary:
  a date when the QC changed what tapes record. Parser boundaries are not
  confounds, because the corpus re-parses every tape with today's parser.
- **Per metric**: the change in arm means against the detection limit,
  2.8 × sigma × √(2/n). Sigma is the larger of the limits doc's and the arms'
  own pooled spread, so a pair noisier than average cannot read "moved" on the
  average's strength; a doc sigma of zero counts as unknown, and the doc's
  spread is used only for tapes of its own length (about 185 s). A change inside
  the limit is "no detectable effect", never "improved". When durations
  differ, per-minute rates are compared and the spread comes from the arms.
- **Lava**: the corpus index counts lava deaths below z -300, which misses
  dm2's and e1m7's lava entirely. With the map's BSP the skeptic recounts lava
  from hull-0 contents at each death and 24 units below, the quality bar's
  definition, and says so.

Run names may be given as `x`, `x.log` or `runs/x.log`, and `--metric` must
name a corpus metric. A tape the corpus cache lacks is parsed by
`argus-mcp corpus`, asked per map and per tape kind. Tapes do not name their
build, so the skeptic cannot see a build confound.

### Graph identity

A tape prints only its graph's `ARGNAV` banner, the node and link counts
navgen bakes into the QC, and the banner is not an identity: #716 changed it
from the pre-clamp to the post-clamp count with no topology change. So a
tape's graph is the committed revision of `src/argus_nav_<map>.qc` in force
when it was recorded, if that revision prints the tape's banner, plus any
later revisions printing the same banner (a surgical edit such as #388's
dead-link removal keeps the banner, and a candidate tape recorded before its
merge matches both). Revisions are compared by topology: seat positions and
typed links, with profile arguments stripped. A banner no revision prints
means a graph that was never committed, such as a candidate arm.

### `review`

One fresh session: its hard gates, its goal measures, whether it counts for a
goal verdict, and every new or regressed cluster of trouble. The harvester
runs it after scoring, so a session is read against the objective and the
claims the moment it lands.

### `claims`

Lists the ledger; `--status open` filters it; `--check` validates the
objective and the claims. `argus_ci.py lab` runs the same validation in CI.

### `pyramid`

Runs the evidence tiers cheapest first. It finishes a tier, and stops before
the next if that tier refuted the change. A step that the last `night` sweep
recorded as failing, and found failing the same way, is a known failure: it
is reported and does not stop the climb, so an accepted condition such as
e1m8's three kept liquid links does not hide a new failure. A known failure
that gets worse is a failure: the navmesh audit and directed reach report
counts where lower is better (liquid entries, reach shortfall, spawns far from
any seat), so a partial fix reads as no worse; other steps compare output.
A failure first seen by a sweep is not trusted as known until a later sweep
finds it still failing, so one sweep cannot launder a breaking change. It exits 1 when a tier failed, 3 when a step was
blocked by a stale artefact and nothing failed (the evidence is incomplete),
and 0 otherwise.

- **Tier 1, static checks**: the CI battery, the claims, the navmesh audit
  (no link from dry ground into a liquid seat, no vertical walk link) and
  directed reach for each map.
- **Tier 2, deterministic cases**: each benchmark suite whose pinned graph
  still ships. A suite pinned to an old graph is reported as blocked, not run.
  The benchmark runs `--no-compile`, so it measures the installed build the
  lab engine loads, which the step names; to test a source change, compile
  and install it into a scratch game folder first (`ARGUS_GAME`). The
  benchmark always exits 0, so the pyramid reads its report and holds a
  ratchet keyed by the graph and the installed binary: the first run sets the
  bar, and a later run fails if a task that pair used to finish no longer
  finishes. A task that has never finished does not block anything.
- **Tier 4, with `--through 4`**: the ladder plan, meaning how many
  listen-class tapes a side each map needs to see a 30 per cent change, from
  the limits doc. It plans ladders; it does not run them.

Each real run leaves a receipt in `runs/lab/` (ignored by git).

### `night`

The unattended census, safe to schedule because it starts no engine unless
given `--engine`. It runs every map compiled into `src/progs.src` through
tier 1 (and tier 2 with `--engine`) without stopping at a failure, triages
every tape recorded since the last sweep (read from each tape's own header,
a week on the first sweep), and lists what is stale. It writes
`runs/lab/night-<stamp>.md` with a JSON receipt beside it.

It exits 1 only on what got worse since the previous sweep: a step that
passed then and fails now or fails worse, a regression at a fixed claim's cell
on a new tape, or an artefact newly void. Void artefacts are compared by a key
naming the artefact and the reason, so rewording a message raises nothing and
a new reason on an already void map does. A step the previous sweep did
not run, skipped or saw pass alerts if it fails now. New tapes are those the
previous sweep had not triaged (by name and size), whatever their header date,
so a tape recorded earlier and merged later is still triaged; the first
sweep triages the last week and records the rest as seen. A failure that was already failing is listed as
still failing and does not alert, so a known defect such as e1m8's reach gate
does not drown a new one.

## Adding a claim

Add an entry to `tools/lab_claims.json` and run `claims --check`. Every claim
has an id (lower-case words joined by hyphens), a title, a status (`open`,
`supported`, `refuted`, `fixed`, `parked`), a kind (`defect`, `hypothesis`,
`rule`, `graveyard`), a statement and evidence. Evidence is a repo path, an
issue or PR as `#n`, or a run name in `runs/`. The validator enforces:

- an open hypothesis says what would refute it (`refute_by`);
- a fixed claim says when (`fixed_on`, YYYY-MM-DD, or YYYY-MM-DD HH:MM:SS
  in local time for an exact merge), so triage can tell a regression from an
  old tape;
- a graveyard entry is refuted or parked;
- a cell's map is one of the claim's maps;
- no claim repeats a rule already in `tools/refuted_claims.json`.

When a change is reverted, add it to the graveyard with the numbers that
convicted it and `do_not_retry`. When a fix lands, set `status` to `fixed` and
`fixed_on` to the merge date.

## Signing off the objective

`tools/lab_objective.json` is a draft until `status` is `signed` and
`signed_off` names who approved it and when. Until then `state` says so and
the goal targets are proposals. The values mirror the objective page; change
them in both places.

## Limits

- Build attribution uses the merge time of the commit that last changed
  `game/argus/progs.dat`, not when a binary was copied to a machine; a binary
  installed before its merge is credited to the previous build until then.
- Graph identity reads a tape's banner against git history; two revisions in
  force at the same time with the same banner and different topology would
  look alike, and the spine reports both.
- The skeptic sees graph and skill confounds, not build ones.
- Triage clusters by distance alone; two problems within 96 units merge.
- Goal verdicts count only sessions whose tape names its skill tier, which
  every tape has done since 2026-09-21.
