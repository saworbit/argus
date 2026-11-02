"""Verify body separation and continuing dm3 routing with native collision."""
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

CASES=('upper_floor','wall_refused','clear_step','upper_fire','overlap_axis','overlap_diagonal')
LABELS=(*CASES,'route_complete','continuous_motion','task_preserved','dry_and_alive')


def stage(root,out,source=None):
    return stage_fixture(root,out,source,
        fixtures={'body_nudge_fixture.qc':(root/'tools/fixtures/body_nudge.qc').read_text(encoding='utf-8')},
        frame_wrap='BodyNudgeBefore ();\n    if (!bn_done) Argus_FrameAll ();\n    BodyNudgeAfter ();')


def inspect_fixture(text,ticrate):
    require(text.count('BHVRPL begin body_nudge')==1,'missing quarantine')
    ms=frame_ms(text,'BNFIX',ticrate)
    require(len(re.findall(r'^BNFIX begin dt_ms\s+[\d.]+ layout 1\r?$',text,re.M))==1,'wrong nudge layout')
    checks=re.findall(r'^BNCHECK (\w+) ([01])\r?$',text,re.M)
    require(tuple(n for n,_ in checks)==LABELS,'missing nudge cases')
    cases=re.findall(r'^BNCASE (\w+) initialfit ([01]) finalfit ([01]) distance\s+([\d.-]+) dodge ([01])\r?$',text,re.M)
    require(tuple(r[0] for r in cases)==CASES,'missing real-hull witnesses')
    verdicts={}
    for name,initial,final,distance,dodge in cases:
        require(initial==('0' if name.startswith('overlap_') else '1'),'invalid initial body placement')
        d=float(distance);require(math.isfinite(d) and d>=0,'invalid distance')
        expected={'clear_step':3,'overlap_axis':16,'overlap_diagonal':math.sqrt(512)}.get(name,0)
        verdicts[name]=(final=='1' and dodge=='0' and abs(d-expected)<.1)
    ends=re.findall(r'^BNFIX end checks (\d+) failures (\d+) seconds\s+([\d.]+) frames (\d+)\r?$',text,re.M)
    require(len(ends)==1,'missing terminal outcome')
    count,failures,seconds,frames=ends[0];seconds=float(seconds);frames=int(frames)
    require(seconds>0 and frames>1,'invalid observation duration')
    fps=(frames-1)/seconds
    require((8<=fps<=12) if ticrate==.1 else (60<=fps<=90),'wrong observed cadence')
    results=re.findall(r"^BNRESULT pos '\s*([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)' lost ([01]) discontinuous ([01]) hp\s+([\d.-]+) wet ([0-3])\r?$",text,re.M)
    require(len(results)==1,'missing physical outcome')
    x,y,z,lost,discontinuous,hp,wet=results[0];pos=tuple(map(float,(x,y,z)))
    require(all(math.isfinite(v) for v in (*pos,float(hp))),'invalid physical outcome')
    verdicts['route_complete']=math.dist(pos,(677,193,-200))<48 and seconds<3
    verdicts['continuous_motion']=discontinuous=='0'
    verdicts['task_preserved']=lost=='0'
    verdicts['dry_and_alive']=float(hp)>0 and wet=='0'
    failed=[n for n,ok in checks if ok=='0']
    require(set(failed)=={n for n,ok in verdicts.items() if not ok},'contradictory physical result')
    require((count,failures)==(str(len(LABELS)),str(len(failed))),'wrong totals')
    return dict(checks=len(checks),failures=failed,cases=cases,seconds=seconds,frames=frames,
        frame_ms=ms,measured_fps=fps,position=pos,lost=lost=='1',discontinuous=discontinuous=='1')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--prefix',required=True)
    p.add_argument('--source',type=Path,default=ROOT/'src')
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    p.add_argument('--expect-failure',action='store_true')
    args=p.parse_args();require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix))
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.source)
    with private_game(ROOT,args.prefix,'nudgecheck',autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
        env=dict(ARGUS_SRC=str(out/'src'),ARGUS_PROGS=str(out/'lq1/progs.dat'),ARGUS_RUNS=str(out/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=40)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale lab')
                c=lab.call('compile_qc',install=False);write(out/'compile.json',c);require(c['ok'] and not c['installed_to'],c)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                r=lab.call('experiment',map='dm3',duration_sec=14,skill=2,compile=False,repeats=1,primary='stall_parity',run_name=args.prefix)
                write(out/'experiment.json',r);require(r['ok'],r)
                raw,text=read_tape(out,args.prefix,'dm3');brief=lab.call('brief_run',log=args.prefix,map='dm3',detail='full');write(out/'brief.json',brief)
                identity=dict(map='dm3',ticrate=args.ticrate,failed_control=args.expect_failure,
                    source_sha256=source_identity(out/'src'),binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix())
                write(out/'identity.json',identity)
                row=dict(identity,**inspect_fixture(text,args.ticrate),rescues=brief['events'].get('unstick',0))
                write(out/'receipt.json',row);print(json.dumps(row),flush=True)
                require(bool(row['failures'])==args.expect_failure,'wrong nudge outcome')
                require(args.expect_failure or not row['rescues'],'forced relocation is not completion')
            finally:finish_lab(lab)


if __name__=='__main__':main()
