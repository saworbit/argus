# Argus optional SLM sidecar (parked)

**Date:** 26 August 2026
**Status:** PARKED. Captured for the record, not scheduled. Shane's call
after review: "just capture the idea but park it."
**Repo:** [saworbit/argus](https://github.com/saworbit/argus) (QuakeC bot + Rust lab MCP 0.18)
**Related:** `tools/argus_mcp/README.md`, `docs/specs/2026-08-17-argus-mcp-design.md`, `docs/mcp_quake_dev_spec.md`

---

## Triage (2026-08-26, why this is parked)

The goal is "the bot as intelligent as possible", and every intelligence
gain in project history has come from the tape-forensics -> QC fix ->
A/B ladder loop, not from a bolted-on brain. Against that goal the
sidecar earns nothing:

- **Mode B duplicates the existing lab advisor.** Claude sessions plus
  the MCP already read the tapes, and a 4B local model reading the same
  compact snapshot is a strictly worse analyst. Its only real pitch is
  offline, unattended, free operation, which nobody currently needs.
  The charter-fit version of "learning" already exists: learn_hotspots
  folding tape evidence into navgen costs.
- **The Mode C pipe as specced does not exist in vanilla QC.** Section 9
  leans on impulse/stuffcmd aliases, but impulses carry one number and
  come only from a client's impulse command (dead on a headless
  dedicated match), while the console inject reaches the server console,
  which no vanilla mechanism lets QC read as text. Strings cannot enter
  the VM from outside, full stop. Floats can: the scratch1-scratch4
  cvars are registered in vanilla NetQuake specifically for QuakeC use
  and `cvar()` is a 1996 builtin. So if Mode C were ever built, it would
  be tactic/route hints packed into a scratch cvar float (bot slot +
  goal-class enum + generation counter), polled on the AI tick.
- **The slice ordering is therefore inverted.** The doc calls chat the
  safest Mode C slice zero, but chat is the one advice kind that cannot
  pass the vanilla channel at all. Chat stays lab-only forever; tactic
  bias is all Mode C could ever be, and tactic bias is a nudge on a
  utility scorer that is already good.
- **Latency is optimistic.** 400-800 ms from a 4B Q4 model on the CPU of
  the same box running the dedicated server will miss more often than
  it hits; fail-closed makes that safe but Mode C would mostly be a
  drop counter on this hardware.

What actually moves intelligence, already measured and queued: the dm2
directed-reach nav campaign, the sprint run-up discipline, the ambush
family, offensive displacement, the dm4 quad-hold proof.

Revisit only if an offline, unattended lab advisor becomes wanted (for
example, continuous 1 Hz match commentary or triage with no agent
session running). If revived: build Mode B slice 1 exactly as written
below, rewrite section 9 around scratch cvars, and drop chat from the
live path entirely.

The design as reviewed follows, unchanged apart from em-dash cleanup to
meet the project's editorial rule.

---

## 1. One-line pitch

Argus stays a vanilla QuakeC deathmatch bot. A small language model is an optional sidecar that can advise the lab, and later the live match, through MCP. If the model is missing, slow, or wrong, the bot plays exactly as it does today.

---

## 2. Why this exists

Argus already has a closed loop:

- QuakeC runtime: physics, GOAP, humanised aim, typed nav, personalities, chat Easter eggs.
- Offline toolchain: BSP cartographer, navgen, fteqcc, headless dedicated match, ARGLOG / ARGEVT tape.
- Lab MCP: `see`, `experiment`, `compare_runs`, `tune`, GUI wizard.

The missing piece is a *slow, optional* brain for the jobs QuakeC is bad at:

- talking like a person instead of a canned impulse line
- proposing a next control circuit in English, then mapping it onto existing GOAP goals
- suggesting a waypoint or cost tweak after reading a stall tape
- explaining a death in lab notes

Those jobs do not belong in `StartFrame`. They do not belong in the edict budget. They do not belong in protocol 15.

---

## 3. Non-goals

- The SLM is not the bot.
- The SLM does not aim, jump, board a train, or fire the lightning gun.
- The SLM is not required to compile, install, or play a match.
- No engine fork, no QuakeWorld RCON, no file I/O from QuakeC, no 100x tickrate.
- No live dependency on a 2.5 GB model for a LAN game on old hardware.

If those constraints are broken, it is no longer Argus.

---

## 4. Design principles

