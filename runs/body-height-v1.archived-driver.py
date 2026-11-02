import json,os,shutil,subprocess,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from argus_fixture_harness import new_output,stage_fixture,private_game
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import Lab,finish_lab,lab_executable,lab_cli
from run_map_intelligence import write,digest
OUT=ROOT/'backups/body_height_cohort_20261102'
os.environ['ARGUS_LAB']=str(ROOT/'tools/argus_mcp/target/debug/argus-mcp.exe')
mode=sys.argv[1]
MAPS=('dm3','dm4','e1m6','dm6','lqdm2','e1m1','e1m2','e1m5','e1m7')
REPEATS={m:(3 if m in ('dm3','dm4','e1m6') else 2) for m in MAPS}
COUNT=2*sum(REPEATS.values())
if mode=='compile':
    new_output(OUT,root=ROOT);(OUT/'runs').mkdir()
    protocol=dict(maps=list(MAPS),repeats=REPEATS,seconds=30,skill=2,ticrate=.0139,primary=['stall_parity','engagements'],
        stopping_rule='Exactly three per arm on dm3, dm4 and e1m6, two per arm on each other original broader-study map. Alternate control/candidate. Require both unchanged native stall-parity and engagement cards, including severe-freeze vetoes. No outcome-selected extra repeats.',
        tree_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        tree_diff=subprocess.check_output(['git','diff','HEAD','--binary'],text=True),cli_sha256=digest(lab_executable()),arms={},
        schedule=[dict(map=m,arm=a,repeat=i) for m in MAPS for i in range(1,REPEATS[m]+1) for a in ('control','candidate')])
    for arm in ('control','candidate'):
        folder=OUT/arm;stage_fixture(ROOT,folder)
        if arm=='control':(folder/'src/argus.qc').write_bytes(subprocess.check_output(['git','show','HEAD:src/argus.qc']))
        env=dict(ARGUS_SRC=str(folder/'src'),ARGUS_PROGS=str(folder/'lq1/progs.dat'),ARGUS_RUNS=str(OUT/'runs'))
        with (folder/'compile.stderr').open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=40)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'])
                compiled=lab.call('compile_qc',install=False);write(folder/'compile.json',compiled)
                require(compiled['ok'] and not compiled['installed_to'])
                protocol['arms'][arm]=dict(source_sha256=source_identity(folder/'src'),binary_sha256=digest(folder/'lq1/progs.dat'))
            finally:finish_lab(lab,active=False)
    write(OUT/'protocol.json',protocol);write(OUT/'state.json',dict(next=0));print(str(COUNT)+' ordinary runs registered; both arms privately frozen and compiled.')
elif mode=='compare':
    protocol=json.loads((OUT/'protocol.json').read_text());require(json.loads((OUT/'state.json').read_text())['next']==COUNT)
    for m in ([sys.argv[2]] if len(sys.argv)>2 else protocol['maps']):
        require(m in protocol['maps'])
        controls=','.join(f'height_control_{m}_{i}_20261102' for i in range(1,REPEATS[m]+1))
        candidates=','.join(f'height_candidate_{m}_{i}_20261102' for i in range(1,REPEATS[m]+1))
        for primary in protocol['primary']:
            result=lab_cli(lab_executable(),'compare',candidates,controls,'--primary',primary,environment=dict(ARGUS_RUNS=str(OUT/'runs')),timeout=20)
            require(result.returncode==0,result.stderr);(OUT/(m+'.'+primary+'.gate.txt')).write_text(result.stdout,encoding='utf-8',newline='\n')
            print(json.dumps(dict(map=m,primary=primary,gate=result.stdout),ensure_ascii=True))
else:
    require(mode=='next');protocol=json.loads((OUT/'protocol.json').read_text());state=json.loads((OUT/'state.json').read_text())
    require(state['next']<COUNT);step=protocol['schedule'][state['next']];arm=step['arm'];m=step['map'];repeat=step['repeat']
    folder=OUT/arm;name=f'height_{arm}_{m}_{repeat}_20261102'
    require(source_identity(folder/'src')==protocol['arms'][arm]['source_sha256']);require(digest(folder/'lq1/progs.dat')==protocol['arms'][arm]['binary_sha256'])
    require(not any(p.exists() for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log')))
    require(not list((ROOT/'engine/argus').glob('*.dem')))
    with private_game(ROOT,name,'heightordinary') as game:
        shutil.copy2(folder/'lq1/progs.dat',game/'progs.dat')
        env=dict(ARGUS_SRC=str(folder/'src'),ARGUS_PROGS=str(folder/'lq1/progs.dat'),ARGUS_RUNS=str(OUT/'runs'),ARGUS_GAME=game.name,ARGUS_TICRATE='.0139')
        with (OUT/(name+'.stderr')).open('w',encoding='utf-8') as err:
            lab=Lab(err,env,exe=lab_executable(),timeout=45)
            try:
                require(lab.call('see',what='project')['lab_identity']['authoritative'])
                result=lab.call('experiment',map=m,duration_sec=30,skill=2,compile=False,repeats=1,primary='stall_parity',run_name=name)
                write(OUT/(name+'.experiment.json'),result);require(result['ok'],result)
                brief=lab.call('brief_run',log=name,map=m,detail='full');require(brief['map']==m and brief['totals']['tick_class']=='listen')
                text=(OUT/'runs'/(name+'.log')).read_text(encoding='utf-8');initial={}
                for match in re.finditer(r'^ARGUS difficulty (.+?) t\s+[\d.]+ base\s+([\d.]+) cognition\s+([\d.]+)',text,re.M):
                    initial.setdefault(match[1],(float(match[2]),float(match[3])))
                require(len(initial)==3 and all(v==(2,2) for v in initial.values()),'invalid initial difficulty')
                write(OUT/(name+'.result.json'),dict(**step,name=name,brief=brief,**protocol['arms'][arm],raw_sha256=digest(OUT/'runs'/(name+'.log'))))
                state['next']+=1;write(OUT/'state.json',state)
                print(json.dumps(dict(**step,totals={k:brief['totals'][k] for k in ('stalls','goals','engages','lava_deaths','freezes','freeze_underfire','rescues') if k in brief['totals']})),flush=True)
            finally:finish_lab(lab)
