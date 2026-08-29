#!/bin/bash
# setup_rig.sh - rebuilds the headless Quake botmatch rig from nothing.
# Tested on Ubuntu 24.04 (Claude sandbox). Run from tools/ inside the
# argus repo; the QC tree comes from ../src. Total time: a few minutes.
#
# Revised 2026-08-18 (Shane's project review): the old script copied
# two loose QC files over a pristine LibreQuake qcsrc checkout and
# injected worldspawn/StartFrame hooks by hand - with stale BotLab_*
# function names that no longer compile, and none of the vendored
# base-file touches (defs shim, weapon_touch guard, knockback,
# W_FireLightning makevectors). ../src vendors all of that now, so
# the inject stages are gone. Revised stages not yet re-run on a
# live rig; the gotcha notes below remain valid.
#
# What it produces:
#   quake/           basedir (LibreQuake lite paks + DM maps)
#   quake/argus/    our mod dir with compiled progs.dat
#   match.log        telemetry from a 120 s headless botmatch
#   match_traj.png   trajectory plot over map wireframe
#
# Hard-won gotchas encoded below:
#   * apt fteqcc (svn3400) is too old for LibreQuake QC; build modern fteqcc from fteqw git
#   * LibreQuake repo tree has map/QC sources only; compiled BSPs + paks come from release zips
#   * QuakeSpasm dedicated still wants gfx.wad; the lite paks satisfy this
#   * NQ bprint writes to connected clients only - INVISIBLE on an empty dedicated
#     server. Use dprint for telemetry and run with +developer 1
#   * QuakeSpasm buffers stdout when not a tty; wrap with stdbuf -oL
#   * LibreQuake defs.qc declares bprint QW-style: bprint(level, string)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "== packages =="
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq quakespasm unzip build-essential zlib1g-dev >/dev/null

echo "== modern fteqcc =="
if [ ! -x fteqw/engine/release/fteqcc ]; then
    git clone -q --depth 1 https://github.com/fte-team/fteqw.git
    make -C fteqw/engine qcc-rel >/dev/null 2>&1
fi
QCC="$HERE/fteqw/engine/release/fteqcc"

echo "== game data (LibreQuake, free content) =="
REL=https://github.com/lavenderdotpet/LibreQuake/releases/download/v0.09-beta
[ -f lq-lite.zip ]   || curl -sL -o lq-lite.zip   $REL/lite.zip
[ -f lq-server.zip ] || curl -sL -o lq-server.zip $REL/server.zip
unzip -q -o lq-lite.zip -d lq-lite
unzip -q -o lq-server.zip -d lq-server
mkdir -p quake/id1/maps quake/argus
cp lq-lite/lite/id1/pak0.pak lq-lite/lite/id1/pak1.pak quake/id1/
cp lq-server/server/maps/*.bsp quake/id1/maps/

echo "== QuakeC source (vendored tree: ../src carries the full Argus QC) =="
# ../src is LibreQuake GPL 1.06 WITH every Argus touch already in
# place: defs.qc shim, world.qc hooks (Argus_CountSlots, Argus_Init,
# Argus_FrameAll), items/combat/weapons edits, per-map nav files and
# the argus_nav_dispatch.qc dispatcher. Nothing needs injecting.
rm -rf argus-src && cp -r "$HERE/../src" argus-src

# nav for lqdm2 is vendored (argus_nav_lqdm2.qc). To add another map:
#   python3 "$HERE/argus_navgen.py" quake/id1/maps/MAP.bsp MAP \
#       argus-src/argus_nav_MAP.qc nav_MAP.png --no-dispatcher --register
# (--register wires progs.src and the dispatcher automatically)

echo "== compile =="
mkdir -p lq1
rm -f lq1/progs.dat
# fteqcc exits 0 even when the output write fails - trust the
# "Compile finished ... (id format)" line AND a fresh progs.dat,
# never the exit code (the old pipe swallowed failures with
# || true and shipped whatever stale progs.dat was lying around)
(cd argus-src && "$QCC" 2>&1 | tee ../compile.log | grep -E 'error|Writing|Compile finished') || true
grep -q 'Compile finished.*id format' compile.log || { echo 'COMPILE FAILED (no id-format finish line)'; exit 1; }
[ -f lq1/progs.dat ] || { echo 'COMPILE FAILED (no progs.dat written)'; exit 1; }
cp lq1/progs.dat quake/argus/
# enforce 1996 constraints on every match: protocol 15, vanilla edict ceiling
printf 'sv_protocol 15\nmax_edicts 600\n' > quake/argus/autoexec.cfg

echo "== 120 s headless botmatch on lqdm2 =="
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
timeout 120 stdbuf -oL -eL /usr/games/quakespasm -dedicated 8 \
    -basedir "$HERE/quake" -game argus \
    +developer 1 +deathmatch 1 +map lqdm2 > match.log 2>&1 || true
# grammar is ARGLOG since the v3 era (BOTLOG died with the first
# milestones; counting it reported zero telemetry on healthy matches)
echo "telemetry records: $(grep -c ARGLOG match.log)"

echo "== analysis =="
python3 analyze_match.py quake/id1/maps/lqdm2.bsp match.log match_traj.png
echo "done."
