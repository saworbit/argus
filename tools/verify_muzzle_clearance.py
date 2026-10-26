"""Bounded native-engine verification. One smoke and three private fixtures."""
import hashlib,json,re,shutil
from pathlib import Path
from run_behaviour_equivalence import ROOT,Lab,identity
from run_health_fixture import body
from check_muzzle_fixture import check,audit
from health_inventory_parked import parked_source

OUT=ROOT/'backups/muzzle-clearance'
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source=(ROOT/'src/argus.qc').read_text();audit(source);parked_source()
    before=(OUT/'before-src/argus.qc').read_text()
    for name in ('Argus_Perceive','Argus_Hunch','Argus_DodgeScan','Argus_SelectWeapon'):
        assert body(source,name)[1]==body(before,name)[1]
    engine=ROOT/'engine/argus/progs.dat';original=OUT/'1.dat'
    assert engine.read_bytes()==original.read_bytes()
    results=[]
    try:
        for mode in ('production','candidate','legacy','uncapped'):
            folder=OUT/mode;assert not folder.exists()
            shutil.copytree(ROOT/'src',folder/'src');(folder/'lq1').mkdir()
            if mode!='production':
                p=folder/'src/argus.qc';changed=p.read_text()
                if mode=='legacy':
                    a='if (!self.ar_tactic && self.weapon != IT_ROCKET_LAUNCHER)'
                    assert changed.count(a)==1;changed=changed.replace(a,'if (!self.ar_tactic)')
                if mode=='uncapped':
                    a='if (targetdist < reach) reach = targetdist;'
                    assert changed.count(a)==1;changed=changed.replace(a,'reach = 240;')
                p.write_text(changed,newline='\r\n')
                shutil.copy2(ROOT/'tools/fixtures/muzzle_clearance.qc',folder/'src/muzzle_clearance.qc')
                p=folder/'src/progs.src';text=p.read_text();assert text.count('\nworld.qc\n')==1
                p.write_text(text.replace('\nworld.qc\n','\nmuzzle_clearance.qc\nworld.qc\n'),newline='\r\n')
                p=folder/'src/world.qc';text=p.read_text()
                assert text.count('Argus_CountSlots ();')==text.count('Argus_FrameAll ();')==1
                text=text.replace('Argus_CountSlots ();','Argus_CountSlots ();\n    dprint ("BHVRPL begin muzzle_fixture\\n");')
                text=text.replace('Argus_FrameAll ();','if (time > 1) MuzzleFixture ();\n    Argus_FrameAll ();')
                p.write_text(text,newline='\r\n')
            environment=dict(ARGUS_SRC=str(folder/'src'),ARGUS_PROGS=str(folder/'lq1/progs.dat'))
            with (folder/'lab.stderr').open('w') as err:
                lab=Lab(err,environment)
                try:
                    compiled=lab.call('compile_qc',install=False);save(folder/'compile.json',compiled)
                    assert compiled['ok'] and not compiled['installed_to'] and compiled['new_errors']==0
                    assert compiled['new_warnings']==0,compiled
                    binary=folder/'lq1/progs.dat';shutil.copy2(binary,engine)
                    name='muzzle1_'+mode
                    assert not (ROOT/f'runs/{name}.log').exists()
                    native=lab.call('experiment',map='dm4',duration_sec=10,skill=1,compile=False,
                        repeats=1,primary='stall_parity',run_name=name)
                    save(folder/'native.json',native);assert native['ok']
                    tape=ROOT/f'runs/{name}.log';text=tape.read_text(errors='replace')
                    assert not any(t in text for t in ('Host_Error','Program error','WRONG MAP'))
                    row=dict(mode=mode,name=name,compile=compiled,native=native,
                        identity=identity('dm4'),binary_sha256=sha(binary),raw_sha256=sha(tape))
                    if mode!='production':
                        row['failures']=check(text)
                        expected={'candidate':[],'legacy':['ordinary_wall','ordinary_overhang'],
                            'uncapped':['wall_behind_target']}[mode]
                        assert row['failures']==expected,row['failures']
                    results.append(row);save(OUT/'results.json',results)
                    print(json.dumps(dict(mode=mode,passed=True,expected_rejections=row.get('failures',[]))),flush=True)
                finally:lab.close()
    finally:shutil.copy2(original,engine)
    assert (ROOT/'game/argus/progs.dat').read_bytes()==(OUT/'0.dat').read_bytes()
    assert (ROOT/'lq1/progs.dat').read_bytes()==(OUT/'2.dat').read_bytes()
    save(OUT/'restored.json',{str(p.relative_to(ROOT)):sha(p) for p in
        (ROOT/'game/argus/progs.dat',engine,ROOT/'lq1/progs.dat')})

if __name__=='__main__':main()
