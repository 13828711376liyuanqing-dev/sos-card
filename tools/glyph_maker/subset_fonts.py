"""SAM | 2026-11-03 +08:00 | Shrink the GR fixed fonts (font_cn_24/28/32.c) to the characters each size really shows.

Font plan phase 1 (doc/2026-11-02_字体整体规划方案.md): the name is pushed by the platform and kept on the device, so the
32px font needs no CJK; 28px only shows the room, 24px only fixed UI text. Kept glyphs are copied byte for byte from the
full 2026-10-11 export in fonts/full_20261011 (no re-rendering), so they draw exactly as before. 16px and 40px are left alone.

Usage:  python subset_fonts.py [--check]      (--check: report only, write nothing)
Writes ble_app_uart_c/.../guider_fonts/font_cn_{24,28,32}.c and the same files into tools/glyph_maker/fonts/ (the snapshot
the name-glyph tools read when the dev pack runs outside the project).
"""
import re
import sys
from pathlib import Path

import glyphlib as G

FONT_DIR = Path(__file__).resolve().parents[2] / 'ble_app_uart_c' / 'Src' / 'user' / 'gui' / 'guider' / 'guider_fonts'
# Always subset from the full export (95 ASCII + 185 CJK per size), never from an already slim file, so putting back a
# character the full set has is only a KEEP edit.
SOURCE_DIR = Path(__file__).resolve().parent / 'fonts' / 'full_20261011'
SNAPSHOT_DIR = Path(__file__).resolve().parent / 'fonts'
ASCII = [chr(c) for c in range(0x20, 0x7F)]
# Non-ASCII characters to keep per size (characters the full source does not have are reported and skipped).
KEEP = {
    32: '',                                                   # main page name only: CJK comes from pushed glyphs
    28: '号楼栋幢单元层室区座',                                  # main page room
    24: '当前电量低请及时充电正在呼叫通话结束' '星期一二三四五六日',   # lowbat, calling, call end; time page default
}