1. **Optional by construction.** Default build and default match path never load a model. `ARGUS_SLM=off` is the implicit default.
2. **Advise, do not drive.** The QuakeC loop owns action. Suggestions expire. Stale suggestions are discarded.
3. **Fail closed.** Missing binary, OOM, timeout, garbage JSON, or a suggestion that fails a nav check is treated as silence.
4. **Same lab pipe.** The sidecar talks to the world only through `argus-mcp`. It does not spawn a second Quake process and it does not scrape the renderer.
5. **Cheap first.** Offline lab advice ships before live in-match advice. Live is a later, gated experiment.

---

## 5. Architecture

```
                    optional
                 ┌─────────────┐
                 │  SLM sidecar│  Phi-4 Mini Q4 (~2.5 GB on disk)
                 │  (llama.cpp │  default: off
                 │   / Ollama) │
                 └──────┬──────┘
                        │ JSON advice
                        ▼
 LLM client  ←stdio→  argus-mcp  ←→  fteqcc / navgen / analyze_match
                        │
                        │ at most one dedicated child
                        ▼
              Quake engine (protocol 15, 600 edicts)
                        │
                        ▼
              Argus QuakeC (GOAP, nav, combat, chat)
```

Three layers. The bottom two already exist.

| Layer | Cadence | Owns | Blocks the game? |
|---|---|---|---|
| QuakeC runtime | every server frame | move, aim, shoot, route, GOAP | no, it *is* the game |
| Lab MCP | human / agent request, or 0.5-2 Hz live poll | compile, cartograph, match, tape, optional SLM | no |
| SLM sidecar | 0.5-2 Hz when enabled | waypoints-as-advice, tactic hint, chat line | no. Timeout = skip |

The only new process is the model runner, and only when the operator turns it on.

---

## 6. Operating modes

### Mode A: Argus as shipped (default)

No model. No extra RAM. MCP is the compile / cartograph / A/B lab it is today.

### Mode B: Lab advisor (first experiment, recommended)

The model never talks to the running match. An agent or the human asks MCP for advice after a tape:

- "Why did Reap stall at the west pad?"
- "Propose three nav cost bumps from this lava cluster."
- "Write a Romero line for a rocket frag on dm2."

Output is notes, JSON patches for `argus_nav_<map>.costs.json`, or candidate chat strings. A human or the existing `learn_hotspots` / navgen path applies them. Then `experiment` judges the result the usual way.

This is the mode that is actually worth building first. It uses tools that already exist (`see what=bot`, `see what=plan`, `see what=path`, `learn_hotspots`).

### Mode C: Live sidecar (optional extra, gated)

A slow loop polls `see what=live` / `live_snapshot` while a dedicated match is running. The model emits a short suggestion. MCP drops it into a suggestion buffer. QuakeC peeks at that buffer when convenient and may ignore it.

Live Mode C is *not* required for Mode B. It needs a tiny QC contract (section 9) because vanilla QuakeC cannot read files.

---

## 7. What the SLM is allowed to do

Three subroutines. All optional. All advice.

### 7.1 Tactic suggester

**Input:** compact live or tape snapshot: bot name, hp, armour, weapon, position, nearest node, current GOAP goal, visible enemies, last few ARGEVT verbs.

**Output (strict JSON):**

```json
{
  "kind": "tactic",
  "bot": "Reap",
  "goal_class": "weapon_rocketlauncher",
  "intent": "deny",
  "ttl_sec": 4,
  "why": "enemy stacked on YA, RL still live"
}
```

`goal_class` must be a classname the existing utility scorer already understands. The QC side, if live, treats this as a *bias* on `Argus_PickGoal`, not a forced state machine rewrite.

### 7.2 Waypoint / route hint

**Input:** map name, bot node, desired item token (`dm2:rl`), cartographer reach label, optional stall hotspot.

**Output:**

```json
{
  "kind": "route",
  "bot": "Omi",
  "map": "dm2",
  "via_nodes": [88, 91, 104],
  "ttl_sec": 6,
  "why": "avoid west pad wait storm"
}
```

MCP validates `via_nodes` against the inspect BFS (`see what=path`) before the hint is offered. Illegal hops are dropped. The runtime router remains the sliced BFS in `argus_nav.qc`. The hint is only a preferred next hop, and only while the stamp is fresh.

### 7.3 Personality / chat line

