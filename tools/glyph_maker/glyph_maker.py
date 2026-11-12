"""SAM | 2026-11-02 +08:00 | 姓名字形生成器：文字输入 + 描点编辑 -> 平台 JSON / CAT1->GR 串口行 / COM26 实板注入。
无参数运行打开窗口；命令行：
  python glyph_maker.py gen  --name 张秀华 [--room 1#1-102 --campus 泰康之家·燕园 --seq N --out 目录]
  python glyph_maker.py send --name 张秀华 [--port COM26]       经 GR 调试口 busline 注入（需要新 GR 固件）
  python glyph_maker.py check                                  T0 自检：与 font_cn_16/32 逐字节对比
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import glyphlib as G

HERE = Path(__file__).resolve().parent
_PROJECT_OUT = G.PROJECT / 'firmware_releases'
OUT_ROOT = _PROJECT_OUT / 'name_glyphs' if _PROJECT_OUT.is_dir() else HERE / 'output'


def build(name, room, campus, seq, overrides=None):
    glyphs = G.resident_glyphs(name, campus, overrides=overrides)
    msg = G.platform_msg(name, room, campus, seq, glyphs)
    return glyphs, msg, G.bus_lines(msg, txn=int(time.time()) % 100000)


def coverage(name):
    return [(ch, all(G.local_font(s).has(ord(ch)) for s in G.SIZES)) for ch in dict.fromkeys(name) if ord(ch) >= 0x80]


def write_outputs(out, name, glyphs, msg, lines):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'residentNameMsg.json').write_text(json.dumps(msg, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'bus_evt.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'cli_busline.txt').write_text(''.join('busline ' + l[8:] + '\n' for l in lines), encoding='utf-8')
    rep = [f'# 字形生成 {name}', '', f'- 时间 {datetime.now():%Y-%m-%d %H:%M:%S}；渲染 '
           f'{"lv_font_conv（与 font_cn 同源，逐字节一致）" if G.lfc_available() else "Pillow（近似，未与字库校准）"}',
           f'- 字形 {len(glyphs)} 个，平台 JSON {len(json.dumps(msg, ensure_ascii=False).encode())} 字节，'
           f'串口行最长 {max(len(l.encode()) for l in lines)} 字节', '', '| 字 | 码点 | 字号 | 宽×高 | 偏移 | 本地字库 | CRC |', '|---|---|---|---|---|---|---|']
    for g in glyphs:
        rep.append(f'| {chr(g.u)} | U+{g.u:04X} | {g.size} | {g.w}×{g.h} | {g.ofs_x},{g.ofs_y} | '
                   f'{"有" if G.local_font(g.size).has(g.u) else "无"} | {g.crc:04X} |')
    rep += ['', '```'] + [f'U+{g.u:04X} {g.size}px\n{g.art()}\n' for g in glyphs] + ['```']
    (out / 'report.md').write_text('\n'.join(rep), encoding='utf-8')
    try:
        preview(glyphs, name, campus=msg.get('Campus', '')).save(out / 'preview.png')
    except Exception as e:  # preview is informational only
        print('preview skipped:', e)


def preview(glyphs, name, scale=3, campus=''):
    """200x200 simulated screen: name 32px, name 16px, campus 16px (same metrics as the GR labels)."""
    from PIL import Image
    img = Image.new('1', (200, 200), 1)
    by = {(g.u, g.size): g for g in glyphs}
    for size, top, text in ((32, 50, name), (16, 110, name), (16, 160, campus)):
        lf = G.local_font(size)
        x = 10
        for ch in text:
            g = by.get((ord(ch), size)) or (lf.glyph(ord(ch)) if lf.has(ord(ch)) else None)
            if g is None:
                x += size // 2
                continue
            y0 = top + (lf.line_height - lf.base_line) - g.h - g.ofs_y
            for yy, r in enumerate(g.rows):
                for xx, c in enumerate(r):
                    if c and 0 <= x + g.ofs_x + xx < 200 and 0 <= y0 + yy < 200:
                        img.putpixel((x + g.ofs_x + xx, y0 + yy), 0)
            x += (g.adv_w + 8) >> 4
    return img.resize((200 * scale, 200 * scale), Image.NEAREST)


def send_serial(lines, port='COM26', log=print):
    """Inject each line through GR CLI `busline`; returns the GR echo lines."""
    import serial
    echo = []
    with serial.Serial(port, 115200, timeout=0.2) as s:
        s.write(b'\r\n'); time.sleep(0.3); s.read(4096)
        for l in lines:
            s.write(('busline ' + l[8:] + '\r\n').encode('utf-8'))
            buf, t = b'', time.time()
            while time.time() - t < 2.0 and b'[BUSLINE]' not in buf:
                buf += s.read(1024)
            text = buf.decode('utf-8', 'replace')
            got = [x.strip() for x in text.splitlines() if '[BUSLINE]' in x or 'Unknown command' in x]
            echo += got
            log(got[-1] if got else '(无回应) ' + l[:40])
            if any('Unknown command' in x for x in got):
                log('GR 固件里没有 busline 命令：需要先烧新 GR 固件'); break
            time.sleep(0.1)
    return echo


def t0_check(log=print):
    bad = 0
    for s in G.SIZES:
        lf = G.local_font(s)
        us = [u for u in lf.map if u > 0x20]
        got = G.render_lfc(''.join(map(chr, us)), s)
        key = lambda g: (g.w, g.h, g.ofs_x, g.ofs_y, g.adv_w, g.data)  # noqa: E731
        n = sum(key(got[u]) != key(lf.glyph(u)) for u in us)
        bad += n
        log(f'{s}px：本地字库 {len(us)} 个字，生成结果不一致 {n} 个')
    return bad == 0


# ---------------------------------------------------------------- GUI
def gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    root = tk.Tk()
    root.title('YP001 姓名字形生成器（文字输入 + 描点）')
    state = {'glyphs': [], 'msg': None, 'lines': [], 'overrides': {}}
    nb = ttk.Notebook(root); nb.pack(fill='both', expand=True)

    # ---- tab 1: text
    t1 = ttk.Frame(nb, padding=8); nb.add(t1, text='文字输入')
    v_name, v_room, v_campus = tk.StringVar(value='张秀华'), tk.StringVar(value='1#1-102'), tk.StringVar(value='泰康之家·燕园')
    v_seq, v_port = tk.StringVar(value=str(int(time.time()))), tk.StringVar(value='COM26')
    for i, (lab, var, w) in enumerate((('姓名', v_name, 16), ('房号', v_room, 16), ('园区', v_campus, 24), ('Seq', v_seq, 14))):
        ttk.Label(t1, text=lab).grid(row=0, column=2 * i, sticky='e')
        ttk.Entry(t1, textvariable=var, width=w).grid(row=0, column=2 * i + 1, sticky='w', padx=4)
    cov = ttk.Label(t1, text='', foreground='#555'); cov.grid(row=1, column=0, columnspan=8, sticky='w', pady=4)
    canvas = tk.Canvas(t1, width=600, height=600, bg='white'); canvas.grid(row=2, column=0, columnspan=5, rowspan=6)
    logbox = tk.Text(t1, width=52, height=30); logbox.grid(row=2, column=5, columnspan=3, rowspan=6, sticky='n')

    def log(msg):
        logbox.insert('end', msg + '\n'); logbox.see('end'); root.update()

    img_ref = {}

    def generate():
        name = v_name.get().strip()
        try:
            G.check_name(name)
            state['glyphs'], state['msg'], state['lines'] = build(name, v_room.get(), v_campus.get(), int(v_seq.get()),
                                                                  state['overrides'])
        except Exception as e:
            messagebox.showerror('生成失败', str(e)); return
        cov.config(text='本地字库：' + '  '.join(f'{c} {"有" if ok else "无（靠推送）"}' for c, ok in coverage(name)) +
                   f'    字形 {len(state["glyphs"])} 个；手绘 {len(state["overrides"])} 个')
        from PIL import ImageTk
        img_ref['p'] = ImageTk.PhotoImage(preview(state['glyphs'], name, campus=v_campus.get()).convert('RGB'))
        canvas.delete('all'); canvas.create_image(0, 0, anchor='nw', image=img_ref['p'])
        log(f'生成 {name}：{len(state["lines"])} 行，最长 {max(len(l.encode()) for l in state["lines"])} 字节')
        refresh_pick()

    def save():
        if not state['msg']:
            generate()
        out = OUT_ROOT / f'{datetime.now():%Y%m%d_%H%M%S}_{v_name.get().strip()}'
        write_outputs(out, v_name.get().strip(), state['glyphs'], state['msg'], state['lines'])
        log(f'已保存：{out}')

    def send():
        if not state['lines']:
            generate()
        try:
            send_serial(state['lines'], v_port.get(), log)
        except Exception as e:
            log(f'串口失败：{e}（COM 口是否被 Luatools/串口助手占用？）')

    bar = ttk.Frame(t1); bar.grid(row=8, column=0, columnspan=8, sticky='w', pady=6)
    ttk.Button(bar, text='生成预览', command=generate).pack(side='left')
    ttk.Button(bar, text='保存 JSON/串口行/报告', command=save).pack(side='left', padx=4)
    ttk.Label(bar, text='  GR 调试口').pack(side='left')
    ttk.Entry(bar, textvariable=v_port, width=8).pack(side='left')
    ttk.Button(bar, text='发到 GR（busline）', command=send).pack(side='left', padx=4)
    ttk.Button(bar, text='T0 自检', command=lambda: log('T0 通过' if t0_check(log) else 'T0 有差异')).pack(side='left')

    # ---- tab 2: dot editor
    t2 = ttk.Frame(nb, padding=8); nb.add(t2, text='描点编辑')
    v_pick, v_size = tk.StringVar(), tk.IntVar(value=32)
    ttk.Label(t2, text='字').grid(row=0, column=0)
    pick = ttk.Combobox(t2, textvariable=v_pick, width=6, state='readonly'); pick.grid(row=0, column=1)
    ttk.Radiobutton(t2, text='32px', variable=v_size, value=32, command=lambda: load_edit()).grid(row=0, column=2)
    ttk.Radiobutton(t2, text='16px', variable=v_size, value=16, command=lambda: load_edit()).grid(row=0, column=3)
    info = ttk.Label(t2, text=''); info.grid(row=0, column=4, columnspan=4, sticky='w')
    CELL = 14
    grid_c = tk.Canvas(t2, width=40 * CELL + 1, height=40 * CELL + 1, bg='white'); grid_c.grid(row=1, column=0, columnspan=8)
    ed = {'w': 32, 'h': 33, 'px': [], 'base': 28, 'adv': 512}

    def refresh_pick():
        chars = [c for c in dict.fromkeys(v_name.get()) if ord(c) >= 0x80]
        pick['values'] = chars
        if chars and v_pick.get() not in chars:
            v_pick.set(chars[0])
        load_edit()

    def load_edit():
        if not v_pick.get():
            return
        u, s = ord(v_pick.get()), v_size.get()
        lf = G.local_font(s)
        W, H, base = s, lf.line_height, lf.line_height - lf.base_line   # editing box = one LVGL line, pen at x=0
        g = state['overrides'].get((u, s)) or next((x for x in state['glyphs'] if x.u == u and x.size == s), None)
        px = [[0] * W for _ in range(H)]
        if g:
            for yy, r in enumerate(g.rows):
                for xx, c in enumerate(r):
                    X, Y = g.ofs_x + xx, base - g.ofs_y - g.h + yy
                    if c and 0 <= X < W and 0 <= Y < H:
                        px[Y][X] = 1
        ed.update(w=W, h=H, px=px, base=base, adv=g.adv_w if g else s * 16)
        info.config(text=f'U+{u:04X} {s}px  编辑框 {W}×{H}，基线在第 {base} 行（红线）  左键画 / 右键擦 / 可拖动')
        draw()

    def draw():
        grid_c.delete('all')
        for y in range(ed['h']):
            for x in range(ed['w']):
                grid_c.create_rectangle(x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL,
                                        fill='black' if ed['px'][y][x] else 'white', outline='#ddd')
        grid_c.create_line(0, ed['base'] * CELL, ed['w'] * CELL, ed['base'] * CELL, fill='red', width=2)

    def paint(e, v):
        x, y = e.x // CELL, e.y // CELL
        if 0 <= x < ed['w'] and 0 <= y < ed['h'] and ed['px'][y][x] != v:
            ed['px'][y][x] = v
            grid_c.create_rectangle(x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL,
                                    fill='black' if v else 'white', outline='#ddd')
    for ev, v in (('<Button-1>', 1), ('<B1-Motion>', 1), ('<Button-3>', 0), ('<B3-Motion>', 0)):
        grid_c.bind(ev, lambda e, v=v: paint(e, v))

    def edited_glyph():
        u, s = ord(v_pick.get()), v_size.get()
        full = G.Glyph(u, s, ed['px'], 0, ed['base'] - ed['h'], ed['adv'])
        return full.trimmed()

    def apply_edit():
        if not v_pick.get():
            return
        g = edited_glyph()
        if not g.rows:
            messagebox.showwarning('空字形', '没有画任何点'); return
        state['overrides'][(g.u, g.size)] = g
        log(f'描点字形已采用：U+{g.u:04X} {g.size}px {g.w}×{g.h}'); generate(); nb.select(0)

    def shift(dx, dy):
        W, H = ed['w'], ed['h']
        ed['px'] = [[ed['px'][y - dy][x - dx] if 0 <= y - dy < H and 0 <= x - dx < W else 0 for x in range(W)] for y in range(H)]
        draw()

    def save_glyph():
        g = edited_glyph()
        p = filedialog.asksaveasfilename(defaultextension='.glyph.json', initialfile=f'U{g.u:04X}_{g.size}.glyph.json')
        if p:
            Path(p).write_text(json.dumps(g.to_json(), indent=1), encoding='utf-8')

    def load_glyph():
        p = filedialog.askopenfilename(filetypes=[('字形', '*.glyph.json')])
        if p:
            g = G.Glyph.from_json(json.loads(Path(p).read_text(encoding='utf-8')))
            state['overrides'][(g.u, g.size)] = g
            if chr(g.u) not in v_name.get():
                v_name.set(v_name.get() + chr(g.u))
            refresh_pick(); v_pick.set(chr(g.u)); v_size.set(g.size); load_edit()

    b2 = ttk.Frame(t2); b2.grid(row=2, column=0, columnspan=8, pady=6, sticky='w')
    for txt, fn in (('清空', lambda: (ed.update(px=[[0] * ed['w'] for _ in range(ed['h'])]), draw())),
                    ('←', lambda: shift(-1, 0)), ('→', lambda: shift(1, 0)), ('↑', lambda: shift(0, -1)), ('↓', lambda: shift(0, 1)),
                    ('重新载入文字结果', lambda: (state['overrides'].pop((ord(v_pick.get()), v_size.get()), None), generate(), load_edit())),
                    ('采用这个字形', apply_edit), ('保存字形文件', save_glyph), ('载入字形文件', load_glyph)):
        ttk.Button(b2, text=txt, command=fn).pack(side='left', padx=2)

    generate()
    root.mainloop()


def main():
    if len(sys.argv) == 1:
        return gui()
    # SAM | 2026-11-03 +08:00 | A GBK console cannot print Ext-A/B characters (䶮, 𠮷): replace them instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['gen', 'send', 'check'])
    ap.add_argument('--name', default='张秀华'); ap.add_argument('--room', default='1#1-102')
    ap.add_argument('--campus', default='泰康之家·燕园'); ap.add_argument('--seq', type=int, default=int(time.time()))
    ap.add_argument('--out'); ap.add_argument('--port', default='COM26')
    a = ap.parse_args()
    if a.cmd == 'check':
        return 0 if t0_check() else 1
    glyphs, msg, lines = build(a.name, a.room, a.campus, a.seq)
    print('本地字库：' + '  '.join(f'{c}:{"有" if ok else "无"}' for c, ok in coverage(a.name)))
    if a.cmd == 'gen':
        out = Path(a.out) if a.out else OUT_ROOT / f'{datetime.now():%Y%m%d_%H%M%S}_{a.name}'
        write_outputs(out, a.name, glyphs, msg, lines)
        print('输出：', out)
    else:
        send_serial(lines, a.port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
