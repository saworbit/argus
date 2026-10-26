ARGUS - QUICK PLAY GUIDE
=======================
Full installation, controls and lab workflow: README.md

Development-source status and tests: docs/behaviour-diagnostics.md.
The supplied binaries are unchanged; step 1b remains parked.

PLAY: CLASSIC ENGINES
--------------------
1. Copy game/argus next to your Quake installation's id1 folder.
   The installed files must be argus/progs.dat and argus/autoexec.cfg.
2. From that Quake directory, start:

   quakespasm -listen 8 -game argus +skill 1 +deathmatch 1 +map dm4

   Replace quakespasm with your engine executable. In Windows PowerShell,
   use .\quakespasm.exe. Keep autoexec.cfg: protocol 15, max_edicts 600.
   The listen slots provide space for the bot scoreboard and roster.
3. Carmack, Romero and Joe Rogan spawn automatically. Play normally.
   Press Tab for scores; open the Quake console to enter commands.

PLAY: OFFICIAL 2021 RERELEASE
---------------------------
Copy game/argus to Saved Games/Nightdive Studios/Quake/argus in your
Windows profile. Use these launch options:

   +game argus +skill 1 +deathmatch 1 +map dm4

KEX uses +game, not the classic -game switch. See README.md for details.

COMMON CONSOLE COMMANDS
-----------------------
   impulse 210    Enter/leave ArgusCam
   impulse 211    Cycle camera mode
   impulse 212    Cycle target bot
   impulse 214    Toggle camera HUD
   impulse 100    Show roster command menu
   impulse 105    Show statistics
   skill 1.5      Set baseline 0-3; applies at next bot respawn
   fraglimit 20   Set score limit (0 disables)
   timelimit 10   Set minutes per match (0 disables)
   map dm2        Start another map

In deathmatch/co-op, the SERVER console must first set scratch1 147
before client roster commands are allowed:

   impulse 101    Add a bot (four maximum, with spare client slots)
   impulse 102    Remove the newest bot
   impulse 103    Cycle baseline 0/1/2/3 and retune active bots now
   impulse 106-109  Per-slot offsets (issue one impulse, e.g. impulse 106)
   impulse 110    Toggle adaptive difficulty (human deathmatch, skill 1)

The roster switch is server-wide. developer 1 enables logging, not access.
Full camera modes, chat and skin setup: docs/controls.md

MAPS AND ASSETS
---------------
Routed deathmatch maps: dm2, dm3, dm4, dm6, lqdm2. You must install their
game data/BSPs. Licensed id maps and extra player-model skins are not
bundled. See docs/controls.md for optional locally generated bot colours.

DEVELOPMENT AND RECORDING
-------------------------
The prebuilt mod does not require Python, Rust or a compiler to play.
Lab setup and MCP/terminal examples: docs/lab-workflow.md
Recording and harvest: docs/telemetry.md
Source architecture: docs/architecture.md
Changes and build identities: CHANGELOG.md

Before any new engine launch, harvest a human session so its console log
and demo survive. Never hand-edit generated src/argus_nav_<map>.qc.
