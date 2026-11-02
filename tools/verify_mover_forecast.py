"""Real brush/world controls for the mover forecast and production physics.

One seeded component call at 140 u/s is followed by 1.5 seconds of production
physics. These isolated controls do not claim end-to-end route completion.
Pair them with verify_mover_transfer at both cadences, including its played
e1m6 launch witness. Every run uses a fresh private source and game directory.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys

from argus_validation import require
from argus_source import source_identity
from argus_fixture_harness import (new_output, stage_fixture, private_game,
    read_tape, check_tape, frame_ms, run_match)
from run_behaviour_equivalence import lab_executable, finish_lab
from run_map_intelligence import ROOT, Lab, digest, write

CASES = {1: 'feasible', 2: 'brush_obstruction', 3: 'mismatched_floor',
         4: 'undocked', 5: 'wet_entry'}


def audit_fixture(text):
    observer = text.split('void() MoverForecastObserve =', 1)[1].split('\n};', 1)[0]
    decision = text.split('void(float allowed, float yaw, float speed) MoverForecastDecision =', 1)[1].split('\n};', 1)[0]
    frame = text.split('void() MoverForecastFrame =', 1)[1]
    active, terminal = frame.split('    if (time >= mc_when + 1.5 || mc_bot.health <= 0)', 1)
    for body in (observer, decision, active):
        require(not re.search(r'\b\w+\.\w+\s*=(?!=)', body), 'post-setup actor mutation')
        require(not re.search(r'\b(setorigin|setsize|walkmove|spawn|remove)\s*\(', body), 'post-setup steering')
    for body in (observer, decision):
        require(not re.search(r'\bArgus_\w+\s*\(', body), 'observer calls controller')
    require(active.count('Argus_FrameAll ();') == 1 and
        'if (time < 2) { Argus_FrameAll (); return; }' in active,
        'AI reselection after setup')
    calls = set(re.findall(r'\b(Argus_\w+)\s*\(', active))
    require(calls == {'Argus_FrameAll', 'Argus_MoverGapJumpOK', 'Argus_Physics'}, 'unexpected controller calls')
    require(set(re.findall(r'\b(\w+\.\w+)\s*=(?!=)', terminal)) ==
            {'self.velocity', 'self.movetype', 'self.think', 'self.nextthink'}, 'terminal mutation')
    require(not re.search(r'\b(setorigin|setsize|walkmove|Argus_\w+)\s*\(', terminal))


def instrument_forecast(text):
    definition = 'float(float yaw, float spd) Argus_MoverGapJumpOK ='
    require(text.count(definition) == 1, 'production mover forecast changed')
    require('Argus_MoverGapJumpCore' not in text, 'forecast is already instrumented')
    start = text.index(definition)
    end = text.index('\n};', start) + 3
    core = text[start:end].replace('Argus_MoverGapJumpOK', 'Argus_MoverGapJumpCore', 1)
    wrapper = ('\n\nfloat(float yaw, float spd) Argus_MoverGapJumpOK =\n{\n'
        '    local float allowed;\n    allowed = Argus_MoverGapJumpCore (yaw, spd);\n'
        '    MoverForecastDecision (allowed, yaw, spd);\n    return allowed;\n};')
    return ('void(float allowed, float yaw, float speed) MoverForecastDecision;\n' +
            text[:start] + core + wrapper + text[end:])


def stage(root, output, source=None):
    fixture = (root / 'tools/fixtures/mover_forecast.qc').read_text(encoding='utf-8')
    audit_fixture(fixture)
    return stage_fixture(root, output, source,
        fixtures={'mover_forecast_fixture.qc': fixture}, frame_wrap='MoverForecastFrame ();',
        edits={'argus.qc': instrument_forecast})


def inspect_fixture(text, case, ticrate):
    require(case in CASES, 'unknown control case')
    check_tape(text, 'e1m6')
    require(text.count('BHVRPL begin mover_forecast') == 1, 'missing quarantine marker')
    ms = frame_ms(text, 'MCFIX', ticrate)
    starts = re.findall(r'^MCFIX begin dt_ms\s+[\d.]+ layout ([12]) case (\d+)\r?$', text, re.M)
    require(len(starts)==1 and starts[0][1]==str(case), 'wrong control layout/case')
    pattern = (r'^MCFIX result case (\d+) forecast ([01]) jump ([01]) '
        r'invalid_jump ([01]) checks (\d+) refused (\d+) accepted (\d+) alive ([01]) retained ([01]) '
        r'wetlevel ([0-3]) depth\s+([\d.]+) dry_floor ([01]) world_floor ([01]) '
        r'state (\d+) dock_gap\s+([-\d.]+) blocked ([01]) target_contents\s+([-\d.]+) '
        r"frames (\d+) seconds\s+([\d.]+) predicted '([^']+)' pos '([^']+)' "
        r'pool_floor\s+([-\d.]+) pool_surface\s+([-\d.]+) final_gap\s+([-\d.]+)\r?$')
    results = re.findall(pattern, text, re.M)
    require(len(results) == 1, 'missing or repeated control result')
    result = results[0]
    r = result[:3] + result[7:]
    require(result[3] == '0', 'mover launch lacked a same-frame accepted forecast')
    decisions = re.findall(r"^MCFIX decision frame (\d+) allowed ([01]) yaw\s+([-\d.]+) speed\s+([\d.]+) pos '([^']+)'\r?$", text, re.M)
    counts = (len(decisions), sum(d[1] == '0' for d in decisions), sum(d[1] == '1' for d in decisions))
    require(tuple(map(int, result[4:7])) == counts, 'missing live forecast decisions')
    launches = re.findall(r'^MCFIX launch frame (\d+) accepted ([01])\r?$', text, re.M)
    accepted_frames = {d[0] for d in decisions if d[1] == '1'}
    require((r[2] == '1') == bool(launches) and all(
        event[1] == '1' and event[0] in accepted_frames for event in launches),
        'launch without same-frame accepted forecast evidence')
    require(int(r[0]) == case and r[3:5] == ('1', '1'), 'control died or lost its task/route')
    frames, seconds = int(r[13]), float(r[14])
    require(1.5 <= seconds <= 1.7 and frames > 1, 'bad control window')
    fps = (frames - 1) / seconds
    require((8 <= fps <= 12) if ticrate == .1 else (60 <= fps <= 90), 'wrong measured cadence')
    require(len({d[0] for d in decisions}) == len(decisions)
        and all(1 <= int(d[0]) <= frames for d in decisions), 'invalid decision frame')
    predicted, position = (tuple(map(float, value.split())) for value in r[15:17])
    require(all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in (predicted, position)),
            'invalid measured position')
    require(r[1] == ('1' if case in (1, 5) else '0'), 'forecast control failed')
    if case == 2: require(r[11] == '1', 'obstruction was not a real blocking brush')
    if case == 3: require(abs(predicted[2] - (376 - 24)) > 18,
                          'predicted floor matches the exit')
    if case == 4:
        require(r[9] == '2' and 0 < float(r[19]) < float(r[10]),
                'platform was docked or did not physically ascend')
    if case == 5:
        require(float(r[12]) == -3 and float(r[6]) > 0 and int(r[5]) > 0,
                'wet case did not reach real water')
        require(r[7] == '0', 'wet entry claimed a dry world-floor landing')
        require(abs(float(r[18]) - float(r[17]) - float(r[6])) <= 1,
                'water column does not match measured depth')
    return dict(case=case, name=CASES[case], fixture_layout='mover-forecast-v'+starts[0][0],
        observer_predicates_verified=starts[0][0]=='2',
        forecast=r[1] == '1', jump=r[2] == '1', alive=True, retained=True,
        invalid_jump=False, live_checks=counts[0], live_refusals=counts[1], live_accepts=counts[2],
        wetlevel=int(r[5]), pool_depth=float(r[6]), dry_floor=r[7] == '1',
        world_floor=r[8] == '1', initial_state=int(r[9]), dock_gap=float(r[10]),
        brush_blocked=r[11] == '1', target_contents=float(r[12]),
        pool_floor=float(r[17]), pool_surface=float(r[18]), final_dock_gap=float(r[19]),
        frames=frames, seconds=seconds, measured_fps=fps, frame_ms=ms,
        predicted=predicted, position=position)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--case', type=int, choices=CASES, required=True)
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--port', type=int, default=26003)
    args = parser.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix) and 1024 <= args.port <= 65535)
    output = new_output(args.output, root=ROOT, create=False)
    stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'forecastcheck',
            autoexec=f'sv_protocol 15\nmax_edicts 600\nscratch2 {args.case}\n') as folder:
        env = dict(ARGUS_SRC=str(output/'src'), ARGUS_PROGS=str(output/'lq1/progs.dat'),
            ARGUS_RUNS=str(output/'runs'), ARGUS_GAME=folder.name,
            ARGUS_PYTHON=sys.executable, ARGUS_TICRATE=str(args.ticrate))
        with (output/'lab.stderr').open('w', encoding='utf-8', newline='\n') as err:
            lab = Lab(err, env, exe=lab_executable(), timeout=45)
            try:
                project = lab.call('see', what='project')
                require(project['lab_identity']['authoritative'], 'stale lab')
                compiled = lab.call('compile_qc', install=False); write(output/'compile.json', compiled)
                require(compiled['ok'], compiled)
                shutil.copy2(output/'lq1/progs.dat', folder/'progs.dat')
                run_match(lab, 'e1m6', 10, args.prefix, port=args.port, timeout=25,
                    environment=env, stderr_path=output/'match.stderr')
                raw, text = read_tape(output, args.prefix, 'e1m6')
                # Keep identities and raw on failed controls too.
                identity = dict(source_sha256=source_identity(output/'src'),
                    production_argus_sha256=digest(args.source/'argus.qc'),
                    fixture_sha256=digest(output/'src/mover_forecast_fixture.qc'),
                    binary_sha256=digest(folder/'progs.dat'), raw_sha256=digest(raw),
                    raw=raw.relative_to(ROOT).as_posix(), ticrate=args.ticrate, case=args.case)
                write(output/'identity.json', identity)
                result = dict(identity, **inspect_fixture(text, args.case, args.ticrate))
                write(output/'receipt.json', result); print(json.dumps(result), flush=True)
            finally:
                finish_lab(lab)


if __name__ == '__main__':
    main()
