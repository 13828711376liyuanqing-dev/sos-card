# SAM | 2026-11-02 +08:00 | Glyph core for platform-pushed resident names: render/edit 1bpp glyphs in the exact
# lv_font_fmt_txt layout used by font_cn_16/32 (rows padded to whole bytes, MSB first), and build the
# platform JSON and the CAT1->GR BUS_EVT lines. Same code is meant to be reusable as the platform generator.
import base64
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
_PROJECT_FONTS = PROJECT / 'ble_app_uart_c' / 'Src' / 'user' / 'gui' / 'guider' / 'guider_fonts'   # font_cn_*.c compiled into GR
# Inside the YP001 project use the live GR fonts; a standalone copy of this folder uses its fonts/ snapshot.
FONT_DIR = _PROJECT_FONTS if _PROJECT_FONTS.is_dir() else HERE / 'fonts'
DEFAULT_TTF = Path('C:/Windows/Fonts/simhei.ttf')
SIZES = (16, 32)
MAX_GLYPH_BYTES = 200          # 40x40 1bpp = 200; GR rejects larger
MAX_NAME_CHARS = 8
LINE_LIMIT = 400               # GR BUS_EVT parse buffer is 512 incl. prefix


# ---------- bit packing (lv_font_conv --bpp 1 --no-compress) ----------
def pack(rows):
    """rows: list of lists/strings of 0/1, all the same width. Each row padded to a whole byte, MSB first."""
    out = bytearray()
    for r in rows:
        bits = [1 if c in (1, '1', '#') else 0 for c in r]
        for i in range(0, len(bits), 8):
            chunk = bits[i:i + 8] + [0] * (8 - len(bits[i:i + 8]))
            out.append(int(''.join(map(str, chunk)), 2))
    return bytes(out)


def unpack(data, w, h):
    stride = (w + 7) // 8
    if len(data) != stride * h:
        raise ValueError(f'glyph data {len(data)} B != {stride}x{h}')
    rows = []
    for y in range(h):
        bits = ''.join(f'{b:08b}' for b in data[y * stride:(y + 1) * stride])
        rows.append([int(c) for c in bits[:w]])
    return rows


def crc16(data, crc=0xFFFF):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF): same routine is implemented on GR and CAT1."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class Glyph:
    def __init__(self, u, size, rows, ofs_x, ofs_y, adv_w):
        self.u, self.size = u, size
        self.rows = [list(r) for r in rows]
        self.ofs_x, self.ofs_y, self.adv_w = ofs_x, ofs_y, adv_w

    w = property(lambda s: len(s.rows[0]) if s.rows else 0)
    h = property(lambda s: len(s.rows))

    @property
    def data(self):
        return pack(self.rows) if self.rows else b''

    @property
    def crc(self):
        # CRC covers the header fields too so a mismatched header cannot reuse valid pixels.
        hdr = bytes([self.u >> 16 & 0xFF, self.u >> 8 & 0xFF, self.u & 0xFF, self.size, self.w, self.h,
                     self.ofs_x & 0xFF, self.ofs_y & 0xFF, self.adv_w >> 8 & 0xFF, self.adv_w & 0xFF])
        return crc16(hdr + self.data)

    def trimmed(self):
        """Crop empty border rows/cols, adjusting offsets (LVGL draws box at ofs_x / ofs_y)."""
        rows = self.rows
        if not any(any(r) for r in rows):
            return Glyph(self.u, self.size, [], 0, 0, self.adv_w)
        top = next(i for i, r in enumerate(rows) if any(r))
        bot = max(i for i, r in enumerate(rows) if any(r))
        left = min(r.index(1) for r in rows if any(r))
        right = max(len(r) - 1 - r[::-1].index(1) for r in rows if any(r))
        nr = [r[left:right + 1] for r in rows[top:bot + 1]]
        return Glyph(self.u, self.size, nr, self.ofs_x + left, self.ofs_y + (len(rows) - 1 - bot), self.adv_w)

    def to_json(self):
        return {'U': f'{self.u:04X}', 'S': self.size, 'W': self.w, 'H': self.h, 'X': self.ofs_x, 'Y': self.ofs_y,
                'A': self.adv_w, 'D': base64.b64encode(self.data).decode(), 'C': f'{self.crc:04X}'}

    @staticmethod
    def from_json(j):
        u, w, h = int(j['U'], 16), int(j['W']), int(j['H'])
        data = base64.b64decode(j['D'])
        g = Glyph(u, int(j['S']), unpack(data, w, h) if w and h else [], int(j['X']), int(j['Y']), int(j['A']))
        if 'C' in j and int(j['C'], 16) != g.crc:
            raise ValueError(f'CRC mismatch U+{u:04X}')
        return g

    def art(self):
        return '\n'.join(''.join('#' if c else '.' for c in r) for r in self.rows)


