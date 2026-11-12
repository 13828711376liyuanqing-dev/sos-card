"""SAM | 2026-10-11 00:45 +08:00 | Reproducible GUI import because
the validated Goodix renderer requires byte-aligned monochrome glyph rows.
Run from the repository root after GUI Guider has finished Ctrl+G.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'LVGL/YP001'
TARGETS = [ROOT / 'ble_app_uart_c',
           ROOT / 'SVN交付_YP001_GR5526_20261001/ble_app_uart_c']
STAMP = 'SAM | 2026-10-11 00:45 +08:00'
NOTE = f'/* {STAMP} | Import YP001 GUI Guider assets because the six-page UI replaces the old runtime page. */\n'


def pad_font(text):
    assert re.search(r'\.bpp\s*=\s*1\b', text)
    assert re.search(r'\.bitmap_format\s*=\s*0\b', text)
    bitmap = re.search(r'(glyph_bitmap\[\]\s*=\s*\{)(.*?)(\n\};)', text, re.S)
    raw = re.sub(r'/\*.*?\*/', '', bitmap[2], flags=re.S)
    old = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', raw))
    pattern = re.compile(r'(\.bitmap_index\s*=\s*)(\d+)(,\s*\.adv_w\s*=\s*\d+,\s*\.box_w\s*=\s*)(\d+)(,\s*\.box_h\s*=\s*)(\d+)')
    data = bytearray()
    offsets = []
    for glyph in pattern.finditer(text):
        offset, width, height = int(glyph[2]), int(glyph[4]), int(glyph[6])
        offsets.append(len(data))
        stride = (width + 7) // 8
        rows = bytearray(stride * height)
        for y in range(height):
            for x in range(width):
                source_bit = y * width + x
                bit = (old[offset + source_bit // 8] >> (7 - source_bit % 8)) & 1
                rows[y * stride + x // 8] |= bit << (7 - x % 8)
        # Verify every source pixel survived the new row stride.
        for y in range(height):
            for x in range(width):
                source_bit = y * width + x
                assert ((old[offset + source_bit // 8] >> (7 - source_bit % 8)) & 1) == ((rows[y * stride + x // 8] >> (7 - x % 8)) & 1)
        data.extend(rows)
    values = '\n' + '\n'.join('    ' + ', '.join(f'0x{b:02x}' for b in data[i:i+16]) + ',' for i in range(0, len(data), 16))
    text = text[:bitmap.start(2)] + values + text[bitmap.end(2):]
    iterator = iter(offsets)
    text = pattern.sub(lambda m: m[1] + str(next(iterator)) + m[3] + m[4] + m[5] + m[6], text)
    return NOTE + f'/* {STAMP} | Pad each glyph row to bytes because lv_draw_sw_letter uses aligned rows; source pixels and metrics are preserved. */\n' + text


def imported_files():
    generated = SOURCE / 'generated'
    screens = sorted(generated.glob('setup_scr_*.c'))
    assert len(screens) == 6, 'Finish GUI Guider code generation first'
    files = {}
    for path in screens + [generated / n for n in ('gui_guider.c', 'gui_guider.h', 'events_init.c', 'events_init.h', 'widgets_init.c', 'widgets_init.h')]:
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'lv_font_simhei_(16|24|28|32|40)\b', r'font_cn_\1', text)
        # The generated Montserrat references are only for empty separator labels.
        text = text.replace('lv_font_montserratMedium_16', 'font_cn_16')
        if path.name == 'setup_scr_screen.c':
            before = 'lv_obj_set_pos(ui->screen_img_1, 42, 88);'
            assert before in text
            text = text.replace(before, f'/* {STAMP} | Move QR up four pixels because 88 + 116 exceeds the 200px display. */\n    lv_obj_set_pos(ui->screen_img_1, 42, 84);')
        files[path.name] = (NOTE + text).encode('utf-8')
    for path in (SOURCE / 'custom').glob('*'):
        if path.suffix in ('.c', '.h'):
            files['custom/' + path.name] = (NOTE + path.read_text(encoding='utf-8')).encode('utf-8')
    for folder, pattern in [('guider_fonts', 'font_cn_*.c'), ('guider_customer_fonts', '*.c')]:
        paths = sorted((generated / folder).glob(pattern))
        assert len(paths) == 5
        for path in paths:
            files[folder + '/' + path.name] = pad_font(path.read_text(encoding='utf-8')).encode('utf-8')
    path = generated / 'guider_customer_fonts/guider_customer_fonts.h'
    files['guider_customer_fonts/' + path.name] = (NOTE + path.read_text(encoding='utf-8')).encode('utf-8')
    images = sorted((generated / 'images').glob('*.c'))
    assert len(images) == 5
    for path in images:
        text = path.read_text(encoding='utf-8')
        assert 'LV_IMG_CF_INDEXED_1BIT' in text
        files['images/' + path.name] = (NOTE + text).encode('utf-8')
    return files


def main():
    files = imported_files()
    # SAM | 2026-10-11 01:19 +08:00 | Refuse independent delivery edits
    # because repeated imports must not silently overwrite divergent copies.
    for name in files:
        copies = [target / 'Src/user/gui/guider' / name for target in TARGETS]
        if any(path.exists() for path in copies):
            assert all(path.exists() for path in copies), f'Missing peer copy: {name}'
            assert copies[0].read_bytes() == copies[1].read_bytes(), f'Independent delivery edit: {name}'
    for target in TARGETS:
        for name, data in files.items():
            dest = target / 'Src/user/gui/guider' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    manifest = {'source': 'LVGL/YP001', 'note': 'Five 1bpp font_cn fonts are linked; customer fonts retained as source assets.',
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    (ROOT / 'doc/YP001_GUI_Guider导入清单_20261011.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Imported {len(files)} files to both projects; verified every converted glyph pixel.')


if __name__ == '__main__':
    main()