Argus already has name-keyed canned lines and impulse Easter eggs. The SLM does not replace that table.

**Output:**

```json
{
  "kind": "chat",
  "bot": "Romero",
  "line": "The rocket launcher is still a musical instrument.",
  "ttl_sec": 2
}
```

Rules:

- one short line, ASCII, no control characters
- voice must match the roster slot / name already in QC
- rate-limit: at most one SLM line per bot per N seconds
- if the model is off, impulse chat still works

Chat is the least dangerous live experiment and the most visible one. It is a good Mode C slice zero.
[Triage note: refuted, see the parking triage. Strings cannot enter the
VM; chat is the one kind that can never go live.]

---

## 8. What the SLM is not allowed to do

- Change `AR_JUMPVEL`, spring aim constants, or hazard math at runtime. Those stay compile-time. Lab advisor may *propose* a constant change; `experiment` still has to pass.
- Invent nav nodes. Nodes come from `argus_navgen.py`.
- Override brink vetoes, lava probes, or board gates. Safety stays in QuakeC.
- Speak as a human client or stuff unwhitelisted console.
- Run every frame, or block `Argus_FrameAll`.

---

## 9. Live contract with QuakeC (Mode C only)

[Triage note: this section is the part that failed review. The
impulse/stuffcmd channel below does not compose in vanilla; the viable
channel is scratch1-scratch4 cvar floats. Kept as written for the
record.]

Vanilla QuakeC cannot open a file and cannot speak MCP. The live path has to be something the engine already allows.

**Chosen pipe:** existing dedicated-child console inject (`tune` / `match_command`) plus a small, explicit impulse / alias surface compiled into Argus.

Proposed QC additions, all no-ops when unused:

| Symbol | Role |
|---|---|
| `impulse 240` | "accept next SLM tactic bias if buffer fresh" |
| `impulse 241` | "accept next SLM chat line if buffer fresh" |
| `impulse 242` | "clear SLM buffers" |
| `argus_slm` cvar or impulse latch | 0 = ignore sidecar (default), 1 = allow chat, 2 = allow chat+tactic |

The MCP server is the only writer. It stuffs a short, whitelisted console line, for example:

```
argus_slm_chat Romero The rocket launcher is still a musical instrument.
```

Implementation sketch (QC):

- parse is not free-form natural language inside the VM
- MCP encodes the payload as a bounded token string the QC already knows how to read from `impulse` / `stuffcmd` aliases, the same family as the existing Easter-egg aliases
- each payload carries a generation counter; QC ignores a payload older than `ttl_sec` or from a previous map

If that encoding turns out uglier than it is worth, **do not ship Mode C**. Keep Mode B. The bot is already good. A bad live pipe is worse than no model.

Parked alternatives (do not do these under the charter):

- engine file watch on `slm.json`
- UDP RCON
- VM memory poke

---

## 10. Recommended model

For the experiment: **Phi-4 Mini Instruct**, 4-bit GGUF.

| | |
|---|---|
| Why | Strongest small-model reasoning / structured JSON in this size class |
| Disk | about 2.5 GB at Q4_K_M |
| RAM at runtime | about 2.5-3 GB |
| Context | keep prompts tiny; live snapshot is tens of tokens, not the whole tape |
| License | MIT |
| Swap | any OpenAI-compatible local endpoint (Ollama, llama.cpp server). Argus must not hard-require Claude or any cloud API |

Gemma 3 4B is the fallback if Phi is awkward on the machine. Same disk class. Do not pull Nemotron or anything that needs tens of gigabytes into this loop.

The sidecar should speak a local HTTP or subprocess API so the model file is not compiled into `argus-mcp`.

---

## 11. Prompt and snapshot contract

Live and lab prompts share one snapshot schema so the model never sees raw qconsole.

```json
{
  "map": "dm2",
  "t": 84.2,
  "bot": {
    "name": "Reap",
    "hp": 67,
    "arm": 0,
    "weap": "rl",
    "pos": [128, -512, 24],
    "node": 91,
    "goal": "item_armor2",
    "mode": 2
  },
  "foes": [
    {"name": "Romero", "hp": 90, "node": 88, "dist": 420}
  ],
  "events_tail": ["engage Romero", "grab weapon_rocketlauncher", "hazard"],
  "ask": "tactic"
}
```

Hard limits:

