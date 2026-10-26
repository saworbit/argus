"""Private deterministic-input fixture; normal gameplay RNG is never edited.

Copies QC under backups/, substitutes only its random-input provider, pins the
vanilla host_framerate cvar, and stops after 3842 server frames. Compilation,
engine ownership and briefing all use the native lab MCP. Two disabled repeats
must agree before enabled/compute/legacy arms can provide evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

from run_behaviour_equivalence import ROOT, OUT, Lab, MODES, identity, cpu_seconds

FIXTURE = '''// PRIVATE TEST INPUT PROVIDER. Never included in shipped progs.src.
.float bhvrng_state, bhvrng_calls;
entity bhvrng_input;
float bhvrpl_frames;
float() random =
{
    // Every intermediate integer is below 2^24, exactly representable in QC.
    bhvrng_input.bhvrng_state = bhvrng_input.bhvrng_state * 109 + 1021;
    bhvrng_input.bhvrng_state = bhvrng_input.bhvrng_state
        - floor (bhvrng_input.bhvrng_state / 65521) * 65521;
    bhvrng_input.bhvrng_calls = bhvrng_input.bhvrng_calls + 1;
    return bhvrng_input.bhvrng_state / 65521;
};
void() BehaviourReplayReset =
{
    // A nonsolid metadata-only edict: runtime world writes are forbidden.
    bhvrng_input = spawn ();
    bhvrng_input.classname = "bhvrpl_inputs";
    bhvrng_input.bhvrng_state = cvar ("scratch2");
    if (bhvrng_input.bhvrng_state <= 0) bhvrng_input.bhvrng_state = 113;
    bhvrng_input.bhvrng_calls = 0; bhvrpl_frames = 0;
    cvar_set ("host_framerate", "0.015625");
    dprint ("BHVRPL begin "); dprint (mapname);
    dprint (" seed "); dprint (ftos (bhvrng_input.bhvrng_state)); dprint ("\\n");
};
void() BehaviourReplayTick =
{
    bhvrpl_frames = bhvrpl_frames + 1;
    if (bhvrpl_frames != 3842) return;
    dprint ("BHVRPL end frames "); dprint (ftos (bhvrpl_frames));
    dprint (" calls "); dprint (ftos (bhvrng_input.bhvrng_calls)); dprint ("\\n");
    // These stock engine commands run after this frame's physics completes.
    localcmd ("echo BHVRPL dump_begin\\nedicts\\necho BHVRPL dump_end\\nquit\\n");
};
'''


def prepare(folder, source=None):
    assert not folder.exists(), 'private build already exists: do not overwrite evidence'
    shutil.copytree(source or ROOT / 'src', folder / 'src')
    (folder / 'lq1').mkdir()
    src = folder / 'src'
    path = src / 'defs.qc'
    text = path.read_text()
    text, count = re.subn(r'float\(\) random\s*= #7;[^\n]*',
        'float() random; // private deterministic input provider\nvoid() BehaviourReplayReset;\nvoid() BehaviourReplayTick;', text)
    assert count == 1
    path.write_text(text, newline='\r\n')
    path = src / 'progs.src'
    text = path.read_text()
    assert text.count('localized_text.qc') == 1
    path.write_text(text.replace('localized_text.qc', 'behaviour_replay_inputs.qc\nlocalized_text.qc'), newline='\r\n')
    (src / 'behaviour_replay_inputs.qc').write_text(FIXTURE, newline='\r\n')
    path = src / 'world.qc'
    text = path.read_text()
    assert text.count('Argus_CountSlots ();') == 1
    path.write_text(text.replace('Argus_CountSlots ();', 'Argus_CountSlots ();\n    BehaviourReplayReset ();'), newline='\r\n')
    path = src / 'argus.qc'
    text = path.read_text()
    anchor = '    Argus_BehaviourFixturePost ();' if source is None else '    Argus_TacticFixtureTick ();'
    assert text.count(anchor) == 1
    path.write_text(text.replace(anchor, anchor + '\n    BehaviourReplayTick ();'), newline='\r\n')
    return dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(folder / 'lq1/progs.dat'))


def audit_private(folder, source):
    """Independently remove the explicit harness edits and compare every source."""
    private = folder / 'src'
    paths = {p.relative_to(source) for p in source.rglob('*') if p.suffix in {'.qc', '.src', '.json'}}
    actual = {p.relative_to(private) for p in private.rglob('*') if p.suffix in {'.qc', '.src', '.json'}}
    assert actual == paths | {Path('behaviour_replay_inputs.qc')}, 'unexpected private source files'
    assert (private / 'behaviour_replay_inputs.qc').read_text() == FIXTURE
    for relative in paths:
        original = (source / relative).read_text()
        modified = (private / relative).read_text()
        if relative == Path('defs.qc'):
            original_decl = re.search(r'float\(\) random\s*= #7;[^\n]*', original)[0]
            modified = modified.replace('float() random; // private deterministic input provider\nvoid() BehaviourReplayReset;\nvoid() BehaviourReplayTick;', original_decl)
        elif relative == Path('progs.src'):
            modified = modified.replace('behaviour_replay_inputs.qc\n', '')
        elif relative == Path('world.qc'):
            modified = modified.replace('\n    BehaviourReplayReset ();', '')
        elif relative == Path('argus.qc'):
            modified = modified.replace('\n    BehaviourReplayTick ();', '')
        assert modified == original, f'private fixture changed gameplay source: {relative}'
    assert 'behaviour_replay_inputs.qc' not in (ROOT / 'src/progs.src').read_text()
    assert re.search(r'float\(\) random\s*= #7;', (ROOT / 'src/defs.qc').read_text())
    return dict(files_restored_exactly=len(paths), production_rng_unchanged=True)


def extract(text, map_name, seed):
    starts = list(re.finditer(rf'^BHVRPL begin {re.escape(map_name)} seed\s+{seed}[ \t]*$', text, re.M))
    assert starts, 'missing controlled-input start'
    segment = text[starts[-1].start():]
    assert not any(error in segment for error in ('Host_Error', 'runaway loop error', 'Program error')), 'engine error in replay'
    assert len(re.findall(r'^BHVRPL begin ', segment, re.M)) == 1, 'wrong final input seed'
    ends = re.findall(r'^BHVRPL end frames (\d+) calls (\d+)[ \t]*$', segment, re.M)
    assert len(ends) == 1 and int(ends[0][0]) == 3842 and int(ends[0][1]) > 0, 'incomplete/duplicate fixed-frame replay'
    begin = re.search(r'^BHVRPL dump_begin[ \t]*\n', segment, re.M)
    end = re.search(r'^BHVRPL dump_end[ \t]*$', segment, re.M)
    assert begin and end and begin.end() < end.start(), 'missing entity state'
    assert len(re.findall(r'^BHVRPL dump_begin[ \t]*$', segment, re.M)) == 1, 'duplicate state begin'
    assert len(re.findall(r'^BHVRPL dump_end[ \t]*$', segment, re.M)) == 1, 'duplicate state end'
    gameplay = '\n'.join(line for line in segment.splitlines() if line.startswith(('ARGLOG ', 'ARGEVT ', 'ARGUS ', 'TACTIC')))
    assert 'ARGLOG ' in gameplay and 'ARGEVT ' in gameplay, 'empty gameplay stream'
    dump = segment[begin.end():end.start()]
    count = re.search(r'^(\d+) entities[ \t]*$', dump, re.M)
    assert count and 0 < int(count[1]) <= 600, 'replay exceeds vanilla edict budget'
    # This excludes only explicitly diagnostic fields, never gameplay fields.
    state = '\n'.join(line for line in dump.splitlines() if not re.search(r'\bar_bd_\w+\b', line))
    assert 'bhvrng_calls' in state and 'bhvrng_state' in state, 'missing final input-provider state'
    assert 'EDICT ' in state, 'missing entity dump'
    return dict(gameplay=gameplay, state=state)


def compare(control, candidate):
    for key in ('gameplay', 'state'):
        assert control[key] == candidate[key], f'{key} differs under identical inputs'
    return {key + '_sha256': hashlib.sha256(control[key].encode()).hexdigest() for key in control}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepare', action='store_true')
    ap.add_argument('--shipped', action='store_true', help='private original-source control; candidate controls must exist first')
    ap.add_argument('--maps', default='dm2,dm4')
    ap.add_argument('--seeds', default='113,50917')
    ap.add_argument('--output', type=Path, default=OUT, help='fresh evidence directory for a new candidate')
    ap.add_argument('--prefix', default='bhv1_replay3', help='unique native run-name prefix')
    ap.add_argument('--baseline-source', type=Path, default=ROOT / 'backups/behaviour-step0/src')
    args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9._-]{1,40}', args.prefix), 'invalid run-name prefix'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    folder = out / ('replay-shipped-build' if args.shipped else 'replay-build-v2')
    environment = dict(ARGUS_SRC=str(folder / 'src'), ARGUS_PROGS=str(folder / 'lq1/progs.dat'))
    if args.prepare:
        environment = prepare(folder, args.baseline_source if args.shipped else None)
        stem = 'replay-shipped' if args.shipped else 'replay-v2'
        with (out / f'{stem}-compile.stderr').open('w') as err:
            lab = Lab(err, environment)
            try:
                result = lab.call('compile_qc', install=False)
                (out / f'{stem}-compile.json').write_text(json.dumps(result, indent=2))
                assert result['ok'], result
            finally:
                lab.close()
        return
    isolation = audit_private(folder, args.baseline_source if args.shipped else ROOT / 'src')
    (folder / 'isolation.json').write_text(json.dumps(isolation, indent=2))
    maps = args.maps.split(','); seeds = list(map(int, args.seeds.split(',')))
    assert set(maps) <= {'dm2', 'dm4'} and len(seeds) <= 4 and all(0 < seed < 65521 for seed in seeds)
    staged = ROOT / 'engine/argus/progs.dat'
    original = staged.read_bytes()
    results_path = out / 'replay-v3-results.json'
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    private_hash = hashlib.sha256()
    for path in sorted((folder / 'src').rglob('*')):
        if path.suffix in {'.qc', '.src'}:
            private_hash.update(path.relative_to(folder / 'src').as_posix().encode() + b'\0')
            private_hash.update(path.read_bytes())
    try:
        staged.write_bytes((folder / 'lq1/progs.dat').read_bytes())
        for map_name in maps:
            for seed in seeds:
                control = None
                if args.shipped:
                    control = extract((ROOT / f'runs/{args.prefix}_{map_name}_s{seed}_off.log').read_text(encoding='latin-1'), map_name, seed)
                for label in (('shipped',) if args.shipped else ('off', 'off_repeat', 'compute', 'legacy', 'on')):
                    mode = 'off' if label in {'off_repeat', 'shipped'} else label
                    name = f'{args.prefix}_{map_name}_s{seed}_{label}'
                    known = next((r for r in results if r['name'] == name), None)
                    if known:
                        evidence = extract((ROOT / f'runs/{name}.log').read_text(encoding='latin-1'), map_name, seed)
                        if label == 'off': control = evidence
                        else: compare(control, evidence)
                        continue
                    assert not (ROOT / f'runs/{name}.log').exists(), 'orphan tape: investigate before retry'
                    before = identity(map_name)
                    active = False
                    with (out / f'{name}.stderr').open('w') as err:
                        lab = Lab(err, environment)
                        try:
                            start = lab.call('match_start', map=map_name, duration_sec=100, skill=1, run_name=name)
                            active = True
                            deadline = time.monotonic() + 10
                            while True:
                                status = lab.call('match_status')
                                if 'ARGLOG ' in json.dumps(status): break
                                assert status.get('running') and time.monotonic() < deadline, status
                                time.sleep(.1)
                            lab.call('tune', command='scratch1 591')
                            lab.call('tune', command=f'scratch2 {seed}')
                            lab.call('tune', command=f'scratch4 {MODES[mode]}')
                            boundary = lab.call('match_status')['next_line']
                            lab.call('tune', command=f'map {map_name}')
                            ready_deadline = time.monotonic() + 10
                            while True:
                                ready = lab.call('match_status', since_line=boundary)
                                if f'BHVRPL begin {map_name} seed {seed}' in json.dumps(ready): break
                                assert ready.get('running') and time.monotonic() < ready_deadline, ready
                                time.sleep(.1)
                            cpu_begin = cpu_seconds(start['pid'])
                            wall_begin = time.monotonic()
                            cpu_window = None
                            deadline = time.monotonic() + 85
                            while True:
                                time.sleep(1)
                                status = lab.call('match_status')
                                if not status.get('running'): break
                                elapsed = time.monotonic() - wall_begin
                                if cpu_window is None and elapsed >= 50:
                                    consumed = cpu_seconds(start['pid']) - cpu_begin
                                    cpu_window = dict(wall_seconds=elapsed, cpu_seconds=consumed,
                                                      cpu_ms_per_wall_second=1000 * consumed / elapsed)
                                assert time.monotonic() < deadline, 'controlled replay timed out'
                            stop = lab.call('match_stop')
                            active = False
                            brief = lab.call('brief_run', log=name, map=map_name)
                            text = (ROOT / f'runs/{name}.log').read_text(encoding='latin-1')
                            evidence = extract(text, map_name, seed)
                            segment = text[text.rindex(f'BHVRPL begin {map_name} seed {seed}'):]
                            assert ('BHVDBG ' in segment) == (mode in {'legacy', 'on'}), 'wrong output arm'
                            assert ('ar_bd_valid' in segment) == (mode != 'off'), 'observer computation was not exercised'
                            assert identity(map_name) == before, 'candidate changed during replay'
                            if label == 'off':
                                control = evidence
                                hashes = {k + '_sha256': hashlib.sha256(v.encode()).hexdigest() for k, v in evidence.items()}
                            else:
                                hashes = compare(control, evidence)
                            row = dict(name=name, map=map_name, seed=seed, mode=label, identity=before,
                                source_kind='shipped' if args.shipped else 'candidate',
                                private_source_sha256=private_hash.hexdigest(),
                                cpu_window=cpu_window,
                                private_fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),
                                stop=stop, brief=brief, **hashes)
                            results.append(row)
                            results_path.write_text(json.dumps(results, indent=2))
                            print(json.dumps(dict(name=name, exact=True, goals=brief['totals']['goals'], **hashes)), flush=True)
                        finally:
                            if active: lab.call('match_stop')
                            lab.close()
    finally:
        staged.write_bytes(original)


if __name__ == '__main__':
    main()
