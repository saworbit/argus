# CI fast lane and invariant battery (2026-09-17)

Status: design, approved by Shane 2026-09-17. Not yet implemented.

The question that started it: "do we need to run all the CIs every
time? Are they effective and efficient? Can we build some intelligence
into them?"

The measured answer is that the suite is already efficient enough and
is not effective enough. It runs 2.5 minutes on every commit including
the 21 per cent that touch no tested code, and in 200 runs over twelve
days it failed once. This spec cuts the waste and spends the headroom
on checks tied to defects the record says have already happened.

## What was measured

Everything below is from the tree and the Actions API on 2026-09-17,
not from reading the workflow.

### The cost

200 runs over twelve days, median 146 s wall, three jobs. THE REPO IS
PUBLIC, so Actions minutes are free: the cost is latency and attention,
never money. That single fact reframes the whole question, because it
means buying coverage is cheap and saving minutes is worthless except
where a human is waiting.

```
critical path   quakec 12s ---> smoke 127s        = 146s total
inside smoke    90s botmatch + 26s uncached apt-get + 7s checkout
lab (parallel)  16s rust (about 190 tests) + 1s python (23 tests)
```

The waste, from 138 commits since 1 September:

- 21 per cent touch no tested code at all (docs, tapes, built
  artefacts) and still pay the full 2.5 minutes.
- Every merged PR runs twice on the same tree: 106 pull_request runs
  against 92 push-to-main runs.
- Dependabot cargo bumps run a QuakeC compile and a 90 s botmatch to
  validate a Rust dependency.

### The effectiveness

ONE FAILURE IN 200 RUNS, 0.5 per cent, and that one was the lab job on
a gitignore PR. A suite that never speaks is not thereby healthy. What
it declines to look at:

- THE SMOKE RUNS A REAL 90 s BOTMATCH AND THEN THROWS AWAY EVERYTHING
  EXCEPT "DID IT CRASH". It never asks the question the lab's own
  hard-fail gate asks. tools/argus_review.py summary is committed,
  pure python, and answers it in milliseconds on a tape CI already
  holds.
- TEN OF ELEVEN COMMITTED NAV GRAPHS GET ZERO SCRUTINY. Only lqdm2 is
  reached, because the reach gate needs a BSP and id content cannot
  live in CI. But the 8-slot link budget and the no-exit orphan test
  are pure graph properties needing no map at all.
- NOTHING CHECKS THE SHIP. Both game/argus/progs.dat and
  engine/argus/progs.dat are tracked, and four scratch mod dirs
  (argus_bis, argus_bb, argus_bb2, argus_ctl) exist precisely because
  a ladder can modify the tracked one.
- TAPES ARE EVIDENCE AND CI DOES NOT PROTECT THEM. #328 overwrote a
  committed tape twice in one week. History since 1 August: 761 tape
  additions against 22 modifications, and 21 of those 22 are mx_* or
  probe_* tapes, which are overwritten by design. Exactly ONE ladder
  tape was legitimately modified in seven weeks.
- THE CI COMPILER IS PINNED BY ACCIDENT. The workflow clones fteqw
  master at --depth 1 under a fixed cache key fteqcc-<os>-v1. CI
  stamps git-30-f937b9d where this rig stamps git-6729-f937b9d88: the
  same commit, a different revision count because of the shallow
  clone, and an 8-byte shorter banner. Whatever landed in the cache
  first is the compiler, and an eviction moves it with nothing said.

Also true and worth knowing: main is NOT branch-protected, so every
check is advisory in the sense that a red build blocks no merge.

### Two claims verified before they were designed against

fteqcc IS byte-stable here, to the byte. A fresh compile of the current
src/ against the shipped v4.21 progs.dat differs in EXACTLY ONE BYTE at
offset 116, the day digit of "Compiled [2026/09/16]". The v4.17-era
note was exactly right.

lqdm2 IS quiet enough to assert against. All five committed lqdm2 tapes
report zero freezes under argus_review.py, at 185 s each, twice the CI
duration. A zero-freeze assertion on that map is a crash-class check
rather than a movement verdict, so it does not walk into the one-tape
trap. THE CAVEAT THAT KEEPS IT ADVISORY FOR NOW: all five predate the
tick pin and ran a different rate class than CI's sys_ticrate 0.0139.

## The shape

