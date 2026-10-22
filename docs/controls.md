# Play and camera controls

[Back to the README](../README.md#controls)

Enter commands in Quake's console, usually opened with `~`. An `impulse`
is a game command, not an operating-system command. Bind one to a key with
`bind F6 "impulse 210"`; this replaces the key's existing binding.

## Roster access

Deathmatch and co-op require **`scratch1 147` in the server console** before
clients can add/remove bots or alter live skill through roster impulses.
On a listen server, use the host's console. On a dedicated server, use its
server console. This switch authorises client roster controls server-wide;
it is not per-player authentication. `developer 1` only enables logging.
Set `scratch1 0` to disarm the roster switch. Plain single-player is local.

`scratch1` is also used by debug and fixture modes. Only one value can be
active: setting `scratch1 1` for decision traces or `197` for a fixture
replaces the roster opt-in until you restore `147`.

## Match and roster commands

| Command | Behaviour |
|---|---|
| `map dm4` | Start the named map |
| `fraglimit 20` | Set the score limit; `0` disables it |
| `timelimit 10` | Set the time limit in minutes; `0` disables it |
| `skill 1.5` | Set a continuous baseline in 0-3; bots apply console changes on respawn |
| `impulse 100` | Print the roster command menu |
| `impulse 101` | Add the next roster bot, up to four total and available client capacity |
| `impulse 102` | Remove the most recently spawned bot |
| `impulse 103` | Cycle integer baseline 0 -> 1 -> 2 -> 3 -> 0; retune active bots now |
| `impulse 104` | Toggle ArgusCam |
| `impulse 105` | Print match and per-bot statistics |
| `impulse 106` | Cycle slot 0's skill offset |
| `impulse 107` | Cycle slot 1's skill offset |
| `impulse 108` | Cycle slot 2's skill offset |
| `impulse 109` | Cycle slot 3's skill offset |
| `impulse 110` | Toggle adaptive per-bot difficulty and clear previous adaptive offsets |
| `omicron` / `impulse 146` | Toggle tribute roster names in plain single-player; refused in deathmatch and co-op |

Per-slot offsets cycle through `0, +0.5, +1, -1, -0.5`; effective skill is
bounded to 0-3. Adaptive difficulty starts off. It is active only against
connected humans in deathmatch at global skill 1, not in co-op or bot-only
matches. Each bot adjusts independently; positive adaptive changes affect
raw aim less strongly than cognition. With `developer 1`, the tape records
base, cognition and aim tiers, offsets, drift eligibility and aim-share
percent whenever skill is applied. The current share remains 35 percent.

Three bots spawn outside co-op: Carmack, Romero and Joe Rogan. Co-op starts
with Carmack. The runtime cap is four bots, also limited by spare client
slots. On classic engines, launch with `-listen 8` so scoreboard rows and
the optional fourth bot have capacity.

## ArgusCam

| Command | Behaviour |
|---|---|
| `impulse 210` | Enter or leave the camera; initial entry uses director mode |
| `impulse 211` | Advance to the next camera mode |
| `impulse 212` | Select the next target bot |
| `impulse 213` | Toggle centred versus shoulder chase framing |
| `impulse 214` | Toggle broadcast HUD information |

| Mode | View |
|---|---|
| 0: POV | First person with the bot's weapon and status |
| 1: Chase | Third person following the target |
| 2: Director | Automatic action selection and cuts |
| 3: Duel | Frame the target and its opponent together |
| 4: Free flight | Move with the engine's ordinary noclip controls |
| 5: Orbit | Orbit the subject |

POV hides the tracked bot's world model. The camera also hides the observer's
body while active and restores its rendering and viewpoint on exit. If the
target dies, the camera can select another living bot.

Outside free-flight mode, the **attack action** cycles camera modes and the
**jump action** cycles targets. The physical keys depend on your bindings;
the impulse commands work independently of those bindings. Free flight keeps
ordinary movement input, so use the impulses to change mode or target there.

## Chat commands

These trigger themed responses rather than changing difficulty or navigation.

| Impulse | Speaker / action |
|---|---|
| `220` | Carmack |
| `221` | Romero |
| `222` | Joe Rogan |
| `223` | Mr Elusive |
| `224` | Thresh |
| `225` | Arena shout |
| `226` | Trent Reznor |
| `227` | American McGee |
| `228` | Sarge |
| `229` | Gabe Newell |
| `230` | Killcreek |

Use the full command, for example `impulse 220`.

## Bot colours

The repository's `game/argus` contains `progs.dat` and `autoexec.cfg`, not a
modified player model. Bots select player-model skins 1-4. GL-style engines
need a local model with those extra skins to display distinct bot colours;
the scoreboard alone cannot colour these non-client entities.

To generate one, you need Python and your own version-6 Quake player MDL.
From the repository root, this Windows-path example extracts the model and
adds the four scoreboard colour pairs:

```text
python tools/pak_extract.py "C:/Quake/id1/pak0.pak" --out backups/player-model player.mdl
python tools/mdl_skins.py backups/player-model/player.mdl "C:/Quake/argus/progs/player.mdl" 0:4 1:5 2:6 3:7
```

Replace the paths and create `C:/Quake/argus/progs` first. Skin 0 remains
unchanged for human players. The generated model is derived from your input
asset and stays local; it is not part of the repository package. See
[the skin tool](../tools/mdl_skins.py) for its input and licence notes.

KEX's remastered player model has only skin 0. With the extra MDL skins
installed, KEX can report `MDL will be enforced` for bot skins 1-4 while
retaining the remastered human model. Install the local model under the
rerelease mod's own `argus/progs` folder as well.

## Developer-only controls

Keep these out of ordinary play bindings. They reuse stock scratch cvars
and impulses for isolated lab tests.

- `developer 1` enables diagnostics. `scratch1 1` enables goal-decision traces;
  set `scratch1 0` to silence them.
- With `developer 1` and server-console `scratch1 374`, impulse `215` assigns
  A/B arms from `scratch4`. A successful snapshot consumes the key.
- With `developer 1` and server-console `scratch1 216`, impulse `216` teleports
  its sender to (`scratch2`, `scratch3`, `scratch4`). Set `scratch1 0` to disarm.
- With `developer 1` and `scratch1 197`, impulse `217` runs the tactical case
  selected by `scratch2`. It takes precedence over navigation-task dispatch.
  It changes live state and freezes other bots for six seconds. Keep it
  disarmed on shared servers.
  See the [fixture protocol](attack-cover-return.md#engine-acceptance).
- Impulses `217`-`219` also serve the gated fixed-navigation task protocol.
  Use the [benchmark runner](../tools/argus_mcp/README.md#fixed-navigation-benchmark)
  instead of issuing those task controls during an ordinary match.
