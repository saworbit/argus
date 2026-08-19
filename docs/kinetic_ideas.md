# KINETIC capture: roadmap ideas and reference spec

Provenance: pasted by Shane on 2026-08-17 with the instruction "ignore
the name - but capture this as roadmap and ideas in the repo". The
project remains Argus; "Project KINETIC" is kept below only because it
is the name inside the captured document. The spec reads like a
blue-sky engineering blueprint for a modernised QuakeWorld bot stack.
It was not written against Argus's constraints, so this file starts
with a triage: what Argus can adopt as-is, what fits the offline
tooling layer, and what would require abandoning the vanilla charter.

## Triage against the Argus hard constraints

Argus's charter (CLAUDE.md): pure vanilla QuakeC, protocol 15,
max_edicts 600, no engine extensions, the engine is a test harness and
never a dependency. Each KINETIC idea lands in one of three buckets.

### Bucket 1: adoptable in pure vanilla QuakeC (M4-M6 candidates)

- Damped-spring aim model (spec 6.4). Second-order tracking with
  overshoot and micro-correction, damping ratio ~0.72, rate cap near
  human biomechanics, perceptual noise. Direct upgrade to the current
  rate-limited tracker; a few floats per bot, entirely QC. Strong M4
  candidate alongside per-bot skill parameters.
