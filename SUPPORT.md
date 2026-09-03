# Getting Support for Argus

Thank you for playing and developing with Argus! Here is how to get help, find answers to common questions, or troubleshoot issues.

---

## Quick Reference & Documentation

Before opening an issue, check the following resources:

- **[README.md](README.md)**: Complete quick-start guide, system architecture, impulse codes, and command-line options.
- **[README.txt](README.txt)**: Plain-text quick play instructions bundled with the game mod.
- **[CLAUDE.md](CLAUDE.md)**: Deep technical constraints, engine quirks, and architecture details.
- **[tools/argus_mcp/README.md](tools/argus_mcp/README.md)**: Documentation for the MCP server, localhost wizard, and telemetry analysis suite.

---

## Playing with Argus

### Supported Quake Engines

Argus is pure vanilla QuakeC and works across virtually all modern Quake source ports and original binaries:

- **QuakeSpasm / QuakeSpasm-Spiked**: Highly recommended.
- **Ironwail**: Excellent performance and high-framerate support.
- **vkQuake**: Vulkan-based engine.
- **FTEQW**: Multi-protocol support.
- **DarkPlaces**: Compatible.
- **Quake 2021 Re-Release (Kex engine)**: Compatible. Copy `game/argus` into your `rerelease/` directory.

### Quick Start Command

```bash
# Example launching on dm4 with deathmatch enabled
quakespasm -game argus +deathmatch 1 +map dm4
```

---

## Common Questions & Troubleshooting

### 1. Telemetry / `qconsole.log` is empty
- **Solution**: Quake requires both `-condebug` and `+developer 1` to write detailed bot telemetry (`ARGLOG` and `ARGEVT`) to `qconsole.log`:
  ```bash
  quakespasm -game argus -condebug +developer 1 +deathmatch 1 +map dm4
  ```

### 2. Spectator Director (ArgusCam)
- In game, use the following impulse commands:
  - `impulse 210`: Activate ArgusCam director mode.
  - `impulse 211`: Cycle camera modes (Follow, Chase, Static, Fly).
  - `impulse 212`: Cycle target bot.

### 3. Adjusting Bot Difficulty
- In the Quake engine console, set `skill 0`, `skill 1`, `skill 2`, or `skill 3`:
  ```text
  skill 3
  ```

### 4. Talk to Bots (Chat Easter Eggs)
- Talk with individual bot personalities via impulse commands:
  - `impulse 220`: Carmack
  - `impulse 221`: Romero
  - `impulse 222`: Joe Rogan
  - `impulse 223`: Mr Elusive
  - `impulse 224`: Thresh
  - `impulse 226`: Trent Reznor
  - `impulse 228`: Sarge
  - `impulse 229`: Gabe Newell
  - `impulse 230`: Killcreek

---

## Where to Ask Questions & Connect

- **[GitHub Discussions](https://github.com/saworbit/argus/discussions)**: The best place for general chat, questions, bot behavior discussion, sharing custom map navs, or showing match highlight clips.
  - [Q&A](https://github.com/saworbit/argus/discussions/categories/q-a): Get help with setups, Quake engines, and commands.
  - [Ideas](https://github.com/saworbit/argus/discussions/categories/ideas): Propose bot tactics, Easter eggs, and new features.
  - [Show and tell](https://github.com/saworbit/argus/discussions/categories/show-and-tell): Share demos, screenshots, and custom navigation graphs.
- **Bug Reports & Glitches**: If you found a bug or unexpected engine crash, open a [Bug Report](https://github.com/saworbit/argus/issues/new?template=bug_report.yml).
- **Feature & AI Ideas**: Want to file a formal enhancement issue? Open a [Feature Request](https://github.com/saworbit/argus/issues/new?template=feature_request.yml).
- **Map Navigation Requests**: Need help generating navigation for a custom deathmatch map? Open a [Map Support Issue](https://github.com/saworbit/argus/issues/new?template=map_support.yml).
