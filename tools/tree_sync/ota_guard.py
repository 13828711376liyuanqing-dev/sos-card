"""CAT1 代码 OTA 规则检查：把 doc/2026-11-02_CAT1代码交接清单_同事改代码与OTA.md 的规则变成自动检查。

SAM | 2026-11-02 +08:00 | 只读两个目录：DIR（要检查的，通常是同事/SVN 侧）和 REF（实板验证过的，通常是本项目侧）。
REF 可省略；省略时只做不需要对比的检查。结果是 (级别, 规则, 文件, 说明) 列表：
  BLOCK  会直接让 OTA 失败或不可控，必须先处理
  WARN   需要人确认（例如新增的根目录写入）
  INFO   提示
用法：python ota_guard.py DIR [REF]
"""
import fnmatch, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
G = json.loads((HERE / 'sync_config.json').read_text(encoding='utf-8'))['ota_guard']
LIBS = set(G['vendor_libs'])  # Luatools 库：原样使用，规则 R3/R4 不查
BUILTIN = set(G['builtin_modules'])


def protected(name):
    return any(fnmatch.fnmatch(name, p) for p in G['protected'])


def lua_files(d):
    return {p.name: p for p in sorted(Path(d).glob('*.lua'))}


def text(p):
    b = p.read_bytes()
    if b.startswith(b'\xef\xbb\xbf'):
        b = b[3:]
    return b.decode('utf-8', 'replace').replace('\r\n', '\n')


def code_lines(s):
    """去掉行注释后的 (行号, 代码)；块注释 --[[ ]] 整段跳过。"""
    out, block = [], False
    for i, line in enumerate(s.split('\n'), 1):
        t = line
        if block:
            if ']]' in t:
                block, t = False, t.split(']]', 1)[1]
            else:
                continue
        if '--[[' in t:
            head, rest = t.split('--[[', 1)
            if ']]' not in rest:
                block = True
            t = head
        t = t.split('--', 1)[0] if '--' in t and not re.search(r'["\'][^"\']*--', t) else t
        if t.strip():
            out.append((i, t))
    return out


VERSION_PAIR_FILES = ('ota_trial.lua', 'ota_native_fota.lua')  # 这两个文件里的 'x.y.z' 是本轮升级范围，每轮由一键工具改写


def norm(name, s):
    """比较前的规范化：升级范围版本号字面量视为相同。"""
    return re.sub(r"'\d+\.\d+\.\d+'", "'V'", s) if name in VERSION_PAIR_FILES else s


def protected_digest(d):
    """受保护文件（规范化后）的合并摘要：一键工具用它判断“OTA 代码是否与验证版一致”。"""
    import hashlib
    h = hashlib.sha256()
    for n, p in sorted(lua_files(d).items()):
        if protected(n):
            h.update(n.encode() + b'\0' + norm(n, text(p)).encode() + b'\0')
    return h.hexdigest()


def main_ota_section(s, versions=True):
    """main.lua 中受保护的部分：版本与 OTA_TRIAL 赋值、OTA 运行时几行、require 顺序。versions=False 时不含版本赋值。"""
    keep = []
    for _, t in code_lines(s):
        x = t.strip()
        if not versions and re.match(r'^(VERSION|PRODUCT_VERSION|FW_RELEASE_BUILD|OTA_TRIAL_\w+)\s*=', x):
            continue
        if re.match(r'^(VERSION|PRODUCT_VERSION|FW_RELEASE_BUILD|OTA_TRIAL_\w+)\s*=', x) or 'first_trial_profile' in x \
                or 'ota_runtime' in x or 'ota_device_options' in x or 'ota_platform' in x or 'bind_' in x or re.match(r'^(local\s+\w+\s*=\s*)?require', x):
            keep.append(re.sub(r'\s+', ' ', x))
    return keep


