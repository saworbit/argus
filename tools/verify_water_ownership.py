"""Check task/goal identity through the actual private route observer."""
import argparse
import json
from pathlib import Path
import re
import shutil

from argus_fixture_harness import new_output,stage_fixture,private_game,read_tape,frame_ms
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import Lab,lab_executable,finish_lab
from run_map_intelligence import ROOT,write,digest
from verify_water_route import audit_fixture

CASES=('owned','task_only','goal_only','neither')
CURRENT='active = (wr_bot.ar_taskgoal == wr_goal && wr_bot.ar_goal == wr_goal);'
LEGACY='active = wr_bot.ar_taskgoal == wr_goal && wr_bot.ar_goal == wr_goal;'


def stage(root,out,legacy=False):
    fixture=(root/'tools/fixtures/water_route.qc').read_text(encoding='utf-8')
    audit_fixture(fixture);require(fixture.count(CURRENT)==1,'unexpected observer predicate')
    if legacy:fixture=fixture.replace(CURRENT,LEGACY)
    contracts=(root/'tools/fixtures/route_decisions.qc').read_text(encoding='utf-8')
    if 'Argus_GaitApproachAction =' in (root/'src/argus.qc').read_text(encoding='utf-8'):
        fixture='#define ROUTE_ACTION_COMPONENTS\n'+fixture
        contracts='#define ROUTE_DECISION_COMPONENTS\n'+contracts
    return stage_fixture(root,out,fixtures={'route_decisions_fixture.qc':contracts,
        'water_route_fixture.qc':fixture,
        'water_ownership_fixture.qc':(root/'tools/fixtures/water_ownership.qc').read_text(encoding='utf-8')},
        frame_wrap='if (time < 2) Argus_FrameAll ();\n    WaterOwnershipFixture ();')


def inspect_fixture(text,ticrate):
    require(text.count('BHVRPL begin water_ownership')==1,'missing quarantine')
    ms=frame_ms(text,'WRID',ticrate)
    require(len(re.findall(r'^WRID begin dt_ms\s+[\d.]+ layout 1\r?$',text,re.M))==1,'wrong layout')
    rows=re.findall(r'^WRID case (\w+)\r?\nWRFIX sample [^\r\n]* active ([01]) hp 100 frames (\d+)\r?$',text,re.M)
    require(tuple(r[0] for r in rows)==CASES,'missing actual observer calls')
    require([int(r[2]) for r in rows]==[1,2,3,4],'wrong observer frame counter')
    require(len(re.findall(r'^WRFIX sample ',text,re.M))==4,'extra observer samples')
    require(len(re.findall(r'^WRID ',text,re.M))==6,'extra ownership records')
    require(re.findall(r'^WRID end cases 4 cleanup ([01])\r?$',text,re.M)==['1'],'actor cleanup failed')
    failures=[name for name,active,_ in rows if int(active)!=int(name=='owned')]
    return dict(frame_ms=ms,cases=rows,failures=failures)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--prefix',required=True)
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    p.add_argument('--legacy',action='store_true')
    args=p.parse_args();require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix))
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.legacy)
    with private_game(ROOT,args.prefix,'ownershipcheck',autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
        env=dict(ARGUS_SRC=str(out/'src'),ARGUS_PROGS=str(out/'lq1/progs.dat'),ARGUS_RUNS=str(out/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=30)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale lab')
                c=lab.call('compile_qc',install=False);write(out/'compile.json',c);require(c['ok'] and not c['installed_to'],c)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                r=lab.call('experiment',map='dm3',duration_sec=10,skill=2,compile=False,repeats=1,primary='engagements',run_name=args.prefix)
                write(out/'experiment.json',r);require(r['ok'],r)
                raw,text=read_tape(out,args.prefix,'dm3')
                row=dict(ticrate=args.ticrate,legacy=args.legacy,source_sha256=source_identity(out/'src'),
                    binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix(),**inspect_fixture(text,args.ticrate))
                write(out/'receipt.json',row);print(json.dumps(row),flush=True)
                require(row['failures']==(['task_only'] if args.legacy else []),'wrong ownership result')
            finally:finish_lab(lab)


if __name__=='__main__':main()
