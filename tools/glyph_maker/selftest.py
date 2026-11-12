"""SAM | 2026-11-03 +08:00 | 开发自检：改了打包/CRC/消息格式后先跑这个。
  python selftest.py          基本检查（几秒）
  python selftest.py --t0     另加 T0：用 lv_font_conv 重新生成 fonts/ 里的全部字，逐字节对比（约 20 秒，需要 Node）
"""
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import glyphlib as G

# SAM | 2026-11-03 +08:00 | A GBK console cannot print Ext-A/B characters (䶮, 𠮷): replace them instead of crashing.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(errors='replace')

HERE = Path(__file__).resolve().parent
fails = []


def check(cond, what):
    print(('PASS ' if cond else 'FAIL ') + what)
    if not cond:
        fails.append(what)


# 1. Known vector from docs/字段与格式说明.md: U+4DAE 16px header 00 4D AE 10 0E 0E 01 FF 01 00 -> CRC 2152
ex = json.loads((HERE / 'examples' / 'residentNameMsg_欧阳䶮𠮷.json').read_text(encoding='utf-8'))
g = next(x for x in ex['Glyphs'] if x['U'] == '4DAE' and x['S'] == 16)
d = base64.b64decode(g['D'])
check(G.crc16(bytes.fromhex('004DAE100E0E01FF0100') + d) == 0x2152, 'CRC 已知向量（䶮 16px = 2152）')

# 2. Every glyph in the example decodes, matches its CRC and re-encodes identically
ok = True
for j in ex['Glyphs']:
    try:
        ok &= G.Glyph.from_json(j).to_json() == j
    except Exception as e:
        print('   ', j['U'], j['S'], e); ok = False
check(ok, f'示例文件 {len(ex["Glyphs"])} 个字形：解码、CRC、重新编码一致')

# 3. pack/unpack round trip at awkward widths
rt = all(G.unpack(G.pack(r), len(r[0]), len(r)) == r
         for r in ([[1]], [[1, 0, 1] * 3], [[(x * y) % 2 for x in range(17)] for y in range(5)]))
check(rt, '点阵打包/解包互逆（宽 1、9、17）')

# 4. bus lines stay under the GR line limit
check(max(len(l.encode()) for l in G.bus_lines(ex)) < G.LINE_LIMIT, f'CAT1->GR 串口行 < {G.LINE_LIMIT} 字节')

# 5. The web tool's CORE functions give the same JSON as Python (needs Node)
node = shutil.which('node')
if node:
    html = (HERE / 'backend' / '姓名字形生成器_后台版.html').read_text(encoding='utf-8')
    core = re.search(r'// CORE-BEGIN.*?// CORE-END', html, re.S).group(0)
    with tempfile.TemporaryDirectory() as td:
        Path(td, 'core.js').write_text(core, encoding='utf-8')
        cases = [{'u': int(j['U'], 16), 'size': j['S'], 'rows': G.Glyph.from_json(j).rows, 'x': j['X'], 'y': j['Y'], 'a': j['A']}
                 for j in ex['Glyphs']]
        Path(td, 'cases.json').write_text(json.dumps(cases), encoding='utf-8')
        Path(td, 't.js').write_text("const C=require('./core.js');const cs=require('./cases.json');"
                                    "console.log(JSON.stringify(cs.map(c=>C.glyphJson(c))))", encoding='utf-8')
        r = subprocess.run([node, 't.js'], cwd=td, capture_output=True, text=True)
        js = json.loads(r.stdout) if r.returncode == 0 else []
    check(js == ex['Glyphs'], '网页版 CORE 与 Python 结果一致')
else:
    print('SKIP 网页版 CORE 对比（没有 Node）')

# 6. T0: regenerate every built-in glyph with lv_font_conv and compare byte for byte
if '--t0' in sys.argv:
    if not G.lfc_available():
        print('SKIP T0（fontconv 不可用：需要 Node）')
    else:
        for s in G.SIZES:
            lf = G.local_font(s)
            us = [u for u in lf.map if u > 0x20]
            got = G.render_lfc(''.join(map(chr, us)), s)
            key = lambda x: (x.w, x.h, x.ofs_x, x.ofs_y, x.adv_w, x.data)  # noqa: E731
            check(all(key(got[u]) == key(lf.glyph(u)) for u in us), f'T0 {s}px：{len(us)} 个字与 {G.FONT_DIR.name}/font_cn_{s}.c 逐字节一致')

print('ALL PASS' if not fails else f'{len(fails)} FAIL')
raise SystemExit(1 if fails else 0)
