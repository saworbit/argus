# Co-op Companion AI and Campaign Lab Mode

**Date:** 2026-09-02  
**Scope:** Vanilla QuakeC loop (no neural-net / RL path). Testable, incremental implementation brief.  
**Core Goal:** Transform Argus from a deathmatch combatant into an intelligent, fair co-op companion, backed by campaign telemetry validation.

---

## 0. Existing Foundation (Do Not Rebuild)

Argus already possesses the hardest components of bot navigation:
- **Vortex navmesh**: Incremental, spawn/item seeded, zero pre-baking.
- **Phantom apprenticeships**: Physics-validated edges without artificial teleport shortcuts.
- **Cursed / glory nodes**: Stuck-learning and death/kill bias with decay.
- **Vortex telechains**: One-way teleporter edges.
- **Ripple oracles**: Button / plat / door cascade prediction.
- **Puppet client**: Walks real engine geometry to validate legal links.
- **Lab loop**: Closed-loop telemetry in, A/B comparison out, explicit parameter folding.

This stack already solves the fundamental portability challenge: *a player or mapper drops a map in and bots can navigate it immediately*. The remaining work is **behaviour**, not navigation.

---

## 1. Design Principles

Every addition must maintain three core properties:
1. **Readable**: A human developer can look at a stall on a lift or door and identify the exact rule that fired.
2. **Portable**: Drop in any new map, run the lab, and get a working match without hand-placed waypoints.
3. **Fair**: Bots never vacuum items through walls, steal the player's weapon drops, or cheese co-op objectives.

---

## 2. Workstream A — Co-op Companion

### 2.1 Four-Slot LIFO Goal Stack

Replace rigid "current target / current item" states with a lightweight, QuakeC-friendly 4-slot LIFO goal stack:

```c
enum GoalKind {
    GOAL_NONE,
    GOAL_ESCORT,          // Stay near teammate (moving annulus)
    GOAL_COVER,           // Hold lane / doorway while human acts
    GOAL_ENGAGE,          // Fight a monster (or pack)
    GOAL_INTERACT,        // Button, key door, plat, shootable secret wall
    GOAL_FETCH,           // Get a key / required quest item, then return
    GOAL_REVIVE_SUPPORT,  // Loiter at corpse / backpack; guard without looting
    GOAL_RETREAT          // Health critical; fall back to human or cover
};

struct Goal {
    float    kind;
    entity   subject;      // Player, monster, button, door, item
    vector   anchor;       // Fallback position if subject moves/dies
    float    priority;     // Higher priority wins on push
    float    timeout;      // Think-time expiration
    float    flags;        // Sticky, interruptible, exclusive
};
```

#### Push / Pop Rules
- **Combat interrupts escort**: Pushing `GOAL_ENGAGE` suspends `GOAL_ESCORT`. When threats are neutralized, pop back to escort.
- **Interact / Fetch are sticky**: Do not drop a key run because a distant grunt barked.
- **Cover is requested**: Push `GOAL_COVER` when the human stands still at a button/locked door/plat for $N$ seconds or lines up a tricky jump.
- **Single-carrier fetch**: Never allow two bots on `GOAL_FETCH` for the same item. First claim wins; others escort or cover.

### 2.2 Think Tick Execution Loop

