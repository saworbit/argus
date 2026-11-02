"""Exercise every actual-trigger observer predicate with private state negatives."""
import argparse
import json
from pathlib import Path
import re
import shutil
from argus_fixture_harness import new_output,stage_fixture,private_game,read_tape,frame_ms
from argus_source import source_identity
from argus_validation import require
from check_muzzle_combat import check
from run_behaviour_equivalence import Lab,lab_executable,finish_lab
from run_map_intelligence import ROOT,write,digest

CASES=('owned','gates','seen','enemy','cache','weapon','tactic','motor_set','motor_equal','velocity')
PREDICATES=('owned != 0','mc_gates == gates + 1','self.ar_seen == time',
    'self.ar_enemy == foe','self.ar_obsenemy == foe','self.weapon == IT_ROCKET_LAUNCHER',
    '!self.ar_tactic','self.ar_moveyaw != 10000','self.ar_moveyaw == mc_motor',
    "self.velocity == '23 7 0'")
FAULTS=('owned = 0;','gates = mc_gates;','self.ar_seen = time - 1;',
    'self.ar_enemy = world;','self.ar_obsenemy = world;','self.weapon = IT_SHOTGUN;',
    'self.ar_tactic = 1;','self.ar_moveyaw = 10000; mc_motor = 10000;',
    'mc_motor = self.ar_moveyaw + 1;',"self.velocity = '0 0 0';")


def replace_once(text,old,new):
    require(text.count(old)==1,'muzzle fixture anchor changed: '+old)
    return text.replace(old,new)


def stage(root,out,variant):
    require(variant in ('current','legacy'))
    text=(root/'tools/fixtures/muzzle_combat.qc').read_text(encoding='utf-8')
    pattern=r'(?m)^    ok = (.*?);$'
    rows=re.findall(pattern,text)
    require(len(rows)==5,'expected five observer assignments')
    if variant=='legacy':
        text=re.sub(pattern,lambda m:'    ok = '+(m[1][1:-1] if m[1].startswith('(') and m[1].endswith(')') else m[1])+';',text)
    else:
        require(all(s.startswith('(') and s.endswith(')') for s in rows),'unparenthesized observer')
    # The original time-one fixture can run in the zero-frametime map spawn.
    text=replace_once(text,'if (mc_done || time < 1) return;','if (mc_done || time < 2) return;')
    injected='    owned = Argus_Combat ();\n    if (mp_active)\n    {\n'
    for index,fault in enumerate(FAULTS,1):
        injected+=f'        if (mp_active == {index}) {{ {fault} }}\n'
    injected+='        dprint ("MPSTATE "); dprint (label);\n'
    for predicate in PREDICATES:
        injected+=f'        dprint (" "); dprint (ftos ({predicate}));\n'
    injected+='        dprint ("\\n");\n    }'
    text=replace_once(text,'    owned = Argus_Combat ();',injected)
    text=replace_once(text,'    dprint ("MCFIX outcome ");',
        '    if (mp_active) dprint ("MPOUTCOME "); else dprint ("MCFIX outcome ");')
    text=replace_once(text,'    MuzzleCombatCheck (label, ok);',
        '    if (!mp_active) MuzzleCombatCheck (label, ok);\n'
        '    else { dprint ("MPCHECK "); dprint (label); dprint (" "); dprint (ftos (ok)); dprint ("\\n"); }')
    text=replace_once(text,'dprint (ftos (mc_ok)); dprint ("\\n");',
        'dprint (ftos (mc_ok)); dprint ("\\n");\n    if (geometry) MuzzlePredicates ();')
    extra='\nvoid() MuzzlePredicates =\n{\n    local vector aim;\n'
    extra+='    dprint ("MPP begin dt_ms "); dprint (ftos (frametime * 1000)); dprint (" layout 1\\n");\n'
    extra+='    aim = vectoangles (mc_target - mc_origin);\n'
    for index,label in enumerate(CASES,1):
        extra+=f'    mp_active = {index}; MuzzleCombatCase ("{label}", mc_origin, mc_target, aim_y, 0);\n'
    extra+='    mp_active = 0;\n    dprint ("MPP end rows 10\\n");\n};\n'
    text='float mp_active;\nvoid() MuzzlePredicates;\n'+text+extra
    source=(root/'src/argus.qc').read_text(encoding='utf-8')
    anchor='        if (!Argus_MuzzleClear (aimpt))'
    source=replace_once(source,anchor,
        '        if (self == mc_actor) { mc_gates = mc_gates + 1; mc_motor = self.ar_moveyaw; }\n'+anchor)
    return stage_fixture(root,out,fixtures={'muzzle_combat.qc':text},
        edits={'argus.qc':lambda _: 'entity mc_actor; float mc_gates, mc_motor;\n'+source},
        frame_wrap='if (!mc_done && time >= 2) dprint ("BHVRPL begin muzzle_combat\\n");\n    MuzzleCombatFixture ();')


