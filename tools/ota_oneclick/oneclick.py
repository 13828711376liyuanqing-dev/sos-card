"""YP001 整机 OTA 一键工具：给 GR 编译出的 HEX 和 CAT1 源码两个位置，自动做完全部检查并生成
  1_GR烧写文件       签名后的 GR 固件（bin/hex，给 GR 有线烧写工具用，也是升级包里的 GR 部分）
  2_CAT1刷机目录     目标版本的完整 CAT1 脚本 USB_IMPORT（出厂和换新基线用；OTA 不需要刷它）
  3_上传平台的升级包  整机升级包 zip
  报告.md            每一步的结论、哪些要人确认、下一步怎么做

SAM | 2026-11-02 +08:00 | 把 YP001_工具包 里 4 个工具和 tools/ota 的主机测试串成一条流水线，规则来自技能 yp001-whole-ota-run：
2026-11-10 起 OTA 出厂即可接收，不再生成“接收端”。以实板验证过的代码为底，OTA 受保护文件不许改（tree_sync/ota_guard.py R1），版本/空间/签名/打包校验失败一律停。
不改源码目录、不碰 Git/SVN、不删任何文件；所有产物在新目录 firmware_releases/ota_<源>_to_<目标>_<时间>/。
用法：python oneclick.py            菜单
      python oneclick.py run --gr-hex <hex> --cat1-src <目录> [--from 1.5.8 --from-build 12] [--free <字节>] [--no-device] [--auto-prune]
      python oneclick.py check ...   只检查不生成
"""
import argparse, hashlib, io, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT / 'tools' / 'tree_sync'))
sys.path.insert(0, str(PROJECT / 'tools' / 'ota' / 'bench'))
import ota_guard  # noqa: E402
import release_gate  # SAM | 2026-11-07 09:31 +08:00 | Exact GR/CAT1/SDK review replaces global bypass.
import budget  # noqa: E402  SAM | 2026-11-04 +08:00 | size red lines (budget.json)

os.system('')
USE_COLOR = (sys.stdout.isatty() or bool(os.environ.get('FORCE_COLOR'))) and not os.environ.get('NO_COLOR')
CODES = {'red': '31', 'green': '32', 'yellow': '33', 'cyan': '36', 'dim': '90', 'bold': '1'}


def C(color, text):
    return f'\033[{CODES[color]}m{text}\033[0m' if USE_COLOR else str(text)


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception:
        return default


CFG = load(HERE / 'config.json', {})
P = lambda rel: Path(rel) if Path(rel).is_absolute() else PROJECT / rel
STATE_FILE = HERE / 'state.json'
TOOLBOX = P(CFG['toolbox'])
GR_TOOL = TOOLBOX / '2_GR5526固件检查签名' / 'Gr5526Tool.exe'
PACK_TOOL = TOOLBOX / '3_整机OTA打包' / 'YpOtaPack.exe'
CAT_TOOL = TOOLBOX / '1_CAT1刷机目录生成' / 'Cat1UsbImport.exe'
VER_TOOL = TOOLBOX / '4_固件版本与空间' / 'YpVersionTool.exe'
KEY, PUB = P(CFG['private_key']), P(CFG['public_key_xml'])


# SAM | 2026-11-04 +08:00 | Mandatory behaviours (user rule), checked in the CAT1 source before packaging; cannot be bypassed
# by --reviewed-ota-change. (file, text that must be present, what it guarantees)
MUST_HAVE = [
    ('update.lua', "'/log/app.log', '/log/app.log.bak'", 'OTA 发令前删除 CAT1 app 日志（app.log 和 .bak）'),
    ('update.lua', "[OTA] LOG_CLEARED", '删日志后回报 [OTA] LOG_CLEARED，发令脚本据此必检'),
    ('update.lua', "for _, name in ipairs({'accept', 'receive'})", '台架 OTA_TRIAL 和平台 otaMsg 两个入口都先删日志'),
    ('update.lua', "_G.ota_log_paused", 'OTA 进行中暂停写日志的开关'),
    ('fs_log.lua', "if ota_paused() then return end", 'fs_log 在 OTA 进行中不缓存日志'),
    ('fs_log.lua', "if ota_paused() then buf, buf_len = {}, 0; return true end", 'fs_log 在 OTA 进行中不写日志文件'),
    # SAM | 2026-11-06 +08:00 | /log/ble.ini (temporary BLE location cache) grew to 75 KB and made the GR component fail with COMPONENT_SPACE.
    ('update.lua', "'/log/ble.ini'", 'OTA 发令前一并删除 /log/ble.ini（BLE 定位临时缓存，会涨到 70 KB 以上占满空间）'),
    ('update.lua', "'[OTA_HOLD] '", 'OTA 保电锁：通知 GR 保持 CAT1 供电'),
    ('update.lua', "ota_hold(true)", '台架 OTA_TRIAL 一收到就上保电锁'),
    ('update.lua', "ota_hold(not stuck and (s.phase~='IDLE'", '每 10 s 信标续锁，OTA 结束才放锁'),
]


def must_have(src):
    missing = []
    for name, text, why in MUST_HAVE:
        f = src / name
        body = f.read_bytes().decode('utf-8', 'replace') if f.exists() else ''
        if text not in body:
            missing.append(f'{name}：缺 {text!r} → {why}')
    return missing


