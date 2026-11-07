"""SAM | 2026-10-20 19:39 +08:00 | Verify clock-font subsetting against immutable pre-change glyph bytes and metrics."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / 'logs/ota_preflight_20261020/clock_font_before'
PATHS = [
    'ble_app_uart_c/Src/user/gui/guider/guider_fonts/font_cn_40.c',
    'SVN交付_YP001_GR5526_20261001/ble_app_uart_c/Src/user/gui/guider/guider_fonts/font_cn_40.c',
    'LVGL/YP001/generated/guider_fonts/font_cn_40.c',
]

def array(text, name):
    return re.search(r'\b' + name + r'\[\]\s*=\s*\{(.*?)\n\};', text, re.S).group(1)

def bitmap(text):
    body = re.sub(r'/\*.*?\*/', '', array(text, 'glyph_bitmap'), flags=re.S)
    return bytes(int(x, 0) for x in re.findall(r'0x[0-9a-fA-F]+|\b\d+\b', body))

def glyphs(text):
    return [tuple(map(int, re.findall(r'=\s*(-?\d+)', x)))
            for x in re.findall(r'\{[^{}]+\}', array(text, 'glyph_dsc'))]

if __name__ == '__main__':
    for index, rel in enumerate(PATHS):
        before = (BACKUP / f'{index}.c').read_text(encoding='utf-8-sig')
        after = (ROOT / rel).read_text(encoding='utf-8-sig')
        old, new = glyphs(before), glyphs(after)
        assert len(new) == 96, f'{rel}: expected reserved glyph plus 95 ASCII glyphs'
        assert new == old[:96], f'{rel}: ASCII glyph metrics changed'
        assert bitmap(after) == bitmap(before)[:old[96][0]], f'{rel}: ASCII bitmap changed'
        assert '.cmap_num = 1,' in after and 'unicode_list_1' not in after
        assert '.range_start = 32, .range_length = 95, .glyph_id_start = 1,' in after
        for field in ('line_height', 'base_line', 'subpx', 'underline_position', 'underline_thickness', 'fallback', 'bpp', 'bitmap_format'):
            pattern = r'\.' + field + r'\s*=\s*([^,\n]+)'
            assert re.findall(pattern, before) == re.findall(pattern, after), (rel, field)
        for ch in '0123456789:-':
            assert 32 <= ord(ch) <= 126
        print(f'PASS {rel}: 95 ASCII glyphs byte-identical; clock metrics retained')
    assert (ROOT / PATHS[0]).read_bytes() == (ROOT / PATHS[1]).read_bytes()
    print('PASS main/delivery font sources identical')