Three shapes were considered. The chosen one is THIN CI, FAT TOOL,
because it matches an idiom the tree already keeps: argus_reach.py,
argus_review.py and test_tools_cli.py are all committed tools that CI
merely invokes, so a check runs in the lab before it runs in CI, which
is this project's whole method. The two rejected shapes were a single
workflow with per-job if: guards (spins a runner up just to compute a
diff, and the invariants want to be a local tool regardless) and
bolting the checks onto the existing lab job (smallest diff, leaves the
latency half untouched, couples repo invariants to the cargo cache).

### Part 1, the tool

tools/argus_ci.py, one committed battery, about a second locally. Three
hard checks, each tied to a recorded defect, AND ALL THREE VERIFIED
PASSING ON THE TREE AS IT STANDS on 2026-09-17.

ship - the binary and the paper trail agree, where a paper trail exists.

- game/argus/progs.dat and engine/argus/progs.dat byte-identical. BOTH
  ARE TRACKED, so this half runs everywhere, including CI, and it is
  also the half that catches the primary hazard: a ladder leaving an
  experimental build installed in engine/argus.
- Their MD5 equals the single MD5 in CLAUDE.md's current
  "## State at handoff" block, when CLAUDE.md exists. Verified on
  Shane's machine: that block parses to exactly one hash,
  E0A63B4D52ECB517BB6D6F814642CBA7, and both files match it.
  CORRECTION, found only by running CI, after this passed locally
  and three reviews: CLAUDE.md IS NOT IN THE REPOSITORY.
  .gitignore's `**/claude*.md` keeps it deliberately machine-local, so
  a CI checkout has never contained it and never will - this half of
  the check is LOCAL-ONLY BY CONSTRUCTION. On a tree without
  CLAUDE.md the tool skips the hash comparison and reports it plainly
  (exit 0, "handoff hash not checked, CLAUDE.md is machine-local")
  rather than failing on an absent file it can never satisfy in CI. A
  CLAUDE.md that is present and still malformed, or present and
  disagreeing with the binary, keeps failing exactly as designed.
- Catches an experimental build left installed by a ladder, and (on a
  machine that has CLAUDE.md) a handoff hash drifting from the
  binary, which the v4.18 note records happening.
