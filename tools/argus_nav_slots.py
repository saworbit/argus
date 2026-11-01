"""Runtime slots are unique directed destinations, regardless of typing."""
from collections import defaultdict

MAX_LINKS = 8


def typed_targets(*families):
    targets = defaultdict(set)
    for family in families:
        for source, target in family:
            targets[source].add(target)
    return targets


def slot_count(source, links, *families):
    targets = set(links.get(source, {}))
    for family in families:
        targets.update(b for a, b in family if a == source)
    return len(targets)


def clamp_walk(links, *families, key=None):
    """Keep typed connectivity. Refuse typed overflow before changing walks."""
    typed = typed_targets(*families)
    overflow = {a: len(targets) for a, targets in typed.items() if len(targets) > MAX_LINKS}
    if overflow:
        raise ValueError(f'typed link slot overflow: {overflow}; refusing to drop a typed route')
    replacements = {}
    evicted = 0
    for source, outgoing in links.items():
        targets = typed[source]
        room = MAX_LINKS - len(targets)
        plain = [(b, value) for b, value in outgoing.items() if b not in targets]
        if len(plain) <= room:
            continue
        order = (lambda item: key(source, item)) if key else (lambda item: (not item[1][1], item[1][0]))
        keep = set(b for b, _ in sorted(plain, key=order)[:room]) | targets
        replacements[source] = {b: value for b, value in outgoing.items() if b in keep}
        evicted += len(outgoing) - len(replacements[source])
    links.update(replacements)
    return evicted


def require_slots(links, *families):
    sources = set(links) | set(typed_targets(*families))
    overflow = {a: slot_count(a, links, *families) for a in sources
                if slot_count(a, links, *families) > MAX_LINKS}
    if overflow:
        raise ValueError(f'final link slot overflow: {overflow}')