```c
void BotCoopThink()
{
    BotScanThreats();          // Monsters in awareness radius
    BotScanHuman();            // Teammate position, health, facing, last item
    BotScanInteractables();    // Ripple candidates in LOS / audible range

    // 1. Hard interrupts
    if (self.health + self.armortype * self.armorvalue < RETREAT_THRESH)
        GoalPush(GOAL_RETREAT, teammate, 90, 3.0);
    else if (VisibleMonsterThreat() && GoalTopKind() != GOAL_ENGAGE)
        GoalPush(GOAL_ENGAGE, nearest_threat, 80, 8.0);

    // 2. Opportunity goals (when stack is at escort or empty)
    if (GoalTopKind() <= GOAL_ESCORT)
    {
        if (NeededKeyInSight() && !KeyClaimedByOtherBot())
            GoalPush(GOAL_FETCH, key_ent, 70, 20.0);
        else if (HumanStuckAtInteractable())
            GoalPush(GOAL_COVER, teammate, 60, 6.0);
        else if (TeammateCorpseFresh())
            GoalPush(GOAL_REVIVE_SUPPORT, corpse, 65, 10.0);
    }

    // 3. Expire / complete
    GoalTickTimeouts();
    if (GoalComplete(GoalTop()))
        GoalPop();

    // 4. Act
    switch (GoalTopKind())
    {
        case GOAL_ESCORT:         ActEscort(); break;
        case GOAL_COVER:          ActCover(); break;
        case GOAL_ENGAGE:         ActEngageMonster(); break;
        case GOAL_INTERACT:       ActUseRipple(); break;
        case GOAL_FETCH:          ActFetchAndReturn(); break;
        case GOAL_REVIVE_SUPPORT: ActGuardBackpack(); break;
        case GOAL_RETREAT:        ActFallBack(); break;
        default:                  ActEscort(); break;
    }
}
```

### 2.3 Escort Annulus Movement

Rather than rigid point-following that causes door jams and lift crushes, escort operates within a moving annulus:

```c
void ActEscort()
{
    vector p = teammate.origin;
    float dist = vlen(self.origin - p);

    // Too far: path to 192-256u behind teammate look vector
    if (dist > 320)
        BotMoveTo(p - teammate.v_forward * 192);

    // Sweet spot: strafe and face teammate look direction + threat scan
    else if (dist > 128)
        BotStrafeKeepFacing(teammate.angles);

    // Too close: yield space, never body-block jumps or doors
    else
        BotSidestepOffLine(teammate.v_forward);

    // Additive suppressive fire when teammate engages
    if (HumanIsFiring() && VisibleSharedTarget())
        BotAddSuppressiveFire();
}
```

### 2.4 Covering Fire & Splash Safety

Reuse Predator / Mastermind targeting filters:
1. Target must be a monster (or shootable button marked by ripple oracle).
2. Target is in teammate's view cone or crossing path.
3. Splash-safe check before firing Rocket Launcher or Grenade Launcher near allies:
   ```c
   float SplashSafe(entity shooter, entity victim, entity ally)
   {
       if (weapon_is_hitscan) return TRUE;
       if (vlen(victim.origin - ally.origin) < 160) return FALSE;
       if (trace_from_impact_to_ally_is_short) return FALSE;
       return TRUE;
   }
   ```

### 2.5 Fairness Layer & Claim Mutex

| Resource | Rule |
| :--- | :--- |
| **Weapons on Map** | Human has first claim for 2–3s after spawn/reveal. Bot takes only if human is >512u away or already owns the weapon. |
| **Keys** | Exactly one carrier. Bot fetches only if human is fighting or down. Deliver directly to locked door; no pocket-touring. |
| **Backpacks / Corpses** | Bot never loots a teammate's dropped pack. Guards it until respawn. |
| **Health / Cells** | Bot skips Megahealth / 100s if teammate is below 50 HP and in range. |
| **Kills** | Finishing tagged monsters is allowed. Sniping lined-up grunts at point-blank is suppressed (300–500ms hold fire if human has LOS). |

#### Item Claim Mutex
```c
.entity claimed_by;
.float  claim_time;

float TryClaim(entity item)
{
    if (item.claimed_by && item.claimed_by != self && time < item.claim_time + 3.0)
        return FALSE;
    item.claimed_by = self;
    item.claim_time = time;
    return TRUE;
}
```

### 2.6 Revive Support & Backpack Guarding

On teammate death:
1. Push `GOAL_REVIVE_SUPPORT`.
2. Path to corpse origin. Hold perimeter and eliminate incoming monsters.
3. Do not touch or loot the backpack.
4. When teammate respawns, pop goal and resume escort (optional path-ping to backpack).

