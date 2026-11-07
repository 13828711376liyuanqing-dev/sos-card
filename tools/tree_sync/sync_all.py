#!/usr/bin/env python3
"""One-command "finish the round" sync: project -> D:\\SVN, with every check in between.

SAM | 2026-11-04 +08:00 | Wraps tree_sync.py (plain file compare/copy only) so one run does: scan -> stop on
colleague changes / conflicts / OTA-rule BLOCK -> push -> re-scan to verify -> baseline -> handoff. Prints a short summary.

  python sync_all.py          preview only (nothing is written)
  python sync_all.py --yes    do it
"""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANSI = re.compile(r'\x1b\[[0-9;]*m|\r[^\n]*?(?=\r|\n|$)')
BAD = ('同事改了', '两边都改', '仅 SVN 有')       # something only the other side has: pull / merge first


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([sys.executable, str(HERE / 'tree_sync.py'), *args], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    out = ANSI.sub('', (r.stdout or '') + (r.stderr or ''))
    return r.returncode, out


def areas(out):
    """[(name, mode, row_text)] from the region table of `scan`."""
    rows = []
    for ln in out.splitlines():
        m = re.match(r'^(\w+)\s+(two-way|report-only)\s+(.*)$', ln.strip())
        if m:
            rows.append((m.group(1), m.group(2), m.group(3)))
    return rows


def guard(out):
    m = re.search(r'BLOCK=(\d+)\s+WARN=(\d+)', out)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def tail(out, n=12):
    return '\n'.join(out.strip().splitlines()[-n:])


def main():
    go = '--yes' in sys.argv
    rc, out = run('scan')
    if rc != 0:
        print('scan failed:\n' + tail(out)); return 2
    rows = areas(out)
    block, warn = guard(out)
    other = [(n, t) for n, mode, t in rows if mode == 'two-way' and any(b in t for b in BAD)]
    mine = [(n, t) for n, mode, t in rows if mode == 'two-way' and ('项目改了' in t or '仅项目有' in t)]
    print('scan: ' + '; '.join(f'{n}[{t}]' for n, mode, t in rows if mode == 'two-way' and t.strip()))
    print(f'OTA rules: BLOCK={block} WARN={warn}')
    if other:
        print('STOP: the SVN side has changes (colleague). Run `tree_sync.py pull` / `merge` first:')
        for n, t in other: print(f'  {n}: {t}')
        return 1
    if block:
        print('STOP: OTA rule BLOCK, see the latest tools/tree_sync/reports/*/summary.md'); return 1
    if not mine:
        print('Nothing to push: both sides already match.'); return 0
    if not go:
        print('Preview only. Run again with --yes to push, verify, record the baseline and run the handoff check.'); return 0

    rc, out = run('push', '--yes')
    print('push: ' + (re.search(r'完成：.*', out).group(0) if re.search(r'完成：.*', out) else tail(out, 3)))
    rc, out = run('scan')
    left = [(n, t) for n, mode, t in areas(out) if mode == 'two-way' and any(k in t for k in ('项目改了', '仅项目有') + BAD)]
    if left:
        print('FAIL: still different after push:'); [print(f'  {n}: {t}') for n, t in left]; return 1
    print('verify: every two-way area matches' + f'; OTA rules BLOCK/WARN={guard(out)}')
    rc, out = run('baseline')
    print('baseline: ' + (re.search(r'基线已更新：.*', out).group(0) if re.search(r'基线已更新：.*', out) else tail(out, 2)))
    rc, out = run('handoff')
    res = re.search(r'结论：.*', out)
    print('handoff: ' + (res.group(0) if res else tail(out, 4)))
    print('Next: commit to SVN by the user / Codex (never by this tool).')
    return 0 if res and '可以交接' in res.group(0) else 1


if __name__ == '__main__':
    sys.exit(main())