def check(d, ref=None, versions_free=False, legacy_ok=False):
    """versions_free：一键工具用，版本号和升级范围每轮都变，不算改动；legacy_ok：验证版里已有的写法降级为 WARN。"""
    d = Path(d)
    F, R = lua_files(d), lua_files(ref) if ref else {}
    res = []
    add = lambda lv, rule, f, msg: res.append((lv, rule, f, msg))

    # R1 受保护文件被改 / 删
    if ref:
        for n in sorted(set(F) | set(R)):
            if not protected(n):
                continue
            if n not in F:
                add('BLOCK', 'R1 OTA文件', n, '验证版有、这边缺失')
            elif n not in R:
                add('BLOCK', 'R1 OTA文件', n, '新增了受保护名字的文件')
            elif norm(n, text(F[n])) != norm(n, text(R[n])):
                add('BLOCK', 'R1 OTA文件', n, '内容与实板验证版不同（只允许我们改）')
        if 'main.lua' in F and 'main.lua' in R and main_ota_section(text(F['main.lua']), not versions_free) != main_ota_section(text(R['main.lua']), not versions_free):
            add('BLOCK', 'R1 OTA文件', 'main.lua', '版本号/OTA_TRIAL/OTA 启动段或 require 顺序与验证版不同')

    ref_lines = {n: {re.sub(r'\s+', ' ', t.strip()) for _, t in code_lines(text(p))} for n, p in R.items()}
    is_new = lambda n, t: bool(ref) and re.sub(r'\s+', ' ', t.strip()) not in ref_lines.get(n, set())
    handlers, mods = {}, set(F) and {n[:-4] for n in F}
    for n, p in F.items():
        s = text(p)
        cl = code_lines(s)
        lib = n in LIBS
        for k, (i, t) in enumerate(cl):
            loc = f'{n}:{i}'
            # R2 新建目录（快照遇到未登记目录会 DIRECTORY_UNVERIFIED）
            if re.search(r'\bio\.mkdir\s*\(', t):
                add('BLOCK' if is_new(n, t) else 'INFO', 'R2 新建目录', loc,
                    t.strip()[:100] + ('  ← 新增：根目录新目录需加入 ota_data_inventory 放行名单' if is_new(n, t) else '  （已放行的 /log、/ble）'))
            # R3 重启前必须 reboot_allowed()
            if re.search(r'\b(rtos|pm)\.reboot\s*\(', t):
                ctx = ' '.join(x for _, x in cl[max(0, k - 8):k + 1])
                if lib:
                    add('INFO', 'R3 重启', loc, '库自带的重启（平台 FOTA 路径）：业务代码不得调用该功能')
                elif protected(n):
                    pass
                elif 'reboot_allowed' not in ctx:
                    legacy = legacy_ok and ref and not is_new(n, t)
                    add('WARN' if legacy else 'BLOCK', 'R3 重启', loc, t.strip()[:80] + ('  ← 验证版里就有（既有遗留，交接清单已列）' if legacy else '  ← 重启前没有检查 ota_runtime.instance():reboot_allowed()'))
            # R4 UART1 只能在 uart_app 注册
            if re.search(r'\buart\.(setup|on|close)\s*\(', t) and not lib and n != 'uart_app.lua' and not protected(n):
                add('BLOCK', 'R4 串口', loc, t.strip()[:80] + '  ← UART 只在 uart_app.lua 注册')
            if n == 'uart_app.lua' and re.search(r'log\.\w+\(\s*["\']uart_recv', t):
                add('WARN', 'R4 串口', loc, '接收回调打印原始数据：OTA 二进制帧会拖慢通道')
            # R5 根目录写入（OTA 期间写会让数据快照不一致）
            if not protected(n) and not lib and re.search(r'io\.open\([^)]*["\'][wa]b?\+?["\']|io\.writeFile\s*\(|os\.remove\s*\(|fskv\.(set|del|clear)\s*\(', t):
                if any(x in t for x in G['write_ok_tokens']) or n in G['write_ok_files']:
                    continue
                if is_new(n, t) or not ref:
                    add('WARN', 'R5 写文件', loc, t.strip()[:90] + '  ← 写根目录：确认 OTA 期间（reboot_allowed()==false）不执行，或改写 /ram')
            # R6 命令名
            for m in re.finditer(r'at_cmd_handlers(?:\.(\w+)|\[\s*["\'](\w+)["\']\s*\])\s*=', t):
                h = m.group(1) or m.group(2)
                # SAM | 2026-11-04 +08:00 | A wrapper (saves the previous handler first: local prior = at_cmd_handlers.X) chains, it does not duplicate.
                before = '\n'.join(x for j, x in cl[:k])
                if re.search(r'=\s*(?:_G\.)?at_cmd_handlers(?:\.' + h + r'\b|\[\s*["\']' + h + r'["\']\s*\])', before):
                    continue
                handlers.setdefault(h, []).append(loc)
            # R7 require 能找到
            for m in re.finditer(r'require\s*\(?\s*["\']([\w.]+)["\']', t):
                if m.group(1) not in mods and m.group(1) not in BUILTIN:
                    add('BLOCK', 'R7 require', loc, f'require "{m.group(1)}" 在目录里找不到（缺库会导致 CAT1 反复重启）')
        # R8 fs_log 上限
        if n == 'fs_log.lua':
            m = re.search(r'LOG_MAX\s*=\s*([\d\s*]+)', s)
            if m:
                v = eval(m.group(1).replace(' ', '')) if re.fullmatch(r'[\d*]+', m.group(1).replace(' ', '')) else 0
                if v > G['fs_log_max_bytes']:
                    add('WARN', 'R8 空间', n, f'LOG_MAX={v} 字节（加备份共 {2 * v}），建议 ≤ {G["fs_log_max_bytes"]}：写满后 OTA 报 COMPONENT_SPACE')
    for h, locs in handlers.items():
        if len(locs) > 1:
            add('BLOCK', 'R6 命令名', ','.join(locs), f'at_cmd_handlers.{h} 注册了 {len(locs)} 次')
        elif h in G['reserved_commands'] and not protected(locs[0].split(':')[0]) and locs[0].split(':')[0] != 'main.lua':
            add('BLOCK', 'R6 命令名', locs[0], f'{h} 是 OTA 保留命令名')
    # R9 脚本区大小（源码估算；准确值以 Cat1UsbImport 为准）
    total = sum(p.stat().st_size for p in d.iterdir() if p.is_file() and p.suffix.lower() in ('.lua', '.mp3', '.json', '.bin', '.amr', '.wav', '.pcm'))
    if ref:
        rt = sum(p.stat().st_size for p in Path(ref).iterdir() if p.is_file() and p.suffix.lower() in ('.lua', '.mp3', '.json', '.bin', '.amr', '.wav', '.pcm'))
        delta = total - rt
        lv = 'WARN' if delta > G['luadb_headroom_bytes'] // 2 else 'INFO'
        add(lv, 'R9 脚本区', '-', f'源码比验证版多 {delta:+d} 字节；验证版 LuaDB {G["luadb_last_bytes"]}/524288，余 {524288 - G["luadb_last_bytes"]}（编译后大小以 Cat1UsbImport 为准）')
    # R10 语法
    try:
        sys.path.insert(0, G['lupa_path'])
        from lupa import lua54
        chk = lua54.LuaRuntime().eval('function(s,n) local f,e=load(s,"="..n) return e end')
        for n, p in F.items():
            e = chk(text(p), n)
            if e:
                add('BLOCK', 'R10 语法', n, str(e))
    except ImportError:
        add('INFO', 'R10 语法', '-', '没有 lupa，跳过语法检查')
    order = {'BLOCK': 0, 'WARN': 1, 'INFO': 2}
    return sorted(res, key=lambda r: (order[r[0]], r[1], r[2]))


def report_md(res, title):
    n = {k: sum(1 for r in res if r[0] == k) for k in ('BLOCK', 'WARN', 'INFO')}
    lines = [f'## {title}', '', f'BLOCK={n["BLOCK"]} WARN={n["WARN"]} INFO={n["INFO"]}', '', '| 级别 | 规则 | 位置 | 说明 |', '|---|---|---|---|']
    lines += [f'| {lv} | {rule} | {f} | {msg.replace("|", "/")} |' for lv, rule, f, msg in res]
    return '\n'.join(lines) + '\n', n


if __name__ == '__main__':
    r = check(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    for lv, rule, f, msg in r:
        print(f'{lv:5} {rule:10} {f:28} {msg}')
    print('BLOCK=%d WARN=%d' % (sum(x[0] == 'BLOCK' for x in r), sum(x[0] == 'WARN' for x in r)))
