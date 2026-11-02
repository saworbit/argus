"""Verify each retained/dry clause through the actual native mover observers."""
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
from verify_mover_transfer import audit_fixture as audit_transfer
from verify_mover_forecast import audit_fixture as audit_forecast

BASE=('owned','missing_task','missing_goal','neither')
LIQUID=('water_feet','lava_feet','slime_feet','wet_body')
CASES=tuple((family,label) for family in ('transfer','forecast')
    for label in (*BASE,*(('missing_node',) if family=='forecast' else ()),*LIQUID))


def stage(root,out,variant='current'):
    require(variant in ('current','legacy_retention','legacy_dry'))
    fixtures={}
    for family,prefix,filename,audit in (
            ('transfer','mv','mover_transfer.qc',audit_transfer),
            ('forecast','mc','mover_forecast.qc',audit_forecast)):
        text=(root/'tools/fixtures'/filename).read_text(encoding='utf-8');audit(text)
        field='retained' if variant=='legacy_retention' else 'dry'
        if variant!='current':
            pattern=r'(?m)^    '+field+r' = \((.*?);'
            matches=list(re.finditer(pattern,text,re.S));require(len(matches)==1,'predicate changed')
            m=matches[0];require(m[1].endswith(')'))
            text=text[:m.start()]+'    '+field+' = '+m[1][:-1]+';'+text[m.end():]
        anchor=('    if (!mv_landed && mv_boarded && retained && dry && mv_bot.health > 0'
            if family=='transfer' else '    if ((mc_bot.flags & FL_ONGROUND) && mc_bot.groundentity == world)')
        require(text.count(anchor)==1,'observer changed')
        call=f'    MoverPredicateWitness ({int(family=="forecast")}, retained, dry, {prefix}_lost);\n'
        text=text.replace(anchor,call+anchor)
        if family=='transfer':text='void(float family, float retained, float dry, float lost) MoverPredicateWitness;\n'+text
        fixtures[filename.replace('.qc','_fixture.qc')]=text
    fixtures['mover_predicates_fixture.qc']=(root/'tools/fixtures/mover_predicates.qc').read_text(encoding='utf-8')
    return stage_fixture(root,out,fixtures=fixtures,
        frame_wrap='if (time < 2) Argus_FrameAll ();\n    MoverPredicateFixture ();')


def inspect_fixture(text,ticrate):
    require(text.count('BHVRPL begin mover_predicates')==1,'missing quarantine')
    ms=frame_ms(text,'MPP',ticrate)
    require(len(re.findall(r'^MPP begin dt_ms\s+[\d.]+ layout 1\r?$',text,re.M))==1,'wrong predicate layout')
    rows=re.findall(r'^MVPRED (transfer|forecast) (\w+) retained ([01]) dry ([01]) lost ([01])\r?$',text,re.M)
    require(tuple(r[:2] for r in rows)==CASES,'missing/repeated observer cases')
    require(len(re.findall(r'^MVPRED ',text,re.M))==len(CASES),'extra observer records')
    latches=re.findall(r'^MPLATCH (\w+) dry ([01]) lost ([01])\r?$',text,re.M)
    forecast=[r for r in rows if r[0]=='forecast']
    require(latches==[(r[1],r[3],r[4]) for r in forecast],'computed flags differ from actual latches')
    require(len(re.findall(r'^MPLATCH ',text,re.M))==len(forecast),'extra latch records')
    require(len(re.findall(r'^MPP ',text,re.M))==2,'extra predicate records')
    failures=[]
    for family,label,retained,dry,lost in rows:
        owned=label not in ('missing_task','missing_goal','neither','missing_node')
        safe=label not in LIQUID
        if (int(retained),int(dry),int(lost))!=(int(owned),int(safe),int(not owned)):
            failures.append(family+':'+label)
    require(re.findall(r'^MPP end rows (\d+) cleanup ([01])\r?$',text,re.M)==[(str(len(CASES)),'1')],'wrong totals or dirty cleanup')
    return dict(frame_ms=ms,rows=rows,failures=failures)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prefix',required=True)
    p.add_argument('--variant',choices=('current','legacy_retention','legacy_dry'),default='current')
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    args=p.parse_args();require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix))
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.variant)
    with private_game(ROOT,args.prefix,'moverpredicate',autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
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
                row=dict(variant=args.variant,ticrate=args.ticrate,source_sha256=source_identity(out/'src'),binary_sha256=digest(game/'progs.dat'),raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix(),**inspect_fixture(text,args.ticrate))
                write(out/'receipt.json',row);print(json.dumps(row),flush=True)
                expected=[]
                if args.variant=='legacy_retention':expected=['transfer:missing_task','forecast:missing_task','forecast:missing_node']
                if args.variant=='legacy_dry':expected=[f+':'+n for f in ('transfer','forecast') for n in LIQUID[:3]]
                require(row['failures']==expected,'wrong predicate outcome')
            finally:finish_lab(lab)


if __name__=='__main__':main()
