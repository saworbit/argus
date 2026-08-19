#!/usr/bin/env python3
"""Append palette-remapped player skins to a Quake .mdl.

Why this exists: GLQuake-lineage renderers (QuakeSpasm included) apply
shirt/pants colour translation only to entities numbered 1..maxclients,
i.e. real client edicts. Argus bots are spawned edicts with high entity
numbers, so no QC field value can ever colour them there (the colormap
field is read as a mere flag; the translation is keyed by entity
number). The one renderer-agnostic vanilla channel left is the .skin
field, so we bake each bot's scoreboard colours into extra skins on the
player model itself. Skin 0 stays untouched for humans.

The remap is exactly the engine's own translation (CL_NewTranslation /
R_TranslatePlayerSkin): palette indexes 16-31 are the shirt ramp and
96-111 the pants ramp; each maps onto the target colour's 16-index
palette row, ramp-reversed for the dark rows (colour >= 8).

Licence note: the output is derived from the input model. Run against
id's player.mdl the result is id-derived and machine-local (never
commit or redistribute, same rule as maps_local/). Run against
LibreQuake's player model for a shippable build.

Usage:
  python mdl_skins.py IN.mdl OUT.mdl top:bottom [top:bottom ...]
"""
import struct
import sys


def remap_table(top, bottom):
    t = list(range(256))
    for i in range(16):
        t[16 + i] = top * 16 + (i if top < 8 else 15 - i)
        t[96 + i] = bottom * 16 + (i if bottom < 8 else 15 - i)
    return bytes(t)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    pairs = [tuple(int(x) for x in a.split(':')) for a in sys.argv[3:]]
    data = open(src, 'rb').read()

    ident, version = struct.unpack_from('<4si', data, 0)
    if ident != b'IDPO' or version != 6:
        sys.exit(f'not a version-6 IDPO mdl: {ident!r} v{version}')
    numskins, w, h = struct.unpack_from('<3i', data, 48)
    print(f'{src}: {numskins} skin(s), {w}x{h}')

    # walk the existing skins to find the insertion point (end of the
    # skin block) and grab the first single-skin image as the source
    off = 84
    first = None
    for _ in range(numskins):
        group, = struct.unpack_from('<i', data, off)
        off += 4
        if group == 0:
            if first is None:
                first = data[off:off + w * h]
            off += w * h
        else:
            n, = struct.unpack_from('<i', data, off)
            off += 4 + 4 * n
            if first is None:
                first = data[off:off + w * h]
            off += w * h * n
    if first is None:
        sys.exit('no skin image found')

    extra = bytearray()
    for top, bottom in pairs:
        extra += struct.pack('<i', 0)
        extra += first.translate(remap_table(top, bottom))
        print(f'  + skin: shirt colour {top}, pants colour {bottom}')

    out = bytearray(data[:off]) + extra + data[off:]
    struct.pack_into('<i', out, 48, numskins + len(pairs))
    with open(dst, 'wb') as f:
        f.write(bytes(out))
    print(f'{dst}: {numskins + len(pairs)} skins, {len(out)} bytes')


if __name__ == '__main__':
    main()
