"""SAM | 2026-11-04 +08:00 | Check a platform-generated residentNameMsg JSON before it is pushed to devices: the confirmed
framework (Name / Room / Campus all from the platform; every non-ASCII character pushed, nothing kept at the factory), field ranges, each glyph's
bitmap length and CRC (the GR rules), NVDS store size, and Seq. Optional --seq-min: the last Seq the device accepted.
Usage: python check_platform_json.py <residentNameMsg_*.json> [--seq-min N] [--compare-ours]
Exit 0 = acceptable (warnings allowed), 1 = the device would refuse it or it breaks the framework."""
import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import glyphlib as gl  # noqa: E402

HEAD_FIELDS = ('MsgType', 'Seq', 'Name', 'Room', 'Campus', 'FontId', 'FontVer', 'Glyphs')


def cjk(s):
    return [c for c in s if ord(c) >= 0x80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('json', type=Path)
    ap.add_argument('--seq-min', type=int, help='Seq the device last accepted; the new one must be larger')
    ap.add_argument('--compare-ours', action='store_true', help='also generate with glyph_maker and compare bitmaps')
    a = ap.parse_args()
    errs, warns, oks = [], [], []
    raw = a.json.read_bytes()
    try:
        m = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as e:
        print('ERROR 不是 UTF-8 JSON：', e); return 1

    # 1. top level
    missing = [k for k in HEAD_FIELDS if k not in m]
    if missing: errs.append('缺字段 ' + ','.join(missing))
    extra = [k for k in m if k not in HEAD_FIELDS]
    if extra: warns.append('多余字段（设备忽略）' + ','.join(extra))
    if m.get('MsgType') != 'residentNameMsg': errs.append('MsgType 必须是 residentNameMsg')
    name, room, campus = m.get('Name', ''), m.get('Room', ''), m.get('Campus', '')
    if not isinstance(name, str) or not name or len(name.encode('utf-8')) > 63: errs.append('Name 为空或超过 63 字节')
    if len(cjk(name)) > gl.SHOWN_NAME_CHARS: errs.append(f'Name 非英文字 {len(cjk(name))} 个 > {gl.SHOWN_NAME_CHARS}（工具应截断）')
    if len(set(cjk(campus))) > gl.MAX_CAMPUS_CHARS: errs.append(f'Campus 非英文字 > {gl.MAX_CAMPUS_CHARS}')
    # SAM | 2026-11-04 +08:00 | Room is drawn with the built-in 28px font only (ASCII + 号楼栋单元层室); pushes cover 16/32px, not 28px.
    room_missing = [c for c in dict.fromkeys(cjk(room)) if not gl._local_has(ord(c), 28)]
    if room_missing: errs.append('Room 里有设备 28px 字库没有的字（屏幕显示 --，推送也补不了）：' + '、'.join(room_missing))
    elif cjk(room): oks.append('Room 的字都在设备 28px 字库里')
    seq = m.get('Seq')
    if not isinstance(seq, int) or seq <= 0 or seq > 0xFFFFFFFF: errs.append('Seq 必须是正整数（32 位内）')
    else:
        oks.append(f'Seq {seq}（{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seq))}）')
        if a.seq_min is not None and seq <= a.seq_min:
            errs.append(f'Seq {seq} 不大于设备上一次的 {a.seq_min}：设备会当成旧消息拒收（stale）')
        if seq < 1767225600:     # 2026-01-01; SAM | 2026-11-04 +08:00 | an error now, same rule as the generator
            errs.append(f'Seq {seq} 是 {time.strftime("%Y-%m-%d", time.localtime(seq))} 的时间，比本项目设备上已有的 2026 年 Seq 小，'
                         '收过新 Seq 的设备会拒收；后台应取当前时间（秒）')

    # 2. glyphs: format and CRC (same rules as GR yp_name_glyphs.c)
    glyphs = m.get('Glyphs') if isinstance(m.get('Glyphs'), list) else []
    if len(glyphs) > gl.MAX_GLYPHS: errs.append(f'字形 {len(glyphs)} 个 > {gl.MAX_GLYPHS}')
    seen, store, bad = set(), 20, 0     # GR record header is 20 B (yp_name_glyphs.c, 2026-11-04)
    for i, g in enumerate(glyphs):
        tag = f'#{i} {g.get("U")}/{g.get("S")}'
        try:
            u = int(g['U'], 16); s = int(g['S']); w, h, x, y, adv = (int(g[k]) for k in 'WHXYA')
            data = base64.b64decode(g['D'], validate=True); crc = g['C']
        except (KeyError, ValueError, TypeError) as e:
            errs.append(f'{tag} 字段缺失或格式错：{e}'); bad += 1; continue
        if not re.fullmatch(r'[0-9A-F]{4}', crc): errs.append(f'{tag} C 必须是 4 位大写十六进制')
        if s not in gl.SIZES: errs.append(f'{tag} S 只能是 16 或 32')
        if not (1 <= w <= 40 and 1 <= h <= 40): errs.append(f'{tag} W/H 超出 1..40')
        if adv != s * 16: warns.append(f'{tag} A={adv}，汉字应为 {s * 16}')
        if len(data) != ((w + 7) // 8) * h: errs.append(f'{tag} 点阵 {len(data)} 字节 ≠ ⌈W/8⌉×H = {((w + 7) // 8) * h}')
        if len(data) > gl.MAX_GLYPH_BYTES: errs.append(f'{tag} 点阵 {len(data)} 字节 > {gl.MAX_GLYPH_BYTES}')
        head = u.to_bytes(3, 'big') + bytes([s, w, h, x & 255, y & 255]) + adv.to_bytes(2, 'big')
        if '%04X' % gl.crc16(head + data) != crc: errs.append(f'{tag} CRC 不对（应为 {gl.crc16(head + data):04X}）'); bad += 1
        if (u, s) in seen: errs.append(f'{tag} 重复')
        seen.add((u, s)); store += 16 + len(data)
    if not bad: oks.append(f'{len(glyphs)} 个字形格式、点阵长度、CRC 全部正确')

    # 3. framework (user, 2026-11-04): Name / Room / Campus come only from the platform, the device keeps none of them at the
    # factory (storage space only). So every non-ASCII character of the shown name needs 32px + 16px and every campus one 16px,
    # whatever the built-in fonts hold.
    shown = gl.shown_name(name) if name else ''
    need = {(ord(c), s) for c in dict.fromkeys(cjk(shown)) for s in gl.SIZES}
    need |= {(ord(c), 16) for c in dict.fromkeys(cjk(campus))}
    lack = sorted(need - seen); other = sorted(seen - need)
    fmt = lambda ks: '、'.join(f'{chr(u)}{s}px' for u, s in ks)
    if lack: errs.append('缺少字形（设备出厂不留字库，会显示方框）：' + fmt(lack))
    if other: warns.append('推了 Name/Campus 里没有的字：' + fmt(other))
    if not lack: oks.append(f'Name/Campus 需要的 {len(need)} 个字形都有（姓名 32+16px，园区 16px）')
    if store > gl.MAX_STORE_BYTES: errs.append(f'存储 {store} 字节 > {gl.MAX_STORE_BYTES}：当前 GR 存放空间放不下，整批拒收（要加大设备存放空间）')
    else: oks.append(f'存储 {store} 字节 ≤ {gl.MAX_STORE_BYTES}（20 + 每字 16 + 点阵）')

    # 4. optional: our generator for the same input (same renderer as the board fonts)
    if a.compare_ours and not errs:
        ours = gl.resident_glyphs(name, campus)
        mine = {(g.u, g.size): g.to_json() for g in ours}
        same = sum(1 for g in glyphs if (int(g['U'], 16), g['S']) in mine and all(mine[(int(g['U'], 16), g['S'])][k] == g[k] for k in 'WHXYDC'))
        oks.append(f'与本地生成工具对比：{same}/{len(glyphs)} 个字形逐字节相同（不同说明渲染方式不同，不算错）')

    for t in oks: print('  OK    ' + t)
    for t in warns: print('  WARN  ' + t)
    for t in errs: print('  ERROR ' + t)
    print('结论：' + ('设备会拒收或不符合框架' if errs else '可以下发' + ('（有提醒）' if warns else '')))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