- snapshot < 1 KB
- model timeout 400-800 ms for live, 5 s for lab
- temperature low for tactic/route, slightly higher for chat
- response must parse as the JSON in section 7 or it is dropped

Do not feed BSP lumps or full QC source to the live loop. Lab advisor may call `see what=fn` / `see what=map` itself through MCP, then summarise.

---

## 12. MCP additions

The current server is a lab toolchain. That job stays. The SLM rides beside it.

### 12.1 Config

New optional keys. Missing means off.

| Key | Meaning | Default |
|---|---|---|
| `ARGUS_SLM` | `off` / `lab` / `live` | `off` |
| `ARGUS_SLM_BIN` | llama.cpp server, Ollama, or equivalent | unset |
| `ARGUS_SLM_MODEL` | GGUF path or Ollama tag | unset |
| `ARGUS_SLM_ENDPOINT` | `http://127.0.0.1:11434` style | unset |
| `ARGUS_SLM_TIMEOUT_MS` | per call | `800` live / `5000` lab |

`config_check` lists these as optional. A live tool errors with `{error, hint}` if mode is `live` and the endpoint is dead. It never fails the rest of the lab.

### 12.2 New tools

Keep the "one inspect" philosophy. Do not explode the vocabulary.

| Tool | Mode | Does |
|---|---|---|
| `see what=slm` | all | Status: off / lab / live, model id, last advice, last error |
| `advise` | lab | Run one subroutine against a snapshot or a named run (`latest:Reap`). Returns JSON advice. Does not touch the match. |
| `advise_apply` | lab | If kind is `route`/`cost`, write a candidate `*.costs.json` patch or a notes file under `runs/`. Never writes QC by itself. |
| `advise_live` | live | One-shot: snapshot current child → model → validated suggestion → optional console inject. No-op if `ARGUS_SLM!=live` or no child. |

Aliases under `see` are enough for status. `advise` is a real tool because it has side effects in lab mode when `advise_apply` is used.

Do **not** add `slm_chat`, `slm_waypoint`, `slm_tactic` as three separate tools. One `advise kind=chat|tactic|route` is enough.

### 12.3 Enhancements to existing tools

These are the gaps that actually matter. Ranked.

| Existing tool | Gap | Enhancement |
|---|---|---|
| `live_snapshot` / `see what=live` | Last ARGLOG row is thin for a model. No goal classname, no nearest node, no foe list. | Add an optional `detail=slm` pack: node id, goal class, hp/arm/weap, last 8 ARGEVT verbs, nearest control item. Still lite. |
| `see what=bot` | Deep tape is for humans/agents. Too large to stuff into a live prompt. | Add `detail=compact` (the snapshot schema in section 11). |
| `see what=plan` | GOAP events exist. No "current want + via" per live bot in one call. | Include current plan in the compact snapshot. |
| `tune` whitelist | Live inject has no SLM verbs. | If Mode C ships, add `argus_slm_*` to the whitelist. Reject anything else. |
| `match_status` | No way to know the sidecar is falling behind. | Surface `slm_lag_ms`, `slm_drops` on `see what=slm`. |
| `experiment` | Cannot A/B "with advice notes" vs baseline. | Do not run the model inside `experiment` by default. Optional `advise=true` only generates a post-match notes file. Physics A/B stays clean. |
| `learn_hotspots` | Already writes `argus_nav_<map>.costs.json`. | Lab advisor should emit patches in that same schema, not a new format. |
| `quality_bars` | No bar for "model made it dumber." | If Mode C is on during a harvested match, tag the run `slm=live` so it can never silently become a baseline. |

### 12.4 Tools we should not add

- `bot_capture_pov_frame` as an SLM eye. Parked in the charter. Nav PNG + ARGLOG are enough.
- A second match process for the model.
- Free-form `rcon_exec` of model text.
- Embedding the model weights in the Rust binary.

---

## 13. QuakeC changes, if any

**Mode B: none.** That is the point.

**Mode C, minimum viable:**

- a few impulses / aliases and a short-lived per-bot buffer
- default off
- chat slice first
- tactic bias second, and only as a utility offset, not a planner replacement
- no route override until the inspect BFS validation has a season of lab use

Budget: this must stay inside the 600-edict ceiling and must not add per-frame traces. The buffer is a handful of fields on the bot edict that already exists.

---

## 14. Failure and safety