# ---------- the project's own LVGL fonts (for coverage check and T0 comparison) ----------
class LocalFont:
    def __init__(self, size, path=None):
        p = Path(path) if path else FONT_DIR / f'font_cn_{size}.c'
        t = p.read_text(encoding='utf-8', errors='replace')
        self.size = size
        self.line_height = int(re.search(r'\.line_height = (\d+)', t).group(1))
        self.base_line = int(re.search(r'\.base_line = (-?\d+)', t).group(1))
        self.bpp = int(re.search(r'\.bpp = (\d+)', t).group(1))
        raw = re.sub(r'/\*.*?\*/', '', re.search(r'glyph_bitmap\[\] = \{(.*?)\n\};', t, re.S).group(1), flags=re.S)
        self.bitmap = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{1,2})(?![0-9a-fA-F])', raw))
        self.dsc = [tuple(map(int, g)) for g in re.findall(
            r'\{\.bitmap_index = (\d+), \.adv_w = (\d+), \.box_w = (\d+), \.box_h = (\d+), '
            r'\.ofs_x = (-?\d+), \.ofs_y = (-?\d+)\}', t)]
        self.map = {}
        lists = {m.group(1): [int(x, 16) for x in re.findall(r'0x[0-9a-fA-F]+', m.group(2))]
                 for m in re.finditer(r'unicode_list_(\d+)\[\] = \{(.*?)\}', t, re.S)}
        for m in re.finditer(r'\.range_start = (\d+), \.range_length = (\d+), \.glyph_id_start = (\d+),\s*'
                             r'\.unicode_list = (\w+)', t):
            start, length, gid0, ul = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if ul == 'NULL':
                for i in range(length):
                    self.map[start + i] = gid0 + i
            else:
                for i, off in enumerate(lists[ul.split('_')[-1]]):
                    self.map[start + off] = gid0 + i

        # lv_font_conv emits a continuous bit stream; the project's fonts were re-packed to byte-aligned rows.
        seq = [d for d in self.dsc[1:] if d[2] and d[3]]
        self.aligned = all(b[0] - a[0] == (a[2] + 7) // 8 * a[3] for a, b in zip(seq, seq[1:]))
        if len(seq) == 1:
            # SAM | 2026-11-03 +08:00 | One glyph has no neighbour to compare (e.g. only 龑 missing): use the bytes it occupies.
            a = seq[0]
            self.aligned = len(self.bitmap) - a[0] == (a[2] + 7) // 8 * a[3]

    def has(self, u):
        return u in self.map

    def glyph(self, u):
        bi, adv, w, h, ox, oy = self.dsc[self.map[u]]
        if self.aligned:
            data = self.bitmap[bi:bi + (w + 7) // 8 * h]
            rows = unpack(data, w, h) if w and h else []
        else:
            bits = ''.join(f'{b:08b}' for b in self.bitmap[bi:bi + (w * h + 7) // 8])
            rows = [[int(c) for c in bits[y * w:(y + 1) * w]] for y in range(h)]
        return Glyph(u, self.size, rows, ox, oy, adv)


_local = {}


def local_font(size):
    if size not in _local:
        _local[size] = LocalFont(size)
    return _local[size]


# ---------- rendering from a TTF ----------
LFC = HERE / 'fontconv' / 'node_modules' / '.bin' / 'lv_font_conv.cmd'


def lfc_available():
    return LFC.exists()


# Fonts tried for characters the main font lacks (CJK Ext-B and beyond), same idea as the web tool.
FALLBACK_TTFS = [Path('C:/Windows/Fonts/simsunb.ttf'), Path('C:/Windows/Fonts/mingliub.ttc')]


def _lfc_once(cps, size, ttf):
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / 'g.c'
        cmd = [str(LFC), '--font', str(ttf), '--size', str(size), '--bpp', '1', '--format', 'lvgl', '--no-compress',
               '--range', ','.join(hex(u) for u in cps), '--lv-include', 'lvgl.h', '-o', str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, shell=False)
        if r.returncode != 0 or not out.exists():
            if "doesn't have any characters" in (r.stderr + r.stdout):
                return {}                       # none of these characters is in this font
            raise RuntimeError('lv_font_conv failed: ' + (r.stderr or r.stdout)[-300:])
        f = LocalFont(size, out)
        return {u: f.glyph(u) for u in cps if f.has(u)}


def _lfc_font(cps, size, ttf):
    """_lfc_once, then each character the batch missed on its own: one Ext-B code point in --range makes lv_font_conv
    return nothing for the whole batch (11-03: 欧阳 of 欧阳䶮𠮷 fell through to the fallback fonts)."""
    got = _lfc_once(cps, size, ttf)
    if len(cps) > 1:
        for u in [u for u in cps if u not in got]:
            got.update(_lfc_once([u], size, ttf))
    return got


def embolden_x(g):
    """Widen every ink run by one pixel to the right (thin serif fallback fonts look pale on the 1bpp panel)."""
    rows = []
    for r in g.rows:
        o = list(r) + [0]
        for i, v in enumerate(r):
            if v:
                o[i + 1] = 1
        rows.append(o)
    return Glyph(g.u, g.size, rows, g.ofs_x, g.ofs_y, g.adv_w).trimmed()


def render_lfc(chars, size, ttf=DEFAULT_TTF):
    """Render with lv_font_conv, the tool that produced font_cn_*: byte-identical to the on-device fonts.
    Characters the main font lacks come from FALLBACK_TTFS and are emboldened like the web tool does."""
    cps = sorted({ord(c) for c in chars})
    got = _lfc_font(cps, size, ttf)
    for fb in FALLBACK_TTFS:
        left = [u for u in cps if u not in got]
        if not left:
            break
        if not fb.exists():
            continue
        if fb.suffix.lower() == '.ttc':          # lv_font_conv cannot read font collections: Pillow + same tofu test as the web tool
            for u in left:
                g = render(chr(u), size, fb, threshold=64)
                tofu = render(chr(0x10FFFD), size, fb, threshold=64)
                if g.rows and g.rows != tofu.rows:
                    got[u] = embolden_x(g)
        else:
            got.update({u: embolden_x(g) for u, g in _lfc_font(left, size, fb).items()})
    return got


def render(ch, size, ttf=DEFAULT_TTF, threshold=128, cal=None):
    """Render one character to a trimmed Glyph. cal = per-size calibration dict (see calibrate())."""
    from PIL import Image, ImageDraw, ImageFont
    cal = cal or {}
    px = cal.get('px', size)
    font = ImageFont.truetype(str(ttf), px)
    canvas = size * 3
    img = Image.new('L', (canvas, canvas), 0)
    ox, base = size, size * 2          # pen origin and baseline row in the canvas
    ImageDraw.Draw(img).text((ox + cal.get('dx', 0), base + cal.get('dy', 0)), ch, font=font, fill=255, anchor='ls')
    th = cal.get('threshold', threshold)
    px_bytes = img.tobytes()
    rows = [[1 if v >= th else 0 for v in px_bytes[y * canvas:(y + 1) * canvas]] for y in range(canvas)]
    # LVGL: bottom pixel row = baseline_row - ofs_y - 1, so a full canvas has ofs_y = base - 1 - (canvas - 1).
    g = Glyph(ord(ch), size, rows, -ox, base - canvas, size * 16)
    g = g.trimmed()
    g.ofs_y += cal.get('oy', 0)
    g.ofs_x += cal.get('ox', 0)
    if 'adv' in cal:
        g.adv_w = cal['adv']
    return g


def diff(a, b):
    """Pixel difference between two glyphs placed by their offsets; returns (box_equal, offset_equal, n_diff, n_ink)."""
    def pts(g):
        return {(g.ofs_x + x, g.ofs_y + (g.h - 1 - y)) for y, r in enumerate(g.rows) for x, c in enumerate(r) if c}
    pa, pb = pts(a), pts(b)
    return (a.w, a.h) == (b.w, b.h), (a.ofs_x, a.ofs_y) == (b.ofs_x, b.ofs_y), len(pa ^ pb), max(len(pb), 1)


# ---------- message builders ----------
MAX_CAMPUS_CHARS = 11            # campus label is 180 px wide at 16 px: 11 CJK characters per line
MAX_GLYPHS = 28                  # name 8 x 2 sizes + campus 11 x 16px (GR accepts 28)
# SAM | 2026-11-03 +08:00 | User decision 11-03: the main page shows at most 5 characters (32px, 180 px label);
# the rest is cut off, so the name is trimmed after its 5th non-ASCII character and only those glyphs are pushed.
SHOWN_NAME_CHARS = 5
# SAM | 2026-11-04 +08:00 | GR keeps the set in two dedicated Flash pages (4 KB, user rule: all Name/Room/Campus glyphs come from the
# platform); the record (20 B header + 16 B per glyph + bitmaps) is refused above 4000 B. Was one ~1 KB NVDS tag.
MAX_STORE_BYTES = 4000


def shown_name(name):
    """Name as displayed: everything up to and including the 5th non-ASCII character (English is not counted)."""
    out, n = [], 0
    for ch in name:
        if ord(ch) >= 0x80:
            if n == SHOWN_NAME_CHARS:
                break
            n += 1
        out.append(ch)
    return ''.join(out).rstrip()


def store_bytes(glyphs):
    """Size of GR's stored record for this set: 20 B header + 16 B per glyph + bitmaps (yp_name_glyphs.c)."""
    return 20 + 16 * len(glyphs) + sum(len(g.data) for g in glyphs)


def _local_has(u, size):
    try:
        return local_font(size).has(u)
    except (OSError, AttributeError):
        return False                  # no font snapshot: push everything


def resident_glyphs(name, campus='', ttf=DEFAULT_TTF, cal=None, overrides=None):
    """Name characters in 32+16px, plus campus characters (it changes per site) in 16px only.
    SAM | 2026-11-03 +08:00 | Only the shown part of the name; hand-drawn overrides replace rendered glyphs.
    (Built-in-font filtering removed 2026-11-04: everything is pushed.)"""
    overrides = overrides or {}
    # SAM | 2026-11-04 +08:00 | User rule: Name / Room / Campus come only from the platform and the device keeps none of them at the
    # factory (storage space only), so every non-ASCII character of the shown name and the campus is pushed, built-in fonts or not.
    res = name_glyphs(shown_name(name), SIZES, ttf, cal, overrides)
    have = {(g.u, g.size) for g in res}
    extra = ''.join(dict.fromkeys(c for c in campus if ord(c) >= 0x80 and (ord(c), 16) not in have))
    if sum(ord(c) >= 0x80 for c in dict.fromkeys(campus)) > MAX_CAMPUS_CHARS:
        raise ValueError(f'campus: at most {MAX_CAMPUS_CHARS} non-ASCII characters')
    return res + (name_glyphs(extra, (16,), ttf, cal, overrides) if extra else [])


def name_glyphs(name, sizes=SIZES, ttf=DEFAULT_TTF, cal=None, overrides=None):
    """Glyphs for every distinct non-ASCII character of the name, each in every size (overrides: hand-drawn)."""
    overrides = overrides or {}
    out, seen = [], set()
    for ch in name:
        if ord(ch) < 0x80 or ch in seen:
            continue
        seen.add(ch)
    chars = ''.join(sorted(seen, key=name.index))
    for ch in chars:
        for s in sizes:
            out.append(overrides.get((ord(ch), s)))
    missing = {s for s in sizes for ch in chars if (ord(ch), s) not in overrides}
    done = {s: (render_lfc(chars, s, ttf) if lfc_available() else {}) for s in missing}
    res = []
    i = 0
    for ch in chars:
        for s in sizes:
            g = out[i]; i += 1
            if g is None:
                g = done.get(s, {}).get(ord(ch)) or render(ch, s, ttf, cal=(cal or {}).get(str(s)))
            res.append(g)
    return res


def check_name(name):
    # English (ASCII) uses the built-in font; only characters needing pushed glyphs count toward the limit.
    if not name or sum(ord(c) >= 0x80 for c in name) > MAX_NAME_CHARS or len(name.encode('utf-8')) > 63:
        raise ValueError(f'name: at most {MAX_NAME_CHARS} non-ASCII characters and 63 UTF-8 bytes')
    for ch in name:
        u = ord(ch)
        if u < 0x20 or u > 0x10FFFF or 0xD800 <= u <= 0xDFFF:
            raise ValueError(f'unsupported character U+{u:04X}')


def platform_msg(name, room, campus, seq, glyphs, font_id='simhei', font_ver=1, max_store=MAX_STORE_BYTES):
    name = shown_name(name)
    check_name(name)
    if len(glyphs) > MAX_GLYPHS:
        raise ValueError(f'{len(glyphs)} glyphs > {MAX_GLYPHS}')
    if max_store and store_bytes(glyphs) > max_store:
        raise ValueError(f'glyph data {store_bytes(glyphs)} B > {max_store} B that the device can keep')
    for g in glyphs:
        if len(g.data) > MAX_GLYPH_BYTES:
            raise ValueError(f'U+{g.u:04X}/{g.size} is {len(g.data)} B > {MAX_GLYPH_BYTES}')
    return {'MsgType': 'residentNameMsg', 'Seq': int(seq), 'Name': name, 'Room': room, 'Campus': campus,
            'FontId': font_id, 'FontVer': font_ver, 'Glyphs': [g.to_json() for g in glyphs]}


def bus_lines(msg, txn=1):
    """The exact lines CAT1 sends to GR for one platform message (flat JSON, one object per line)."""
    gl = msg['Glyphs']
    lines = [{'op': 'name_begin', 'id': txn, 'seq': msg['Seq'], 'g': len(gl),
              'name': msg['Name'], 'room': msg.get('Room', ''), 'campus': msg.get('Campus', '')}]
    for i, j in enumerate(gl):
        lines.append({'op': 'glyph', 'id': txn, 'i': i, 'u': j['U'], 's': j['S'], 'w': j['W'], 'h': j['H'],
                      'x': j['X'], 'y': j['Y'], 'a': j['A'], 'd': j['D'], 'c': j['C']})
    lines.append({'op': 'name_end', 'id': txn, 'g': len(gl)})
    out = ['BUS_EVT=' + json.dumps(l, ensure_ascii=False, separators=(',', ':')) for l in lines]
    for l in out:
        if len(l.encode('utf-8')) > LINE_LIMIT:
            raise ValueError(f'line too long ({len(l.encode())} B): {l[:60]}')
    return out

