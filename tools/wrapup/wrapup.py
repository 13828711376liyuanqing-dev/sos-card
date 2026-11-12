#!/usr/bin/env python3
"""One command to finish a round: sync to D:\\SVN (with checks), then tidy debug leftovers.

SAM | 2026-11-04 +08:00 | Runs tools/tree_sync/sync_all.py, and only if that succeeds, tools/tidy/tidy.py.
  python wrapup.py          preview of both (nothing is written)
  python wrapup.py --yes    sync, verify, baseline, handoff check, then tidy (moves old files to D:\\CODEX\\_archive)
Extra options after --yes are passed to tidy.py (--log-days, --keep-releases, --tmp-days).
"""
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def run(script, *args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, str(script), *args], env=env).returncode


def main():
    args = sys.argv[1:]
    go = '--yes' in args
    rest = [x for x in args if x != '--yes']
    print('== 1/2 sync to D:\\SVN ==')
    rc = run(TOOLS / 'tree_sync' / 'sync_all.py', *(['--yes'] if go else []))
    if rc != 0:
        print('Sync did not finish cleanly, tidy skipped (nothing was tidied).')
        return rc
    print('\n== 2/2 tidy debug leftovers ==')
    return run(TOOLS / 'tidy' / 'tidy.py', *(['--yes'] if go else []), *rest)


if __name__ == '__main__':
    sys.exit(main())
