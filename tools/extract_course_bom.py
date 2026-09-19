# -*- coding: utf-8 -*-
"""Extract text + positions from Visio EPRINT (EMF) streams embedded in the course .doc."""
import sys
import struct
import olefile

STD = {'iGfx': 8, 'ptx': 20, 'pty': 24, 'nChars': 28, 'offString': 32, 'offDx': 56}
# This Visio build writes records with extra bytes between EMR header and iGraphicsMode.
SHIFTS = (16, 0, 12, 20, 8, 4, 24)


def decode(rec, nchars, offstring, wide):
    start = offstring
    if start + nchars * (2 if wide else 1) > len(rec):
        return None
    raw = rec[start:start + nchars * (2 if wide else 1)]
    try:
        txt = raw.decode('utf-16-le' if wide else 'cp1252', errors='replace')
    except Exception:
        return None
    txt = txt.replace('\x00', '').strip()
    if not txt:
        return None
    bad = sum(1 for c in txt if ord(c) < 32 or 0xE000 <= ord(c) <= 0xF8FF)
    if bad > len(txt) * 0.2:
        return None
    return txt


def parse_emf(data):
    items = []
    off = 0
    n = len(data)
    while off + 8 <= n:
        rtype, rsize = struct.unpack_from('<II', data, off)
        if rsize < 8 or off + rsize > n:
            break
        if rtype in (83, 84):
            wide = rtype == 84
            rec = data[off:off + rsize]
            got = None
            for sh in SHIFTS:
                if sh + 36 > len(rec):
                    continue
                nchars = struct.unpack_from('<I', rec, STD['nChars'] + sh)[0]
                offstr = struct.unpack_from('<I', rec, STD['offString'] + sh)[0]
                if not (0 < nchars < 512) or offstr < 8 or offstr % 2 or offstr >= rsize:
                    continue
                txt = decode(rec, nchars, offstr, wide)
                if txt:
                    x = struct.unpack_from('<i', rec, STD['ptx'] + sh)[0]
                    y = struct.unpack_from('<i', rec, STD['pty'] + sh)[0]
                    got = (y, x, txt)
                    break
            if got:
                items.append(got)
        off += rsize
    return items


def dump(path, key=None, out=None):
    ole = olefile.OleFileIO(path)
    streams = ['/'.join(s) for s in ole.listdir()]
    targets = [s for s in streams if s.split('/')[-1].endswith('EPRINT')]
    if key:
        targets = [s for s in targets if key in s]
    for t in targets:
        items = parse_emf(ole.openstream(t).read())
        header = '--- %s : %d text runs ---' % (t, len(items))
        print(header, file=out)
        for y, x, txt in sorted(items):
            print('y=%6d x=%6d  %s' % (y, x, txt), file=out)
        print(file=out)
    ole.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    dump(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)