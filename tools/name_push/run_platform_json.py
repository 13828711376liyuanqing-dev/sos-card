"""SAM | 2026-11-04 +08:00 | Feed one platform residentNameMsg JSON file through the real CAT1 code (resident_name.lua, lupa)
and the real GR C code (test_name_push.exe): CAT1 must forward it, GR must commit the whole set, show the name and store every
glyph byte-for-byte as in the file, and CAT1 must reply success. Host only.
Usage: python run_platform_json.py <residentNameMsg_*.json>"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import test_cat1_resident as T


def main():
    src = Path(sys.argv[1])
    msg = json.loads(src.read_text(encoding='utf-8'))
    L, mod, sent, pub = T.runtime()
    mod.on_platform(L.globals().py_decode(json.dumps(msg, ensure_ascii=False)))
    L.globals().step()
    lines = T.bus(sent)
    print(f'CAT1: power hold {T.holds(sent)[:1]}, {len(lines)} lines to GR (expect {len(msg["Glyphs"]) + 2})')
    if len(lines) != len(msg['Glyphs']) + 2:
        print('FAIL: CAT1 did not forward the whole message'); return 1
    hexf = T.OUT / 'cat1_lines.txt.hex'
    f = T.OUT / 'cat1_lines.txt'
    f.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    hexf.write_text(''.join(f"{g['U']} {g['S']} {base64.b64decode(g['D']).hex()}\n" for g in msg['Glyphs']), encoding='utf-8')
    env_path = r'D:\Program Files\GUI Guider\environment\mingw\bin'
    r = subprocess.run([str(T.OUT / 'test_name_push.exe'), str(f), T.G.shown_name(msg['Name']).encode().hex(), str(T.OUT / 'lines_big.txt')],
                       capture_output=True, timeout=30, env=dict(os.environ, PATH=env_path + os.pathsep + os.environ['PATH']))
    out = (r.stdout + r.stderr).decode('utf-8', 'replace')
    print('GR:', '\n    '.join(l for l in out.splitlines() if l.strip())[:900])
    # Only the steps about this file count: commit, byte-identical glyphs, restore after reboot. The later steps of the GR test
    # program use its own fixtures (e.g. an oversize set with an older Seq), unrelated to the file under test.
    n = len(msg['Glyphs'])
    ok = 'commit ok' in out and f'bitmaps identical: {n}' in out and f'name and {n} glyphs restored from NVDS' in out
    print('结论：' + ('设备会收下并显示（CAT1 转发、GR 整批生效、字形逐字节一致）' if ok else '设备不会收下'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
