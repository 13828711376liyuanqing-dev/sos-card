"""SAM | 2026-11-03 +08:00 | Check that every GUI label can draw its text with the font it uses (after subset_fonts.py).

1. Each label in gui/guider/setup_scr_*.c: its default text against its font_cn_* (pushed-glyph labels are listed, not failed).
2. Every non-ASCII character in C string literals of the GR user code, with the files using them (to spot new UI text).
3. Extra runtime texts given with --text SIZE:TEXT (e.g. --text "28:1号楼2单元303室").
Exit code 1 if a fixed-font label misses a character.
"""
import argparse
import glob
import os
import re
import sys
from pathlib import Path

import glyphlib as G

USER = Path(__file__).resolve().parents[2] / 'ble_app_uart_c' / 'Src' / 'user'
# Labels whose font is replaced at runtime by the pushed-glyph fonts (epaper_ui.c name_fonts_init): CJK there is pushed.
PUSHED = {'screen_main_label_name', 'screen_main_label_campus', 'screen_lowbat_label_info'}


def c_bytes(s):
    out, i = bytearray(), 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            n = s[i + 1]
            if n == 'x':
                m = re.match(r'[0-9a-fA-F]{1,2}', s[i + 2:])
                out.append(int(m.group(0), 16)); i += 2 + len(m.group(0)); continue
            out += {'n': b'\n', 't': b'\t', 'r': b'\r', '0': b'\0'}.get(n, n.encode('utf-8')); i += 2; continue
        out += s[i].encode('utf-8'); i += 1
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--text', action='append', default=[], help='SIZE:TEXT runtime text to check')
    a = ap.parse_args()
    fonts = {}
    font = lambda s: fonts.setdefault(s, G.LocalFont(s, G.FONT_DIR / f'font_cn_{s}.c'))
    bad = 0
    print('== labels (default text) ==')
    for f in sorted(glob.glob(str(USER / 'gui' / 'guider' / 'setup_scr_*.c'))):
        t = open(f, encoding='utf-8').read()
        texts = {v: c_bytes(s).decode('utf-8', 'replace') for v, s in re.findall(r'lv_label_set_text\(ui->(\w+), "((?:[^"\\]|\\.)*)"\)', t)}
        for var, size in re.findall(r'lv_obj_set_style_text_font\(ui->(\w+), &font_cn_(\d+)', t):
            txt = texts.get(var, '')
            miss = ''.join(dict.fromkeys(c for c in txt if not font(int(size)).has(ord(c))))
            tag = 'OK' if not miss else ('PUSHED' if var in PUSHED else 'MISSING')
            bad += tag == 'MISSING'
            print(f'  {tag:7} {int(size):2}px {var:34} {txt!r}' + (f'  missing {miss}' if miss else ''))
    print('== runtime texts ==')
    for item in a.text:
        size, txt = item.split(':', 1)
        miss = ''.join(dict.fromkeys(c for c in txt if not font(int(size)).has(ord(c))))
        bad += bool(miss)
        print(f'  {"OK" if not miss else "MISSING":7} {size}px {txt!r}' + (f'  missing {miss}' if miss else ''))
    print('== non-ASCII in string literals (all GR user code) ==')
    chars = {}
    for f in glob.glob(str(USER / '**' / '*.c'), recursive=True):
        if 'guider_fonts' in f or 'customer_fonts' in f:
            continue
        t = open(f, encoding='utf-8', errors='ignore').read()
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
        t = re.sub(r'//[^\n]*', '', t)
        for s in re.findall(r'"((?:[^"\\\n]|\\.)*)"', t):
            for c in c_bytes(s).decode('utf-8', errors='ignore'):
                if ord(c) >= 0x80:
                    chars.setdefault(c, set()).add(os.path.basename(f))
    for c in sorted(chars):
        have = ''.join(str(s) for s in (16, 24, 28, 32) if font(s).has(ord(c))) and \
            ' '.join(f'{s}' for s in (16, 24, 28, 32) if font(s).has(ord(c)))
        print(f'  {c}  in {have or "none":12} used by {" ".join(sorted(chars[c]))}')
    print('RESULT', 'FAIL' if bad else 'OK')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(errors='replace')
    raise SystemExit(main())
