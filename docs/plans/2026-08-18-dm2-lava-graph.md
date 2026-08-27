# dm2 lava graph implementation plan (campaign slice 1)

> EXECUTED COMPLETE 2026-08-18 night, shipped as v3.25
> (AF6800DC8FFD84565FD309D9BDA019E1). All four tasks green: 29 lava
> seats and 158 lava-stepping links in the shipped nav (red state),
> 399 samples dropped and GREEN after Tasks 1-2, dm6 spot check
> unaffected, analyzer verified on ab_dm2_first (Zeus's 3 hidden
> lava deaths surfaced) and ab_dm4_areastreak1 (agrees with the MCP
> count), A/B gates all passed (world deaths 3 to 1, stalls 73 to
> 46, routefails 112 to 108, components 186+5+2, edicts 464).
> Tapes: ab_dm2_lava_probe.log, ab_dm2_lava.log, ab_dm2_lava.png.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop navgen seating waypoints in lava and routing walk links
through it, and make the analyzer classify lava deaths by contents
instead of the dm4 z threshold.

**Architecture:** Hull 1 (the clip hull navgen samples) collapses
liquids to empty, so the sampler cannot see lava at all; the hull-0
classifier that can see it already exists but is only consulted for
swim links. This slice hoists that classifier ahead of sampling, drops
lava and slime seats before anything can build on them, refuses walk
links whose beeline steps onto a lava floor, and gives
analyze_match.py its own hull-0 contents lookup for death
classification. No QuakeC logic changes; the progs.dat delta is nav
data only.

**Tech stack:** Python 3 (tools/argus_navgen.py, tools/analyze_match.py),
fteqcc (id format), QuakeSpasm dedicated for the A/B.

**Spec:** docs/specs/2026-08-18-dm2-campaign-design.md

## Global constraints

- Pure vanilla QuakeC: this slice must not touch any .qc logic; only
  the generated src/argus_nav_dm2.qc data file changes.
- Matches validate at sv_protocol 15 with max_edicts 600; navgen's
  edict estimate must stay under 500 (waypoints plus entity lump).
- The navgen change is map-agnostic. No dm2-specific coordinates,
  names or branches inside tools.
- One compiler at a time: do not run this while another author has QC
  edits in flight, and record the build MD5 with every tape.
- Editorial for all docs: sentence case headings, Australian English,
  no em-dashes.
- This project is not a git repository. Where a step would commit,
  instead record the evidence named in the step (tool output, tape in
  runs/, MD5) before moving on.
- maps_local/ BSPs and engine/id1 are licensed id data: machine-local,
  never redistributed, never copied into game/argus.
- Match harness gotchas: QuakeSpasm on Windows writes qconsole.log to
  the process working directory, so cd to C:\argus\engine first;
  fteqcc exits 0 even when the output write fails, so trust the
  "Compile finished ... (id format)" line and a fresh
  C:\argus\lq1\progs.dat timestamp, never the exit code.

---

### Task 1: hull-0 classifier ahead of sampling, lava and slime seats dropped

**Files:**
- Modify: `tools/argus_navgen.py` (hoist lines currently at 612-631,
  the block from `CONTENTS_WATER = -3` through the end of
  `water_surface_z`; insert the seat filter after the
  "fine samples" print near line 113)
- Create: `<session scratchpad>/dm2_lava_check.py` (verification)

**Interfaces:**
- Consumes: `lump()`, `m0`, `planes`, `struct` (already defined above
  `column_floors`), `samples` dict keyed `(cx, cy)` holding floor-z
  lists, coordinate arrays `xs`, `ys`.
- Produces: module-level `CONTENTS_SLIME = -4`, `CONTENTS_LAVA = -5`,
  and `h0_contents(x, y, z)` available from sampling time onward.
  Task 2 and section 7d both rely on `h0_contents` by this name.

- [ ] **Step 1: Write the failing verification script**

Save as `dm2_lava_check.py` in the session scratchpad:

```python
"""Red/green check for the dm2 lava graph slice.
Asserts 1: no emitted waypoint seat sits in lava or slime (hull 0,
torso height). Asserts 2: no walk link's beeline steps onto a lava or
slime floor. Runs standalone against a nav json plus its BSP."""
import json, struct, sys

BSP = r"C:\argus\maps_local\dm2.bsp"
NAV = sys.argv[1] if len(sys.argv) > 1 else r"C:\argus\src\argus_nav_dm2.qc.json"
LAVA, SLIME = -5, -4

data = open(BSP, "rb").read()
def lump(i):
    off, ln = struct.unpack_from("<ii", data, 4 + i * 8)
    return data[off:off + ln]

pl = lump(1)
planes = [struct.unpack_from("<4f", pl, i * 20) for i in range(len(pl) // 20)]
nd = lump(5)
nodes5 = [struct.unpack_from("<i8h2H", nd, i * 24) for i in range(len(nd) // 24)]
lf = lump(10)
leaves = [struct.unpack_from("<2i6h2H4B", lf, i * 28) for i in range(len(lf) // 28)]
HULL0 = struct.unpack_from("<9f7i", lump(14), 0)[9]

def contents(x, y, z):
    n = HULL0
    while n >= 0:
        node = nodes5[n]
        nx, ny, nz, d = planes[node[0]][:4]
        n = node[1] if (nx * x + ny * y + nz * z - d) >= 0 else node[2]
    return leaves[-1 - n][0]

nav = json.load(open(NAV))
way = nav["nodes"]

bad_seats = [i for i, p in enumerate(way)
             if contents(p[0], p[1], p[2] + 24) in (LAVA, SLIME)]
print(f"seats in lava/slime: {len(bad_seats)} -> {bad_seats}")

bad_links = []
for l in nav["links"]:
    a, b = way[l[0]], way[l[1]]
    steps = max(2, int(((b[0]-a[0])**2 + (b[1]-a[1])**2) ** 0.5 // 24))
    for s in range(steps + 1):
        f = s / steps
        x = a[0] + (b[0]-a[0]) * f
        y = a[1] + (b[1]-a[1]) * f
        z = min(a[2], b[2])
        if contents(x, y, z + 24) in (LAVA, SLIME):
            bad_links.append((l[0], l[1]))
            break
print(f"links stepping through lava/slime: {len(bad_links)} -> {bad_links[:12]}")

assert not bad_seats, "lava/slime seats present"
assert not bad_links, "links step through lava/slime"
print("GREEN")
```

- [ ] **Step 2: Run it against the shipped nav to verify it fails**