def inspect_fixture(text,ticrate):
    require(text.count('BHVRPL begin muzzle_combat')==1,'missing quarantine')
    baseline=check(text);require(not baseline['failures'],'baseline combat failed')
    ms=frame_ms(text,'MPP',ticrate)
    require(re.findall(r'^MPP begin dt_ms\s+[\d.]+ layout (\d+)\r?$',text,re.M)==['1'],'wrong layout')
    states=re.findall(r'^MPSTATE (\w+) ((?:[01] ){9}[01])\r?$',text,re.M)
    checks=re.findall(r'^MPCHECK (\w+) ([01])\r?$',text,re.M)
    outcomes=re.findall(r'^MPOUTCOME (\w+) gates (\d+) ammo (\d+) rockets (\d+) motor (-?[\d.]+)\r?$',text,re.M)
    require(tuple(s[0] for s in states)==tuple(s[0] for s in checks)==tuple(s[0] for s in outcomes)==CASES,'missing/reordered cases')
    require(sum(s.startswith(('MPSTATE ','MPCHECK ','MPOUTCOME ','MPP ')) for s in text.splitlines())==32,'extra predicate records')
    for index,(label,bits) in enumerate(states):
        require(bits.split()==['0' if j==index else '1' for j in range(10)],'negative premise not isolated: '+label)
    for label,gates,ammo,rockets,_ in outcomes:
        require((gates,ammo,rockets)==('0' if label=='gates' else '1','1','1'),'actual trigger outcome changed: '+label)
    require(re.findall(r'^MPP end rows (\d+)\r?$',text,re.M)==['10'],'incomplete controls')
    return dict(frame_ms=ms,baseline=baseline,states=states,checks=checks,
        failures=[label for label,value in checks if value!='0'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prefix',required=True)
    p.add_argument('--variant',choices=('current','legacy'),default='current')
    p.add_argument('--ticrate',type=float,choices=(.0139,.1),default=.0139)
    args=p.parse_args();require(re.fullmatch(r'[a-z0-9_]{1,48}',args.prefix))
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')),'harvest human logs first')
    require(not list((ROOT/'engine/argus').glob('*.dem')),'harvest human demos first')
    out=new_output(args.output,root=ROOT,create=False);stage(ROOT,out,args.variant)
    with private_game(ROOT,args.prefix,'muzzlepredicate',autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
        env=dict(ARGUS_SRC=str(out/'src'),ARGUS_PROGS=str(out/'lq1/progs.dat'),ARGUS_RUNS=str(out/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE=str(args.ticrate))
        with (out/'lab.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=30)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'],'stale lab')
                c=lab.call('compile_qc',install=False);write(out/'compile.json',c);require(c['ok'] and not c['installed_to'],c)
                shutil.copy2(out/'lq1/progs.dat',game/'progs.dat')
                r=lab.call('experiment',map='dm4',duration_sec=10,skill=2,compile=False,repeats=1,primary='engagements',run_name=args.prefix)
                write(out/'experiment.json',r);require(r['ok'],r)
                raw,text=read_tape(out,args.prefix,'dm4')
                row=dict(variant=args.variant,ticrate=args.ticrate,source_sha256=source_identity(out/'src'),
                    fixture_sha256=digest(out/'src/muzzle_combat.qc'),binary_sha256=digest(game/'progs.dat'),
                    raw_sha256=digest(raw),raw=raw.relative_to(ROOT).as_posix(),**inspect_fixture(text,args.ticrate))
                write(out/'receipt.json',row);print(json.dumps(row),flush=True)
                require(row['failures']==(list(CASES[1:]) if args.variant=='legacy' else []),'wrong observer result')
            finally:finish_lab(lab)


if __name__=='__main__':main()