| Failure | Behaviour |
|---|---|
| `ARGUS_SLM=off` or keys unset | Tools that need the model return `{error:"slm_off", hint:"see what=slm"}`. Match unaffected. |
| Model process dead | Same as off after one failed ping. |
| Timeout | Drop the tick. Count `slm_drops`. |
| JSON parse fail / unknown kind | Drop. |
| `via_nodes` fail inspect BFS | Drop route hint. |
| Chat line too long / bad charset | Drop. |
| Suggestion older than TTL | QC ignores. |
| Run harvested with SLM live | Filename or brief tag `slm=live`. Cannot be written into `runs/baselines.json` by accident. |

The quality bars in MCP 0.18 stay the judge. A clever taunt that walks into lava is a failed experiment.

---

## 15. Packaging and what you copy to someone else

Argus remains:

- `game/argus/progs.dat` + `autoexec.cfg`: the playable mod
- `src/`: QuakeC
- `tools/argus_mcp`: lab binary
- optional: a GGUF on disk and two env keys

You can zip the mod without the model. That zip is still Argus. The model is an extra folder, like a local lab engine install: machine-local, not part of the shipped `progs.dat`.

---

## 16. Implementation plan

### Slice 0: paper and config (this document)

No code required beyond optional config keys and `see what=slm` returning `off`.

### Slice 1: Mode B lab advisor

1. Compact snapshot builder from existing ARGLOG / ARGEVT / nav graph (`see what=bot detail=compact`).
2. `advise kind=tactic|route|chat` against a named run or `latest`.
3. Phi-4 Mini behind a local endpoint.
4. `advise_apply` only for `costs.json` notes and a `runs/advise_*.md` log.
5. Keep using `experiment` to verify any accepted cost patch.

Success looks like: after a west-pad wait storm, the advisor proposes a cost bump that `learn_hotspots` could have written, and a human can read why.

### Slice 2: chat-only Mode C

1. QC buffer + impulse 241.
2. `tune` whitelist entry.
3. `advise_live kind=chat` at 1 Hz max per bot.
4. Compare a harvested `slm=live` tape against baseline on quality bars, ignoring chat.

Success looks like: Romero sounds a bit more present, and K/D does not move.

### Slice 3: tactic bias Mode C (only if slice 2 is boringly stable)

Utility offset on `Argus_PickGoal`. Hard cap on TTL. Invalid classnames dropped. A/B required.

Route hints stay lab-only until slice 3 has not regressed dm2/dm4 bars.

---

## 17. Rationale against the alternatives

**"Just let the LLM play."**
A 4B model cannot run Quake physics at 10 Hz, cannot board a dm2 train, and will eat the frame budget. The 1998 lesson still holds: locomotion is code.

**"Bake the model into progs.dat."**
Impossible under vanilla QC, and wrong even if it were possible.

**"Require Claude."**
The lab already runs offline. The sidecar should too. Cloud is fine as an endpoint behind the same JSON schema, never as a hard dependency.

**"Skip MCP and scrape the screen."**
Argus already has a better eye: ARGLOG, cartographer briefs, nav PNG. Vision is parked in `docs/mcp_quake_dev_spec.md` for charter reasons.

**"Always-on live model."**
Two to three gigabytes of RAM for a Quake 1 bot is an experiment, not a default. Mode A stays the product.

---

## 18. Open questions

1. Is a stuffcmd/impulse payload acceptable for Mode C, or is chat-from-lab enough forever? [Answered in triage: no; scratch cvar floats or nothing, and chat never goes live.]
2. One shared model for all bots, or a persona prefix per roster slot? Start with one model and a system prompt that names the bot.
3. Should `advise` be allowed to see `see what=fn` source when proposing a constant change, or only tapes? Prefer tapes first so it cannot hallucinate QC.
4. Windows console inject is already the fragile live path. Mode C on Windows may need to wait until `tune` is boringly reliable.

---

## 19. Decision

Ship Argus without an SLM.

Treat Phi-4 Mini as an optional lab advisor that reads the tape Argus already writes.

If that advisor earns its disk space, consider a live chat sidecar. Never let the model become the movement code.

[Parking addendum, 2026-08-26: reviewed and PARKED before any slice was
built. Not even slice 1 is scheduled; the intelligence budget goes to
the dm2 directed-reach campaign, the sprint run-up discipline, the
ambush family, offensive displacement and the dm4 quad-hold proof
instead. See the triage at the top for the technical corrections a
revival must absorb.]
