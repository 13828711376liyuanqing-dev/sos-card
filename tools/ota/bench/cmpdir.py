# Compare two plain-file trees (top level + subdirs), skipping every dot-directory. Usage: cmpdir.py <src> <dst>
import os, sys, hashlib


def files(root):
    out = {}
    for d, subs, names in os.walk(root):
        subs[:] = [s for s in subs if not s.startswith('.')]
        for n in names:
            p = os.path.join(d, n)
            out[os.path.relpath(p, root).replace('\\', '/')] = hashlib.md5(open(p, 'rb').read()).hexdigest()
    return out


a, b = files(sys.argv[1]), files(sys.argv[2])
print('src', len(a), 'dst', len(b))
for k in sorted(set(a) | set(b)):
    if k not in b: print('NEW    ', k)
    elif k not in a: print('DSTONLY', k)
    elif a[k] != b[k]: print('DIFF   ', k)
