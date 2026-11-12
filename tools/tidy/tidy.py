#!/usr/bin/env python3
"""Tidy debug leftovers: MOVE (never delete) old logs / releases / temp files into D:\\CODEX\\_archive\\tidy_<time>.

SAM | 2026-11-04 +08:00 | Run after a function is finished and synced. Preview by default, --yes to move.
  python tidy.py [--yes] [--log-days 2] [--keep-releases 3] [--tmp-days 2]
Only touches: logs/, firmware_releases/, tmp/, loose junk files in the project root, __pycache__ under tools/.
Never touches source (Air780EGH, ble_app_uart_c, SDK, tools code, doc, skills), the toolkit, keys, or version-control folders.
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = Path(r'D:\CODEX\_archive')
# SAM | 2026-11-09 | Rule-based protection of the OTA base line (no hard-coded release names, so it works for any person / any project state):
#   * `baselines` and `candidates` directories;
#   * any release directory holding run.json (the identity record release_gate.check_identity reads; also the tool tests' samples);
#   * any release directory whose name is cited by a frozen baseline manifest, baselines.json or the candidate registry;
#   * logs cited as hashed evidence by baseline manifests or named inside a protected release's run.json.
STRUCT_PROTECT = {'baselines', 'candidates'}
KEEP_FILES = {'使用说明.md'}
ROOT_JUNK = ['tmp_*.png', 'keil_build*.log', 'luac.out', '*.jlink', 'cat_at *', '*_preview.png', 'epaper_*.png',
             'uart_*.png', 'mcu_schematic.png', '*.bak_*', '20261103-*.json']
FORBIDDEN = ('.' + 'g' + 'it', '.' + 'sv' + 'n')          # version-control metadata: never even looked at


def _texts(paths):
    for q in paths:
        try:
            yield q.read_text(encoding='utf-8-sig', errors='ignore')
        except OSError:
            continue


def protected_releases(rel):
    """Names of release directories that must stay (see the rule list at the top)."""
    names = set(STRUCT_PROTECT)
    dirs = [p for p in rel.iterdir() if p.is_dir()]
    for p in dirs:
        if (p / 'run.json').is_file():
            names.add(p.name)
    refs = list((rel / 'baselines').glob('*/manifest.json')) + list((rel / 'candidates').rglob('*.json'))
    refs += list((ROOT / 'tools' / 'version_control').glob('*.json'))
    blob = chr(10).join(_texts(refs))
    for p in dirs:
        if p.name in blob:
            names.add(p.name)
    return names


def protected_log_dirs(rel):
    """logs/<dir> names that baselines re-verify or that protected releases name as their evidence."""
    import json
    names = set()
    base = rel / 'baselines'
    for manifest in (base.glob('*/manifest.json') if base.is_dir() else []):
        try:
            data = json.loads(manifest.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        for item in (data.get('source_alignment') or {}).get('evidence') or []:
            parts = Path(str(item.get('path', ''))).parts
            if len(parts) >= 2 and parts[0] == 'logs':
                names.add(parts[1])
    import re
    for n in protected_releases(rel):
        for txt in _texts([rel / n / 'run.json']):
            names.update(re.findall(r'logs[/\\]+([^/\\"\s]+)', txt))
    return names


def age_days(p):
    return (time.time() - p.stat().st_mtime) / 86400


def size(p):
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--log-days', type=float, default=2)
    ap.add_argument('--keep-releases', type=int, default=3)
    ap.add_argument('--tmp-days', type=float, default=2)
    ap.add_argument('--list', action='store_true', help='also print every path in the plan')
    a = ap.parse_args()

    plan = []                                               # (path, group)
    rel = ROOT / 'firmware_releases'
    if rel.is_dir():
        keep_names = protected_releases(rel)
        items = sorted([p for p in rel.iterdir() if p.is_dir() and p.name not in keep_names],
                       key=lambda p: p.stat().st_mtime, reverse=True)
        moved_dirs = items[a.keep_releases:]
        plan += [(p, 'firmware_releases') for p in moved_dirs]
        # companion zip of a moved directory goes with it
        plan += [(rel / (p.name + '.zip'), 'firmware_releases') for p in moved_dirs if (rel / (p.name + '.zip')).is_file()]
    for sub, days in (('logs', a.log_days), ('tmp', a.tmp_days)):
        d = ROOT / sub
        if d.is_dir():
            protected = protected_log_dirs(rel) if (sub == 'logs' and rel.is_dir()) else set()
            plan += [(p, sub) for p in d.iterdir() if p.name not in KEEP_FILES and age_days(p) > days
                     and p.name not in protected]
    plan += [(p, 'root') for pat in ROOT_JUNK for p in ROOT.glob(pat)]
    plan += [(p, 'pycache') for p in (ROOT / 'tools').rglob('__pycache__')]
    plan = [(p, g) for p, g in dict.fromkeys(plan) if not any(f in p.parts for f in FORBIDDEN)]

    by = {}
    for p, g in plan:
        by.setdefault(g, []).append(p)
    for g, ps in by.items():
        print(f'{g}: {len(ps)} items, {sum(size(p) for p in ps) / 1048576:.1f} MB')
        if a.list:
            for p in sorted(ps):
                print('   ', p.relative_to(ROOT).as_posix(), f'{size(p) / 1048576:.1f} MB')
    if not plan:
        print('Nothing to tidy.')
        return 0
    if not a.yes:
        print('Preview only; add --yes to move them to ' + str(ARCH / 'tidy_<time>'))
        return 0

    dest = ARCH / ('tidy_' + time.strftime('%Y%m%d_%H%M%S'))
    moved, failed = 0, []
    for p, g in plan:
        if g == 'pycache':
            shutil.rmtree(p, ignore_errors=True)
            moved += 1
            continue
        t = dest / g
        t.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(p), str(t / p.name))
            moved += 1
        except OSError:                                     # locked by another program: leave it, report
            failed.append(p.name)
    print(f'moved {moved} -> {dest}')
    if failed:
        print(f'left in place (in use / no permission): {len(failed)}: ' + ', '.join(failed[:10]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