def apply_budget(R, B, prev, sizes, **kw):
    """SAM | 2026-11-04 +08:00 | Red line = stop packaging; yellow / growth over growth_yellow = warning in the report."""
    out, got = budget.checks(B, prev=prev, **kw)
    sizes.update(got)
    for lv, text in out:
        R.ok(('红线 ' if lv == 'red' else '') + text, 'warn' if lv != 'ok' else 'ok')
    red = [text for lv, text in out if lv == 'red']
    if red:
        raise Fail('超过大小红线（tools/toolkit/budget.json；说明 doc/2026-11-04_OTA空间红线_GR与CAT1大小管控.md）：\n      ' +
                   '\n      '.join(red))


class Fail(Exception):
    pass


def decode(b):
    for enc in ('utf-8', 'gbk'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode('utf-8', 'replace')


def sh(cmd, log=None, env=None, timeout=900):
    r = subprocess.run([str(x) for x in cmd], capture_output=True, env=env, timeout=timeout)
    text = decode(r.stdout) + decode(r.stderr)
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text(text, encoding='utf-8')
    return r.returncode, text


def vtuple(v):
    return tuple(int(x) for x in v.split('.'))


def vlong(v):  # 1.5.8 -> 001.005.008
    return '.'.join(f'{int(x):03d}' for x in v.split('.'))


# ---------- 进度输出 ----------
class Run:
    def __init__(self, total):
        self.total, self.n, self.rows, self.t0 = total, 0, [], time.time()

    def step(self, title):
        self.n += 1
        self.cur, self.t = title, time.time()
        filled = int(24 * self.n / self.total)
        print(f'\n{C("cyan", "[" + "#" * filled + "-" * (24 - filled) + "]")} {C("bold", f"{self.n}/{self.total}")} {title}')

    def ok(self, msg='', level='ok'):
        sym = {'ok': C('green', '  ✓ '), 'warn': C('yellow', '  ! '), 'info': C('dim', '    ')}[level]
        print(sym + msg)
        self.rows.append((self.cur, level, msg))

    def done(self):
        print(C('dim', f'    用时 {time.time() - self.t:.1f} s'))


def need_ok(rc, text, what, keep=6):
    if rc != 0:
        errs = [l.strip() for l in text.splitlines() if 'ERROR' in l or '失败' in l or '错误' in l][:keep] or text.strip().splitlines()[-keep:]
        raise Fail(f'{what} 失败：\n      ' + '\n      '.join(errs))


# ---------- 选择位置 ----------
def pick(kind, title, initial):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        init = initial if initial and Path(initial).exists() else str(PROJECT)
        if kind in ('file', 'key', 'pub'):
            ft = {'file': [('GR 固件 HEX', '*.hex')], 'key': [('私钥', '*.key *.pem')], 'pub': [('公钥 XML', '*.xml')]}[kind]
            p = filedialog.askopenfilename(title=title, initialdir=str(Path(init).parent if Path(init).is_file() else init),
                                           filetypes=ft + [('全部文件', '*.*')])
        else:
            p = filedialog.askdirectory(title=title, initialdir=init)
        root.destroy()
        if p:
            return p
    except Exception:
        pass
    return input(f'{title}（输入路径）：').strip().strip('"')


# ---------- 设备（可选） ----------
def _gr_port():
    """SAM | 2026-11-09 | the COM number changes: --env YP_GR_PORT > configured (if present) > auto-detect; '' on failure so dev_read reports it."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ota'))
        import gr_port
        return gr_port.resolve(None, CFG.get('port'))
    except Exception as exc:
        print('  ! 串口：' + str(exc).splitlines()[0])
        return ''


def dev_read(port):
    """Query a running GR/CAT1 only; never power, reset or recover either device."""
    return _dev_read(port)


def _dev_read(port):
    # SAM | 2026-11-07 09:36 +08:00 | Read-only diagnostics must not reset a possibly active installation transaction.
    try:
        import serial
    except ImportError as exc:
        return None, f'缺 Python 模块：{exc}'
    try:
        stream = serial.Serial(port, 115200, timeout=0.1)
    except Exception as exc:
        return None, f'打不开 {port}：{exc}'
    patterns = (r'YP001_FW\|GR5526\|(\d+)\.(\d+)\.(\d+)\|(\d+)\|END',
                r'OTA_FS total=(\d+) used=(\d+) block=(\d+)')
    matches = []
    with stream:
        for command, pattern in zip(('fw_version', 'cat_at OTA_FS'), patterns):
            stream.write((command + '\r\n').encode())
            response, match, deadline = '', None, time.time() + 10
            while time.time() < deadline:
                response += stream.read(4096).decode('utf-8', 'replace')
                match = re.search(pattern, response)
                if match: break
            if not match:
                return None, f'{command} 无真实回应，设备启动/在线状态未知；未执行供电/复位'
            matches.append(match)
    gr, fs = matches
    total, used, block = map(int, fs.groups())
    return dict(version='.'.join(str(int(x)) for x in gr.groups()[:3]), build=int(gr.group(4)),
                total=total, used=used, block=block, free=(total - used) * block), ''


# ---------- 源码补丁（保持 CRLF，逐处必须恰好命中一次） ----------
def patch(path, pairs):
    b = Path(path).read_bytes().decode('utf-8-sig' if Path(path).read_bytes()[:3] == b'\xef\xbb\xbf' else 'utf-8')
    for pat, repl in pairs:
        b, n = re.subn(pat, repl, b, flags=re.M)
        if n != 1:
            raise Fail(f'{Path(path).name} 里找不到唯一的 {pat!r}（命中 {n} 处）：源码格式不是工具认识的样子')
    Path(path).write_bytes(b.encode('utf-8'))


def set_versions(src, version, build, source=None, target=None, md5=None):
    # SAM | 2026-11-10 | OTA is ready from the factory: only the identity is set; source/target/md5 are accepted for old callers and ignored.
    patch(src / 'main.lua', [
        (r'^(VERSION\s*=\s*)"[^"]*"', rf'\g<1>"{vlong(version)}"'),
        (r'^(PRODUCT_VERSION\s*=\s*)"[^"]*"', rf'\g<1>"{version}"'),
        (r'^(FW_RELEASE_BUILD\s*=\s*)\d+', rf'\g<1>{build}')])


CLEAN_BLOCK = '''-- SAM | {day} +08:00 | One-shot recovery (marker): drop the CAT1 OTA journal, candidate files and older clean markers left by earlier rounds. Added by ota_oneclick --clean-ota-log.
if not io.exists("{marker}") then
    for _, f in ipairs({{"/yp001_ota_state_0", "/yp001_ota_state_1", "/yp001_cat_fota_0", "/yp001_cat_fota_1"}}) do if io.exists(f) then os.remove(f) end end
    local c, ok, list = pcall(io.lsdir, "/", 100, 0)
    if c and ok and type(list) == "table" then for _, e in ipairs(list) do if type(e.name) == "string" and (e.name:match("^o[%w]+%.p$") or e.name:match("^yp001_clean_")) then os.remove("/" .. e.name) end end end
    io.writeFile("{marker}", "1")
end
'''


def add_cleanup(src, marker):
    p = src / 'main.lua'
    t = p.read_bytes().decode('utf-8')
    m = re.search(r'^local first_trial_profile=', t, re.M)
    if not m:
        raise Fail('main.lua 里找不到 first_trial_profile 赋值行')
    i = m.start()
    block = CLEAN_BLOCK.format(day=time.strftime('%Y-%m-%d'), marker=marker).replace('\n', '\r\n')
    p.write_bytes((t[:i] + block + t[i:]).encode('utf-8'))


def copy_cat1(src, dst):
    dst.mkdir(parents=True)
    for p in src.iterdir():
        if p.is_file():
            shutil.copy2(p, dst / p.name)
        elif p.is_dir() and p.name == 'soc':
            shutil.copytree(p, dst / 'soc')


def main_info(src):
    t = (src / 'main.lua').read_bytes().decode('utf-8-sig', 'replace')
    g = lambda pat: (re.search(pat, t, re.M) or [None, None])[1]
    return g(r'^PRODUCT_VERSION\s*=\s*"([^"]+)"'), g(r'^FW_RELEASE_BUILD\s*=\s*(\d+)'), g(r'^VERSION\s*=\s*"([^"]+)"')


# ---------- 主流程 ----------
def run_all(a, check_only=False):
    # SAM | 2026-11-07 09:36 +08:00 | Missing review must fail before tools/device access; flags cannot fabricate approval.
    if getattr(a, 'clean_ota_log', False) or getattr(a, 'auto_prune', False):
        raise Fail('禁止自动清除OTA/native事务；需要独立恢复方案和真实安全状态证据')
    review_arg = getattr(a, 'review_manifest', None)
    if not review_arg:
        raise Fail('必须提供 --review-manifest 精确评审清单；--reviewed-ota-change / --yes-attest 不能代替证据')
    try:
        review_path = release_gate.safe_path(PROJECT, review_arg)
        review_bytes = review_path.read_bytes()
        review_manifest = json.loads(review_bytes.decode('utf-8-sig'))
        if not isinstance(review_manifest, dict):
            raise release_gate.GateError('review manifest must be an object')
    except (release_gate.GateError, OSError, ValueError) as exc:
        raise Fail(f'评审清单无效：{exc}') from exc
    state = load(STATE_FILE, {})
    global KEY, PUB
    last = CFG.setdefault('last', {})
    if getattr(a, 'key', None):
        KEY = Path(a.key)
    if getattr(a, 'pub', None):
        PUB = Path(a.pub)
    if not KEY.exists() or not PUB.exists():
        raise Fail(f'找不到 OTA 签名密钥：{KEY} / {PUB}')
    for t in (GR_TOOL, PACK_TOOL, CAT_TOOL):
        if not t.exists():
            raise Fail(f'工具包缺文件：{t}')
    gr_hex = Path(a.gr_hex or pick('file', '选择 GR 编译生成的 HEX（未签名的 YP001_GR5526.hex）', last.get('gr_hex')))
    cat_src = Path(a.cat1_src or pick('dir', '选择 CAT1 源码目录（含 main.lua，目标版本）', last.get('cat1_src')))
    if not gr_hex.is_file() or not (cat_src / 'main.lua').is_file():
        raise Fail('GR HEX 或 CAT1 源码目录不对（目录里要有 main.lua）')
    last.update(gr_hex=str(gr_hex), cat1_src=str(cat_src), key=str(KEY), pub=str(PUB))
    (HERE / 'config.json').write_text(json.dumps(CFG, ensure_ascii=False, indent=2), encoding='utf-8')
    total = 8 if check_only else 12
    R = Run(total)
    t_all = time.time()
    tmp = Path(os.environ.get('TEMP', '.')) / f'ota_oneclick_{os.getpid()}'
    tmp.mkdir(parents=True, exist_ok=True)

    R.step('读取 GR 固件和 CAT1 源码的版本')
    rc, text = sh([GR_TOOL, 'check', gr_hex], tmp / 'gr_check.txt')
    m = re.search(r'YP001_FW\|GR5526\|(\d+)\.(\d+)\.(\d+)\|(\d+)\|END', text)
    need_ok(rc, text, 'GR 固件检查（请确认选的是 Keil/GCC 编译出的未签名 HEX）')
    if not m:
        raise Fail('GR 固件里没有 YP001_FW 版本标记')
    to_v, to_b = '.'.join(str(int(x)) for x in m.groups()[:3]), int(m.group(4))
    body = int((re.search(r'应用正文 (\d+) 字节', text) or [0, 0])[1])
    cv, cb, cl = main_info(cat_src)
    R.ok(f'GR 固件 {to_v}/b{to_b}，应用正文 {body} 字节（上限 441464，余 {441464 - body}）')
    R.ok(f'CAT1 源码 {cv}/b{cb}')
    B, sizes = budget.load(), {}
    prev = (state.get('last_success') or {}).get('sizes')
    apply_budget(R, B, prev, sizes, gr_body=body)
    if (cv, int(cb or -1)) != (to_v, to_b):
        raise Fail(f'GR 固件是 {to_v}/b{to_b}，CAT1 源码是 {cv}/b{cb}：两端版本必须相同（用「固件版本与空间」工具一起改版本，GR 重新编译）')
    if body > 441464:
        raise Fail('GR 固件超过 441464 字节槽')
    if 441464 - body < 4096:
        R.ok('GR 固件已用到槽的 99% 以上，下一版很容易超', 'warn')
    R.done()

    R.step('OTA 规则检查（对照实板验证过的代码）')
    base = P(state['baseline_dir'])
    res = ota_guard.check(cat_src, base, versions_free=True, legacy_ok=True)
    blocks = [r for r in res if r[0] == 'BLOCK']
    # SAM | 2026-11-07 09:31 +08:00 | Only exact R1 changes are reviewable; all other BLOCK gates remain hard.
    try:
        input_identity = release_gate.validate(PROJECT, review_manifest, cat_src, base, gr_hex, res)
        release_gate.check_known_identity(PROJECT, P(CFG['out_root']), to_v, to_b, input_identity)
    except release_gate.GateError as exc:
        raise Fail(f'发布门禁拒绝：{exc}') from exc
    R.ok(f'GR/CAT1/SDK 原始字节与精确评审一致；BLOCK {len(blocks)}（仅允许已审查 R1）')
    miss = must_have(cat_src)
    if miss:
        raise Fail('CAT1 源码缺少必检功能（不能用 --reviewed-ota-change 放行）：\n      ' + '\n      '.join(miss))
    R.ok(f'必检功能齐全：OTA 发令前清日志、OTA 中不写日志、保电锁（{len(MUST_HAVE)} 项）')
    for r in res:
        if r[0] == 'WARN':
            R.ok(f'{r[1]} {r[2]} {r[3][:90]}', 'warn')
    R.done()

    R.step('评审证据（与设备验收状态分开）')
    # SAM | 2026-11-07 09:31 +08:00 | Review attests activation + baseline Boot capability, never target device success.
    proof = review_manifest['attestation']
    at = dict(confirmed_by_user=False, reviewer=proof['reviewer'],
              evidence=proof['reason'], confirmed_at='精确清单证据', source_sha256=input_identity['candidate_sha256'])
    R.ok(f'评审主体 {at["reviewer"]}；候选实板 OTA/业务验收仍独立记录')
    R.done()

    R.step('确定设备当前版本（升级起点）')
    dev = None
    if not a.no_device and a.from_ver is None:
        dev, why = dev_read(_gr_port())
        if dev:
            R.ok(f'读到设备：GR {dev.get("version")}/b{dev.get("build")}，CAT1 可用 {dev["free"]} 字节（已用 {dev["used"]}/{dev["total"]} 块）')
        else:
            R.ok(f'没读到设备（{why}），用记录里的版本', 'warn')
    src_v = a.from_ver or (dev or {}).get('version') or state.get('device', {}).get('version')
    src_b = int(a.from_build or (dev or {}).get('build') or state.get('device', {}).get('build') or 0)
    if not src_v or not src_b:
        raise Fail('不知道设备当前版本：加 --from 1.5.8 --from-build 12，或接上板子')
    R.ok(f'升级范围 {src_v}/b{src_b} → {to_v}/b{to_b}')
    if vtuple(to_v) <= vtuple(src_v) or to_b <= src_b:
        raise Fail('目标版本和 build 必须都高于设备当前版本')
    if state.get('device', {}).get('version') and (state['device']['version'], state['device']['build']) != (src_v, src_b):
        R.ok(f'注意：记录里的设备版本是 {state["device"]["version"]}/b{state["device"]["build"]}，与本次起点不同', 'warn')
    R.done()

    R.step('CAT1 空间和主机测试')
    work_probe = tmp / 'probe_receiver'  # 2026-11-10: 目标源码的副本（身份按设备当前版本）：容量和流程测试按它查
    copy_cat1(cat_src, work_probe)
    set_versions(work_probe, src_v, src_b, src_v, to_v, 'f' * 32)
    rc, text = sh([CAT_TOOL, '--source', work_probe, '--check-only'], tmp / 'cat_check.txt')
    need_ok(rc, text, 'CAT1 源码检查（Cat1UsbImport）')
    lm = re.search(r'LuaDB (\d+)/(\d+) 字节，余 (\d+)', text)
    R.ok(f'CAT1 脚本区 {lm.group(1)}/{lm.group(2)} 字节，余 {lm.group(3)}' if lm else 'CAT1 源码检查通过')
    if lm:
        apply_budget(R, B, prev, sizes, luadb=int(lm.group(1)))
    env = dict(os.environ, PYTHONPATH=str(P(CFG['python_deps'])), PYTHONIOENCODING='utf-8')
    host = []
    for name, cmd in (('全链路 OTA 流程', [sys.executable, PROJECT / 'tools/ota/test_ota152_flow.py', work_probe]),
                      ('数据快照', [sys.executable, PROJECT / 'tools/ota/bench/test_inv_dirs.py', work_probe])):
        rc, text = sh(cmd, tmp / f'host_{len(host)}.txt', env=env)
        need_ok(rc, text, f'主机测试「{name}」')
        host.append(f'{name}：PASS（一键工具 {time.strftime("%Y-%m-%d")}）')
        R.ok(f'主机测试「{name}」通过')
    R.done()

    if check_only:
        try:
            if review_path.read_bytes() != review_bytes:
                raise release_gate.GateError('review manifest changed during checks')
            release_gate.validate(PROJECT, review_manifest, cat_src, base, gr_hex, res)
        except release_gate.GateError as exc:
            raise Fail(f'检查结束输入复核拒绝：{exc}') from exc
        R.step('设备可用空间')
        free = a.free or (dev or {}).get('free')
        if free is None and not a.no_device:
            dev, why = dev_read(_gr_port())
            free = (dev or {}).get('free')
        need = body + 904 + B['ota_reserve'] + B['ota_growth_margin']
        if free is None:
            R.ok(f'没读到设备空间（打包时需要 ≥ {need} 字节，用 --free 或接板子）', 'warn')
        else:
            apply_budget(R, B, None, {}, gr_body=body, free=free)
        R.done()
        print('\n' + C('green', '检查完成：没有发现会阻止打包的问题。') + C('dim', f'（共 {time.time() - t_all:.0f} s，没有生成发布包）'))
        return None

    stamp = time.strftime('%Y%m%d_%H%M')
    out = P(CFG['out_root']) / f'ota_{src_v}_to_{to_v}_{stamp}'
    if out.exists():
        raise Fail(f'输出目录已存在：{out}（一分钟内重复运行？）')
    try:
        # SAM | 2026-11-07 09:31 +08:00 | Atomic reservation prevents release_id overwrite, including concurrent runs.
        release_gate.reserve_output(out)
    except release_gate.GateError as exc:
        raise Fail(str(exc)) from exc
    work = out / 'work'
    work.mkdir()
    d_gr, d_cat, d_up = out / '1_GR烧写文件', out / '2_CAT1刷机目录', out / '3_上传平台的升级包'
    shutil.copytree(tmp, work / 'logs_check')

    R.step('签名 GR 固件')
    gdir = work / 'gr'
    rc, text = sh([GR_TOOL, 'sign', gr_hex, '--out', gdir, '--private', KEY, '--expect-version', to_v, '--format', 'both'], work / 'logs' / 'gr_sign.txt')
    need_ok(rc, text, 'GR 签名')
    sbin = next(gdir.glob('GR5526_*_signed.bin'), None)
    shex = next(gdir.glob('GR5526_*_signed.hex'), None)
    if not sbin:
        raise Fail('签名后没有找到 signed.bin')
    R.ok(f'{sbin.name}（{sbin.stat().st_size} 字节）' + (f' 和 {shex.name}' if shex else ''))
    R.done()

    R.step('生成升级包里的 CAT1 包')
    tgt = work / 'target_source'
    copy_cat1(cat_src, tgt)
    set_versions(tgt, to_v, to_b, src_v, to_v, '0' * 32)
    cdir = work / 'cat1'
    basis = f'一键工具 {time.strftime("%Y-%m-%d")}：{src_v}→{to_v}；对照实板验证版 {base.name}'
    cmd = [PACK_TOOL, 'cat1', '--source', tgt, '--out', cdir, '--basis', basis]
    for h in host:
        cmd += ['--host-check', h]
    rc, text = sh(cmd, work / 'logs' / 'pack_cat1.txt')
    need_ok(rc, text, '生成 CAT1 包')
    sota, review = next(cdir.glob('CAT1_*.sota'), None), cdir / 'review.json'
    if not sota or not review.exists():
        raise Fail('没有生成 .sota 或 review.json')
    R.ok(f'{sota.name}（{sota.stat().st_size} 字节）')
    apply_budget(R, B, prev, sizes, sota=sota.stat().st_size)
    R.done()

    R.step('生成签名授权文件')
    auth = work / 'ota_authorization.json'
    rc, text = sh([PACK_TOOL, 'auth', '--gr', sbin, '--cat', sota, '--review', review, '--source', src_v, '--out', auth,
                   '--private', KEY, '--public', PUB, '--reviewed', '--boot-verified', '--basis', f'{basis}；{at.get("evidence", "")}'],
                  work / 'logs' / 'pack_auth.txt')
    need_ok(rc, text, '生成授权文件')
    R.ok(f'授权范围 {src_v} → {to_v}')
    R.done()

    R.step('检查设备空间并打包')
    free = a.free if a.free else None
    if free is None and not a.no_device:
        if dev is None:
            dev, why = dev_read(_gr_port())
        free = (dev or {}).get('free')
    if free is None:
        raise Fail('没有设备空间读数：接上板子（GR 命令口没被别的程序占用），或用 --free <字节>（必须是 cat_at OTA_FS 的真实读数，不能估）')
    R.ok(f'设备可用空间 {free} 字节' + ('' if not a.free else '（手填）'))
    apply_budget(R, B, None, {}, gr_body=body, free=free)
    pdir = work / 'pkg'
    rc, text = sh([PACK_TOOL, 'pack', '--gr', sbin, '--cat', sota, '--review', review, '--auth', auth, '--free', free, '--out', pdir,
                   '--private', KEY, '--public', PUB], work / 'logs' / 'pack.txt')
    if rc != 0 and re.search(r'超过CAT1可用文件区|空间', text):
        raise Fail(f'设备空间不够（可用 {free}，需要 ≥ {body + 904 + 16384}）：停止打包，按独立恢复方案核对事务和可用空间')
    need_ok(rc, text, '打包')
    zp = next(pdir.glob('YP001_*---*_FIRST.zip'), None)
    if not zp:
        raise Fail('没有生成升级包 zip')
    md5 = hashlib.md5(zp.read_bytes()).hexdigest()
    R.ok(f'{zp.name}（{zp.stat().st_size} 字节），MD5 {md5}')
    R.done()

    R.step('独立验证升级包')
    rc, text = sh([PACK_TOOL, 'verify', '--zip', zp, '--public', PUB, '--auth', auth], work / 'logs' / 'pack_verify.txt')
    need_ok(rc, text, '验证升级包')
    R.ok('签名、清单、组件摘要、版本和大小检查通过')
    R.done()

    R.step('生成 CAT1 刷机目录（目标版本的完整脚本，出厂用）')
    fac = work / 'factory_source'
    copy_cat1(tgt, fac)
    if a.clean_ota_log:
        add_cleanup(fac, f'/yp001_clean_{time.strftime("%m%d%H%M")}')
        R.ok('已加入一次性清理块：刷机后第一次开机清掉 OTA 状态、候选文件和旧清理标记', 'warn')
    rout = work / 'receiver_out'
    rc, text = sh([CAT_TOOL, '--source', fac, '--out', rout, '--force'], work / 'logs' / 'cat_import.txt')
    need_ok(rc, text, '生成 USB_IMPORT')
    integ = load(rout / 'integrity.json', {})
    R.ok(f'LuaDB {integ.get("luadb_bytes")}/{integ.get("capacity")}，版本 {to_v}/b{to_b}（OTA 不需要刷它；出厂或台架换新基线时用）')
    R.done()

    R.step('整理输出')
    # SAM | 2026-11-07 09:31 +08:00 | Re-read originals after host/build work so stale reviews cannot publish.
    try:
        if review_path.read_bytes() != review_bytes:
            raise release_gate.GateError('review manifest changed while packaging')
        if release_gate.validate(PROJECT, review_manifest, cat_src, base, gr_hex, res) != input_identity:
            raise release_gate.GateError('inputs changed while packaging')
        artifact_identity = dict(gr_signed_sha256=release_gate.file_hash(sbin), package_sha256=release_gate.file_hash(zp))
        release_gate.check_known_identity(PROJECT, P(CFG['out_root']), to_v, to_b, input_identity, artifact_identity)
    except release_gate.GateError as exc:
        raise Fail(f'发布前复核拒绝：{exc}') from exc
    d_gr.mkdir(); d_up.mkdir()
    for f in (sbin, shex):
        if f:
            shutil.copy2(f, d_gr / f.name)
    for f in gdir.glob('*'):
        if f.suffix not in ('.bin', '.hex') and f.is_file():
            shutil.copy2(f, d_gr / f.name)
    shutil.copytree(rout / 'USB_IMPORT', d_cat / 'USB_IMPORT')
    shutil.copy2(rout / 'integrity.json', d_cat / 'integrity.json')
    shutil.copy2(zp, d_up / zp.name)
    target_source_files = release_gate.tree_files(tgt, 'cat1')
    run_info = dict(target_source_files=target_source_files, target_source_sha256=release_gate.digest(target_source_files),
                    artifact_files=release_gate.delivery_files(out), from_version=src_v, from_build=src_b, to_version=to_v, to_build=to_b, package=zp.name, md5=md5,
                    artifact_identity=artifact_identity, input_identity=input_identity, review_manifest_sha256=release_gate.file_hash(review_path),
                    device_verification='pending', out=str(out), target_source=str(tgt), created=time.strftime('%Y-%m-%d %H:%M'), free=free, sizes=sizes)
    shutil.copy2(review_path, out / 'review_manifest.json')
    (out / 'run.json').write_text(json.dumps(run_info, ensure_ascii=False, indent=2), encoding='utf-8')
    state['last_run'] = run_info
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    write_report(out, R, run_info, res, body, free, zp, sbin, d_cat, at, a)
    R.ok(f'输出目录 {out}')
    R.done()

    print('\n' + C('green', C('bold', f'全部完成（{time.time() - t_all:.0f} s）')))
    print(f'  {C("bold", "GR 烧写文件")}      {d_gr}')
    print(f'  {C("bold", "CAT1 刷机目录")}    {d_cat / "USB_IMPORT"}   （出厂/换新基线用，OTA 不需要刷）')
    print(f'  {C("bold", "上传平台的包")}      {d_up / zp.name}   MD5 {md5}')
    print(C('dim', f'  报告：{out / "报告.md"}'))
    print(C('yellow', '  下一步：刷 CAT1 → 上传升级包把下载地址发给 Claude → Claude 预检并发起 OTA；成功后在菜单选「记录 OTA 已成功」'))
    return out


def write_report(out, R, info, res, body, free, zp, sbin, d_cat, at, a):
    L = [f'# 整机 OTA 一键生成报告 {info["created"]}', '',
         f'升级范围：**{info["from_version"]}/b{info["from_build"]} → {info["to_version"]}/b{info["to_build"]}**', '',
         '| 产物 | 位置 |', '|---|---|',
         f'| GR 烧写文件 | `1_GR烧写文件\\{sbin.name}`（及 .hex） |',
         f'| CAT1 刷机目录 | `2_CAT1刷机目录\\USB_IMPORT`（目标版本完整脚本：出厂或台架换新基线用，**OTA 不需要刷它**） |',
         f'| 上传平台的升级包 | `3_上传平台的升级包\\{zp.name}`，**MD5 `{info["md5"]}`** |', '',
         f'设备 CAT1 可用空间 {free} 字节；GR 应用正文 {body} 字节。', '', '## 每一步', '']
    cur = None
    for title, lv, msg in R.rows:
        if title != cur:
            L.append(f'### {title}'); cur = title
        L.append(f'- {"✓" if lv == "ok" else "⚠" if lv == "warn" else "·"} {msg}')
    L += ['', '## 需要人知道的', '',
          f'- 精确清单评审主体 {at.get("reviewer")}；依据：{at.get("evidence", "")}；目标实板验收仍 pending。',
          '- 主机测试通过 ≠ 实板通过；同事新增的业务功能没有因为这次打包而被实板验证。',
          '- 升级包的 GR 部分与 `1_GR烧写文件` 里的是同一份签名镜像。',
          '- 清理 OTA 历史' + ('：刷机目录带一次性清理块（刷机后首次开机执行）。' if a.clean_ota_log else '：刷机目录没带清理块；设备空间由本次读数保证。'), '',
          '## 下一步', '',
          '1. 上传 `3_上传平台的升级包` 里的 zip 到平台，核对 MD5；设备在线，后台推送（不需要刷接收端、不需要逐台刷机）。',
          '2. 把下载地址发给 Claude（核对 MD5、预检、发起 OTA）。',
          '3. 实板通过后，done 必须提供 --device-evidence、--device-reviewer、--device-reason，独立记录实际验收范围。']
    (out / '报告.md').write_text('\n'.join(L) + '\n', encoding='utf-8')


def cmd_done(a):
    # SAM | 2026-11-07 09:31 +08:00 | A command invocation is not successful-device evidence.
    if not getattr(a, 'device_evidence', None) or not getattr(a, 'device_reviewer', None) or not getattr(a, 'device_reason', None):
        raise Fail('done 需要 --device-evidence、--device-reviewer、--device-reason；自动确认参数不能生成实板成功')
    state = load(STATE_FILE, {})
    lr = state.get('last_run')
    if not lr:
        raise Fail('没有最近一次一键生成记录')
    try:
        evidence_path = release_gate.safe_path(PROJECT, a.device_evidence)
        device_proof = json.loads(evidence_path.read_text(encoding='utf-8-sig'))
        release_gate.verify_run_files(PROJECT, lr)
        release_gate.validate_device(PROJECT, device_proof, lr)
        if device_proof['reviewer'] != a.device_reviewer or device_proof['reason'] != a.device_reason:
            raise release_gate.GateError('CLI reviewer/reason differs from device record')
        device_proof = dict(device_proof, record_path=a.device_evidence, record_sha256=release_gate.file_hash(evidence_path))
    except (release_gate.GateError, OSError, ValueError) as exc:
        raise Fail(f'实板证据无效：{exc}') from exc
    state['device'] = {'version': lr['to_version'], 'build': lr['to_build']}
    state['last_success'] = {'at': time.strftime('%Y-%m-%d %H:%M'), 'package': lr['package'], 'md5': lr['md5'],
                             'sizes': lr.get('sizes')}  # SAM | 2026-11-04 +08:00 | growth baseline for budget.py
    state['last_success']['promotion'] = 'pending_immutable_baseline'
    state['last_success']['candidate_source'] = lr['target_source']
    state['last_success']['device_proof'] = device_proof
    state['last_success']['input_identity'] = lr.get('input_identity')
    state['last_success']['artifact_identity'] = lr.get('artifact_identity')
    # Device evidence is separate from the source review attestation; do not invent state-machine outcomes.
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    print(C('green', f'已记录：设备当前版本 {lr["to_version"]}/b{lr["to_build"]}，实板证据已绑定；冻结基线晋升待单独完成。'))


def cmd_status(a):
    s = load(STATE_FILE, {})
    print(C('bold', '== 当前记录 =='))
    print(f'  设备当前版本   {s.get("device", {}).get("version")}/b{s.get("device", {}).get("build")}')
    print(f'  验证基线       {s.get("baseline_dir")}')
    at = s.get('attest', {})
    print(f'  评审声明       {"已确认 " + str(at.get("confirmed_at")) if at.get("confirmed_by_user") else C("yellow", "未确认")}')
    print(f'  依据           {at.get("evidence")}')
    if s.get('last_run'):
        print(f'  最近一次生成   {s["last_run"]["from_version"]}→{s["last_run"]["to_version"]}  {s["last_run"]["created"]}  MD5 {s["last_run"]["md5"]}')
        print(f'                 {s["last_run"]["out"]}')


def cmd_device(a):
    info, why = dev_read(_gr_port())
    if not info:
        raise Fail(why)
    print(f'GR {info.get("version")}/b{info.get("build")}；CAT1 已用 {info["used"]}/{info["total"]} 块，可用 {info["free"]} 字节')


MENU = [('run', '一键生成（选 GR HEX 和 CAT1 源码 → GR 烧写文件 + CAT1 刷机目录 + 上传包）'),
        ('check', '只检查，不生成文件（版本 / OTA 规则 / 空间 / 主机测试）'),
        ('device', '读设备版本和 CAT1 可用空间（接板子，串口自动识别）'),
        ('done', 'OTA 实板成功后：记录设备证据（冻结基线另行晋升）'),
        ('status', '查看当前记录')]


def build_parser():
    ap = argparse.ArgumentParser(description='YP001 整机 OTA 一键工具；不带参数显示菜单')
    ap.add_argument('cmd', nargs='?', choices=[m[0] for m in MENU])
    ap.add_argument('--gr-hex'); ap.add_argument('--cat1-src')
    ap.add_argument('--key', help='OTA 签名私钥文件'); ap.add_argument('--pub', help='OTA 公钥 XML 文件')
    ap.add_argument('--from', dest='from_ver', help='设备当前版本，如 1.5.8（默认读设备，读不到用记录）')
    ap.add_argument('--from-build', type=int)
    ap.add_argument('--free', type=int, help='cat_at OTA_FS 的真实可用字节（不接板子时用）')
    ap.add_argument('--no-device', action='store_true', help='不连板子')
    ap.add_argument('--auto-prune', action='store_true', help='旧参数已禁用：需独立恢复方案')
    ap.add_argument('--clean-ota-log', action='store_true', help='旧参数已禁用：需独立恢复方案')
    ap.add_argument('--yes-attest', action='store_true', help='兼容旧参数；不生成用户确认或实板证据')
    ap.add_argument('--reviewed-ota-change', action='store_true', help='兼容旧参数；不能绕过 BLOCK，必须提供精确评审清单')
    ap.add_argument('--device-evidence', help='done：工作区相对路径，实际实板验收记录')
    ap.add_argument('--device-reviewer', help='done：验收记录人')
    ap.add_argument('--device-reason', help='done：明确本次实际通过范围及未覆盖项')
    ap.add_argument('--review-manifest', help='工作区相对路径：绑定 GR/CAT1/SDK、构建及基线 Boot 证据的 JSON 清单')
    return ap


def pick_paths(extra):
    """选 1/2 后让用户确认或重选三个位置：GR HEX、CAT1 源码、签名密钥。"""
    last = CFG.get('last', {})
    items = [('GR HEX（未签名）', 'file', '--gr-hex', last.get('gr_hex')),
             ('CAT1 源码目录', 'dir', '--cat1-src', last.get('cat1_src')),
             ('OTA 私钥文件', 'key', '--key', last.get('key') or str(KEY)),
             ('OTA 公钥 XML', 'pub', '--pub', last.get('pub') or str(PUB))]
    print('\n' + C('bold', '请确认四个位置') + C('dim', '（已设置的回车沿用；未设置的自动弹窗）'))
    for name, kind, flag, cur in items:
        while True:
            shown = cur if cur and Path(cur).exists() else None
            if shown:
                s = input(f'  {C("cyan", name)}  [{C("green", shown)}]（回车=用这个，c=弹窗重选）：').strip()
            else:
                print(f'  {C("cyan", name)}  {C("yellow", "未设置，请在弹出的窗口里用鼠标选择...")}')
                s = 'c'
            if s.lower() == 'c' or (not s and not shown):
                if kind == 'key':
                    cur = pick('key', '选择 OTA 私钥文件（.key）', cur)
                elif kind == 'pub':
                    cur = pick('pub', '选择 OTA 公钥 XML', cur)
                else:
                    cur = pick(kind, f'选择 {name}', cur)
            elif s:
                cur = s.strip('"')
            if cur and Path(cur).exists():
                break
            print(C('red', '    路径不存在，请重选。'))
        extra += [flag, cur]
    return extra


def dispatch(a):
    try:
        {'run': lambda: run_all(a), 'check': lambda: run_all(a, True), 'done': lambda: cmd_done(a),
         'status': lambda: cmd_status(a), 'device': lambda: cmd_device(a)}[a.cmd]()
        return 0
    except Fail as e:
        print('\n' + C('red', C('bold', '停止：')) + C('red', str(e)))
        return 1
    except subprocess.TimeoutExpired as e:
        print('\n' + C('red', f'停止：工具超时 {e.cmd[0]}'))
        return 1


if __name__ == '__main__':
    ap = build_parser()
    a = ap.parse_args()
    if a.cmd:
        sys.exit(dispatch(a))
    while True:
        print('\n' + C('bold', 'YP001 整机 OTA 一键工具') + C('dim', '（不改源码目录，所有产物在新目录）') + '\n')
        for i, (c, d) in enumerate(MENU, 1):
            print(f'  {C("cyan", i)}. {d}')
        s = input('\n选择编号（回车退出）：').strip()
        if not s:
            break
        if not (s.isdigit() and 1 <= int(s) <= len(MENU)):
            print(C('red', '没有这个编号。')); continue
        extra = []
        if MENU[int(s) - 1][0] in ('run', 'check') and input('接了板子并且 GR 命令口没被占用吗？(y=读设备版本和空间，其他=不连板子)：').strip().lower() != 'y':
            extra = ['--no-device']
        if MENU[int(s) - 1][0] in ('run', 'check'):
            extra = pick_paths(extra)
        a = ap.parse_args([MENU[int(s) - 1][0]] + extra)
        if a.cmd in ('run', 'check') and a.no_device and not a.free and not a.from_ver:
            v = input('设备当前版本（回车=用记录）：').strip()
            if v:
                a.from_ver = v; a.from_build = int(input('设备当前 build：').strip())
            f = input('cat_at OTA_FS 的可用字节（回车=不填，只在“一键生成”时必须）：').strip()
            if f:
                a.free = int(f)
        dispatch(a)
        input(C('dim', '\n按回车返回主菜单...'))
