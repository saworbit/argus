"""Check production stall decisions with explicit stationary and moving inputs."""
import argparse
import json
from pathlib import Path
import re
import shutil

from argus_fixture_harness import new_output, stage_fixture, private_game, read_tape, frame_ms
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import Lab, lab_executable, finish_lab
from run_map_intelligence import ROOT, write, digest

LABELS=('stationary_train_released','stationary_jump_released','stationary_rj_released',
        'stationary_swim_released','stationary_door_released','moving_typed_pause',
        'combat_wait','lift_wait','lift_hop_wait','gait_tail','camp_orbit_keeps_goal',
        'camp_deadline_unchanged','camp_wedge_released','far_item_not_pause','live_item_not_pause')


def stage(root,out,source=None):
    source=Path(source or root/'src')
    production=(source/'argus.qc').read_text(encoding='utf-8')
    require(production.count('    // ---- stall detection ----')==1,'stall boundary changed')
    block=production.split('    // ---- stall detection ----',1)[1].split('    if (time > self.ar_nextlog)',1)[0]
    require(block.count('self.ar_lastpos = self.origin;')==1,'incomplete stall block')
    wrapper='void() StallWaitDecision =\n{\n    local vector gp;\n    local float fighting;\n    fighting = sw_fighting;\n'+block+'};\n'
    fixture=(root/'tools/fixtures/stall_ownership.qc').read_text(encoding='utf-8')
    require(fixture.count('// INSERT_DECISION')==1)
    return stage_fixture(root,out,source,fixtures={'stall_ownership_fixture.qc':fixture.replace('// INSERT_DECISION',wrapper)},
        frame_wrap='Argus_FrameAll ();\n    StallWaitFixture ();')


def inspect_fixture(text,ticrate):
    require(text.count('BHVRPL begin stall_ownership')==1,'missing decision quarantine')
    ms=frame_ms(text,'SWCHECK',ticrate)
    require(len(re.findall(r'^SWCHECK begin dt_ms [\d.]+ layout 1\r?$',text,re.M))==1,'wrong decision layout')
    rows=re.findall(r'^SWCHECK (\w+) ([01])\r?$',text,re.M)
    require(tuple(name for name,_ in rows)==LABELS,'missing decision cases')
    failures=[name for name,ok in rows if ok!='1']
    require(re.findall(r'^SWCHECK end checks (\d+) failures (\d+)\r?$',text,re.M)==[(str(len(LABELS)),str(len(failures)))],'wrong decision totals')
    return dict(frame_ms=ms,checks=len(rows),failures=failures)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prefix',required=True)
    p.add_argument('--source',type=Path,default=ROOT/'src')
    p.add_argument('--map',choices=('dm3','e1m6'),default='dm3')
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    p.add_argument('--expect-failure',action='store_true',help='retain a failed control, never report it as acceptance')
    args=p.parse_args();require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix))
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.source)
    with private_game(ROOT,args.prefix,'stallcheck') as game:
        env=dict(ARGUS_SRC=str(out/'src'),ARGUS_PROGS=str(out/'lq1/progs.dat'),ARGUS_RUNS=str(out/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=40)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale lab')
                compiled=lab.call('compile_qc',install=False);write(out/'compile.json',compiled)
                require(compiled['ok'] and not compiled['installed_to'],compiled)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                result=lab.call('experiment',map=args.map,duration_sec=10,skill=2,compile=False,repeats=1,primary='stall_parity',run_name=args.prefix)
                write(out/'experiment.json',result);require(result['ok'],result)
                raw,text=read_tape(out,args.prefix,args.map)
                row=dict(map=args.map,ticrate=args.ticrate,failed_control=args.expect_failure,
                    source_sha256=source_identity(out/'src'),binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix(),**inspect_fixture(text,args.ticrate))
                write(out/'receipt.json',row);print(json.dumps(row),flush=True)
                require(bool(row['failures'])==args.expect_failure,'wrong decision outcome')
            finally:finish_lab(lab)


if __name__=='__main__':main()
