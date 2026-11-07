"""YP001 工程目录同步工具：D:\\SVN（同事/交付目录） <-> D:\\CODEX\\sos-card（本项目）。

SAM | 2026-11-01 +08:00 | 只做普通文件的比较和复制：不运行任何版本控制命令，不进入版本控制元数据目录，不删除任何文件。
基线 = 上次两边完全一致时每个文件的 SHA-256（baseline.json）。据此把差异分成：
  svn_changed  只有 SVN 侧改了        -> pull（SVN -> 项目）
  prj_changed  只有项目侧改了         -> push（项目 -> SVN）
  new_in_svn / new_in_prj  只存在一侧 -> pull / push
  conflict     两边都改了且不同       -> 不自动处理，差异存到报告目录，由人/Claude 合成后用 --resolve 指定
  diverged     没有基线且两边不同     -> 同上（先 baseline 或人工判断）
  eol_only     只有换行符不同         -> 视为相同，不复制
  deleted_*    一侧删了               -> 只报告
用法：
  python tree_sync.py scan                    # 比较，写报告到 reports/<时间>/summary.md，终端只打印摘要
  python tree_sync.py baseline                # 把"当前两边完全相同"的文件记为基线（首次、或合成完成后）
  python tree_sync.py push  --yes [--only 子串] [--resolve 相对路径=prj|svn]...
  python tree_sync.py pull  --yes [--only 子串] [--resolve 相对路径=prj|svn]...
  python tree_sync.py merge                   # CAT1 两边都改的文件：以项目（实板验证版）为底三方合并到报告目录，不写两边
  python tree_sync.py handoff                 # 交给同事前的检查：两边是否一致、OTA 规则、密钥/临时文件、GR 与 CAT1 版本号
  push/pull 只处理 mode=two-way 的区域；覆盖前先把被覆盖的文件打包到 D:\\CODEX\\_archive\\tree_sync_<时间>.zip。
SAM | 2026-11-02 +08:00 | 按 OTA 技能补全：baseline 同时把 CAT1 与 GR Src 内容存档（三方合并要用基线内容）；scan 附 OTA 规则检查；
pull 不覆盖 CAT1 受保护文件（ota_*、business_*、update.lua 等，只能由我们改）；新增 merge、handoff。
"""
import argparse, difflib, fnmatch, hashlib, json, os, re, shutil, subprocess, sys, time, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / 'sync_config.json').read_text(encoding='utf-8'))
SVN_ROOT, PRJ_ROOT = Path(CFG['svn_root']), Path(CFG['project_root'])
META = '.' + 'sv' + 'n'  # version-control metadata folder name: never entered
ALWAYS_SKIP_DIRS = {META, '.git', '__pycache__'}
G = CFG['ota_guard']
CACHE_FILE, BASE_FILE = HERE / 'hash_cache.json', HERE / 'baseline.json'
import ota_guard
SNAPSHOT_AREAS = ('cat1', 'gr_src')
TEXT_EXT = {'.c', '.h', '.cpp', '.s', '.lua', '.md', '.txt', '.json', '.ini', '.sct', '.uvprojx', '.xml', '.py', '.ps1', '.bat', '.csv', '.mk', '.ld'}


def load(p, default):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default


cache = load(CACHE_FILE, {})
baseline = load(BASE_FILE, {})


def sha(path):
    st = path.stat()
    key = str(path)
    c = cache.get(key)
    if c and c[0] == st.st_size and c[1] == int(st.st_mtime):
        return c[2]
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    cache[key] = [st.st_size, int(st.st_mtime), h]
    return h


def excluded(rel, patterns):
    parts = rel.split('/')
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or any(fnmatch.fnmatch(x, pat) for x in parts):
            return True
    return False


def walk(root, patterns):
    out = {}
    if not root.exists():
        return out
    for dp, dns, fns in os.walk(root):
        rel_dir = Path(dp).relative_to(root).as_posix()
        dns[:] = [d for d in dns if d not in ALWAYS_SKIP_DIRS and not excluded((rel_dir + '/' + d).lstrip('./'), patterns)]
        for f in fns:
            rel = (rel_dir + '/' + f).lstrip('./') if rel_dir != '.' else f
            if not excluded(rel, patterns):
                out[rel] = Path(dp) / f
    return out


def norm_eq(a, b):
    if a.suffix.lower() not in TEXT_EXT or max(a.stat().st_size, b.stat().st_size) > 4_000_000:
        return False
    return a.read_bytes().replace(b'\r\n', b'\n') == b.read_bytes().replace(b'\r\n', b'\n')