### 2.7 Keys, Doors, and Ripples

- Path to the **stand-pad** (clear floor point with line of sight to trigger/button), never brush origins.
- Ripple edges are the only valid connections across keyed doors (treated as one-way until key is possessed).
- **Lab Assertion**: On E1M1 / E1M2 / E2M3, a solo bot with `+coop 1` must reach the gold-key door with the key in inventory, or fail with a named reason (`NO_RIPPLE`, `KEY_UNCLAIMED`, `STUCK_LIFT`).

---

## 3. Workstream B — Campaign Lab Mode

Extend the deathmatch lab loop to single-player/co-op campaign maps (`id1` episode maps):

1. **Map Suite**: `start`, E1M1–E1M7, with stretch maps (E2M3, E3M4, E4M2).
2. **Win Conditions**: Exit trigger activation, or named checkpoint (gold key secured, silver door opened, Chthon defeated).
3. **Fail Taxonomy**:
   - `STUCK_TIMEOUT` (stalled > $N$ seconds)
   - `EDICT_OVERFLOW` (entity budget exceeded)
   - `LAVA_DEATH_LOOP` (persistent liquid hazards)
   - `KEY_UNCLAIMED` (key neglected)
   - `NO_RIPPLE` (ripple oracle failed to solve door/switch cascade)
4. **Dual-Seat Evaluation**:
   - **Seat A (Autonomous)**: Solo bot — verifies "can it finish the level".
   - **Seat B (Companion)**: Bot + puppet-human walking recorded path — measures escort fidelity without blocking.
5. **Telemetry Counters**:
   - `escort_break_s`: Time spent >512u away from teammate.
   - `steal_events`: Weapons, packs, or megas picked up against fairness rules.
   - `block_events`: Bot origin inside human AABB during jumps or door interactions.

---

## 4. Workstream C — Deathmatch Polish Transfer

Enhancements that immediately benefit deathmatch:
1. **Stand-Pad Targeting**: Path to reachable floor cells rather than brush origins for lifts, doors, and triggers.
2. **Body-Block Clearance**: If within 48u of teammate and teammate is jumping or firing, sidestep immediately.
3. **Shared-Target Hold Fire**: 300–500ms delay when ally has point-blank line of sight to a target.
4. **Item Mutex in DM**: Claim mutex prevents multiple bots from colliding on the same Megahealth, Quad, or Pentagram.

---

## 5. Scope Boundaries (What NOT to Do)

- **No Neural Networks**: Pure readable QuakeC only.
- **No Hand-Placed Waypoints**: If Vortex/ripple struggles on E1M1, fix the algorithm; never paper over it with manual nodes.
- **No Combat Rewrite**: Retain the proven Predator / Mastermind combat engine; co-op only filters target selection.
- **No Game Balance Overhaul**: Keep vanilla co-op rules (shared weapons, standard respawns); let the bot be an honorable partner within stock mechanics.
- **No Premature Voice Barks**: Solidify the goal stack and navigation before adding cosmetic chat hooks.

---

## 6. Implementation Roadmap

| Step | Milestone | Lab Verification Proof |
| :---: | :--- | :--- |
| **1** | Goal stack + Escort annulus on E1M1 | `escort_break_s` minimized; zero door jams in 3 minutes |
| **2** | Claim mutex table for weapons, keys, and backpacks | `steal_events == 0` on scripted path |
| **3** | Engage filter: monsters only, splash-safe vs allies | Teammate never gibbed by bot RL/GL |
| **4** | Ripple commit for gold key $\rightarrow$ gold door | Bot arrives at door *with* key in inventory |
| **5** | Campaign lab harness + fail taxonomy | Single CLI command, JSON/QC dump line for E1M1 & E1M2 |
| **6** | Revive support + backpack guarding | Backpack remains intact until player respawn |
| **7** | Multi-bot coordination: mutex on `GOAL_FETCH` | Two bots never fight over the same key or jam doors |