- RUNS UNCONDITIONALLY, and needs no diff gate. The first cut of this
  design gated it on progs.dat or CLAUDE.md being in the diff, to
  avoid firing on a QC PR whose binary is legitimately stale, since
  the shipped workflow is a QC PR then a separate install PR (#399
  then #400). The gate is unnecessary: the check reads only committed
  files, so on a QC-only PR neither binary nor CLAUDE.md has moved,
  they still agree, and it passes. A gate could only ever have
  suppressed a true finding. It fires exactly when one of the three
  files moves without the others, which is the defect.

tapes - evidence is append-once.

- No runs/ab_*.log or runs/shane_*.log may be modified or deleted.
- mx_*.log and probe_*.log exempt: matrix probes and diagnostic probes
  are overwritten by design, and they account for 20 and 1 of the 22
  historical modifications respectively.
- Escape hatch: [tape-rewrite] in the commit message. It is needed
  rarely: e768bbd, a legitimate re-run of ab_dm4_unstick.log, is the
  ONLY modification in seven weeks the exemptions do not already
  cover.
- Catches #328.

nav - the committed graphs obey the runtime's limits, READ FROM THE .qc
AND NEVER THE .json.

- No node exceeds 8 outbound slots. That is the v3.88 amputation class,
  where links past the budget were dropped silently at load and only a
  dprint said so.
- No node has zero outbound edges of any type. That is v3.70's
  tele-orphan, where n150 carried inbound teleporter links and no exit
  of any kind, so every route starting there died instantly.
- Measured 2026-09-17 across all eleven graphs: max out-degree is
  exactly 8 on ten of them (e1m2 peaks at 7), which is the slot clamp
  working, and there are zero orphans.

WHY THE .qc AND NOT THE .json, recorded because the first cut of this
audit got it wrong: the runtime compiles the .qc, and the two files do
not agree. Read from the .json, e1m2, e1m5 and e1m6 appear to carry
degree-zero nodes; read from the .qc they do not, because the json's
links array keeps entries for pairs a later pass reminted under a typed
verb. #330 reached the same conclusion from the other direction and
wrote it down as "count door typing from the .qc, never from the json".

DELIBERATELY EXCLUDED: a .qc versus .json cross-check. The counts
disagree on all eleven maps, but that is the superset relationship
above rather than a defect, and untangling it properly is its own
investigation.

### Part 2, the split

fast.yml, always, no path filter, nothing to wait on:

```yaml
on:
  push:    { branches: [main] }
  pull_request:
jobs:
  invariants:   # python3 tools/argus_ci.py            about 1s
  lab:          # cargo test --lib + test_tools_cli.py about 30s
```

compile.yml keeps its jobs and gains a gate:

```yaml
on:
  push:    { branches: [main] }          # always, unfiltered
  pull_request:
    paths: [ 'src/**', 'game/**',
             'tools/argus_reach.py',
             '.github/workflows/compile.yml' ]
```

tools/argus_reach.py is in the filter because the reach gate is its
caller and a change to it changes the gate's verdict.

MAIN STAYS UNFILTERED ON PURPOSE. It looks like the duplicate run this
spec set out to remove, and it is not: PRs here merge minutes apart, so
a merge commit's tree genuinely is not always the PR head's tree, and
main is the branch every install is cut from.

THE CHANGED-FILE LIST COMES FROM THE API, NOT FROM HISTORY. The tapes
check needs to know what the PR touched, and fetch-depth 0 against a
198 MB .git would eat the entire fast-lane budget. CI gets the list
from one "gh api repos/{owner}/{repo}/compare/{base}...{head}" call,
which fetches no history at all; the tool falls back to
"git diff --name-status" when run locally.

Fallout worth having: dependabot's cargo bumps touch only
tools/argus_mcp/**, so they stop running a QuakeC compile and a 90 s
botmatch to validate a Rust dependency. No special-casing, it falls out
of the filter.

### Part 3, the advisory layer

The smoke job already produces a 90 s lqdm2 tape and discards it.
Instead: run argus_review.py summary on it into GITHUB_STEP_SUMMARY,
and upload smoke.log as an artifact. It never fails the build.

THIS IS HOW THE FREEZE GATE EARNS PROMOTION rather than being guessed
at. The five committed lqdm2 tapes that read zero freezes all predate
the tick pin. Ten green CI tapes at sys_ticrate 0.0139 is a baseline at
the rate CI actually runs, and at that point the assertion can go hard
on evidence.

A nav report was designed for the same advisory channel, and the
measurement behind it is worth keeping even though the reporting
itself did not make this change. The audit found 26 no-entry nodes in
the .qc (e1m2 8, e1m5 7, e1m1 4, dm2 3, e1m6 3, dm6 1): seats a bot can
leave but no route can reach. The json agrees with the .qc node for
node here, unlike the no-exit case. Wasted edicts and unreachable
goals are a quality observation rather than a correctness one, so any
future report would surface and not gate - this project's record on
acting against a nav observation without a ladder is bad enough to
make that distinction load-bearing. EMITTING THIS INTO THE JOB SUMMARY
IS NOT PART OF THIS CHANGE. The counts above are recorded here as the
evidence, and the report itself stays a follow-up.

### Part 4, the toolchain pin

Pin the fteqw commit explicitly and put that SHA in the cache key, so
the compiler is a reviewable diff instead of a cache accident. The
shallow-clone banner difference is cosmetic and is NOT worth chasing,
because nothing in this design byte-compares CI's output.

## What stays out

- NO BYTE-COMPARE of CI's fresh build against the committed one. It was
  designed and then refuted: the same compiler commit produces 908230
  bytes in CI against 908238 here, because the shallow clone shortens
  the version banner and shifts every offset after it. The
  MD5-against-CLAUDE.md check gets most of the value for none of the
  cost.
- NO EXTRA MAPS in smoke. id content cannot live in CI and lqdm2 is the
  ceiling.
- NO BRANCH PROTECTION, this pass. Flagged rather than actioned: main
  is unprotected, so a red build blocks nothing. That one setting is
  what converts these gates from a signal into a guarantee, and it is a
  follow-up whenever Shane wants it.

## Expected effect

```
PR shape              before   after
docs or tapes only     146 s   about 35 s, deep lane does not run
rust only              146 s   about 35 s, deep lane does not run
QC change              146 s   about 146 s, plus 3 invariants parallel
push to main           146 s   about 146 s, unchanged by design
```

Roughly 60 per cent of PRs stop paying the deep lane. The failure rate
should RISE from 0.5 per cent, and that is the point: the measure of
success is a red build that means something, not a green one.

## Testing

The tool is the testable unit. Each check gets a fixture pair, passing
and failing, in tools/test_tools_cli.py beside the existing 23 tests,
so the battery is covered by the lab suite that the fast lane runs. The
three checks were each run against the live tree during design and each
passes, which is the regression baseline.

The workflow split itself is verified by observation rather than by
test: open one docs-only PR and one QC PR after the change and confirm
the deep lane runs on exactly one of them.

