# Advanced bot design capture: BotCore / learning navmesh spec

Provenance: supplied by Shane on 2026-08-17 as
Quake1_Advanced_Bot_Design.md ("capture this as roadmap and ideas"),
alongside the KINETIC spec (see kinetic_ideas.md). This one is closer
to Argus's world: it keeps intelligence in QuakeC and builds on
QuakeSpasm. Its central bet, though, is "prefer engine primitives over
being clever inside pure classic QuakeC" — checkextension-gated
builtins, raised limits, file I/O — which is precisely what the Argus
charter rules out. Triage first, then the document as received.

## Triage against the Argus hard constraints

### Adoptable in pure vanilla QuakeC (M4-M6 candidates)

- Apex cornering via lookahead (its "pure pursuit" path following,
  section 6.3): in routed mode 2, when the node after next is visible
  and close, steer for it instead of the current node. Pure QC, a
  traceline per steering tick, and it directly attacks the "on-rails
  pivot at every node" complaint plus possibly our two chronic dm4
  walkway stall corners. Strong M4 candidate.
- Wish-velocity smoothing (section 9's bot_wish blend): Argus's
  moveyaw is already decoupled; a small blend factor on heading
  changes is free and may reduce jitter further.
- Danger/glory/usage link costs, reframed offline (sections 5.1, 7):
  vanilla QC cannot persist files, but the Argus rig already
  persists everything that matters: telemetry logs. The learning loop
  becomes offline reinforcement — analyze_match extracts death
  positions, stall clusters and traversal counts per link, and navgen
  bakes adjusted link costs into the next generated argus_nav_<map>.qc.
  The bot learns between builds instead of between frames, which is
  exactly the project's A/B methodology already. This is the most
  Argus-shaped idea in the document.
- Runtime session-local learning (lite): nav nodes are entities, so
  per-node danger floats updated on deaths are storable today. The
  current router is unweighted BFS; making it cost-aware is a real
  change (frame-sliced Dijkstra) — park until offline reinforcement
  proves insufficient.
- Rocket-jump records with landing/impulse/damage metadata (sections
  4.4, 5.1): landed as prize-only typed pads (same conclusion as
  the KINETIC triage). Navgen solves the arc offline; only pads
  onto quad/pent/ring/mega/LG/RL ship; runtime executes jump plus
  rocket toward the landing. Discovery-by-simulation stays offline.
- Combat/hunt/explore state machine (section 9) and Zeus-style
  cooperative play: QC-sized ideas for the personality milestone.
- Node placement guarantees (section 7, Cartographer step 4):
  guaranteed nodes at items, teleporters, buttons and platform
  endpoints is a direct, cheap navgen improvement — today's decimation
  can drop waypoints near items; pinning them helps goal routing.

### Already covered by Argus

- "Quake Cartographer" offline BSP preprocessor is argus_navgen: BSP
  in, walkable-surface analysis via hull 1, node placement, typed
  links, seed data the runtime loads. The capture's step 3 (coplanar
  face merging so floors read as continuous regions) is the one piece
  navgen lacks; its column sampling sidesteps rather than solves it.
- Debug visualisation: the capture wants in-engine drawline/drawsphere
  builtins; Argus's answer is the offline nav PNGs and trajectory
  plots, which serve the same purpose without engine touches.
- Hierarchical pathfinding (section 6.3): designed for meshes with
  thousands of nodes. Argus caps at 200 waypoints per map and the
  frame-sliced BFS resolves well inside budget; hierarchy is solving a
  problem we deliberately do not have.

### Engine track (parked; violates current charter)

Everything in BotCore (section 4): raised limits, tracebox, trymove,
runplayerphysics, simtrajectory, spawnclient/dropclient, sandboxed
file I/O, drawline/drawsphere, checkextension detection. Also the
"fork QuakeSpasm" recommendation itself (section 3). Same standing as
the KINETIC bucket 3: if ever opened, it is a second deliverable
beside the vanilla progs.dat, which remains canonical. Worth noting
the capture's own observation that QuakeSpasm never added these
builtins because faithfulness was the point — that is also Argus's
point.

### Historical notes worth keeping

