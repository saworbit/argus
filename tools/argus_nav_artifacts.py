"""Generated QC is the authority for sidecar edges and the runtime banner."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from argus_navjson import FAMILIES, STEP

VERBS = {
    'Argus_NavLink': 'links', 'Argus_NavLinkJump': 'jlinks',
    'Argus_NavLinkDoor': 'doorlinks', 'Argus_NavLinkSprint': 'sprintlinks',
    'Argus_NavLinkRocket': 'rjlinks', 'Argus_NavLinkLift': 'liftlinks',
    'Argus_NavLinkSwim': 'swimlinks', 'Argus_NavLinkTrain': 'trainlinks',
}
NODE = re.compile(r"^\s*n(\d+)\s*=\s*Argus_NavNode\s*\('([^']+)'\);", re.M)
LINK = re.compile(r'^\s*(Argus_NavLink\w*)\s*\(\s*n(\d+),\s*n(\d+)(?:\s*,\s*[-+\d.]+)?\s*\);([^\n]*)', re.M)
BANNER = re.compile(r'ARGNAV (\d+) nodes, (\d+) links\\n')
TACTIC = re.compile(r'^\s*Argus_NavTactics\s*\(n(\d+),\s*(\d+),\s*(n\d+|world),\s*(n\d+|world)\);', re.M)


def qc_graph(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    nodes = {int(i): [float(v) for v in pos.split()] for i, pos in NODE.findall(text)}
    if not nodes or sorted(nodes) != list(range(len(nodes))):
        raise ValueError('QC nodes must be nonempty and contiguous')
    edges = {}
    for verb, a, b, tail in LINK.findall(text):
        pair = int(a), int(b)
        if verb not in VERBS or any(i not in nodes for i in pair):
            raise ValueError(f'invalid QC link {verb} {pair}')
        if pair in edges:
            raise ValueError(f'duplicate QC link {pair}')
        edges[pair] = 'teles' if verb == 'Argus_NavLink' and 'teleporter' in tail else VERBS[verb]
    return nodes, edges


def check_nodes(doc, nodes):
    positions = [n['origin'] if isinstance(n, dict) else n for n in doc['nodes']]
    rounded = [[float(f'{v:.0f}') for v in pos] for pos in positions]
    if rounded != [nodes[i] for i in range(len(nodes))]:
        raise ValueError('QC and JSON node positions disagree')


def canonical_sidecar(doc, text):
    """Retain metadata and node precision; derive families from actual calls.

    Door and jump lists type ordinary links. Other families own independent
    edges. Never filter a lift, swim or teleporter through the walk dictionary.
    """
    nodes, edges = qc_graph(text)
    check_nodes(doc, nodes)
    result = dict(doc)
    ordinary = {p for p, family in edges.items() if family in ('links', 'jlinks', 'doorlinks')}
    for family in FAMILIES:
        wanted = {p for p in edges if edges[p] == family}
        ordered = list(dict.fromkeys(tuple(row[:2]) for row in doc.get(family, []) if tuple(row[:2]) in wanted))
        ordered.extend(sorted(wanted - set(ordered)))
        result[family] = [list(p) for p in ordered]
    result['links'] = [[a, b, int((b, a) in ordinary)] for a, b in sorted(ordinary)]
    if 'jumpapproach' in doc:
        result['jumpapproach'] = [row for row in doc['jumpapproach'] if edges.get(tuple(row[:2])) == 'jlinks']
    return result


def refresh_banner(text):
    nodes, edges = qc_graph(text)
    if len(BANNER.findall(text)) != 1:
        raise ValueError('QC must contain one ARGNAV banner')
    return BANNER.sub(lambda _: f'ARGNAV {len(nodes)} nodes, {len(edges)} links\\n', text)


def validate_pair(text, doc, *, banner=True, tactics=True):
    nodes, edges = qc_graph(text)
    check_nodes(doc, nodes)
    canonical = canonical_sidecar(doc, text)
    for family in FAMILIES:
        actual = {tuple(row[:2]) for row in doc.get(family, [])}
        expected = {tuple(row[:2]) for row in canonical[family]}
        if actual != expected:
            raise ValueError(f'{family} differs from QC: extra {sorted(actual - expected)[:5]}, missing {sorted(expected - actual)[:5]}')
    if banner and BANNER.findall(text) != [(str(len(nodes)), str(len(edges)))]:
        raise ValueError('ARGNAV banner differs from emitted node/link counts')
    if not tactics:
        return
    annotations = {}
    for field in ('cover_targets', 'exposure'):
        if field in doc and len(doc[field]) != len(nodes):
            raise ValueError(f'incomplete {field} annotations')
    for source, exposure, target, hop in TACTIC.findall(text):
        source, exposure = int(source), int(exposure)
        target, hop = [-1 if x == 'world' else int(x[1:]) for x in (target, hop)]
        if source in annotations or source not in nodes:
            raise ValueError(f'invalid tactical source n{source}')
        annotations[source] = [target, hop]
        if target >= 0 or hop >= 0:
            if target not in nodes or edges.get((source, hop)) != 'links':
                raise ValueError(f'n{source} cover hop is not a live ordinary walk; use --reanalyze-tactics')
            if nodes[source][2] - nodes[hop][2] > STEP:
                raise ValueError(f'n{source} cover hop is a deliberate drop')
        if 'cover_targets' in doc and doc['cover_targets'][source] != [target, hop]:
            raise ValueError(f'n{source} cover annotation differs from QC')
        if 'exposure' in doc and doc['exposure'][source] != exposure:
            raise ValueError(f'n{source} exposure differs from QC')
    if 'cover_targets' in doc and (len(doc['cover_targets']) != len(nodes) or len(annotations) != len(nodes)):
        raise ValueError('incomplete cover annotations')


def publish_pair(qc, old_qc, old_json, text, doc):
    """Preflight both outputs, then publish with rollback on a second failure."""
    validate_pair(text, doc)
    qc = Path(qc)
    graph = Path(str(qc) + '.json')
    if qc.is_symlink() or graph.is_symlink() or (qc.exists() and graph.exists() and qc.samefile(graph)):
        raise ValueError('artifact outputs must be distinct regular files, not aliases')
    outputs = [(qc, old_qc, text.encode('ascii')), (graph, old_json, json.dumps(doc).encode('utf-8'))]
    staged, published = [], []
    try:
        for path, before, after in outputs:
            if existing_bytes(path) != before:
                raise ValueError(f'output changed during analysis: {path}')
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', delete=False) as f:
                staged.append(Path(f.name))
                f.write(after)
        for (path, before, after), temporary in zip(outputs, staged):
            if existing_bytes(path) != before:
                raise ValueError(f'output changed before publication: {path}')
            os.replace(temporary, path)
            published.append((path, before, after))
    except BaseException as original:
        failures = []
        for path, before, after in reversed(published):
            try:
                if path.read_bytes() != after:
                    raise ValueError('published output changed; refusing rollback')
                if before is None:
                    path.unlink()
                else:
                    path.write_bytes(before)
            except (OSError, ValueError) as error:
                failures.append(f'{path}: {error}')
        if failures:
            raise RuntimeError(f'{original}; rollback failed: {failures}') from original
        raise
    finally:
        active_error = sys.exc_info()[1]
        cleanup = []
        for path in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                cleanup.append(f'{path}: {error}')
        if cleanup:
            raise RuntimeError(f'{active_error or "publication completed"}; staging cleanup failed: {cleanup}') from active_error


def reconcile(qc):
    qc = Path(qc)
    old_qc, old_json = qc.read_bytes(), Path(str(qc) + '.json').read_bytes()
    text = old_qc.decode('ascii')
    doc = canonical_sidecar(json.loads(old_json), text)
    publish_pair(qc, old_qc, old_json, refresh_banner(text), doc)


def existing_bytes(path):
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return None
