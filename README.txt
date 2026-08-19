ARGUS - a vanilla QuakeC deathmatch bot
========================================
Built in 2026. Pure vanilla QuakeC: no engine
extensions, no file I/O, runs on protocol 15 with a 600 edict ceiling.
The spiritual lineage is Reaper -> Omicron; the methodology is new:
every build is tuned from headless botmatch telemetry.

WHAT IS IN THIS FOLDER
----------------------
  game\argus\     Ready-to-run mod: progs.dat + autoexec.cfg.
                  Current build: 18-bot homage roster (Carmack, Romero,
                  Joe Rogan, Trent Reznor, American McGee, Sarge,
                  Thresh, Killcreek, Sandy Petersen, Gabe Newell, Crash,
                  Ranger, Tim Willits, Reap, Omi, Zeus, Ares), full combat,
                  a utility/GOAP goal planner, chat easter eggs (impulses
                  220-230), skill dial (console: skill 0-3), ArgusCam
                  spectator director (impulses 210-214), routed nav for
                  lqdm2, dm2, dm3, dm4, dm6 (lifts ridden on dm2/dm3,
                  rocket-jump routes on dm4, quad included).
  src\            Complete QuakeC source (GPL 1.06 base via LibreQuake
                  plus argus.qc, argus_cam.qc, argus_nav.qc,
                  argus_nav_dispatch.qc and per-map argus_nav_<map>.qc
                  - generated, do not hand-edit).
  tools\          argus_navgen.py  - nav compiler (BSP in, QC out)
                  analyze_match.py - telemetry parser + trajectory plots
                  argus_mcp/       - lab MCP server and human GUI
                                     (argus-mcp gui; see its README)
                  setup_rig.sh     - rebuilds the Linux test rig
  runs\           Match logs and plots from the development sessions.
  backups\        Dated progs + nav copies from the deploy wizard.
  AGENTS.md       How an agent uses the lab. Read this first.
  CLAUDE.md       Project brief, constraints, architecture, handoff.

QUICK START (PLAY NOW)
----------------------
1. Copy game\argus into your Quake directory, next to id1.
2. Launch:  quake -game argus +deathmatch 1 +map dm4
   (any engine or the rerelease; QuakeSpasm example:
    quakespasm.exe -game argus +deathmatch 1 +map dm4)
3. Three bots spawn and fight (Carmack, Romero, Joe Rogan). Press TAB
   to see their names and scores on the scoreboard.
4. Press impulse 210 to activate ArgusCam spectator mode. Use Mouse1
   (impulse 211) to cycle modes and Mouse2 (impulse 212) to cycle target
   bots.
5. Talk to the bots with chat easter egg impulses:
     impulse 220: Ask Carmack (engine architecture)
     impulse 221: Ask Romero (deathmatch swagger)
     impulse 222: Ask Joe Rogan (T1 lines in 1999 & DMT)
     impulse 223: Ask Mr Elusive (AAS navigation & AI)
     impulse 224: Ask Thresh (Red armor & item timing)
     impulse 226: Ask Trent Reznor (soundtracks & nails)
     impulse 227: Ask American McGee (labyrinth traps)
     impulse 228: Ask Sarge (combat strategy)
     impulse 229: Ask Gabe Newell (Steam sale & engine polish)
     impulse 230: Ask Killcreek (Lightning Gun shaft precision)
     impulse 225: Arena shout (Good game everyone!)

Note on maps: compiled-in navigation covers lqdm2, dm2, dm3, dm4 and dm6.
On other maps the bots degrade to line-of-sight seeking and still
fight; for full routed navigation on a new map, see below. dm4 quad
is a rocket-jump pad (pit floor onto the ledge), not a walk.

FULL BUILD (NAV FOR YOUR OWN MAPS)
----------------------------------
Needs: Python 3, and fteqcc (modern build - get win64 from
https://www.fteqcc.org or the fteqw project; the 2010-era one is too old).

Easiest path, same lab binary the agents use:

    tools\argus_mcp\target\release\argus-mcp.exe gui

That opens a localhost page. Drop a .bsp, generate nav, look at the
graph PNG, compile, install. Compile takes a dated backup under
backups\ first (progs.dat, dispatcher, every argus_nav_*.qc). Restore
is on the page. Id maps stay on this machine; the wizard will not
pack them for shipping.

Command-line equivalent:

1. Extract the map you want from your pak (dm4.bsp etc.), then:
     python tools\argus_navgen.py dm4.bsp dm4 src\argus_nav_dm4.qc nav_dm4.png --no-dispatcher --register
   (repeat per map; --register wires argus_nav_dispatch.qc and progs.src)
2. Compile: run fteqcc in src\ (progs.src drives it; output lands in
   ..\lq1\progs.dat - copy it to game\argus\progs.dat).
3. Play. Check nav_dm4.png first: green = walk, orange = one-way
   drops, red dotted = jump, magenta dash-dot = rocket-jump,
   purple = teleporters.

CAPTURING MATCH TAPE AND TELEMETRY
----------------------------------
Launch with -condebug AND +developer 1 - both are required: -condebug
writes qconsole.log, developer 1 puts the telemetry in it (without it
the log is empty of ARGLOG/ARGEVT lines and there is nothing to
review). Use the record command for demos. Use analyze_match.py to parse
trajectories, deaths, and stalls from qconsole.log.

KNOWN QUIRKS (HARD-WON)
-----------------------
* Bots are classname "player" so the stock game machinery accepts them;
  defs.qc shims the client-channel builtins (stuffcmd, sprint,
  centerprint and the two multi-string centerprint forms) because
  engines error sending client messages to non-clients.
* bprint is invisible on an empty dedicated server; telemetry uses
  dprint and needs developer 1.
* Vanilla enforcement lives in game\argus\autoexec.cfg
  (sv_protocol 15, max_edicts 600).
