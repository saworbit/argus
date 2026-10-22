# Getting support for Argus

Start with the [README](README.md) for installation, controls and the lab
workflow. The [plain-text guide](README.txt) mirrors the quick play steps.

## Find the right guide

| Question | Guide |
|---|---|
| Where do I install the mod? | [Installation](README.md#install-and-play), including the separate KEX path |
| How do I add bots or watch a match? | [Controls and roster permissions](docs/controls.md) |
| How do I configure the lab? | [Lab setup](docs/lab-workflow.md) and [full operator guide](tools/argus_mcp/README.md) |
| How do I preserve a human session? | [Recording and harvest](docs/telemetry.md#record-and-harvest-a-human-session) |
| What is in this build? | [Changelog and build ledger](CHANGELOG.md) |

## Common problems

| Symptom | What to check |
|---|---|
| Stock Quake loads without bots | Install `argus/progs.dat` beside `id1`; select `-game argus` on classic engines or `+game argus` on KEX |
| KEX cannot find the mod | Install it under `Saved Games/Nightdive Studios/Quake/argus` in your Windows profile, not inside another `argus` folder |
| Bot scores are absent | On classic engines, restart with `-listen 8` for spare scoreboard slots |
| Roster impulses are refused | The server console must set `scratch1 147`; logging does not authorise roster changes |
| Difficulty appears unchanged | Console `skill` applies on respawn; authorised `impulse 103` retunes immediately |
| Camera mouse shortcuts differ | The shortcuts use attack/jump actions outside free flight; use impulses `211` and `212` for binding-independent control |
| Colours are missing | Extra player-model skins are generated locally; see [bot colours](docs/controls.md#bot-colours) |
| No match telemetry | Both `-condebug` and `+developer 1` are required; look in the process working directory |
| Lab paths are missing or stale | Run MCP `config_check`; install the current lab and restart the MCP client after an update |

## Ask a question or report a problem

Use [Discussions](https://github.com/saworbit/argus/discussions) for setup
questions, ideas and match clips. For a reproducible bug, use
[Issues](https://github.com/saworbit/argus/issues) and include:

- Engine name/version, platform and launch command.
- Map and source commit or binary identity.
- Expected behaviour, observed behaviour and reproduction steps.
- The preserved log/demo where available; describe whether it was human play
  or an automated lab run and how long it ran.

See [contributing](CONTRIBUTING.md), the
[code of conduct](CODE_OF_CONDUCT.md) and the
[security reporting policy](SECURITY.md) for the relevant project policies.