Section 1 is a good potted history (Reaper 1996, Omicron 1997 and the
unreleased source with OBOTS.HTM as the design reference, Zeus coop
bot, the 2021 rerelease's Maleficus .nav bots). The Omicron feature
list (fuzzy decision weights, simulated hearing, personalities,
pursuit AI, partial rocket jumps) reads as a to-do list for Argus M4
written twenty-nine years early. Personalities, chat, and the
prize-only rocket-jump pads have since landed; the rest of that
list is still open. The 2026-08-20 local capture of the three
released zips, ObotDoc, MeQCC and a decompile sketch lives in
`tools/decompiled_omicron/` (see that README and ARCHITECTURE.md;
binaries stay gitignored).

---

## Captured document (verbatim)

# Quake 1 Advanced Deathmatch Bot System – Complete Design Document

**Project Goal**: Build a modern, learning-capable Deathmatch bot for Quake 1 that surpasses the classic Omicron bots. The bot should dynamically learn maps, discover rocket jumps naturally, move smoothly without jitter, navigate corners intelligently (apex turns), persist knowledge across sessions, and support cooperative play (Zeus-style).

This document consolidates **every major topic, decision, design, and pseudocode** discussed across the full conversation.

---

## 1. Historical Context & Inspiration

### Classic Bots

- **Reaper Bot** (Steven Polge, October 1996)
  First major computer-controlled deathmatch opponent for Quake. Introduced dynamic waypoint spawning that allowed the bot to learn maps on the fly. Recognised by Guinness World Records. Revolutionary for its time.

- **Omicron Bots** (Mr. Elusive / Jan Paul van Waveren, December 1997)
  Considered a major leap forward. Featured:
  - Fuzzy logic for decision-making
  - Simulated hearing
  - Individual personalities
  - Dynamic waypoint learning
  - Pursuit AI
  - Partial rocket-jump support
  Mr. Elusive never released the full source code, but provided the detailed `OBOTS.HTM` design document (the "blueprint").

- **Zeus Bot**
  Cooperative companion that helped players through single-player maps.

### Later Developments

- Quake source code released by id Software in 1999 -> enabled modern source ports (QuakeSpasm, QuakeSpasm-Spiked, vkQuake, FTEQW, DarkPlaces, etc.).
- 2021 Quake Remaster (25th anniversary) added official deathmatch bots with a waypoint / `.nav` system (John "Maleficus" Dean). Later updates improved melee, swimming, weapon selection, elevators, and map support. Still limited compared to a fully learning system.

### Core Frustrations with Classic Approaches

- Bots often jittery / skittery.
- Get stuck on inside corners instead of taking apex lines.
- Rocket jumping usually required hard-coded waypoint triggers rather than true discovery.
- Limited ability to learn and improve over time on a map.
- Entity limits and QuakeC constraints forced heavy workarounds.

---

## 2. High-Level Goals for the New System

1. **Dynamic map learning** – Bot explores, builds, and refines its own navigation data. Can save/load per-map knowledge.
2. **Natural rocket-jump discovery** – Give the bot the mechanical ability; let it figure out useful trajectories through simulation and reinforcement rather than scripted nodes.
3. **Smooth, human-like movement** – Eliminate jitter, proper acceleration/deceleration, wall sliding, step handling, and knockback respect.
4. **Intelligent cornering** – Apex turns instead of getting stuck on geometry.
5. **Persistent learning** – Danger, success ("glory"), and usage influence future path costs.
6. **Hierarchical planning** – Fast long-range decisions + detailed local movement.
7. **Strong debugging & visualisation** tools.
8. **Optional offline pre-processing** ("Quake Cartographer") so the bot is not completely blank on first load of a map.
9. Stay as compatible as practical with classic QuakeC while extending the engine where necessary.

---

## 3. Recommended Engine Base

**Prefer forking QuakeSpasm (or QuakeSpasm-Spiked)** rather than the pure 1999 id source.

**Reasons**:
- Already modernised (cross-platform, better input, resolution, bug fixes).
- Conservative philosophy – stays faithful to original architecture and QuakeC VM.
- Far less time wasted fighting 1999-era build systems and platform issues.
- Easy to add the extensions we need.

The pure 1999 source is viable for maximum authenticity but requires significant preliminary work just to compile and run cleanly on modern systems.

**Compiler strategy**:
- Start by adding new **builtins** only (no new opcodes required initially). Existing compilers (fteqcc, gmqcc, classic qcc) can call them once declared.
- Only fork/modify the compiler later if new language features or opcodes become necessary.

**Why QuakeSpasm did not already add richer floating-point / AI helpers**:
Its design philosophy prioritises fidelity and compatibility with existing mods and demos. Expanding the QuakeC language or VM significantly was outside its scope. The original VM already had basic floats; the real gaps for advanced bots were richer builtins, better traces, player-physics access, persistence, and higher limits.

---

## 4. BotCore – Engine Extensions

A coherent set of engine additions collectively called **BotCore**. All features should be detectable via `checkextension`.

### 4.1 Raised Limits (Foundation)

- Significantly increase progs globals, edicts, and runaway instruction limit (e.g. 256k globals, 8k+ edicts).
- Required for dynamic navmeshes + learning state.

### 4.2 Better Traces & Movement Prediction

- `tracebox` – player-hull sized traces (solves "fits through bars" false positives).
- `trymove(entity, wishvel, flags)` – non-destructive movement test that returns outcome flags (`MOVE_OK`, `MOVE_BLOCKED`, `MOVE_STEPPED`, `MOVE_FELL`, etc.).

**Pseudocode (TryMove)**:
```c
int PF_trymove(void) {
    // Save origin, velocity, flags
    // Apply wish velocity and run one physics step
    // Capture results into trace_* globals + result bitfield
    // Restore original state
    // Return flags
}
```

### 4.3 Real Player Physics for Bots

- Allow bots to use the real player movement code path.
- Builtin: `runplayerphysics(entity)`.
- Eliminates most custom `walkmove` hacks that cause jitter and stuck behaviour.
- Bots gain proper acceleration, friction, stepping, sliding, and knockback.

### 4.4 Trajectory Simulation (Rocket-Jump Discovery)

- `simtrajectory(...)` – short-horizon physics simulation.
- Inputs: start origin/velocity, rocket offset & speed, jump impulse, duration, flags (gravity, collide, apply rocket force).
- Outputs: final position & velocity (via globals).
- Enables the bot to test "what if I rocket-jump right now?" without risking the real entity.

**Pseudocode sketch**:
```c
void PF_simtrajectory(...) {
    // Apply jump impulse
    // Integrate for N frames with gravity
    // Optionally apply rocket force at the correct frame
    // Optional cheap collision
    // Write sim_endpos / sim_velocity
}
```

### 4.5 Proper Bot Client Support

- `spawnclient()`, `clienttype()`, `dropclient()` (DarkPlaces-style).
- Clean client slots for bots without networking hacks.

### 4.6 Sandboxed Persistence

- File I/O builtins restricted to a safe directory (`botdata/` or similar).
- Enables saving/loading of learned `.nav` data per map.

### 4.7 Debug Visualisation

- `drawline`, `drawsphere`, `drawbox` (temporary, cvar-gated).
- Essential for seeing nodes, links, paths, and hierarchy in real time.

### 4.8 Minor Sensing Helpers

- Content-mask aware traces.
- Improved or approximate geometry-aware sound queries.

**Implementation priority order**:
1. Limits + `tracebox` + `trymove`
2. Real player physics
3. `simtrajectory`
4. Bot client slots + file I/O
5. Debug drawing + sensing

---

## 5. Navigation Data Structures & Learning

### 5.1 Preferred Layout – Array-Based Mesh

Because limits are raised, store the bulk of data in parallel arrays rather than one entity per node.

**Nodes**:
- `nav_node_origin[]`
- `nav_node_flags[]`
- `nav_node_danger[]`
- `nav_node_glory[]`
- (optional usage counters)

**Links**:
- `nav_link_from[]`, `nav_link_to[]`
- `nav_link_type[]` – `WALK`, `JUMP`, `DROP`, `PLATFORM`, `TELEPORT`, `ROCKETJUMP`, ...
- `nav_link_cost[]` (base)
- `nav_link_usage[]`, `nav_link_danger[]`, `nav_link_glory[]`
- Extra data for rocket-jump links (landing spot, impulse used, etc.)

**Link cost function** (used by pathfinding):
```
cost = base_cost
cost *= (1 + danger * factor)
cost /= (1 + usage * factor)
cost /= (1 + glory * factor)
// type-specific bias (e.g. slightly favour known good rocket-jumps)
```

**Decay**: Danger decays relatively quickly; glory more slowly. Called periodically.

**Recording success**:
- Successful movement -> reinforce link / add new link.
- Successful rocket-jump -> specialised record + glory boost.
- Death near a link -> increase danger.

### 5.2 Entity Hybrid (Optional)

Entities can still be used for debugging, special nodes (buttons, platforms), or as a thin wrapper around array indices.

### 5.3 Persistence

Save/load a compact `.nav` file containing nodes, links, learning values, and rocket-jump records. Format can start as simple text and later become binary.

**Key operations (QuakeC-style)**:
- `Nav_FindOrAddNode(origin, flags)`
- `Nav_AddLink(from, to, type, base_cost)`
- `Nav_RecordRocketJump(start, landing, impulse, rocket_z)`
- `Nav_LinkCost(link)`
- `Nav_Decay()`

---

## 6. Pathfinding

### 6.1 Base A* on the Array Mesh

Standard A* using the learning-aware `Nav_LinkCost`. Open set can start as a simple array (upgrade to heap later if needed). Path is reconstructed via parent pointers.

Core temporary arrays:
- `astar_g[]`, `astar_f[]`, `astar_parent[]`, `astar_closed[]`, open set array.

### 6.2 Jump Point Search (JPS) – Exploration

Classic JPS is excellent on uniform-cost grids but does **not** map cleanly onto our irregular 3D graph with heterogeneous link types and changing costs.

**Useful ideas we can still adopt**:
- Parent-aware / arrival-direction pruning.
- "Forced neighbour" style rules based on link type (e.g. after a DROP or ROCKETJUMP, restrict sensible continuations).
- Collinearity pruning on long walkable corridors.

Full classic JPS is not recommended as a primary algorithm here.

### 6.3 Hierarchical Pathfinding (Recommended)

**Two-level Key-Node Hierarchy** is the practical choice.

**Level 0**: Full detailed mesh (with live learning).
**Level 1**: Much smaller set of **key nodes**.

**Key node categories / flags**:
- `KEY_ITEM` – near weapons, armour, health
- `KEY_TELEPORT`
- `KEY_ROCKETJUMP` – proven takeoff/landing pads
- `KEY_JUNCTION` – high connectivity
- `KEY_PLATFORM`
- `KEY_LEARNED` – promoted by usage/glory
- `KEY_DANGEROUS` – high sustained danger (usually avoided or heavily penalised)

**Promotion rules** (periodic rebuild):
- Always include static important locations (items, teleporters...).
- Promote proven rocket-jump endpoints.
- Score remaining nodes by glory + usage - danger + degree; promote the best.
- Soft cap on total key nodes; demote weakest learned nodes first.

**Search flow**:
1. Find nearest key nodes to start and goal.
2. A* on the abstract key graph.
3. Stitch detailed A* segments between consecutive key nodes.
4. Follow the resulting node list.

**Path following**:
- Look-ahead / pure-pursuit style (consider the node after next when visible and close).
- Special movement states for rocket-jumps, drops, and platforms.
- Use `runplayerphysics` for smooth locomotion.

**Data structures for key layer**:
```quakec
float nav_key_count;
float nav_key_node[MAX_KEY_NODES];     // indices into main node arrays
float nav_key_flags[MAX_KEY_NODES];
```

---

## 7. Quake Cartographer – Offline BSP Pre-processor

External tool that ingests a `.bsp` and produces a high-quality initial `.nav` seed file.

**Pipeline**:
1. Parse BSP (faces, planes, clip hulls, entities, textures).
2. Identify walkable surfaces (upward-facing, non-sky, non-liquid, reasonable slope).
3. Merge coplanar faces so the bot sees continuous floors instead of fragmented geometry (directly addresses the "floor made of many squares" confusion).
4. Place nodes:
   - Centres of walkable regions
   - Extra density on long corridors
   - Guaranteed nodes at items, weapons, teleporters, buttons, platform endpoints
5. Generate initial links via player-hull traces; classify as WALK / JUMP / DROP / etc.
6. Optionally flag candidate rocket-jump opportunities (unproven).
7. Write `.nav` file in the exact format the live bot expects.

The live bot loads this seed, then continues to learn, reinforce, and discover on top of it.

---

## 8. Visualisation & Debugging

### In-Game Debug View (cvar-driven)

**Cvars** (examples):
- `bot_nav_debug` (0-3)
- `bot_nav_debug_keys`
- `bot_nav_debug_links`
- `bot_nav_debug_detailed`
- `bot_nav_debug_path`

**Visual language**:
- Ordinary nodes – small dark grey spheres
- Key Item – bright green
- Key Teleport – cyan
- Key Rocket-Jump – orange/gold, larger + vertical spike
- Key Junction/Learned – yellow
- Key Dangerous – red (optionally pulsing)
- Abstract key links – thick light-blue/white lines
- Current hierarchical path – thick magenta
- Detailed underlying links (when enabled) – thin dark grey

Drawing is performed with the `drawline` / `drawsphere` builtins and only when the relevant cvars are enabled.

### Optional External Export

Dump key nodes and abstract links as point entities (or JSON/CSV) for inspection in TrenchBroom or similar tools.

---

## 9. Example Bot Think Loop (High Level)

```quakec
void() Bot_Think = {
    Bot_UpdateEnemy();
    Bot_UpdateGoals();

    // High-level state machine
    if (self.bot_state == STATE_ENGAGE)
        Bot_CombatDecide();
    else if (self.bot_state == STATE_HUNT)
        Bot_HuntDecide();
    else
        Bot_ExploreDecide();

    // Movement using real physics
    vector wish = Bot_CalculateWishVelocity();
    self.bot_wish = self.bot_wish * 0.7 + wish * 0.3;

    float result = trymove(self, self.bot_wish, 0);
    if (result & MOVE_BLOCKED)
        self.bot_wish = Bot_SlideWish(self.bot_wish);

    self.velocity = self.bot_wish;
    runplayerphysics(self);

    // Opportunistic rocket-jump testing via simulation
    if (Bot_ShouldConsiderRocketJump()) {
        simtrajectory(...);
        if (good landing) {
            Bot_PerformRocketJump();
            Bot_RememberSuccessfulRJ(...);
        }
    }

    // Periodic learning / nav update
    if (time > self.next_learn_time) {
        Bot_UpdateNavMesh();
        self.next_learn_time = time + 0.5;
    }

    if (cvar("bot_debug"))
        Bot_DrawDebug();

    self.nextthink = time + 0.05;
};
```

---

## 10. Suggested Implementation Roadmap

1. Fork QuakeSpasm -> raise limits, add `tracebox` + `trymove`.
2. Expose real player physics to bots.
3. Implement `simtrajectory` and basic file I/O.
4. Build the array-based navmesh + learning (usage/danger/glory) + basic A*.
5. Add debug drawing so the mesh is visible.
6. Implement key-node hierarchy + stitching + smooth path following.
7. Add rocket-jump discovery loop that uses simulation + recording.
8. Build Quake Cartographer for good initial seeds.
9. Iterate on personalities, combat state machine, and cooperative (Zeus-style) behaviours.
10. Polish persistence, promotion rules, and visualisation.

---

## 11. Design Philosophy Summary

- Prefer **engine primitives** that remove artificial QuakeC limitations over trying to be clever inside pure classic QuakeC.
- Keep intelligence (learning, decisions, personalities) in QuakeC so it remains hackable and understandable.
- Learning should be visible and debuggable.
- Rocket jumps should be *discovered*, not merely scripted.
- Movement should feel like a skilled human player, not a script on rails.
- Hierarchy gives speed and better tactical decisions without sacrificing local precision or learning.
- Start simple (flat A* + good primitives) and layer hierarchy and learning on top.

---

## 12. Quick Reference – Key Builtins & Concepts

| Feature                    | Purpose                                      | Priority |
|---------------------------|----------------------------------------------|----------|
| Raised limits             | Dynamic mesh + learning state                | Critical |
| `tracebox` / `trymove`    | Honest reachability & prediction             | Critical |
| `runplayerphysics`        | Smooth human-like movement                   | Critical |
| `simtrajectory`           | Rocket-jump discovery                        | High     |
| Bot client slots          | Clean multi-bot support                      | High     |
| Sandboxed file I/O        | Persistent learning                          | High     |
| Debug draw primitives     | Visibility of mesh, hierarchy, paths         | High     |
| Array navmesh + learning  | Core intelligence                            | Core     |
| Key-node hierarchy        | Scalable long-range planning                 | High     |
| Quake Cartographer        | Good initial seeds                           | Medium   |

---

*End of document.*

This file is intended as a living reference for implementing the full system. All major design decisions, historical context, engine requirements, data structures, pathfinding approaches, tooling, and visualisation strategies discussed in the conversation are captured here.
