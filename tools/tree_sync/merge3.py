"""三方合并工具（文本文件，逐行）：基线 BASE、我们 OURS（实板验证版）、同事 THEIRS -> 合并结果 OUT。

SAM | 2026-11-01 +08:00 | 初版。
SAM | 2026-11-02 +08:00 | 按 11-01 教训改为以 OURS（实板验证过的代码）为底：同事的改动逐处加入；同一处两边改得不一样
-> 写冲突标记，由人工判断；只差日志/注释时保留 OURS。受保护文件（sync_config.json 的 ota_guard.protected）永远保留 OURS，
同事对它的改动只写进报告（.theirs.diff）。没有基线、二进制文件同样保留 OURS 并把同事版本另存 .theirs 供人工比对。
只读三个来源目录，只写 OUT 目录。
用法：python merge3.py --base DIR --ours DIR --theirs DIR --out DIR [--files a.lua b.lua ...] [--decide decide.json]
结果：OUT 下是合并后的文件；OUT/_report.md 列出每个文件的状态；之后对 OUT 跑 ota_guard.py OUT OURS。
"""
import argparse, difflib, fnmatch, json, re, shutil
from pathlib import Path

TEXT = {'.lua', '.md', '.txt', '.json', '.c', '.h', '.ini'}
HERE = Path(__file__).resolve().parent
PROTECTED = json.loads((HERE / 'sync_config.json').read_text(encoding='utf-8'))['ota_guard']['protected']


def is_protected(name):
    return any(fnmatch.fnmatch(name, p) for p in PROTECTED)


def find_base(root, name):
    """基线可以放在子目录里：按文件名递归找（跳过 demo 目录）。"""
    direct = root / name
    if direct.exists():
        return direct
    hits = [p for p in root.rglob(name) if 'demo' not in p.parts and 'Air780EHM' not in str(p)]
    return hits[0] if hits else direct


def read(p):
    b = p.read_bytes()
    eol = '\r\n' if b.count(b'\r\n') > b.count(b'\n') / 2 else '\n'
    return b.decode('utf-8', 'replace').replace('\r\n', '\n').split('\n'), eol


def changes(base, other):
    return [(i1, i2, other[j1:j2]) for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base, other, autojunk=False).get_opcodes() if t != 'equal']


def apply(base, lo, hi, chs):
    out, pos = [], lo
    for i1, i2, new in chs:
        out += base[pos:i1] + new
        pos = i2
    return out + base[pos:hi]


def code_only(lines):
    out = []
    for x in lines:
        t = x.strip()
        if not t or t.startswith('--') or re.match(r'^log\.(info|warn|error|debug)\(', t):
            continue
        out.append(re.sub(r'\s+', ' ', t))
    return out


def merge(base, ours, theirs, decide=None):
    co, ct = changes(base, ours), changes(base, theirs)
    allc = sorted([(c, 'o') for c in co] + [(c, 't') for c in ct], key=lambda x: (x[0][0], x[0][1]))
    out, pos, n_conf, n_open, n_both, idx = [], 0, 0, 0, 0, 0
    while idx < len(allc):
        (i1, i2, _), _s = allc[idx]
        lo, hi, group = i1, i2, [allc[idx]]
        idx += 1
        while idx < len(allc) and allc[idx][0][0] <= hi:  # touching or overlapping -> same region
            hi = max(hi, allc[idx][0][1]); group.append(allc[idx]); idx += 1
        out += base[pos:lo]
        go = [c for c, s in group if s == 'o']; gt = [c for c, s in group if s == 't']
        vo, vt = apply(base, lo, hi, go), apply(base, lo, hi, gt)
        if not go: out += vt
        elif not gt: out += vo
        elif vo == vt: out += vo
        else:
            co_, ct_ = code_only(vo), code_only(vt)
            if co_ == ct_ or not ct_:
                out += vo  # 只差日志/注释，或同事一侧只有日志/注释：保留验证版
            elif not co_:
                out += vt  # 我们一侧只有注释/日志，同事改了代码：取同事的代码
            else:
                n_conf += 1
                ch = (decide or {}).get(str(n_conf))
                if ch == 'o': out += vo
                elif ch == 't': out += vt
                elif ch == 'ot': out += vo + vt
                elif ch == 'to': out += vt + vo
                else:
                    out += [f'<<<<<<< OURS (实板验证版) #{n_conf}'] + vo + ['======= THEIRS (同事)'] + vt + ['>>>>>>> end']
                    n_open += 1
        if go and gt: n_both += 1
        pos = hi
    return out + base[pos:], n_open, n_both


def keep_ours(o, t, out_dir, n, why, rows):
    shutil.copy2(o, out_dir / n)
    if t.suffix.lower() in TEXT:
        a = o.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
        b = t.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
        (out_dir / (n + '.theirs.diff')).write_text(''.join(difflib.unified_diff(a, b, 'OURS/' + n, 'THEIRS/' + n)), encoding='utf-8')
    else:
        shutil.copy2(t, out_dir / (n + '.theirs'))
    rows.append((n, why, '保留验证版；同事版本见 .theirs / .theirs.diff，需人工判断'))


def main():
    ap = argparse.ArgumentParser()
    for k in ('base', 'ours', 'theirs', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--files', nargs='*')
    ap.add_argument('--decide', help='JSON: {文件名: {冲突序号: o|t|ot|to}}')
    a = ap.parse_args()
    B, O, T, OUT = (Path(getattr(a, k)) for k in ('base', 'ours', 'theirs', 'out'))
    OUT.mkdir(parents=True, exist_ok=True)
    DEC = json.loads(Path(a.decide).read_text(encoding='utf-8')) if a.decide else {}
    names = a.files or sorted({p.name for d in (O, T) for p in d.iterdir() if p.is_file()})
    rows = []
    for n in names:
        o, t, b = O / n, T / n, find_base(B, n)
        if o.exists() and not t.exists():
            shutil.copy2(o, OUT / n); rows.append((n, 'ours_only', '')); continue
        if t.exists() and not o.exists():
            shutil.copy2(t, OUT / n); rows.append((n, 'theirs_only', '同事新增：确认 main.lua 是否加载、是否违反 OTA 规则')); continue
        if o.read_bytes() == t.read_bytes():
            shutil.copy2(o, OUT / n); rows.append((n, 'identical', '')); continue
        if is_protected(n):
            keep_ours(o, t, OUT, n, 'PROTECTED_ours_kept', rows); continue
        if t.suffix.lower() not in TEXT:
            keep_ours(o, t, OUT, n, 'binary_ours_kept', rows); continue
        if not b.exists():
            keep_ours(o, t, OUT, n, 'NO_BASE_ours_kept', rows); continue
        lb, _ = read(b); lo, eo = read(o); lt, _ = read(t)
        merged, nc, nb = merge(lb, lo, lt, (DEC.get(n) or {}))
        (OUT / n).write_bytes(('\n'.join(merged)).replace('\n', eo).encode('utf-8'))
        rows.append((n, 'conflict' if nc else ('merged' if lt != lb else 'ours_unchanged'), f'冲突 {nc} 处；两边都改的区域 {nb} 处'))
    rep = ['# 三方合并报告（底 = 实板验证版）', '', '| 文件 | 状态 | 说明 |', '|---|---|---|'] + [f'| {n} | {s} | {d} |' for n, s, d in rows]
    (OUT / '_report.md').write_text('\n'.join(rep) + '\n', encoding='utf-8')
    for n, s, d in rows:
        print(f'{s:20} {n:28} {d}')


if __name__ == '__main__':
    main()