Run: `python <scratchpad>\dm2_lava_check.py C:\argus\src\argus_nav_dm2.qc.json`
Expected: AssertionError with roughly 31 lava/slime seats reported
(Shane's hull-0 walk counted 31). This is the red state. Record the
exact counts; they are the before numbers for the state note.

- [ ] **Step 3: Hoist the hull-0 classifier in navgen**

In `tools/argus_navgen.py`, cut the block that currently reads
(directly below the section 7d comment banner, keep the banner):

```python
CONTENTS_WATER = -3
nd = lump(5)
h0nodes = [struct.unpack_from("<i8h2H", nd, i * 24) for i in range(len(nd) // 24)]
lf = lump(10)
h0leaves = [struct.unpack_from("<2i6h2H4B", lf, i * 28) for i in range(len(lf) // 28)]
HULL0 = m0[9]

def h0_contents(x, y, z):
    n = HULL0
    while n >= 0:
        node = h0nodes[n]
        nx, ny, nz, d = planes[node[0]]
        n = node[1] if (nx * x + ny * y + nz * z - d) >= 0 else node[2]
    return h0leaves[-1 - n][0]

def water_surface_z(x, y, z):
    top = z
    while top < z + 320 and h0_contents(x, y, top + 8) == CONTENTS_WATER:
        top += 8
    return top
```

and paste it immediately after the end of `column_floors` (before the
fine-sampling loop), with two constants added so the block now begins:

```python
# hull 0 sees what the clip hulls cannot: liquids. Parsed here, ahead
# of sampling, because seats and links need it, not just swim exits.
CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5
```

Leave a one-line comment at the old 7d location:
`# h0_contents / water_surface_z now live above sampling (lava slice)`.

- [ ] **Step 4: Add the seat filter after sampling**

Insert directly after the
`print(f"fine samples: {nsamp} standable points in {len(samples)} columns")`
line:

```python
# ---- 4b. lava and slime seats are not standable ----
# hull 1 collapses liquids to empty, so the sampler happily seats
# waypoints on a lava pool's floor (dm2 shipped 31 of them). Classify
# every fine sample against hull 0 at torso height and drop hostile
# seats before decimation, links, pads or jump edges can build on
# them. Water seats stay: swim links (7d) need underwater waypoints.
_n_liquid = 0
for _k in list(samples.keys()):
    _keep = []
    for _z in samples[_k]:
        if h0_contents(xs[_k[0]], ys[_k[1]], _z + 24) in (CONTENTS_LAVA, CONTENTS_SLIME):
            _n_liquid += 1
        else:
            _keep.append(_z)
    if _keep:
        samples[_k] = _keep
    else:
        del samples[_k]
if _n_liquid:
    print(f"lava/slime seats dropped: {_n_liquid}")
```

- [ ] **Step 5: Regenerate dm2 to the scratchpad and check the prints**

Run:
`python C:\argus\tools\argus_navgen.py C:\argus\maps_local\dm2.bsp dm2 <scratchpad>\argus_nav_dm2_lava.qc <scratchpad>\nav_dm2_lava.png --no-dispatcher`
Expected: a `lava/slime seats dropped: N` line with N at least 20; the
run completes; the edict estimate stays under 500. Sections 7a3, 7e,
7f and 7g will also fire because the shipped dm2 nav predates them;
record their output lines, that drift ships with this slice's regen
(the spec's regen note).

- [ ] **Step 6: Run the verification script against the new json, expect seats clean**

Run: `python <scratchpad>\dm2_lava_check.py <scratchpad>\argus_nav_dm2_lava.qc.json`
Expected: `seats in lava/slime: 0`. The link assertion may still fail;
that is Task 2's job. Record both counts.

- [ ] **Step 7: Determinism spot check on an unaffected map**

Run navgen for dm6 to the scratchpad and diff against
`src/argus_nav_dm6.qc`... dm6's vendored nav predates several navgen
sections, so a byte diff is expected; instead verify the run prints
`lava/slime seats dropped` only if dm6 truly has liquid seats and that
node and link counts are within a few percent of the dm6 numbers in
CLAUDE.md (153 nodes era). This guards against the hoist accidentally
changing hull-1 sampling. Do not install the dm6 output.

---

### Task 2: walk links must not step onto lava or slime floors

**Files:**
- Modify: `tools/argus_navgen.py`, inside `beeline_ok`, the
  perpendicular-offset loop (currently near line 344)

**Interfaces:**
- Consumes: `h0_contents`, `CONTENTS_LAVA`, `CONTENTS_SLIME` from
  Task 1; `column_floors`, `STEP`, `DROPMAX` as already defined.
- Produces: `beeline_ok(a, b)` additionally returns False for any
  path whose accepted floor at some step is a lava or slime floor.
  Everything that calls `beeline_ok` (link building, 7a3 pad
  walk-ins, 7f escapes) inherits the rule with no further changes.

- [ ] **Step 1: Amend the offset loop in beeline_ok**

The loop currently reads:

```python
        for off in (0, 16, -16, 32, -32):
            floors = column_floors(cx + px*off, cy + py*off)
            for fz in floors:                 # climbable step first
                if -STEP <= z - fz <= STEP:
                    nz = fz
                    break
            if nz is None:
                for fz in floors:             # forward drop is fine
                    if STEP < z - fz <= DROPMAX:
                        nz = fz
                        break
            if nz is not None:
                break
```

Change the final acceptance to refuse liquid floors, letting the next
perpendicular offset try instead (side-stepping a lava tongue is
legitimate wall-slide slack; walking into it is not):

```python
        for off in (0, 16, -16, 32, -32):
            floors = column_floors(cx + px*off, cy + py*off)
            for fz in floors:                 # climbable step first
                if -STEP <= z - fz <= STEP:
                    nz = fz
                    break
            if nz is None:
                for fz in floors:             # forward drop is fine
                    if STEP < z - fz <= DROPMAX:
                        nz = fz
                        break
            # a lava or slime floor is not a step, it is a death:
            # reject and let the next offset look for a dry line
            if nz is not None and h0_contents(cx + px*off, cy + py*off, nz + 24) in (CONTENTS_LAVA, CONTENTS_SLIME):
                nz = None
            if nz is not None:
                break
```

- [ ] **Step 2: Regenerate dm2 and run the full verification, expect green**

Run the same navgen command as Task 1 step 5, then
`python <scratchpad>\dm2_lava_check.py <scratchpad>\argus_nav_dm2_lava.qc.json`
Expected: `GREEN` (0 bad seats, 0 bad links). Also record the
`beeline verification pruned N wall-piercing links` line; N rises
compared with Task 1's run because lava paths now prune too.

- [ ] **Step 3: Graph integrity check**

Add to the same session a quick component count (reuse the weak
component logic from dm2_verify.py in the scratchpad, or re-run it
pointed at the new json). Expected: the biggest weak component holds
roughly 170 or more of the nodes and total components stay near the
shipped 180+2 shape, allowing a few extra small islands where lava
seats vanished. A shattered graph (biggest component under ~150)
fails the task; investigate before proceeding.

---

### Task 3: analyzer classifies lava deaths by contents

**Files:**
- Modify: `tools/analyze_match.py` (death classification; the current
  rule counts a world-killer death with z < -300 as lava)

**Interfaces:**
- Consumes: the death events already parsed (killer, position vector),
  and the BSP path the analyzer already receives for wireframes.
- Produces: `bsp_contents_classifier(bsp_path)` returning a
  `contents(x, y, z)` callable, and lava classification that uses it
  when a BSP is available, falling back to the z < -300 rule when not.

- [ ] **Step 1: Add the classifier helper**

Add near the BSP-parsing code in analyze_match.py:

```python
CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5

def bsp_contents_classifier(bsp_path):
    """Hull-0 point contents for death classification. Returns a
    contents(x, y, z) callable, or None if the BSP is unreadable."""
    try:
        data = open(bsp_path, "rb").read()
    except OSError:
        return None
    def lump(i):
        off, ln = struct.unpack_from("<ii", data, 4 + i * 8)
        return data[off:off + ln]
    pl = lump(1)
    planes = [struct.unpack_from("<4f", pl, i * 20) for i in range(len(pl) // 20)]
    nd = lump(5)
    nodes5 = [struct.unpack_from("<i8h2H", nd, i * 24) for i in range(len(nd) // 24)]
    lf = lump(10)
    leaves = [struct.unpack_from("<2i6h2H4B", lf, i * 28) for i in range(len(lf) // 28)]
    hull0 = struct.unpack_from("<9f7i", lump(14), 0)[9]
    def contents(x, y, z):
        n = hull0
        while n >= 0:
            node = nodes5[n]
            nx, ny, nz, d = planes[node[0]][:4]
            n = node[1] if (nx * x + ny * y + nz * z - d) >= 0 else node[2]
        return leaves[-1 - n][0]
    return contents
```

- [ ] **Step 2: Use it where lava deaths are counted**

Where the analyzer currently tests the world-killer death position
with `z < -300`, classify with contents when available. The death
position is the victim's origin, which sits above the floor, so probe
the position and one step below:

```python
def death_is_lava(contents, x, y, z):
    if contents is None:
        return z < -300          # legacy rule, no BSP on hand
    return (contents(x, y, z) in (CONTENTS_LAVA, CONTENTS_SLIME)
            or contents(x, y, z - 24) in (CONTENTS_LAVA, CONTENTS_SLIME))
```

Build the classifier once per run from the BSP already used for the
wireframe, and thread it into the death tally. Keep the legacy branch;
old rigs without maps_local must still analyse.

- [ ] **Step 3: Verify against the known tapes**

Run the analyzer on `runs/ab_dm2_first.log` with the dm2 BSP.
Expected: the deaths near z about -35 beside the trains (the ones the
old filter called plain world deaths) now classify as lava; dm4 tapes
re-analysed with the dm4 BSP reclassify pit-floor deaths at exactly
z -360 on solid floor as NOT lava while the -380..-390 swims stay
lava. Record before and after lava counts for one dm2 and one dm4
tape. This is a CLASSIFICATION BOUNDARY: python-side lava counts are
not comparable across it, and the MCP's Rust parser keeps the old
rule until Shane's next rebuild. That note goes in the state section
in Task 4.

---

### Task 4: regen into src, compile, A/B, ship

**Files:**
- Modify: `src/argus_nav_dm2.qc` and `src/argus_nav_dm2.qc.json`
  (replaced by the regen), `game/argus/progs.dat`,
  `engine/argus/progs.dat`, rerelease `progs.dat`, `CLAUDE.md`
  (state note), tapes in `runs/`

**Interfaces:**
- Consumes: the Task 1-2 navgen, the Task 3 analyzer.
- Produces: the slice 1 ship or a documented no-ship.

- [ ] **Step 1: Stash the shipped nav, regen into src**

Copy `src/argus_nav_dm2.qc` and its json to the scratchpad as
`argus_nav_dm2_preslice1.*`, then run navgen with the real output
paths:
`python C:\argus\tools\argus_navgen.py C:\argus\maps_local\dm2.bsp dm2 C:\argus\src\argus_nav_dm2.qc C:\argus\runs\nav_dm2.png --no-dispatcher`
Expected: same stats as the scratch run in Task 2 (the tool is
deterministic); `dm2_lava_check.py` against the src json prints GREEN.

- [ ] **Step 2: Compile and verify the output line**

From `C:\argus\src`, delete `C:\argus\lq1\progs.dat`, run
`tools\win\fteqcc\fteqw-*\fteqcc64.exe`, and require BOTH the
`Compile finished: ../lq1/progs.dat (id format)` line and a fresh
progs.dat timestamp. Record the MD5. Expected warnings: the seven
Q302 no-reference warnings that every build prints; anything else is
a stop.

- [ ] **Step 3: Install to the lab engine only**

Copy `C:\argus\lq1\progs.dat` to `C:\argus\engine\argus\progs.dat`.
Do not touch game/argus or the rerelease until the verdict.

- [ ] **Step 4: Probe match, 120 s, skill 2**

```
cd C:\argus\engine
del qconsole.log (if present)
Start-Process .\quakespasm.exe with arguments:
  -dedicated 8 -basedir C:\argus\engine -game argus -condebug
  +developer 1 +deathmatch 1 +skill 2 +timelimit 0 +map dm2
Stop it after 120 s, then copy qconsole.log to
C:\argus\runs\ab_dm2_lava_probe.log
```

Expected: ARGNAV line reports the new node count; no script errors;
bots move and fight. If the server errors on load, stop and diagnose
before any long match.

- [ ] **Step 5: Full match, 190 s, and the verdict**

Same command shape, 190 s, saved as `C:\argus\runs\ab_dm2_lava.log`.
Analyse with the Task 3 analyzer against `runs/ab_dm2_first.log`.
Gates, judged on dm2's own numbers, never the dm4 tape:
- world deaths fall against ab_dm2_first, and the ones that remain
  classify as lava at their true height (contents), not by z;
- no stall regression: total stalls at or below the ab_dm2_first 73;
- routefails do not rise above the ab_dm2_first 112;
- weak components in the shipped json near 180+2 (no shatter);
- edict estimate under 500.
2-of-3 rule if variance demands extra matches: run up to three, ship
on two agreeing. The t6 door stall cluster at '2785 -55 -72' is NOT
expected to improve; that is slice 2's gate.

- [ ] **Step 6: Ship on pass**

Copy progs.dat to `game/argus/progs.dat` and the rerelease dir;
verify all three MD5s match; update CLAUDE.md: a short state note
naming the build MD5, the seats dropped, the link prune delta, the
classification boundary from Task 3, tape names, and that slices 2-7
remain per the spec. On fail: keep the lab install for forensics,
restore `argus_nav_dm2_preslice1.*` into src, recompile, and record
the negative result in CLAUDE.md with the tape names, per the
retreat-slice precedent.

---

## Self-review notes

- Spec coverage: slice 1 requirements (seat classification, link
  stepping, analyzer ruler, regen with the post-v3.20 navgen
  sections, gates against ab_dm2_first) each map to a task above.
  Slices 2-7 are deliberately out of scope for this plan.
- The hoist in Task 1 moves code used by 7d; 7d's own references
  (`h0_contents`, `water_surface_z`, `CONTENTS_WATER`) keep their
  names, so no 7d edits are needed beyond the leftover comment.
- Type consistency: `h0_contents(x, y, z)` and the two constants are
  spelled identically in Tasks 1, 2 and the 7d survivors; the
  verification script deliberately re-implements its own classifier
  rather than importing navgen (navgen runs top-level code on
  import).
