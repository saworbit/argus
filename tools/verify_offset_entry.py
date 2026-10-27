"""Small physical entry isolation via the native lab; never installs a build.

Use a new --output beneath backups/. --variants accepts current,old_handoff;
--cases accepts 1,2,3,4 (grounded centred/offset, airborne offset/centred).
Current cases must pass. Review old_handoff case 3 manually: its expected
failure is recorded but is not currently enforced by the command's exit code.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil

from run_behaviour_equivalence import Lab, ROOT
from verify_plan_progress import prepare, copy_assets, save, sha


def audit_fixture(source):
    code=re.sub(r'//[^\n]*|/\*.*?\*/','',source,flags=re.S)
    code=re.sub(r'"(?:\\.|[^"\\])*"','""',code)
    assert not re.search(r'\b(?:walkmove|Argus_AI|Argus_Physics|Argus_PlanObserve)\s*\(',code)
    assert len(re.findall(r'setorigin\s*\(self,\s*oe_start\)',code))==1
    assert len(re.findall(r'setorigin\s*\((?:self|oe_bot|other)\b',code))==1
    assert len(re.findall(r'\boe_contact\s*=(?!=)',code))==1
    observing=code.split('    oe_frames = oe_frames + 1;',1)[1].split('    if (oe_contact || !active',1)[0]
    assert not re.search(r'\b(?:self|oe_bot)\.\w+\s*=(?!=)',observing)
    assert set(re.findall(r'\b(\w+)\s*\(',observing)) <= {'if','dprint','ftos','vtos'}


def check(text, case):
    import math
    import re
    assert 'BHVRPL begin offset_entry' in text and 'Host_Error' not in text
    lines = [s for s in text.splitlines() if s.startswith('OFFIX ')]
    assert len(lines)>=5, 'incomplete physical receipt'
    assert re.fullmatch(r"OFFIX begin case " + str(case) + r" start '[^']+' solid 0", lines[0])
    samples = []; contact = None
    for s in lines[1:-2]:
        m = re.fullmatch(r"OFFIX sample t\s+([\d.]+) pos '([^']+)' active ([01]) from ([01]) hp 100 frames (\d+)", s)
        if m:
            row = dict(t=float(m[1]), pos=tuple(map(float, m[2].split())), active=int(m[3]), from_node=int(m[4]), frames=int(m[5]))
            assert len(row['pos']) == 3
            if samples:
                prev = samples[-1]
                assert 0 <= row['t'] - prev['t'] <= .3 and row['frames'] > prev['frames']
                assert math.dist(row['pos'], prev['pos']) < 100, 'teleport/discontinuous entry'
            samples.append(row); continue
        m = re.fullmatch(r"OFFIX contact t\s+([\d.]+) pos '([^']+)' active 1", s)
        assert m and contact is None, 'unknown/duplicate contact'
        contact = dict(t=float(m[1]), pos=tuple(map(float, m[2].split())))
        assert math.dist(contact['pos'], (1361, -191, 320)) < 80
    assert len(samples) >= 3 and samples[0]['t'] == 0
    starts={1:(1361,33,320),2:(1348,32,320),3:(1348.9,32,358.7),4:(1361,33,358.7)}
    assert math.dist(samples[0]['pos'],starts[case])<.2, 'wrong actor placement'
    assert all(math.isfinite(v) for row in samples for v in (*row['pos'],row['t'])), 'nonfinite trajectory'
    success = contact is not None
    if contact:
        assert abs(contact['t']-samples[-1]['t'])<=.2
        assert math.dist(contact['pos'],samples[-1]['pos'])<20
    assert lines[-2] == f'OFFIX end ok {int(success)}' and lines[-1] == 'OFFIX cleanup owned_engine_pending_stop'
    assert samples[-1]['t'] <= 6.2
    return dict(success=success, elapsed=samples[-1]['t'], final_pos=samples[-1]['pos'],
                handoff_positions=[tuple(map(float,p.split())) for p in re.findall(r"OETRACE handoff '([^']+)'",text)],
                handoff_by=next((s['t'] for s in samples if not s['from_node']), None),
                measured_fps=round((samples[-1]['frames'] - 1) / samples[-1]['t'], 1), contact=contact)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory beneath backups/')
    parser.add_argument('--variants', default='current,old_handoff', help='comma-separated current,old_handoff (default: both)')
    parser.add_argument('--cases', default='1,2,3,4', help='comma-separated case IDs 1-4 (default: all)')
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT/'backups') and not output.exists(), 'new backups/ directory required'
    variants=args.variants.split(','); cases=[int(x) for x in args.cases.split(',')]
    assert set(variants) <= {'current','old_handoff'} and set(cases) <= {1,2,3,4}
    output.mkdir(parents=True)
    installed={p:sha(ROOT/p) for p in ('engine/argus/progs.dat','game/argus/progs.dat','lq1/progs.dat')}
    save(output/'plan.json',dict(variants=variants,cases=cases,source_sha256=sha(ROOT/'src/argus.qc'),
        acceptance='Physical goal contact within 6 s at full health with continuous motor movement. Current cases must pass; manually review old_handoff case 3 for the expected distinguishing failure.',
        installed_before=installed))
    with (output/'config.stderr').open('w') as err:
        lab=Lab(err,{'TOKIO_WORKER_THREADS':'2'})
        try:
            lab.call('see',what='project'); cfg=lab.call('config_check')
        finally:lab.close()
    values={r['key']:r['value'] for r in cfg['entries']}; base=Path(values['ARGUS_BASEDIR']); game=values['ARGUS_GAME']
    assert not any(p.exists() for p in (ROOT/'qconsole.log',base/'qconsole.log')), 'harvest first'
    copy_assets(base/'id1',output/'base/id1'); private_game=output/'base'/game;private_game.mkdir()
    for name in ('maps','progs','gfx','sound'):
        if (base/game/name).exists():copy_assets(base/game/name,private_game/name)
    results=[]
    try:
        for variant in variants:
            folder=output/variant;prepare(folder);src=folder/'src'
            code=(src/'argus.qc').read_text()
            if variant=='old_handoff':
                code,count=re.subn(r'float\(entity node\) Argus_WalkArrivalReady =\n\{.*?^\};',
                    'float(entity node) Argus_WalkArrivalReady = { return TRUE; };',code,flags=re.M|re.S)
                assert count==1
            # Passive private prints at the actual branch, without new traces.
            anchor='                oldnode = self.ar_node;'
            assert code.count(anchor)==1
            code=code.replace(anchor,'                if (self == oe_bot) { dprint ("OETRACE handoff "); dprint (vtos (self.origin)); dprint ("\\n"); }\n'+anchor)
            anchor='    if (cspd < '
            at=code.index(anchor,code.index('Argus_WallSlide ='))
            code=code[:at]+'''    if (self == oe_bot && time >= oe_slide_next)
    {
        oe_slide_next = time + 0.2;
        dprint ("OETRACE slide speed "); dprint (ftos (cspd));
        dprint (" normal "); dprint (vtos (n)); dprint ("\\n");
    }
'''+code[at:]
            code='entity oe_bot; float oe_slide_next;\n'+code
            (src/'argus.qc').write_text(code,encoding='utf-8')
            fixture=(ROOT/'tools/fixtures/offset_entry.qc').read_text().replace('entity oe_bot,','entity')
            fixture=fixture.replace(', oe_slide_next;', ';')
            audit_fixture(fixture)
            (src/'offset_entry.qc').write_text(fixture,encoding='utf-8')
            p=src/'progs.src';p.write_text(p.read_text().replace('\nworld.qc\n','\noffset_entry.qc\nworld.qc\n'))
            p=src/'world.qc';world=p.read_text();start=world.index('    if (cvar ("scratch2") >= 3) PlanPhysicalEdges ();')
            end=world.index('else PlanEscapeFixture ();',start)+len('else PlanEscapeFixture ();')
            p.write_text(world[:start]+'    OffsetEntryFixture ();'+world[end:])
            final_tree=hashlib.sha256()
            for item in sorted(src.rglob('*')):
                if item.is_file() and item.suffix in {'.qc','.src'}:
                    final_tree.update(item.relative_to(src).as_posix().encode()+b'\0'+item.read_bytes())
            save(folder/'offset-source.json',dict(variant=variant,production_sha256=sha(ROOT/'src/argus.qc'),
                build_sha256=sha(src/'argus.qc'),fixture_sha256=sha(src/'offset_entry.qc'),final_tree_sha256=final_tree.hexdigest()))
            env=dict(ARGUS_SRC=str(src),ARGUS_PROGS=str(folder/'lq1/progs.dat'),ARGUS_RUNS=str(folder/'runs'),ARGUS_BASEDIR=str(output/'base'),ARGUS_GAME=game,TOKIO_WORKER_THREADS='2')
            with (folder/'offset.stderr').open('w') as err:
                lab=Lab(err,env)
                try:
                    compiled=lab.call('compile_qc',install=False);save(folder/'compile-offset.json',compiled)
                    assert compiled['ok'] and not compiled['installed_to'] and compiled['new_errors']==compiled['new_warnings']==0,compiled
                    shutil.copy2(folder/'lq1/progs.dat',private_game/'progs.dat')
                    for case in cases:
                        (private_game/'autoexec.cfg').write_text(f'sv_protocol 15\nmax_edicts 600\nscratch2 {case}\n')
                        stem=f'offset_{variant}_{case}'
                        r=lab.call('experiment',map='e1m2',duration_sec=10,skill=1,compile=False,repeats=1,primary='stall_parity',run_name=stem)
                        save(folder/(stem+'.native.json'),r);tape=folder/'runs'/(stem+'.log')
                        row=dict(variant=variant,case=case,**check(tape.read_text(errors='replace'),case),tape_sha256=sha(tape),binary_sha256=sha(private_game/'progs.dat'))
                        results.append(row);save(output/'results.json',results);print(json.dumps(row),flush=True)
                        if variant=='current':assert row['success'], 'current physical entry failed'
                finally:lab.close()
    finally:
        after={p:sha(ROOT/p) for p in installed};save(output/'installed-after.json',after);assert installed==after


if __name__=='__main__':main()
