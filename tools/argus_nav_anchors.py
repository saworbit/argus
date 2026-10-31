"""Read bounded, engine-proven seat nominations without trusting new links."""
import hashlib
import json
import math
from pathlib import Path


def load_anchors(path, map_name, root=None):
    """Legacy pair lists are unchanged; anchors need two cadence proofs."""
    path=Path(path)
    if not path.exists(): return []
    doc=json.loads(path.read_text())
    if isinstance(doc,list): return []
    if not isinstance(doc,dict): raise ValueError('proven sidecar must be a pair list or object')
    anchors=doc.get('anchors',[])
    if not anchors: return []
    if doc.get('schema')!='argus-proven-anchors-v1' or doc.get('map')!=map_name:
        raise ValueError('wrong proven-anchor schema/map')
    if not isinstance(anchors,list) or len(anchors)>8:
        raise ValueError('at most eight proven anchors are supported')
    if any(not isinstance(p,list) or len(p)!=3
           or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in p)
           for p in anchors): raise ValueError('anchor must have three finite coordinates')
    if len({tuple(p) for p in anchors})!=len(anchors): raise ValueError('duplicate anchors')
    links=doc.get('links',[])
    if (not isinstance(links,list) or len(links)>8
        or any(not isinstance(pair,list) or len(pair)!=2
               or pair[0] not in anchors or pair[1] not in anchors
               or pair[0]==pair[1] for pair in links)):
        raise ValueError('proven links must join distinct witnessed anchors')
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    from verify_water_route import inspect_fixture, require_outcome
    rates=set(); paths=set()
    for evidence in doc.get('anchor_evidence',[]):
        relative=Path(evidence['raw'])
        if relative.is_absolute() or not relative.parts or relative.parts[0]!='runs' or relative.suffix!='.log':
            raise ValueError('anchor evidence must be a relative runs/*.log path')
        raw=(root/relative).resolve()
        if not raw.is_relative_to(root/'runs') or raw in paths: raise ValueError('unsafe/duplicate evidence path')
        paths.add(raw)
        data=raw.read_bytes()
        if hashlib.sha256(data).hexdigest()!=evidence['sha256']:
            raise ValueError('anchor evidence hash mismatch')
        rate=evidence['ticrate']
        if rate not in (.0139,.1): raise ValueError('unknown anchor evidence cadence')
        text=data.decode('utf-8',errors='replace').replace('\r\n','\n')
        row=inspect_fixture(text,map_name,rate,case=6)
        require_outcome(row,False)
        if not row['grounded'] or row['feet_contents']==-3: raise ValueError('anchor route did not land dry')
        if any(s.startswith('ARGUS ') and ' unstick ' in s for s in text.splitlines()):
            raise ValueError('forced relocation cannot prove an anchor')
        for anchor in anchors:
            if not (any(math.dist(tuple(map(float,s[2].split())),anchor)<.2
                       and math.dist(tuple(map(float,s[1].split())),anchor)<96 for s in row['samples'])
                   or (math.dist(row['target'],anchor)<.2
                       and math.dist(row['final_position'],anchor)<48)):
                raise ValueError('anchor was not executed by the witnessed route')
        # The receipt must have selected these actions in this direction.
        nodes=[tuple(map(float,s[2].split())) for s in row['samples']]
        for source,target in links:
            positions=[i for i,n in enumerate(nodes) if math.dist(n,source)<.2]
            if not positions or not any(math.dist(n,target)<.2 for n in nodes[min(positions)+1:]):
                raise ValueError('link direction was not executed by the route')
        rates.add(rate)
    if rates!={.0139,.1}: raise ValueError('anchors need played and 100ms route proofs')
    return anchors
