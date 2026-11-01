"""Observe full-rate bot movement through the source-built native lab.

Diagnostics read intent and actual positions; they do not change steering.
Use --contracts for the private helper-equivalence checks, outside game bands.
"""
import argparse
import bisect
import json
import math
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import new_output, stage_fixture, private_game, read_tape
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import Lab, finish_lab, lab_executable, lab_cli
from run_map_intelligence import ROOT, digest, write

LABELS = ('disabled_yaw','disabled_fields',*('raw_yaw',)*7,
          'no_steering_write','basis_preserved','trace_preserved')


def stage(root, output, source=None, *, contracts=False):
    fixtures={}
    wrap=None
    if contracts:
        fixtures={'motion_observer_fixture.qc':(root/'tools/fixtures/motion_observer.qc').read_text(encoding='utf-8')}
        wrap='MotionObserverFixture ();\n    Argus_FrameAll ();'
    return stage_fixture(root,output,source,fixtures=fixtures,frame_wrap=wrap)


def inspect_contracts(text):
    require(text.count('BHVRPL begin motion_observer')==1,'missing observer quarantine')
    checks=re.findall(r'^MOCHECK (\w+) ([01])\r?$',text,re.M)
    require(tuple(name for name,_ in checks)==LABELS,'missing observer contracts')
    require(all(ok=='1' for _,ok in checks),'observer changed requested yaw or shared state')
    require(re.findall(r'^MOCHECK end checks (\d+) failures (\d+)\r?$',text,re.M)==[(str(len(LABELS)),'0')])
    return len(checks)


def inspect_demo_alignment(text, exported, name):
    """Compare finalized QC poses with a new same-match native demo export.

    Parse only this observer's grammar. ARGLOG counters stay with brief_run.
    Dead actors have no ARGMOT row, so report matched exposure explicitly.
    """
    require('ARGMOT begin layout 2' in text, 'unsupported sampling phase')
    rows=[]
    pattern=re.compile(r"^ARGMOT (.+?) ms\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' ",re.M)
    for match in pattern.finditer(text):
        if match[1]==name:
            rows.append((float(match[2])/1000,[float(match[i]) for i in (3,4,5)]))
    require(rows and all(b[0]>a[0] for a,b in zip(rows,rows[1:])), 'invalid observer times')
    tracks=[t for t in exported['tracks'] if t.get('name')==name and t['kind']=='player']
    require(len(tracks)==1, 'missing or ambiguous demo track')
    track=tracks[0];require(len(track['t'])==len(track['pos']), 'invalid demo vectors')
    times=[r[0] for r in rows];errors=[]
    for t,pos in zip(track['t'],track['pos']):
        i=bisect.bisect_left(times,t)
        j=min((j for j in (i-1,i) if 0<=j<len(rows)),key=lambda j:abs(times[j]-t))
        if abs(times[j]-t)<.002:
            errors.append(math.dist(pos,rows[j][1]))
    require(len(errors)>=100, 'insufficient matched demo exposure')
    require(all(math.isfinite(e) and e<=.2 for e in errors), 'observer sampled an intermediate pose')
    return dict(name=name,demo_samples=len(track['t']),paired=len(errors),maximum_error=max(errors))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prefix',required=True)
    p.add_argument('--source',type=Path,default=ROOT/'src')
    p.add_argument('--map',choices=('dm4','dm2'),default='dm4')
    p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    p.add_argument('--contracts',action='store_true')
    p.add_argument('--disabled',action='store_true',help='same program with scratch1 diagnostics off')
    p.add_argument('--record-demo',action='store_true',help='verify finalized poses against a new same-match POV demo')
    args=p.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix) and 10<=args.seconds<=40)
    require(not(args.contracts and args.disabled),'contracts require diagnostics')
    require(not(args.record_demo and args.disabled),'demo alignment requires diagnostics')
    for path in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log'):
        require(not path.exists(),'harvest the pending human log before an engine launch: '+str(path))
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest pending human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.source,contracts=args.contracts)
    with private_game(ROOT,args.prefix,'motioncheck',autoexec=
            f'sv_protocol 15\nmax_edicts 600\nscratch1 {0 if args.disabled else 697}\n') as game:
        env=dict(ARGUS_SRC=str(out/'src'),ARGUS_PROGS=str(out/'lq1/progs.dat'),
            ARGUS_RUNS=str(out/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=55)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale lab')
                compiled=lab.call('compile_qc',install=False);write(out/'compile.json',compiled)
                require(compiled['ok'] and not compiled['installed_to'],compiled)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                if args.record_demo:
                    write(out/'start.json',lab.call('match_start',map=args.map,
                        duration_sec=args.seconds+10,skill=2,run_name=args.prefix,dedicated_slots=8))
                    record=lab_cli(lab.executable,'record-pov',args.prefix,0,args.seconds,
                        environment=env,timeout=args.seconds+10)
                    write(out/'record.json',dict(returncode=record.returncode,stdout=record.stdout,stderr=record.stderr))
                    require(record.returncode==0,record.stderr)
                    write(out/'stop.json',lab.call('match_stop',timeout_sec=5))
                else:
                    result=lab.call('experiment',map=args.map,duration_sec=args.seconds,skill=2,
                        compile=False,repeats=1,primary='freezes',run_name=args.prefix)
                    write(out/'experiment.json',result);require(result['ok'],result)
                raw,text=read_tape(out,args.prefix,args.map)
                brief=lab.call('brief_run',log=str(raw),map=args.map,detail='full');write(out/'brief.json',brief)
                identity=dict(map=args.map,ticrate=args.ticrate,contracts=args.contracts,
                    diagnostics=not args.disabled,source_sha256=source_identity(out/'src'),
                    binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix())
                write(out/'identity.json',identity)
                alignment=None
                if args.record_demo:
                    exported=lab_cli(lab.executable,'demo',args.prefix+':export',environment=env,timeout=10)
                    require(exported.returncode==0,exported.stderr)
                    write(out/'demo.json',json.loads(exported.stdout))
                    demo=out/'runs/demos'/args.prefix
                    identity.update(demo_sha256=digest(demo.with_suffix('.dem')),
                        tracks_sha256=digest(demo.with_suffix('.tracks.json')))
                    write(out/'identity.json',identity)
                    alignment=inspect_demo_alignment(text,json.loads(demo.with_suffix('.tracks.json').read_text(encoding='utf-8')),'Carmack')
                if args.contracts:inspect_contracts(text)
                motion=brief.get('movement')
                if args.disabled:require(motion is None,'disabled diagnostics emitted data')
                else:
                    require(motion and motion['eligible_for_reversal_claims'],motion)
                    require(len(motion['bots'])==3,'missing bot motion tracks')
                    low,high=(8,12) if args.ticrate==.1 else (60,90)
                    require(all(low<=b['measured_hz']<=high for b in motion['bots']),'wrong measured motion rate')
                row=dict(identity,movement=motion,totals=brief['totals'],flags=brief['flags'],demo_alignment=alignment)
                write(out/'receipt.json',row)
                summary=None if motion is None else [dict(name=b['name'],
                    hz=b['measured_hz'],rate=b['movement']['reversals_per_moving_minute'],
                    reversals=b['movement']['reversals'],attributed=b['marker_attributed'],
                    unattributed=b['unattributed'],causes=b['reversal_causes']) for b in motion['bots']]
                print(json.dumps(dict(map=args.map,movement=summary)),flush=True)
            finally:finish_lab(lab)


if __name__=='__main__':main()
