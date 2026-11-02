"""Exercise body-height gating and bounded physical escape in private assets."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil

from argus_fixture_harness import (new_output,stage_fixture,private_game,
    read_tape,check_tape,frame_ms)
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import Lab,lab_executable,finish_lab
from run_map_intelligence import ROOT,write,digest

CASES=('upper_floor','lower_floor','upper_fire','lower_fire',
       'touch_upper','touch_lower','same_floor')
PHYSICAL=('entry_bodies_fit','entry_kept','physical_exit','continuous_motion',
          'task_preserved','alive_and_dry')


def audit_fixture(text):
    checker=text.split('void(string label, float ok) BodyHeightCheck =',1)[1].split('void(vector seat',1)[0]
    require(not re.search(r'\b\w+\.\w+\s*=(?!=)',checker),'check helper changes an actor')
    require(set(re.findall(r'\b(\w+)\s*\(',checker))<={'if','dprint','ftos'},
            'check helper invokes an unexpected function')
    after=text.split('void() BodyHeightAfter =',1)[1]
    observe,terminal=after.split('        bh_bot.velocity =',1)
    calls=set(re.findall(r'\b(\w+)\s*\(',after))
    require(calls<={'if','vlen','dprint','ftos','vtos','BodyHeightCheck'},
            'observer invokes an unexpected helper')
    require(not re.search(r'\b(setorigin|setsize|walkmove|droptofloor|Argus_\w+)\s*\(',after),
            'observer invokes movement or production decisions')
    require(not re.search(r'\b\w+\.\w+\s*=(?!=)',observe),'observer changes an actor')
    require(set(re.findall(r'\b(\w+\.\w+)\s*=(?!=)', 'bh_bot.velocity ='+terminal))==
            {'bh_bot.velocity','bh_bot.movetype','bh_bot.think','bh_bot.nextthink'},
            'terminal changes unexpected actor state')


def stage(root,out,source=None):
    text=(root/'tools/fixtures/body_height.qc').read_text(encoding='utf-8')
    audit_fixture(text)
    return stage_fixture(root,out,source,fixtures={'body_height_fixture.qc':text},
        frame_wrap='BodyHeightBefore ();\n    if (!bh_done) Argus_FrameAll ();\n    BodyHeightAfter ();')


def inspect_fixture(text,map_name,ticrate):
    check_tape(text,map_name)
    require(text.count('BHVRPL begin body_height')==1,'missing quarantine')
    require(len(re.findall(r'^BHFIX begin dt_ms\s+[\d.]+ layout 1$',text,re.M))==1,'wrong layout')
    ms=frame_ms(text,'BHFIX',ticrate)
    labels=(*CASES,*PHYSICAL) if map_name=='dm3' else PHYSICAL
    checks=re.findall(r'^BHCHECK (\w+) ([01])$',text,re.M)
    require(tuple(n for n,_ in checks)==labels,'missing, duplicate or reordered check')
    cases=re.findall(r'^BHCASE (\w+) initialfit ([01]) finalfit ([01]) distance\s+([\d.-]+) dodge ([01]) firing ([01])$',text,re.M)
    require(tuple(r[0] for r in cases)==(CASES if map_name=='dm3' else ()),'missing native case')
    verdicts={}
    for name,initial,final,distance,dodge,firing in cases:
        require(initial=='1','invalid initial subject body')
        distance=float(distance);require(math.isfinite(distance) and distance>=0,'invalid nudge distance')
        expected=3 if name=='same_floor' else 0
        verdicts[name]=(final=='1' and abs(distance-expected)<.1 and dodge=='0' and firing=='1')
    entry=re.findall(r'^BHENTRY beforefit ([01]) upperfit ([01]) afterfit ([01]) movement\s+([\d.-]+)$',text,re.M)
    require(len(entry)==1,'missing body entry')
    before,upper,after,movement=entry[0]
    require(before==upper=='1','invalid physical initial bodies')
    movement=float(movement);require(math.isfinite(movement) and movement>=0)
    verdicts['entry_bodies_fit']=True
    verdicts['entry_kept']=(after=='1' and movement<.01)
    results=re.findall(r"^BHRESULT completed ([01]) seconds\s+([\d.]+) frames (\d+) pos '([^']+)' hp\s+(-?[\d.]+) grounded ([01]) worldfloor ([01]) wet ([0-3]) lost ([01]) discontinuous ([01])$",text,re.M)
    require(len(results)==1,'missing physical result')
    completed,seconds,frames,position,hp,ground,world,wet,lost,discontinuous=results[0]
    seconds=float(seconds);frames=int(frames);hp=float(hp);pos=tuple(map(float,position.split()))
    require(len(pos)==3 and all(math.isfinite(v) for v in (*pos,seconds,hp)),'nonfinite result')
    require(0<seconds<=3.2 and frames>1,'invalid duration')
    fps=(frames-1)/seconds
    require((8<=fps<=12) if ticrate==.1 else (60<=fps<=90),'wrong observed cadence')
    poses=re.findall(r"^BHPOSE t\s+([\d.]+) pos '([^']+)' active ([01]) hp\s+(-?[\d.]+)$",text,re.M)
    require(poses and float(poses[0][0])==0,'missing initial observation')
    vectors=[tuple(map(float,p[1].split())) for p in poses]
    require(all(len(v)==3 and all(math.isfinite(x) for x in v) for v in vectors),'invalid pose')
    for a,b in zip(poses,poses[1:]):
        require(0<float(b[0])-float(a[0])<=.7,'invalid observation spacing')
    require(discontinuous=='1' or all(math.dist(a,b)<240 for a,b in zip(vectors,vectors[1:])),
            'sampled discontinuity hidden by terminal')
    require(float(poses[-1][0])<=seconds<=float(poses[-1][0])+.7,'terminal outside observed interval')
    require(math.dist(pos,vectors[-1])<240,'discontinuous terminal position')
    require(lost=='1' or all(p[2]=='1' for p in poses),'ownership loss hidden by terminal')
    recognized=1+len(checks)+len(cases)+len(entry)+len(results)+1+len(poses)
    require(sum(s.startswith(('BHFIX ','BHCHECK ','BHCASE ','BHENTRY ','BHRESULT ','BHPOSE ')) for s in text.splitlines())==recognized,
            'malformed or duplicate body-height record')
    at_exit=(math.dist(pos,(677,193,-200))<48 if map_name=='dm3'
             else math.dist(pos,(-157.1,833,-232))>=64)
    supported=(ground==world=='1' and wet=='0' and hp>0)
    require((completed=='1')==(at_exit and supported),'contradictory completion')
    verdicts.update(physical_exit=(completed=='1' and seconds<3),
        continuous_motion=discontinuous=='0',task_preserved=lost=='0',alive_and_dry=(hp>0 and wet=='0'))
    ends=re.findall(r'^BHFIX end checks (\d+) failures (\d+)$',text,re.M)
    failed=[n for n,ok in checks if ok=='0']
    require(ends==[(str(len(labels)),str(len(failed)))],'wrong check totals')
    require(set(failed)=={n for n,ok in verdicts.items() if not ok},'dishonest check verdict')
    return dict(checks=len(labels),failures=failed,seconds=seconds,frames=frames,
        measured_fps=fps,frame_ms=ms,position=pos,health=hp,
        task_lost=lost=='1',discontinuous=discontinuous=='1',cases=cases,entry=entry[0])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--prefix',required=True)
    p.add_argument('--source',type=Path,default=ROOT/'src')
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    p.add_argument('--maps',default='dm3,e1m6')
    p.add_argument('--expect-failure',action='store_true')
    args=p.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix),'invalid prefix')
    maps=args.maps.split(',');require(maps and len(set(maps))==len(maps) and set(maps)<={'dm3','e1m6'})
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);src=stage(ROOT,out,args.source)
    rows=[]
    with private_game(ROOT,args.prefix,'heightcheck',autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
        env=dict(ARGUS_SRC=str(src),ARGUS_PROGS=str(out/'lq1/progs.dat'),ARGUS_RUNS=str(out/'runs'),
                 ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=40)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale lab')
                c=lab.call('compile_qc',install=False);write(out/'compile.json',c)
                require(c['ok'] and not c['installed_to'],c)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                for m in maps:
                    name=args.prefix+'_'+m
                    r=lab.call('experiment',map=m,duration_sec=10,skill=2,compile=False,repeats=1,
                               primary='stall_parity',run_name=name)
                    write(out/(m+'.experiment.json'),r);require(r['ok'],r)
                    raw,text=read_tape(out,name,m)
                    brief=lab.call('brief_run',log=name,map=m,detail='full');write(out/(m+'.brief.json'),brief)
                    row=dict(map=m,ticrate=args.ticrate,source_sha256=source_identity(src),
                        fixture_sha256=digest(src/'body_height_fixture.qc'),
                        binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),
                        raw=raw.relative_to(ROOT).as_posix(),**inspect_fixture(text,m,args.ticrate),
                        rescues=brief['events'].get('unstick',0))
                    rows.append(row);write(out/'receipt.json',rows);print(json.dumps(row),flush=True)
                    require(bool(row['failures'])==args.expect_failure,'wrong height-gate outcome')
                    require(args.expect_failure or not row['rescues'],'forced relocation is not physical escape')
            finally:finish_lab(lab)


if __name__=='__main__':main()
