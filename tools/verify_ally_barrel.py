"""Exercise lagged-barrel ally safety and speculative shots in the real engine."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil

from argus_fixture_harness import new_output,stage_fixture,private_game,read_tape,frame_ms
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import Lab,lab_executable,finish_lab
from run_map_intelligence import ROOT,write,digest

SHOTS=('lagged_barrel_hold','aligned_shot','aim_only_ally')
PREFIRES=('coop_prefire_hold','prefire_turn_hold','aligned_prefire')
LABELS=('geometry',*SHOTS,*PREFIRES,'cleanup')


def stage(root,out,source=None):
    return stage_fixture(root,out,source,
        fixtures={'ally_barrel_fixture.qc':(root/'tools/fixtures/ally_barrel.qc').read_text(encoding='utf-8')},
        frame_wrap='AllyBarrelFixture ();\n    Argus_FrameAll ();')


def inspect_fixture(text,ticrate):
    require(text.count('BHVRPL begin ally_barrel')==1,'missing firing quarantine')
    ms=frame_ms(text,'ABFIX',ticrate)
    require(len(re.findall(r'^ABFIX begin dt_ms\s+[\d.]+ layout 1\r?$',text,re.M))==1,'wrong firing layout')
    checks=re.findall(r'^ABFIX check (\w+) ([01])\r?$',text,re.M)
    require(tuple(n for n,_ in checks)==LABELS,'missing firing cases')
    require(checks[0][1]==checks[-1][1]=='1','missing geometry or actor cleanup')
    shots=re.findall(r'^ABFIX shot (\w+) ammo ([\d.-]+) ally_damage ([\d.-]+) enemy_damage ([\d.-]+) aim_ally ([01]) barrel_ally ([01]) owned ([01])\r?$',text,re.M)
    require(tuple(r[0] for r in shots)==SHOTS,'missing actual shot witnesses')
    verdicts={}
    for i,r in enumerate(shots):
        name,ammo,damage,enemyhurt,aimally,barrelally,owned=r
        require(all(math.isfinite(float(v)) and float(v)>=0 for v in (ammo,damage,enemyhurt)), 'invalid damage/ammo witness')
        require(owned=='1' and int(aimally)==int(i==2) and int(barrelally)==int(i==0),'invalid shot premise')
        verdicts[name]=(float(ammo)==int(i!=0) and float(damage)==0 and (i!=1 or float(enemyhurt)>0))
    prefires=re.findall(r'^ABFIX prefire (\w+) ammo\s+([\d.-]+) rockets\s+([\d.-]+) turn\s+([\d.-]+) limit\s+([\d.-]+) owned ([01])\r?$',text,re.M)
    require(tuple(r[0] for r in prefires)==PREFIRES,'missing speculative-shot witnesses')
    for i,r in enumerate(prefires):
        name,ammo,rockets,turn,limit,owned=r
        require(owned=='1' and float(limit)>0,'invalid sight-loss premise')
        require(all(math.isfinite(float(v)) and float(v)>=0 for v in (ammo,rockets,turn,limit)), 'invalid speculative-shot witness')
        require(abs(float(limit)-170*ms/1000)<=.2,'wrong measured turn budget')
        verdicts[name]=(float(ammo)==float(rockets)==int(i==2) and float(turn)<=float(limit)+.15)
    failures=[n for n,ok in checks if ok!='1']
    require(set(failures)=={n for n,ok in verdicts.items() if not ok},'contradictory firing result')
    require(re.findall(r'^ABFIX end checks (\d+) failures (\d+)\r?$',text,re.M)==[(str(len(LABELS)),str(len(failures)))],'wrong firing totals')
    return dict(frame_ms=ms,checks=len(checks),failures=failures,shot_witnesses=shots,prefire_witnesses=prefires)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--prefix',required=True)
    p.add_argument('--source',type=Path,default=ROOT/'src')
    p.add_argument('--map',choices=('dm4','dm2'),default='dm4')
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    p.add_argument('--expect-failure',action='store_true')
    args=p.parse_args();require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix))
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.source)
    with private_game(ROOT,args.prefix,'allycheck',autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
        env=dict(ARGUS_SRC=str(out/'src'),ARGUS_PROGS=str(out/'lq1/progs.dat'),ARGUS_RUNS=str(out/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=40)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale native lab')
                compiled=lab.call('compile_qc',install=False);write(out/'compile.json',compiled)
                require(compiled['ok'] and not compiled['installed_to'],compiled)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                result=lab.call('experiment',map=args.map,duration_sec=10,skill=2,compile=False,repeats=1,primary='engagements',run_name=args.prefix)
                write(out/'experiment.json',result);require(result['ok'],result)
                raw,text=read_tape(out,args.prefix,args.map)
                identity=dict(map=args.map,ticrate=args.ticrate,failed_control=args.expect_failure,
                    source_sha256=source_identity(out/'src'),binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix())
                write(out/'identity.json',identity)
                row=dict(identity,**inspect_fixture(text,args.ticrate))
                write(out/'receipt.json',row);print(json.dumps(row),flush=True)
                require(bool(row['failures'])==args.expect_failure,'wrong firing outcome')
            finally:finish_lab(lab)


if __name__=='__main__':main()
