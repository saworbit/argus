"""Names shared by generation and native lab entry points."""
import re

MAP_NAME = re.compile(r'[a-z0-9_]{1,32}', re.ASCII)


def map_name(raw):
    """Normalize the engine name and the QuakeC symbol suffix together."""
    name = raw.strip()
    if not name.isascii():
        raise ValueError('map must match [a-z0-9_]{1,32}; dispatch is reserved')
    name = name.lower()
    if not MAP_NAME.fullmatch(name) or name == 'dispatch':
        raise ValueError('map must match [a-z0-9_]{1,32}; dispatch is reserved')
    return name