os.system('')  # 让 Windows 控制台识别颜色转义
USE_COLOR = (sys.stdout.isatty() or bool(os.environ.get('FORCE_COLOR'))) and not os.environ.get('NO_COLOR')
SHOW_BAR = sys.stderr.isatty() or bool(os.environ.get('FORCE_COLOR'))
CODES = {'red': '31', 'green': '32', 'yellow': '33', 'blue': '34', 'magenta': '35', 'cyan': '36', 'dim': '90', 'bold': '1'}
CLS_STYLE = {'same': ('green', '一致'), 'eol_only': ('dim', '仅换行符不同'), 'svn_changed': ('cyan', '同事改了→可 pull'),
             'prj_changed': ('blue', '项目改了→可 push'), 'new_in_svn': ('yellow', '仅 SVN 有→可 pull'),
             'new_in_prj': ('yellow', '仅项目有→可 push'), 'conflict': ('red', '两边都改→用 merge'),
             'diverged': ('red', '无基线且不同→人工判断'), 'deleted_in_svn': ('magenta', 'SVN 侧删了'), 'deleted_in_prj': ('magenta', '项目侧删了')}
LV_STYLE = {'BLOCK': 'red', 'WARN': 'yellow', 'INFO': 'dim'}


def C(color, text):
    return f'\033[{CODES[color]}m{text}\033[0m' if USE_COLOR else str(text)


def show_guard(res, limit=12):
    """OTA 规则结果：BLOCK 红、WARN 黄、INFO 灰；每级最多 limit 条，其余见报告。"""
    shown = 0
    for lv, rule, f, msg in res:
        if lv == 'INFO':
            continue
        if shown >= limit:
            print(C('dim', f'    ... 还有 {sum(1 for r in res if r[0] != "INFO") - shown} 条，见报告')); break
        print('  ' + C(LV_STYLE[lv], f'[{lv}]') + f' {rule} {C("bold", f)}  {msg[:110]}'); shown += 1
    if not shown:
        print('  ' + C('green', '无 BLOCK / WARN'))


_last_bar = [0.0]


def bar(done, total, label, force=False):
    """SAM | 2026-11-02 +08:00 | 进度条写到 stderr（同一行刷新，0.1 s 节流），不影响 stdout 的结果输出。"""
    now = time.time()
    if not force and now - _last_bar[0] < 0.1:
        return
    _last_bar[0] = now
    n = int(30 * done / total) if total else 30
    sys.stderr.write(f'\r[{"#" * n}{"-" * (30 - n)}] {100 * done // max(total, 1):3d}% {done}/{total} {label:<12}')
    sys.stderr.flush()


def classify():
    res = []  # (area, rel, cls, mode)
    walked = []
    for i, ar in enumerate(CFG['areas'], 1):
        if SHOW_BAR:
            sys.stderr.write(f'\r列目录 {i}/{len(CFG["areas"])} {ar["name"]:<12}'); sys.stderr.flush()
        pats = CFG.get('global_excludes', []) + ar.get('exclude', [])
        walked.append((ar, walk(SVN_ROOT / ar['svn'], pats), walk(PRJ_ROOT / ar['prj'], pats)))
    total, done = sum(len(set(s) | set(p)) for _, s, p in walked), 0
    for ar, s, p in walked:
        for rel in sorted(set(s) | set(p)):
            done += 1
            bar(done, total, ar['name'])
            key = ar['name'] + ':' + rel
            hs = sha(s[rel]) if rel in s else None
            hp = sha(p[rel]) if rel in p else None
            b = baseline.get(key)
            if hs == hp:
                cls = 'same'
            elif hs and hp and norm_eq(s[rel], p[rel]):
                cls = 'eol_only'
            elif b is None:
                cls = 'new_in_svn' if hp is None else 'new_in_prj' if hs is None else 'diverged'
            elif hp is None:
                cls = 'deleted_in_prj'
            elif hs is None:
                cls = 'deleted_in_svn'
            elif hp == b:
                cls = 'svn_changed'
            elif hs == b:
                cls = 'prj_changed'
            else:
                cls = 'conflict'
            res.append((ar, rel, cls, s.get(rel), p.get(rel)))
    bar(done, total, '完成', force=True)
    sys.stderr.write('\n')
    return res


