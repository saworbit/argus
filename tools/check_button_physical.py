"""Physical solid-button receipt oracle. Never reconstructs match metrics."""
import math
import re
from check_perception_fixture import function


def check(text,case,expected):
    assert 'BHVRPL begin button_physical' in text
    assert not any(s in text for s in ('Host_Error','Program error','runaway loop'))
    rows=[s for s in text.splitlines() if s.startswith('BPFIX ')]
    assert len(rows)>=5 and rows[0]==f"BPFIX begin case {case} start '-45.0 288.0 320.0'"
    samples=[]
    for line in rows[1:-2]:
        m=re.fullmatch(r"BPFIX sample t\s+([\d.]+) pos '([^']+)' state ([0-3]) touches (\d+) support ([01]) grounded ([01]) hp 100 frames (\d+)",line)
        assert m,'invalid physical sample'
        t=float(m[1]);pos=tuple(map(float,m[2].split()));frames=int(m[7])
        assert len(pos)==3 and all(math.isfinite(x) for x in (*pos,t))
        assert abs(pos[1]-288)<4
        if samples:
            last=samples[-1]
            assert 0<=t-last['t']<=.300001 and frames>last['frames'],'missing/reordered samples'
            assert math.dist(pos,last['pos'])<160,'discontinuous movement'
        samples.append(dict(t=t,pos=pos,frames=frames,touches=int(m[4]),support=int(m[5])))
    assert samples[0]['t']==0 and samples[0]['pos']==(-45,288,320)
    assert samples[-1]['pos'][0]<=-160 and samples[-1]['t']<=6.2,'no complete crossing'
    end=re.fullmatch(r'BPFIX end touched ([01]) activated ([01]) owner ([01]) ctx 1 support ([01])',rows[-2])
    assert end and rows[-1]=='BPFIX cleanup owned_engine_pending_stop','missing cleanup/context guarantee'
    assert [bool(int(v)) for v in end.groups()[:3]]==[expected]*3,'unexpected button activation'
    assert bool(samples[-1]['touches'])==expected,'contradictory touch count'
    if case==1:assert end[4]=='1','motor never supported by the real button'
    return dict(activated=expected,elapsed=samples[-1]['t'],frames=samples[-1]['frames'],
                touch_calls=samples[-1]['touches'],context_preserved=True,engine_support=bool(int(end[4])))


def audit(source,fixture):
    helper=function(source,'Argus_SupportButton')
    assert 'button = self.groundentity;' in helper and 'FL_ONGROUND' in helper
    assert 'button.touch != button_touch' in helper and 'button.state != STATE_BOTTOM' in helper
    assert 'button.health > 0' in helper and '!self.ar_isbot' in helper
    for restored in ('self = bot;','other = savedother;','activator = savedactivator;'):
        assert restored in helper,'missing callback context restoration'
    assert not re.search(r'\b(?:spawn|walkmove|traceline|setorigin|random)\s*\(',helper)
    assert not re.search(r'\b(?:self|bot)\.(?:origin|velocity|flags|ar_\w+)\s*=',helper),'callback changes movement'
    assert 'Argus_SupportButton ();' in function(source,'Argus_Physics')
    observer=fixture.split('    bp_frames = bp_frames + 1;',1)[1].split('// Passive callback-context guard',1)[0]
    assert not re.search(r'\b(?:self|bp_actor)\.\w+\s*=(?!=)',observer),'observer drives the actor'
    assert not re.search(r'\b(?:walkmove|setorigin|button_touch|Argus_Physics)\s*\(',observer)
    return True