def build(size):
    path = FONT_DIR / f'font_cn_{size}.c'
    src = SOURCE_DIR / f'font_cn_{size}.c'
    text = src.read_text(encoding='utf-8')
    old = G.LocalFont(size, src)
    assert old.aligned, f'{path.name}: expected byte-aligned rows'
    keep_cjk = sorted({ord(c) for c in KEEP[size]})
    missing = [chr(u) for u in keep_cjk if u not in old.map]
    keep_cjk = [u for u in keep_cjk if u in old.map]
    order = [ord(c) for c in ASCII] + keep_cjk
    assert all(u in old.map for u in order[:95]), 'ASCII must be complete'

    bitmap, dsc = bytearray(), ['    {.bitmap_index = 0, .adv_w = 0, .box_w = 0, .box_h = 0, .ofs_x = 0, .ofs_y = 0} /* id = 0 reserved */']
    for u in order:
        bi, adv, w, h, ox, oy = old.dsc[old.map[u]]
        n = (w + 7) // 8 * h
        dsc.append(f'    {{.bitmap_index = {len(bitmap)}, .adv_w = {adv}, .box_w = {w}, .box_h = {h}, .ofs_x = {ox}, .ofs_y = {oy}}}')
        bitmap += old.bitmap[bi:bi + n]

    rows = [', '.join(f'0x{b:02x}' for b in bitmap[i:i + 16]) for i in range(0, len(bitmap), 16)]
    new_bitmap = 'glyph_bitmap[] = {\n    ' + ',\n    '.join(rows) + '\n};'
    new_dsc = 'glyph_dsc[] = {\n' + ',\n'.join(dsc) + '\n};'
    cmaps = ['''    {
        .range_start = 32, .range_length = 95, .glyph_id_start = 1,
        .unicode_list = NULL, .glyph_id_ofs_list = NULL, .list_length = 0, .type = LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY
    }''']
    ulist = ''
    if keep_cjk:
        first = keep_cjk[0]
        offs = [u - first for u in keep_cjk]
        ulist = ('static const uint16_t unicode_list_1[] = {\n    ' +
                 ',\n    '.join(', '.join(f'0x{o:x}' for o in offs[i:i + 8]) for i in range(0, len(offs), 8)) + '\n};\n\n')
        cmaps.append(f'''    {{
        .range_start = {first}, .range_length = {keep_cjk[-1] - first + 1}, .glyph_id_start = 96,
        .unicode_list = unicode_list_1, .glyph_id_ofs_list = NULL, .list_length = {len(keep_cjk)}, .type = LV_FONT_FMT_TXT_CMAP_SPARSE_TINY
    }}''')

    t = text
    t, n1 = re.subn(r'glyph_bitmap\[\] = \{.*?\n\};', lambda m: new_bitmap, t, count=1, flags=re.S)
    t, n2 = re.subn(r'glyph_dsc\[\] = \{.*?\n\};', lambda m: new_dsc, t, count=1, flags=re.S)
    t, n3 = re.subn(r'static const uint16_t unicode_list_1\[\] = \{.*?\n\};\n\n', lambda m: ulist, t, count=1, flags=re.S)
    t, n4 = re.subn(r'(static const lv_font_fmt_txt_cmap_t cmaps\[\] =\n\{\n).*?(\n\};)',
                    lambda m: m.group(1) + ',\n'.join(cmaps) + m.group(2), t, count=1, flags=re.S)
    t, n5 = re.subn(r'\.cmap_num = \d+,', f'.cmap_num = {len(cmaps)},', t, count=1)
    assert (n1, n2, n3, n4, n5) == (1, 1, 1, 1, 1), (path.name, n1, n2, n3, n4, n5)
    note = (f'/* SAM | 2026-11-03 +08:00 | Font plan phase 1: kept ASCII + {len(keep_cjk)} CJK ({"".join(map(chr, keep_cjk)) or "none"}); '
            f'glyphs copied byte for byte from the 185-CJK version (backup D:\\CODEX\\_archive\\fonts_before_subset_20261103). '
            f'Regenerate with tools/glyph_maker/subset_fonts.py. */\n')
    if 'Font plan phase 1' not in t:
        t = note + t
    else:
        t = re.sub(r'/\* SAM \| 2026-11-03 \+08:00 \| Font plan phase 1:.*?\*/\n', lambda m: note, t, count=1)
    return path, text, t, old, order, missing, len(old.bitmap), len(bitmap)


def verify(path, size, old, order, new_text):
    tmp = path.with_suffix('.check.c')
    tmp.write_text(new_text, encoding='utf-8')
    try:
        new = G.LocalFont(size, tmp)
    finally:
        tmp.unlink()
    assert sorted(new.map) == sorted(order), 'character set'
    assert (new.line_height, new.base_line) == (old.line_height, old.base_line)
    for u in order:
        a, b = old.glyph(u), new.glyph(u)
        assert (a.rows, a.ofs_x, a.ofs_y, a.adv_w) == (b.rows, b.ofs_x, b.ofs_y, b.adv_w), f'U+{u:04X}'


def main():
    check = '--check' in sys.argv
    for size in (32, 28, 24):
        path, text, new_text, old, order, missing, b0, b1 = build(size)
        verify(path, size, old, order, new_text)
        print(f'font_cn_{size}: {len(old.map)} -> {len(order)} glyphs, bitmap {b0} -> {b1} B (-{b0 - b1}); '
              f'kept {"".join(chr(u) for u in order[95:]) or "-"}; not in font: {"".join(missing) or "-"}; glyphs identical; '
              f'{"same as" if path.read_text(encoding="utf-8") == new_text else "CHANGES"} the current file')
        if not check:
            path.write_bytes(new_text.encode('utf-8'))
            (SNAPSHOT_DIR / path.name).write_bytes(new_text.encode('utf-8'))
    print('checked only' if check else 'written')


if __name__ == '__main__':
    sys.stdout.reconfigure(errors='replace')
    main()