def cmd_scan():
    res = classify()
    stamp = time.strftime('%Y%m%d_%H%M%S')
    rep = HERE / 'reports' / stamp
    (rep / 'conflicts').mkdir(parents=True, exist_ok=True)
    lines = [f'# 目录同步报告 {stamp}', '']
    summary = {}
    for ar, rel, cls, sp, pp in res:
        summary.setdefault(ar['name'], {}).setdefault(cls, []).append((rel, sp, pp))
    for ar in CFG['areas']:
        d = summary.get(ar['name'], {})
        counts = ' '.join(f'{c}={len(v)}' for c, v in sorted(d.items()))
        lines.append(f"## {ar['name']}  ({ar['mode']})  {counts}")
        for cls in ('conflict', 'diverged', 'svn_changed', 'prj_changed', 'new_in_svn', 'new_in_prj', 'deleted_in_svn', 'deleted_in_prj'):
            for rel, sp, pp in d.get(cls, [])[:60]:
                lines.append(f'- {cls:14} {rel}')
                if cls in ('conflict', 'diverged') and sp and pp and sp.suffix.lower() in TEXT_EXT and max(sp.stat().st_size, pp.stat().st_size) < 2_000_000:
                    a = sp.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
                    b = pp.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
                    diff = ''.join(list(difflib.unified_diff(a, b, 'SVN/' + rel, 'PROJECT/' + rel, n=2))[:3000])
                    (rep / 'conflicts' / (ar['name'] + '__' + rel.replace('/', '__') + '.diff')).write_text(diff, encoding='utf-8')
            if len(d.get(cls, [])) > 60:
                lines.append(f'- ... {cls} 还有 {len(d[cls]) - 60} 个，见 full_list.txt')
        lines.append('')
    guard_res = guard_cat1()
    guard_md, gn = ota_guard.report_md(guard_res, 'CAT1 OTA 规则检查（SVN 侧 对 项目验证版）')
    lines += [guard_md]
    (rep / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    (rep / 'full_list.txt').write_text('\n'.join(f"{ar['name']}\t{cls}\t{rel}" for ar, rel, cls, _, _ in res if cls != 'same'), encoding='utf-8')
    CACHE_FILE.write_text(json.dumps(cache), encoding='utf-8')
    print('\n' + C('bold', '== 对比结果 =='))
    for ar in CFG['areas']:
        d = summary.get(ar['name'], {})
        parts = '  '.join(C(CLS_STYLE[c][0], f'{CLS_STYLE[c][1]} {len(v)}') for c, v in sorted(d.items(), key=lambda kv: kv[0] != 'same'))
        print(f"{C('bold', ar['name']):12} {C('dim', ar['mode']):11} {parts}")
    todo = [(ar['name'], rel, cls) for ar, rel, cls, _, _ in res if cls not in ('same', 'eol_only')]
    if todo:
        print('\n' + C('bold', '== 有差异的文件（最多 20 个）=='))
        for n, rel, cls in todo[:20]:
            print(f'  {C(CLS_STYLE[cls][0], CLS_STYLE[cls][1]):<24} {n}:{rel}')
        if len(todo) > 20:
            print(C('dim', f'  ... 还有 {len(todo) - 20} 个，见 full_list.txt'))
    print('\n' + C('bold', '== CAT1 OTA 规则 ==') + f"  BLOCK={C('red' if gn['BLOCK'] else 'green', gn['BLOCK'])}  WARN={C('yellow' if gn['WARN'] else 'green', gn['WARN'])}")
    show_guard(guard_res)
    print('\n' + C('bold', '结论：') + (C('green', '两边一致，没有 OTA 规则问题') if not todo and not gn['BLOCK'] and not gn['WARN'] else
          C('yellow', f'{len(todo)} 个文件有差异，OTA 规则 BLOCK={gn["BLOCK"]} WARN={gn["WARN"]}')))
    print(C('dim', f'报告：{rep / "summary.md"}'))


def cmd_baseline():
    n = 0
    for ar, rel, cls, sp, pp in classify():
        if cls in ('same', 'eol_only') and sp and pp:
            baseline[ar['name'] + ':' + rel] = sha(sp) if cls == 'same' else sha(pp)
            n += 1
    snap = Path(CFG['archive_dir']) / f'tree_sync_base_{time.strftime("%Y%m%d_%H%M%S")}.zip'
    with zipfile.ZipFile(snap, 'w', zipfile.ZIP_DEFLATED) as z:
        for ar, rel, cls, sp, pp in classify():
            if ar['name'] in SNAPSHOT_AREAS and cls in ('same', 'eol_only') and pp:
                z.write(pp, ar['name'] + '/' + rel)
    baseline['_snapshot'] = str(snap)
    BASE_FILE.write_text(json.dumps(baseline, indent=0), encoding='utf-8')
    CACHE_FILE.write_text(json.dumps(cache), encoding='utf-8')
    print(C('green', f'基线已更新：{n} 个文件（两边相同的才记录）') + C('dim', f'；内容存档 {snap}'))


def cmd_apply(direction, args):
    resolve = dict(x.split('=', 1) for x in args.resolve)
    want = {'push': ('prj_changed', 'new_in_prj'), 'pull': ('svn_changed', 'new_in_svn')}[direction]
    todo = []
    for ar, rel, cls, sp, pp in classify():
        if ar['mode'] != 'two-way' or (args.only and args.only not in ar['name'] + ':' + rel):
            continue
        r = resolve.get(rel) or resolve.get(ar['name'] + ':' + rel)
        if cls in want or (cls in ('conflict', 'diverged') and r == ('prj' if direction == 'push' else 'svn')):
            if direction == 'pull' and ar['name'] == G['cat1_area'] and ota_guard.protected(rel) and not args.allow_protected:
                print('  ' + C('magenta', '跳过（OTA 受保护，只能由我们改）') + f' {ar["name"]}:{rel}'); continue
            todo.append((ar, rel, sp, pp))
        elif cls in ('conflict', 'diverged') and r:
            pass  # resolved the other way: the other direction handles it
    if not todo:
        print(C('green', '没有需要复制的文件。')); return 0
    print(C('bold', f'{direction}：{len(todo)} 个文件'))
    for ar, rel, *_ in todo[:40]:
        print('  ', C('cyan' if direction == 'pull' else 'blue', ar['name'] + ':' + rel))
    if not args.yes:
        print(C('yellow', '（预览，没有写入；确认后加 --yes）')); return len(todo)
    arc = Path(CFG['archive_dir']) / f'tree_sync_{direction}_{time.strftime("%Y%m%d_%H%M%S")}.zip'
    arc.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(arc, 'w', zipfile.ZIP_DEFLATED) as z:
        for ar, rel, sp, pp in todo:
            dst = pp if direction == 'pull' else sp
            if dst and dst.exists():
                z.write(dst, ('PROJECT/' if direction == 'pull' else 'SVN/') + ar['name'] + '/' + rel)
        z.writestr('README.txt', f'{direction} 前被覆盖的文件备份。\n')
    for ar, rel, sp, pp in todo:
        src, dst = (sp, PRJ_ROOT / ar['prj'] / rel) if direction == 'pull' else (pp, SVN_ROOT / ar['svn'] / rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        baseline[ar['name'] + ':' + rel] = sha(src)
        cache.pop(str(dst), None)
    BASE_FILE.write_text(json.dumps(baseline, indent=0), encoding='utf-8')
    CACHE_FILE.write_text(json.dumps(cache), encoding='utf-8')
    print(C('green', f'完成：{len(todo)} 个文件已复制') + C('dim', f'；覆盖前备份 {arc}'))


def area(name):
    return next(a for a in CFG['areas'] if a['name'] == name)


def guard_cat1():
    a = area(G['cat1_area'])
    return ota_guard.check(SVN_ROOT / a['svn'], PRJ_ROOT / a['prj'])


def cmd_merge():
    a = area(G['cat1_area'])
    snap = baseline.get('_snapshot')
    todo = [rel for ar, rel, cls, sp, pp in classify() if ar['name'] == a['name'] and cls in ('conflict', 'diverged') and '/' not in rel]
    if not todo:
        print(C('green', 'CAT1 没有两边都改的文件；单边改动用 pull/push。')); return
    if not snap or not Path(snap).exists():
        print(C('red', '没有基线内容存档（先在两边一致时运行 baseline）：无法三方合并。') + ' 冲突文件：' + ' '.join(todo)); return
    rep = HERE / 'reports' / ('merge_' + time.strftime('%Y%m%d_%H%M%S'))
    base = rep / 'base'
    base.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snap) as z:
        for m in z.namelist():
            if m.startswith(a['name'] + '/') and m.count('/') == 1:
                (base / m.split('/', 1)[1]).write_bytes(z.read(m))
    subprocess.run([sys.executable, str(HERE / 'merge3.py'), '--base', str(base), '--ours', str(PRJ_ROOT / a['prj']),
                    '--theirs', str(SVN_ROOT / a['svn']), '--out', str(rep / 'merged'), '--files', *todo], check=True)
    md, gn = ota_guard.report_md(ota_guard.check(rep / 'merged', PRJ_ROOT / a['prj']), '合并结果 OTA 规则检查')
    (rep / 'guard.md').write_text(md, encoding='utf-8')
    print(C('bold', '== 三方合并 ==') + f'  结果 {rep / "merged"}')
    print(f'  OTA 规则 BLOCK={C("red" if gn["BLOCK"] else "green", gn["BLOCK"])} WARN={C("yellow" if gn["WARN"] else "green", gn["WARN"])}，见 {rep / "guard.md"}')
    print(C('yellow', '含 <<<<<<< 的文件还有冲突要人工处理。') + ' merged 只含冲突文件（R1 对缺失文件的提示可忽略）；处理完冲突标记后复制到项目、跑主机测试、上板验证，再 push。')


def secret_scan():
    bad, skip = [], G.get('secret_scan_skip', [])
    for dp, dns, fns in os.walk(SVN_ROOT):
        dns[:] = [d for d in dns if d not in ALWAYS_SKIP_DIRS]
        rel_dir = Path(dp).relative_to(SVN_ROOT).as_posix()
        if any(rel_dir == s or rel_dir.startswith(s + '/') for s in skip):
            dns[:] = []
            continue
        for f in fns:
            q = Path(dp) / f
            if re.search(r'(\.key|\.pem|\.pfx|\.p12|\.bak|\.tmp|\.orig|\.rej|~)$', f, re.I) or 'private' in f.lower():
                bad.append(rel_dir + '/' + f)
            elif q.suffix.lower() in ('.lua', '.c', '.h', '.json', '.xml', '.txt', '.md', '.ini') and q.stat().st_size < 2_000_000:
                b = q.read_bytes()
                if b'PRIVATE KEY' in b or (b'<RSAKeyValue>' in b and b'<D>' in b):
                    bad.append(rel_dir + '/' + f + '（含私钥内容）')
    return bad


def versions():
    cat = (SVN_ROOT / area(G['cat1_area'])['svn'] / 'main.lua').read_text(encoding='utf-8', errors='replace')
    hdr = SVN_ROOT / G['gr_version_header']
    gr = hdr.read_text(encoding='utf-8', errors='replace') if hdr.exists() else ''
    pick = lambda pat, s: (re.search(pat, s) or [None, '?'])[1]
    return (pick(r'PRODUCT_VERSION\s*=\s*"([^"]+)"', cat), pick(r'FW_RELEASE_BUILD\s*=\s*(\d+)', cat),
            pick(r'YP001_PRODUCT_VERSION\s+"([^"]+)"', gr), pick(r'YP001_FW_BUILD\s+(\d+)', gr))


def cmd_handoff():
    lines = ['# 交接前检查 ' + time.strftime('%Y-%m-%d %H:%M'), '']
    diff = [(ar['name'], rel, cls) for ar, rel, cls, _, _ in classify() if cls not in ('same', 'eol_only') and ar['mode'] == 'two-way']
    lines += [f'## 1. 两边一致性：{"一致" if not diff else f"{len(diff)} 个文件不一致"}', '']
    lines += [f'- {n}:{r} {c}' for n, r, c in diff[:80]] + ['']
    guard_res = guard_cat1()
    md, gn = ota_guard.report_md(guard_res, '2. CAT1 OTA 规则（SVN 侧）')
    bad = secret_scan()
    lines += [md, '## 3. 密钥 / 临时文件（' + '、'.join(G.get('secret_scan_skip', [])) + ' 第三方目录除外）', '']
    lines += ([f'- {x}' for x in bad] or ['- 无']) + ['']
    cv, cb, gv, gb = versions()
    ok_ver = cv == gv and cb == gb
    lines += [f'## 4. 版本号：CAT1 {cv}/b{cb}，GR {gv}/b{gb} —— {"一致" if ok_ver else "不一致"}', '']
    rep = HERE / 'reports' / ('handoff_' + time.strftime('%Y%m%d_%H%M%S'))
    rep.mkdir(parents=True, exist_ok=True)
    (rep / 'handoff.md').write_text('\n'.join(lines), encoding='utf-8')
    CACHE_FILE.write_text(json.dumps(cache), encoding='utf-8')
    mark = lambda ok, warn=False: C('green', '[ OK ]') if ok else C('yellow' if warn else 'red', '[ !! ]' if warn else '[ XX ]')
    print('\n' + C('bold', '== 交接前检查 =='))
    print(f' {mark(not diff)} 两边一致性：' + (C('green', '一致') if not diff else C('red', f'{len(diff)} 个文件不一致（先 scan 看明细）')))
    print(f' {mark(gn["BLOCK"] == 0, gn["BLOCK"] == 0 and gn["WARN"] > 0)} CAT1 OTA 规则：BLOCK={C("red" if gn["BLOCK"] else "green", gn["BLOCK"])}  WARN={C("yellow" if gn["WARN"] else "green", gn["WARN"])}')
    show_guard(guard_res)
    print(f' {mark(not bad)} 密钥 / 临时文件：' + (C('green', '无') if not bad else C('red', f'{len(bad)} 个：' + '、'.join(bad[:5]))))
    print(f' {mark(ok_ver)} 版本号：CAT1 {cv}/b{cb}，GR {gv}/b{gb} ' + (C('green', '一致') if ok_ver else C('red', '不一致')))
    blocking = bool(diff or bad or not ok_ver or gn['BLOCK'])
    print('\n' + C('bold', '结论：') + (C('red', '有必须处理的项（BLOCK 若是已知遗留，在交接清单里写明）') if blocking else
          C('yellow', '可以交接；WARN 请在交接清单里确认') if gn['WARN'] else C('green', '可以交接')))
    print(C('dim', f'报告：{rep / "handoff.md"}'))


MENU = [('scan', '对比两边，出报告（含 CAT1 OTA 规则检查），不改文件'),
        ('handoff', '交给同事前检查（一致性 / OTA 规则 / 密钥 / 版本号），不改文件'),
        ('merge', 'CAT1 两边都改的文件做三方合并，结果放报告目录，不改两边'),
        ('pull', '同事单边改的文件 → 项目（先预览，确认后写入；OTA 受保护文件跳过）'),
        ('push', '项目单边改的文件 → SVN（先预览，确认后写入）'),
        ('baseline', '两边一致时记录基线并存档内容')]


def menu():
    """SAM | 2026-11-02 +08:00 | 双击 sync.bat 不带参数时的菜单；push/pull 先预览，输入 y 才写入。"""
    print(C('bold', 'YP001 项目 ↔ SVN 交接对比工具') + C('dim', '（只复制普通文件，不运行版本控制命令）') + '\n')
    for i, (c, d) in enumerate(MENU, 1):
        print(f'  {C("cyan", i)}. {C("bold", f"{c:9}")} {d}')
    s = input('\n选择编号（回车退出）：').strip()
    if not s:
        return 'quit'
    if not s.isdigit() or not 1 <= int(s) <= len(MENU):
        print(C('red', '没有这个编号。')); return None
    cmd = MENU[int(s) - 1][0]
    if cmd in ('push', 'pull'):
        if not cmd_apply(cmd, argparse.Namespace(yes=False, only='', resolve=[], allow_protected=False)):
            return None
        if input('\n确认写入以上文件？输入 y 执行，其他键取消：').strip().lower() != 'y':
            print(C('yellow', '已取消，没有写入。')); return None
        return [cmd, '--yes']
    return [cmd]


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='项目与 SVN 目录的文件级对比和同步（普通文件复制）；不带参数显示菜单')
    ap.add_argument('cmd', nargs='?', choices=['scan', 'baseline', 'push', 'pull', 'merge', 'handoff'])
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--resolve', action='append', default=[])
    ap.add_argument('--allow-protected', action='store_true', help='pull 时也覆盖 CAT1 受保护文件（只在我们自己确认后使用）')
    a = ap.parse_args()
    run = lambda x: {'scan': cmd_scan, 'baseline': cmd_baseline, 'merge': cmd_merge, 'handoff': cmd_handoff}.get(x.cmd, lambda: cmd_apply(x.cmd, x))()
    if a.cmd:
        run(a)
    else:  # SAM | 2026-11-02 +08:00 | 菜单循环：每个命令跑完回车返回主菜单，主菜单直接回车才退出
        while True:
            picked = menu()
            if picked == 'quit':
                break
            if picked:
                try:
                    run(ap.parse_args(picked))
                except Exception as e:
                    print(C('red', f'出错：{e}'))
            input(C('dim', '\n按回车返回主菜单...'))
            print('\n' + '=' * 60 + '\n')
