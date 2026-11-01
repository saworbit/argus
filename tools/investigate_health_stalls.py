"""Fixed, small dm4 component isolation through the native lab. No deployment."""
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

from run_behaviour_equivalence import ROOT, Lab, identity
from run_health_fixture import body
from argus_source import source_identity as source_digest

OUT=ROOT/'backups/perception-step1b-isolation'
PREV=ROOT/'backups/perception-step1b'
ARMS={'targeting':'Argus_Perceive','retreat':'Argus_Combat','hunch':'Argus_Hunch'}
ORDERS=[['control','targeting','retreat','hunch','full'],
        ['full','hunch','retreat','targeting','control'],
        ['retreat','control','hunch','full','targeting']]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data):(OUT/name).write_text(json.dumps(data,indent=2)+'\n')

def main():
    assert not OUT.exists(), 'retain previous investigation'
    OUT.mkdir()
    frozen=source_digest(ROOT/'src')
    assert frozen==json.loads((PREV/'source-audit-v2.json').read_text())['source_sha256']
    old=(PREV/'control-src/argus.qc').read_text()
    current=(ROOT/'src/argus.qc').read_text()
    save('plan.json',dict(scope='dm4 bounded triage, not equivalence; no deployment or projectile edits',
        cap='15 ordinary30s matches plus3 private10s compile smokes; no extensions',orders=ORDERS,
        source_sha256=frozen,old_source_sha256=source_digest(PREV/'control-src'),
        arm_definition='Only one new production function active per component arm; all other production functions unchanged. Control/full use saved binaries.',
        decision='Provisional component signal requires median stalls >= control median+3 and worse than adjacent same-round control in >=2/3 rounds. Require full candidate to reproduce that signal. Otherwise park full step1b as unresolved; do not claim a culprit. No outcome-driven extra matches.'))
    bins={'control':PREV/'control-progs.dat','full':PREV/'candidate-final-progs.dat'}
    engine=ROOT/'engine/argus/progs.dat'; shipped=PREV/'shipped-engine.dat'
    assert sha(engine)==sha(shipped)
    active=False
    try:
        for arm,fn in ARMS.items():
            folder=OUT/arm
            shutil.copytree(ROOT/'src',folder/'src');(folder/'lq1').mkdir()
            changed=current
            for other in ARMS.values():
                if other!=fn:
                    pat,definition=body(old,other)
                    changed,n=re.subn(pat,lambda _:definition,changed,flags=re.M|re.S);assert n==1
            (folder/'src/argus.qc').write_text(changed,newline='\r\n')
            # Exact-function audit: the tested component is current, other two are old.
            for name in ARMS.values():
                assert body(changed,name)[1]==body(current if name==fn else old,name)[1]
            for path in (ROOT/'src').rglob('*'):
                if path.is_file() and path.relative_to(ROOT/'src')!=Path('argus.qc'):
                    assert path.read_bytes()==(folder/'src'/path.relative_to(ROOT/'src')).read_bytes()
            environment=dict(ARGUS_SRC=str(folder/'src'),ARGUS_PROGS=str(folder/'lq1/progs.dat'))
            with (folder/'lab.stderr').open('w') as err:
                lab=Lab(err,environment)
                try:
                    result=lab.call('compile_qc',install=False);save(arm+'/compile.json',result)
                    assert result['ok'] and not result['installed_to']
                    bins[arm]=folder/'lq1/progs.dat';shutil.copy2(bins[arm],engine)
                    smoke=lab.call('experiment',map='dm4',duration_sec=10,skill=1,compile=False,
                        repeats=1,primary='stall_parity',run_name=f'hi2_{arm}_smoke')
                    save(arm+'/smoke.json',smoke)
                finally:lab.close()
            print(json.dumps(dict(compiled=arm)),flush=True)
        save('pins.json',dict(binary_sha256={a:sha(p) for a,p in bins.items()},
            component_source_sha256={a:source_digest(OUT/a/'src') for a in ARMS},
            original_identity=identity('dm4')))
        rows=[]
        with (OUT/'matches.stderr').open('w') as err:
            lab=Lab(err)
            try:
                for repeat,order in enumerate(ORDERS,1):
                    for arm in order:
                        name=f'hi2_dm4_{arm}{repeat}'
                        assert not (ROOT/f'runs/{name}.log').exists()
                        assert source_digest(ROOT/'src')==frozen
                        shutil.copy2(bins[arm],engine);tree=identity('dm4')
                        start=lab.call('match_start',map='dm4',duration_sec=60,skill=1,run_name=name);active=True
                        deadline=time.monotonic()+10
                        while True:
                            status=lab.call('match_status')
                            if 'ARGLOG ' in json.dumps(status):break
                            assert status.get('running') and time.monotonic()<deadline
                            time.sleep(.05)
                        lab.call('match_command',command='scratch1 591; scratch4 0')
                        time.sleep(30)
                        stop=lab.call('match_stop');active=False
                        brief=lab.call('brief_run',log=name,map='dm4')
                        path=ROOT/f'runs/{name}.log';text=path.read_text(errors='replace')
                        row=dict(name=name,arm=arm,repeat=repeat,identity=tree,binary_sha256=sha(bins[arm]),
                            start=start,stop=stop,brief=brief,raw_sha256=sha(path))
                        save(name+'.attempt.json',row)
                        assert brief['map']=='dm4' and brief['totals']['tick_class']=='listen'
                        assert 28<=brief['totals']['duration_sec']<=34
                        assert not any('WRONG MAP' in f or 'CONTROLLED FIXTURE' in f for f in brief['flags'])
                        assert not any(t in text for t in ('Host_Error','Program error','BHVFIX ','HIFIX ','PERFIX ','BHVDBG '))
                        assert identity('dm4')==tree
                        rows.append(row);save('results.json',rows)
                        print(json.dumps(dict(completed=len(rows),arm=arm,stalls=brief['totals']['stalls'])),flush=True)
            finally:
                if active:lab.call('match_stop')
                lab.close()
    finally:
        shutil.copy2(shipped,engine)

if __name__=='__main__':main()
