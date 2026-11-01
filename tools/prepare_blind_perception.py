"""Four ordinary recordings, fixed clip windows, anonymous local review."""

from run_behaviour_equivalence import lab_executable, lab_cli
import hashlib,json,os,secrets,shutil,subprocess,time
from pathlib import Path
from run_behaviour_equivalence import ROOT,Lab,identity

PRIVATE=ROOT/'backups/blind-perception-v1'
PUBLIC=ROOT/'reviews/blind-perception-v1'
BASE=ROOT/'backups/perception-step1b'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):p.write_text(json.dumps(data,indent=2)+'\n')
def native(args,timeout=65):
    result=lab_cli(lab_executable(), *args, cwd=ROOT, environment=dict(os.environ,ARGUS_ROOT=str(ROOT)), timeout=timeout)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)

def main():
    assert not PRIVATE.exists() and not PUBLIC.exists(),'retain previous review'
    PRIVATE.mkdir(parents=True);PUBLIC.mkdir(parents=True)
    binaries={'step1a':BASE/'control-progs.dat','shipped':BASE/'shipped-engine.dat'}
    engine=ROOT/'engine/argus/progs.dat'
    assert sha(engine)==sha(binaries['shipped'])
    expected={'step1a':'56a4ee159959532c36108d53c49ecf579b1e72164e804ff7561ef06b7dae454a',
        'shipped':'9aa98b29bbe925988d4a70e3b55840f8c2cca12f0e3fda0e4a07101b50c7dcc4'}
    assert all(sha(p)==expected[a] for a,p in binaries.items())
    parked=ROOT/'tools/fixtures/health-inventory-step1b.json'
    assert hashlib.sha256((ROOT/'src/argus.qc').read_text().encode()).hexdigest()==json.loads(parked.read_text())['parked_text_sha256']
    # Before any launch, preserve a human session if one is waiting.
    waiting=[p for p in (ROOT/'qconsole.log',ROOT/'engine/qconsole.log') if p.exists()]
    if waiting:
        harvest=subprocess.run(['python','tools/harvest_session.py','--tag','before_blind_v1'],cwd=ROOT,
            capture_output=True,text=True,encoding='utf-8')
        (PRIVATE/'harvest.txt').write_text(harvest.stdout+'\n'+harvest.stderr)
        assert harvest.returncode==0
    key={};schedule=[]
    for pair,map_name in enumerate(('dm2','dm4'),1):
        arms=['step1a','shipped']
        if secrets.randbelow(2):arms.reverse()
        for label,arm in zip(('A','B'),arms):
            key[f'{pair}{label}']=arm
            schedule.append(dict(pair=pair,map=map_name,label=label,arm=arm))
    secrets.SystemRandom().shuffle(schedule)
    write(PRIVATE/'key.json',key)
    write(PRIVATE/'plan.json',dict(matches=4,skill=1,roster_slot=1,record_seconds=35,
        source_windows=[[5,17],[17,29]],selection='fixed before viewing; no highlight selection or outcome-driven replacement',
        viewer_seconds=96,format='640x480 silent10fps, normal speed, same first-person camera',
        binary_sha256=expected,source_before=identity('dm4'),step1b='parked; source unchanged',
        limitations='Different matches and random encounters. Small subjective review, not skill or equivalence proof. Death can switch camera target.'))
    rows=[]
    with (PRIVATE/'lab.stderr').open('w') as err:
        lab=Lab(err);active=False
        try:
            for row in schedule:
                stem=f"blindv1_{row['pair']}{row['label'].lower()}"
                assert not (ROOT/f'runs/{stem}.log').exists()
                shutil.copy2(binaries[row['arm']],engine)
                row.update(binary_sha256=sha(engine),identity=identity(row['map']),stem=stem)
                row['start']=lab.call('match_start',map=row['map'],duration_sec=80,skill=1,run_name=stem);active=True
                deadline=time.monotonic()+10
                while True:
                    status=lab.call('match_status')
                    if 'ARGLOG ' in json.dumps(status):break
                    assert status.get('running') and time.monotonic()<deadline
                    time.sleep(.05)
                lab.call('match_command',command='developer 1; scratch1 0; scratch4 0')
                row['recording']=native(['record-pov',stem,'1','35'])
                row['stop']=lab.call('match_stop');active=False
                row['brief']=lab.call('brief_run',log=stem,map=row['map'])
                assert row['brief']['map']==row['map'] and row['brief']['totals']['tick_class']=='listen'
                assert not any('WRONG MAP' in f or 'CONTROLLED FIXTURE' in f for f in row['brief']['flags'])
                row['demo_sha256']=sha(Path(row['recording']['demo_path']))
                rows.append(row);write(PRIVATE/'recordings.json',rows)
                print(json.dumps(dict(recorded=f"pair{row['pair']}-{row['label']}",completed=len(rows))),flush=True)
        finally:
            if active:lab.call('match_stop')
            lab.close();shutil.copy2(binaries['shipped'],engine)
    # The native renderer uses an isolated local playback directory, not an install.
    for row in rows:
        row['clips']=[]
        for part,start in enumerate((5,17),1):
            result=native(['capture-video',row['stem'],str(start),'12','1'],timeout=90)
            assert result['duration_seconds']==12 and result['output_fps']==10
            assert len(result['decoded_frame_md5'])==120
            name=f"pair{row['pair']}-{row['label']}-{part}.webm"
            target=PUBLIC/name;shutil.copy2(result['video_path'],target)
            assert sha(target)==sha(Path(result['video_path']))
            row['clips'].append(dict(file=name,sha256=sha(target),native=result))
            write(PRIVATE/'recordings.json',rows)
        print(json.dumps(dict(rendered=f"pair{row['pair']}-{row['label']}")),flush=True)
    write(PRIVATE/'restoration.json',dict(source_after=identity('dm4'),
        binaries={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'game/argus/progs.dat',engine,ROOT/'lq1/progs.dat')}))
    assert all(sha(p)==expected['shipped'] for p in (ROOT/'game/argus/progs.dat',engine,ROOT/'lq1/progs.dat'))
    shutil.copy2(ROOT/'tools/blind_perception_review.html',PUBLIC/'index.html')
    print('Blind review ready',flush=True)

if __name__=='__main__':main()
