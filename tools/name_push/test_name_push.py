"""SAM | 2026-11-02 +08:00 | Build the real GR name-push C code on the host and feed it lines from glyph_maker.
Usage: python test_name_push.py [name]   (default 欧阳䶮𠮷)"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'glyph_maker'))
import glyphlib as G  # noqa: E402

GCC = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
BUS = ROOT / 'ble_app_uart_c' / 'Src' / 'user' / 'business'
CJSON = ROOT / 'ble_app_uart_c' / 'Src' / 'external' / 'cJSON-1.7.19'
OUT = ROOT / 'logs' / 'name_push_20261102'


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else '欧阳䶮𠮷'
    OUT.mkdir(parents=True, exist_ok=True)
    glyphs = G.resident_glyphs(name, '泰康之家·鹏园')
    msg = G.platform_msg(name, '1#1-102', '泰康之家·鹏园', 1730500000, glyphs)
    lines = G.bus_lines(msg, txn=5)
    (OUT / 'lines.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (OUT / 'lines.txt.hex').write_text(''.join(f'{g.u:X} {g.size} {g.data.hex()}\n' for g in glyphs), encoding='utf-8')
    print(f'{name}: {len(glyphs)} glyphs, longest line {max(len(l.encode()) for l in lines)} B')
    # SAM | 2026-11-03 +08:00 | A set too big for the device record (built without the generator's size cap) for the refusal test.
    # SAM | 2026-11-04 +08:00 | The record limit is 4000 B now (Flash pages): 28 full 40x40 glyphs (28 x 216 + 20 = 6068 B).
    big = [G.Glyph(0x4E00 + i, 32, [[1] * 40 for _ in range(40)], 0, 0, 512) for i in range(28)]
    big_msg = G.platform_msg('阿卜杜拉买买提江', '1#1-102', '', 1730500100, big, max_store=0)
    (OUT / 'lines_big.txt').write_text('\n'.join(G.bus_lines(big_msg, txn=7)) + '\n', encoding='utf-8')
    print(f'big set: {len(big)} glyphs, {G.store_bytes(big)} B record')
    env = dict(os.environ, PATH=str(GCC.parent) + os.pathsep + os.environ['PATH'])
    exe = OUT / 'test_name_push.exe'
    cmd = [str(GCC), '-std=c99', '-Wall', '-Wextra', '-Werror', '-Wno-error=unused-variable', '-Wno-error=discarded-qualifiers', '-DYP_BUSINESS_HOST_TEST',
           '-I' + str(HERE / 'stubs'), '-I' + str(BUS), '-I' + str(CJSON),
           str(HERE / 'test_name_push.c'), str(BUS / 'yp001_business.c'), str(BUS / 'yp_name_glyphs.c'),
           str(CJSON / 'cJSON.c'), '-o', str(exe)]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout + r.stderr)
        return 1
    r = subprocess.run([str(exe), str(OUT / 'lines.txt'), name.encode('utf-8').hex(), str(OUT / 'lines_big.txt')],
                       env=env, capture_output=True, timeout=30)
    out = (r.stdout + r.stderr).decode('utf-8', 'replace')
    (OUT / 'test_name_push.log').write_text(out, encoding='utf-8')
    print(out)
    return r.returncode


if __name__ == '__main__':
    raise SystemExit(main())