- Tactical state machine: fake retreat, corner ambush, arrival-time
  estimation (spec 8.1, 11.2). The native builtin it proposes (#501)
  is just a traceline plus corner-apex offset, expressible in pure QC.
  Fits M4 personalities (a cunning parameter).
- Item clocks and delay desynchronisation (spec 8.2). Bots already
  know item entities; tracking respawn timers and deliberately
  delaying pickups is bookkeeping. M4/M5.
- Dynamic combat postures by frag delta (spec 8.3): leading = play
  item control, trailing = aggression, stalemate = ambush. Cheap
  scalar stance selection over systems Argus already has.
- Causality property graph (spec 5.2): button -> door -> region
  dependency edges compiled offline from the entity lump (navgen
  already parses it) and expressed as typed nav links or goal
  preconditions at runtime. This is the vanilla-shaped core of the
  GOAP idea; full 64-bit GOAP bitmasks are not (QC floats give 23
  safe mask bits).
- Rocket-jump tables (spec 5.3): landed as prize-only typed pads
  (Argus_NavLinkRocket). Navgen solves the arc offline (100-240u
  rise, horiz to 260u, rise-then-drift clearance); runtime faces
  the landing and pitches 85/75/65, then jump + rocket. dm4 quad
  pad is node 142 at 209 -183 -296 onto 56. Remaining work is the
  A/B (does a bot hold the ledge) and any extra prize landings,
  not the mechanism.
- Sound awareness (spec 7.3, partial): vanilla QC cannot hook engine
  sound propagation, but most tactically meaningful sounds originate
  in QC we control (pickups, weapon fire, teleporters, doors). A
  QC-level "noise event" board that bots poll would approximate
  auditory perception without any engine help. PVS occlusion is not
  available; distance plus a traceline is the honest approximation.
- Context steering fields (spec 6.3): weighted sum of goal direction,
  dodge, wall repulsion and spacing. Argus_HazardSteer is the first
  slice: hold the last safe deflection yaw so the +50/-50 fan does
  not dither. Formalising the rest with a few extra tracelines per
  steering tick is still affordable.
- Opponent position hypotheses (spec 7.2, lite): the full particle
  filter is out of budget, but last-seen position plus nav-link
  corridor guesses gives a scalar version in QC.
- Zero-allocation discipline and tiered schedulers (spec 9): QC is
  statically allocated by construction, and Argus already runs tiered
  cadences (per-frame physics, 0.2 s AI ticks, frame-sliced BFS).
  The spec validates the pattern; nothing to port.

### Bucket 2: offline tooling ideas (allowed today, any language)

The charter constrains the shipped progs.dat, not the toolchain.
- NavMesh generation with Hertel-Mehlhorn polygon merging and funnel
  (SSFA) smoothing (spec 5.1, 6.1). A polygon mesh with portal edges
  could be compiled down to richer link data. Caveat: true funnel
  smoothing needs runtime mesh awareness; how much survives the
  compile-to-waypoints step is an open design question. Park until
  waypoint navigation actually limits us.
- qk_compiler ideas generally fold into argus_navgen (Python today,
  Rust only if compile times ever hurt).
- MCP dev server, structured compiler diagnostics, headless
  fast-forward benchmark runner (spec 10). The Windows/Linux rigs
  plus telemetry scripts already fill this role informally. The
  structured-diagnostics idea is a nice-to-have for tooling.
- Match analytics and playstyle tuning loops (spec 4, LLM layer):
  operationally this is exactly the existing telemetry + A/B
  methodology.

### Bucket 3: engine modernisation track (parked; charter decision)

Everything here violates "runs unmodified on any NetQuake engine at
protocol 15" and would change what Argus is. Recorded as a possible
future fork of the project, not as roadmap:
- QuakeWorld / mvdsv / ezQuake / FTEQW base engine selection (spec 2).
- Bots as synthetic clients driving usercmd_t, air-strafe input
  synthesis, sv_airaccelerate 106 bunny-hopping (spec 1.2, 6.2).
  Note: Argus deliberately took the opposite fork (server-side
  entities with QC physics replication).
- 125 Hz fixed-timestep accumulator, 32-bit float angles and coords,
  extended QC VM (int64, pointers), CSQC, HRTF audio, backward
  reconciliation netcode (spec 3).
- Native C builtins for bot tactics (spec 11.1).
If this track is ever opened it is a new deliverable beside the
vanilla one, with the vanilla progs.dat remaining the canonical
Argus. The 1997 marvel test happens on vanilla.

### Factual notes made while capturing

- The spec's critique of QuakeSpasm as a deathmatch base concerns
  netcode for human play; it does not affect Argus's use of
  QuakeSpasm as a headless lab harness.
- The 24-bit mantissa limit (spec 3.1) is real and Argus already
  lives inside it (an_jumpmask uses 8 bits; item flags stay below
  bit 23).
- The 8-bit angle quantisation (spec 3.2) applies to client view
  angles on the wire; server-side bot aim in QC is full float and
  unaffected, another argument for the server-side fork Argus took.

---

## Captured specification (content preserved, formatting cleaned)

# Comprehensive Engineering Specification & Architectural Blueprint: Project KINETIC

## 1. Executive summary & design philosophy

Project KINETIC is an end-to-end modernization of the id Tech 2 /
QuakeWorld engine architecture, competitive deathmatch design, and
autonomous AI dueling systems.

### 1.1 The fundamental flaws of legacy systems

Classic Quake bot architectures (such as Reaper Bot, Frogbot, and
Frikbot) pioneered FPS AI in the late 1990s but suffer from
fundamental architectural bottlenecks:

- Discrete node snapping: bots navigate by moving in straight lines
  between discrete 3D waypoints, instantly pivoting upon reaching node
  radii. This creates the characteristic "on-rails" movement.
- Deterministic point-and-click aim: view vectors snap instantaneously
  to target centroids within a single frame, lacking physical inertia,
  biomechanical reaction latency, overshoot, or micro-corrections.
- Lack of environmental causality: spatial graphs only evaluate
  coordinate distances (x, y, z). Bots are incapable of solving
  multi-step causal puzzles (e.g., shoot wall button -> bridge extends
  -> cross bridge -> collect prize).
- Hardcoded physics exploits: complex maneuvers like rocket jumps,
  ramp-slides, or plasma boosts require hardcoded map flags rather
  than dynamic kinematic computation.
- Predictability and exploitable heuristics: legacy bots blindly
  pursue fixed items on exact timers without tactical retreat, sound
  discipline, or bluffing.

### 1.2 Core architectural principles

- Kinematic-driven, input-only agent execution: bots never directly
  set their origin or velocity. They interact with the game engine
  exclusively via synthetic client frames (usercmd_t), driving the
  physics engine via sv_airaccelerate 106, bunny-hopping, and momentum
  surfing.
- Strict computational tiering: high-cost geometric and
  physics-sweeping math is computed offline in a dedicated Rust
  preprocessor (qk_compiler). Real-time path smoothing and
  biomechanical tracking run in a native engine core (C/Rust FFI).
  Macro-strategy and development diagnostics are managed via an LLM
  meta-layer hooked through a Model Context Protocol (MCP) server.
- Engine precision modernization: quantized 1996 data formats (8-bit
  byte angles, 13.3 fixed-point networking, variable-timestep physics)
  are replaced with full 32-bit floating-point protocols and decoupled
  125 Hz physics accumulators.

## 2. Competitive deathmatch & engine lineage selection

    NetQuake lineage                 | QuakeWorld lineage
    (FitzQuake -> QuakeSpasm         | (QW -> ezQuake / FTEQW / mvdsv)
     -> Ironwail)                    |
    - single-player optimized        | - multiplayer / competitive focus
    - rendering fidelity             | - client-side prediction, sub-tick
    - high polygon limits            | - uncapped FPS, decoupled physics
    - sluggish netcode for DM        | - chosen foundation for KINETIC

### 2.1 Why QuakeSpasm is the wrong base for deathmatch

QuakeSpasm derives from the NetQuake single-player branch. While
visually polished, its networking architecture waits for server round
trips to confirm local movement and firing, resulting in perceived
latency. Modifying QuakeSpasm for modern DM would require backporting
the entire QuakeWorld network protocol.

### 2.2 The selected foundation: QuakeWorld / FTEQW / mvdsv

The definitive base builds upon mvdsv (server), ezQuake / FTEQW
(client/engine), or Ironwail backported with QuakeWorld networking:

- Decoupled 125 Hz physics accumulator: completely separates rendering
  framerates (360 Hz+) from server physics ticks, ensuring identical
  movement physics on all displays.
- Sub-tick action queuing and backward reconciliation: lag
  compensation for hitscan weapons (super shotgun, lightning gun)
  ensuring registration at 50-70 ms pings.
- Client-side QuakeC (CSQC): decouples UI, HUD, and custom spectator
  killfeeds from engine C code.
- Binaural spatial HRTF audio (OpenAL): 3D vertical sound localization
  allowing players and bots to pinpoint whether an item was collected
  above or below them through geometry.

## 3. High-precision engine modifications

    Subsystem               | Legacy 1996 limit     | KINETIC v3.0
    ------------------------|-----------------------|--------------------
    View angles             | 8-bit byte (1.406 deg)| 32-bit float
    Entity coordinates      | 13.3 fixed-point      | 32-bit float
    QuakeC VM numeric type  | 24-bit mantissa float | native int32/int64
    Physics step            | variable (frametime)  | fixed 125 Hz tick
    BSP plane intersections | 32-bit float          | 64-bit double interm.

### 3.1 The 24-bit mantissa problem & extended QuakeC VM

Vanilla QuakeC treats all numbers as single-precision 32-bit floats.
Because IEEE 754 floats allocate only 24 bits to the mantissa, bitwise
operations on integer bitmasks above bit 24 (2^24 = 16,777,216)
silently corrupt. Modernization: the engine integrates extended VM
compilers (FTEQCC / GMQCC) supporting native int32, int64, typed
pointers, and array structures directly within QuakeC bytecode.

### 3.2 View angle quantization removal

Legacy Quake compresses client angles into a single byte (360/256 ~=
1.406 degree steps). At a distance of 800 units, one byte increment
shifts the crosshair by ~19.6 units (nearly the width of an entire
player model). Modernization: enable FTE_PEXT_FLOATCOORDS /
uncompressed 32-bit float view angles in usercmd_t, providing
sub-0.0001 degree rotational granularity for smooth tracking.

### 3.3 Fixed-timestep physics accumulator

```c
void Host_Frame(float real_frametime) {
    static float accumulator = 0.0f;
    const float FIXED_TICK = 1.0f / 125.0f; // 125 Hz physics
    accumulator += real_frametime;
    while (accumulator >= FIXED_TICK) {
        SV_Physics_RunTick(FIXED_TICK); // Deterministic bot/player simulation
        accumulator -= FIXED_TICK;
    }
    R_RenderView(accumulator / FIXED_TICK); // Render view interpolation
}
```

## 4. End-to-end system architecture

    OFFLINE / TOOLING LAYER
      [.bsp map file] -> [qk_compiler (Rust CLI)]
        -> .qnav (simplified navmesh)
        -> .qcpg (causality property graph)
        -> .qlut (kinematic jump tables)
      direct ingestion at map load (<5 ms)

    ENGINE RUNTIME
      Strategic meta-brain
        - 64-bit GOAP backward planner
        - incomplete-information particle filter
        - opponent item clocks and delay desync
      Tactical movement and neuromorphic aim
        - Simple Stupid Funnel Algorithm (SSFA) polygon splines
        - context steering fields: F_goal + F_dodge + F_wall + F_spacing
        - second-order damped spring dynamics (PID tracking)
      Synthetic client input layer (125 Hz tick engine)
        - optimal air-strafe yaw rate (sv_airaccelerate 106)
        - continuous usercmd_t generation (forwardmove, sidemove, angles)

    LLM META-LAYER & MCP TOOLCHAIN
      [LLM strategist] <-> [Rust MCP server] <-> [headless mvdsv]
      - match log analytics   - tool interfaces    - 100x sim runner
      - playstyle tuning      - QC compiler bridge - memory inspector

## 5. Offline preprocessor: qk_compiler (Rust)

Written in Rust using multi-threaded execution (Rayon), qk_compiler
extracts and compiles geometric and kinematic metadata ahead of time.

### 5.1 NavMesh generation & Hertel-Mehlhorn polygon merging (.qnav)

- Hull 1 extraction: parses LUMP_CLIPNODES and LUMP_PLANES for the
  player bounding box (32x32x56 units).
- Walkable plane filter: extracts surface polygons where the surface
  normal's z component >= 0.7071 (45 degree slope limit).
- Convex partitioning and simplification: standard BSP compilation
  creates thousands of tiny fragmented triangles. qk_compiler applies
  a Hertel-Mehlhorn polygon merging algorithm to merge adjacent
  coplanar triangles sharing an edge, provided the resulting polygon
  remains strictly convex (<= 8 vertices).
- Performance impact: reduces a map like dm6 from 2,840 triangles to
  214 convex polygons, allowing A* path queries to resolve in <= 12
  microseconds.

### 5.2 Causality property graph builder (.qcpg)

- Entity lump extraction: reads LUMP_ENTITIES (lump 0) ASCII
  dictionary blocks.
- Link resolution: matches every interactive actuator (func_button,
  trigger_multiple) to its slave entity (func_door, func_plat,
  trigger_teleport) via target -> targetname.
- Trigger classification: labels activation mechanisms:
  - ACTUATOR_TOUCH: stepping inside a trigger volume.
  - ACTUATOR_SHOOT: inflicting damage on buttons where health > 0.
  - ACTUATOR_TIMED: periodic or delayed state resets.

### 5.3 Ballistic rocket jump raymarcher (.qlut)

- Scans all node pairs (A, B) where vertical elevation difference
  dz = zB - zA is in [64, 380] units.
- Calculates required vertical impulse velocity:
  v_z0 = sqrt(2 * g * (zB - zA)), with g = 800 units/s^2.
- Evaluates base jump impulse (270 units/s) combined with rocket
  splash knockback (~300 units/s).
- Executes a parabolic 3D swept-cylinder collision test across hull 1
  clipnodes. If collision-free, writes a binary kinematic rocket jump
  record:

```rust
#[repr(C)]
pub struct KinematicJumpRecord {
    pub start_polygon_id: u32,
    pub target_polygon_id: u32,
    pub aim_pitch: f32,       // -85.0 degrees
    pub aim_yaw_offset: f32,  // directional push angle
    pub damage_cost: u16,     // ~45 HP
    pub required_weapon: u8,  // IT_ROCKET_LAUNCHER
}
```

## 6. Dynamic movement & neuromorphic aim systems

### 6.1 Simple Stupid Funnel Algorithm (SSFA)

To eliminate linear node hopping, the bot calculates smooth splines
across walkable polygon portals (string-pulled trajectories around
corner apexes instead of node-to-node beelines).

### 6.2 Continuous air-strafing controller

To accelerate while airborne under sv_airaccelerate 106, the bot
synthesizes the optimal turning rate per tick (as captured, formula
garbled in transit; the shape is):

    omega_optimal = (1/dt) * arccos(min(1.0, (30 - 106*30*dt) / v_horizontal))

The input generator continuously applies
usercmd_t.angles.yaw += omega_optimal * dt while holding
sidemove = 400, executing mathematically optimal strafe-jumping
without artificial speed hacks.

### 6.3 Context steering potential fields

Micro-navigation calculates a composite directional vector every 5
ticks:

    V_desired = w1*F_path + w2*F_rocket_dodge + w3*F_wall_repulsion
                + w4*F_opponent_spacing

### 6.4 Neuromorphic damped spring aim model

Replaces instant angle snapping with a second-order damped harmonic
oscillator:

    theta'' + 2*zeta*omega_n*theta' + omega_n^2 * (theta - theta_target) = 0

- Damping ratio zeta = 0.72: produces human-like slight overshoot on
  high-speed flick shots followed by a ~40 ms micro-correction.
- Natural frequency omega_n = 28.0 rad/s: caps rotational velocity to
  human biomechanical limits (~900 deg/s).
- Perceptual noise (1/f drift): continuous micro-jitter prevents
  synthetic pixel-locking on targets.

## 7. Strategic intelligence, sensory models & GOAP

### 7.1 Goal-oriented action planning (GOAP)

World states are evaluated as a 64-bit integer bitmask:

```c
#define WS_HAS_RL            (1ULL << 0)
#define WS_HAS_LIGHTNING     (1ULL << 1)
#define WS_HP_GT_50          (1ULL << 2)
#define WS_RED_ARMOR_ACTIVE  (1ULL << 3)
#define WS_DOOR_BRIDGE_OPEN  (1ULL << 4)
#define WS_AT_HIGH_LEDGE     (1ULL << 5)
```

The planner performs backward-chaining A* search over atomic actions,
e.g. Collect(Red_Armor) requires WS_DOOR_BRIDGE_OPEN, which chains to
ShootButton() requiring WS_HAS_RL, which chains to
PickupItem(item_rockets).

### 7.2 Incomplete-information particle filter

When an opponent breaks line of sight, the bot spawns 50 hypothesis
particles along probable escape corridors on the navmesh. Particles
update based on movement speed and are culled when the bot inspects a
sector and confirms it empty.

### 7.3 PVS auditory raycasting & stealth

- Acoustic occlusion: when an engine sound() event occurs, the bot
  checks the potentially visible set (PVS). Sounds within the same PVS
  leaf provide exact 3D coordinates; occluded sounds undergo distance
  and portal dampening.
- Noise discipline (shift-walking): when setting an ambush or
  retreating on low health, the bot enters silent walking to cut off
  footstep audio.

## 8. Cunning combat tactics & psychology

### 8.1 Fake retreat & corner trap ambush

When low on health (<60 HP) with an aggressive pursuer:

1. Bait sprint: the bot sprints away around a blind 90 degree corner.
2. Ambush set: the moment line of sight breaks, it zeroes velocity,
   drops into silent walk, turns 180 degrees, and pre-aims at the
   floor of the corner apex.
3. Arrival timing estimation:
   t_intercept = dist(enemy, apex) / max(|v_enemy|, 320).
4. Spring the trap: at t = t_intercept - 0.04 s, fires a pre-aimed
   rocket at the corner floor, instantly queuing a switch to the super
   shotgun for a follow-up meatshot.

### 8.2 20-second item delay desynchronization

If the bot maintains full map control, it intentionally delays
collecting major items (red armor / megahealth) for 3 to 7 seconds
after spawn, desynchronizing the opponent's internal clock and
catching them out of position.

### 8.3 Dynamic combat postures

    Match situation      | Adopted tactical stance
    ---------------------|------------------------------------------
    Leading (+3 frags)   | strict item clocks (defensive), long-range
                         | denial and grenades, refuses risky rocket
                         | jumps
    Trailing (-2 frags)  | high aggression and desperation, aggressive
                         | rocket jump flanks, forces point-blank
                         | shaft duels
    Stalemate            | stealth shift-walking, ambush traps and
                         | fake retreats

## 9. Performance hardening & static memory model

To maintain a sub-millisecond execution envelope across 8 to 16
concurrent bots, all dynamic heap allocations are banned from the
real-time frame loop (static per-slot arenas: path polys, portals,
steering vectors, world-state masks, ambush timers).

Multi-ring time-sliced scheduler:

    125 Hz (every tick)   | synthetic usercmd_t, PID aim, air-strafe yaw
    25 Hz (every 5 ticks) | SSFA funneling, context steering, dodge rays
    5 Hz (every 25 ticks) | opponent tracking, item clocks, auditory PVS
    1 Hz / event-driven   | GOAP long-term planning, global A* rerouting

## 10. Rust implementation sketch: Quake dev MCP server

Implemented reading (vanilla charter): `tools/argus_mcp/` version
0.18. Operator guide `tools/argus_mcp/README.md`. RCON, mvdsv, and
100x dilation stay parked. The five spec tool names exist as extras
beside the native `see` / `compile_qc` / `cartograph` / `experiment`
/ `tune` set. `see` walks the nav graph including rocket/lift/swim
hops, greps QC, and reads GOAP plan events. Cartograph briefs name
islands and door cuts. `learn_hotspots` writes a cost overlay for
navgen. Humans use `argus-mcp gui` (localhost attach / compile /
backup). Config can discover the tree from
`game/argus/autoexec.cfg`. `matrix_experiment` probes
dm2/dm3/dm4/dm6/lqdm2 after one compile. `match_status since_line`
streams logs without dumping the same tail twice.

Original sketch: a Model Context Protocol server (JSON-RPC over
stdio) giving LLMs access to QuakeC compilation with structured
diagnostics (fteqcc), binary BSP entity-lump inspection, QuakeWorld
out-of-band UDP RCON execution, and fast-forward headless match
benchmarking (100x tickrate) via mvdsv. Tools: quake_compile_qc,
bsp_inspect_entities, rcon_exec, bot_simulate_match. (The capture
included a full ~500-line Rust listing implementing these four tools
plus the JSON-RPC router; the tool surface above is the durable
idea. Argus's Python tooling already covers the same ground
informally: pak_extract, navgen, analyze_match, and scripted
headless matches.)

## 11. Combat state machine sketch

### 11.1 Native C helper (bot_tactics.c)

A proposed engine builtin (#501) that traces bot eye to enemy eye,
detects a blocking corner, offsets the apex 18 units along the plane
normal to clear wall splash, and estimates pursuer arrival time from
distance and speed (floor 320 ups). Note: expressible in pure QC with
traceline; no builtin needed for the Argus version.

### 11.2 QuakeC tactical state machine (bot_combat.qc)

States: NORMAL_COMBAT -> RETREAT_SPRINT (health < 60, armed, pursuer
at 250-850 units) -> AMBUSH_SET (line of sight broken: zero velocity,
silent, pre-aim corner apex floor, equip RL, timeout 2.2 s) ->
SPRING_TRAP (at arrival time minus 40 ms or on visual: fire rocket at
apex floor, queue SSG switch, re-engage aggressively).

## 12. Performance verification matrix (as captured)

    Subsystem                  | Classical      | KINETIC target
    ---------------------------|----------------|---------------------
    NavMesh geometry           | ~3,000 tris    | 150-380 convex polys
    View angle resolution      | 1.406 deg      | 0.0001 deg (float)
    Physics timestep           | 20-72 Hz var.  | 125 Hz fixed
    Pathing compute time       | 0.05 ms        | 0.012 ms (A* + SSFA)
    Frame memory allocations   | dynamic        | zero-alloc arenas
    Server CPU budget (8 bots) | ~0.40 ms       | ~0.14 ms
