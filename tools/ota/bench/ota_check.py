"""SAM | 2026-11-10 | One page instead of five commands: is the package safe to push (pre), and did the OTA really succeed (post).

  python ota_check.py pre  --zip <本地包.zip> [--url <平台下载地址>] [--auth <ota_authorization.json>] [--no-device]
  python ota_check.py post --target 1.5.31 [--no-jlink]

pre  : reads source/target from the package itself, checks name/range, downloads the platform file and compares it byte for byte, runs the
       3 号工具 verify, reads the device (GR/CAT1 version, OTA state, free space) and requires: source == the version BOTH firmwares run now,
       target higher, OTA idle, enough CAT1 space, and that the number typed into the package is not more than the device really has.
post : both firmwares == target, OTA idle, outbox empty, owner COMPLETE/CAT1/success == target, Boot CONFIRMED, no install error.
The GR port must be free (stop keep_cat1.py first). Exit code 0 = every check passed, 1 = something failed. Read-only (one CAT1 wake-up reset).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import device_probe  # noqa: E402

results = []


def add(level, text):
    results.append((level, text))
    print({'PASS': '[通过]', 'FAIL': '[失败]', 'WARN': '[提醒]', 'INFO': '[信息]'}[level], text, flush=True)


def vnum(v):
    p = [int(x) for x in v.split('.')]
    return p[0] * 1000000 + p[1] * 1000 + p[2]


def read_bundle(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = {i.filename: i.file_size for i in z.infolist()}
        b = json.loads(z.read('bundle.json').decode('utf-8'))
    return b, names


def find_tool():
    for c in (ROOT / 'YP001_工具包' / '3_整机OTA打包' / 'YpOtaPack.exe',):
        if c.is_file():
            return c
    return None


def pre(a):
    zp = Path(a.zip)
    if not zp.is_file():
        add('FAIL', f'找不到本地包 {zp}')
        return
    b, names = read_bundle(zp)
    src, tgt = b.get('source_version'), b.get('target_version')
    gr_size = names.get('GR5526/payload.bin', 0)
    add('INFO', f'包 {zp.name}：{src} → {tgt}，GR 镜像 {gr_size} 字节，包内记录的 CAT1 可用空间 {b.get("cat_free_operator_input")}')
    if f'{src}---{tgt}' not in zp.name:
        add('FAIL', f'包名和包里的版本范围不一致：包里是 {src}---{tgt}')
    if not (src and tgt and re.match(r'^\d+\.\d+\.\d+$', src) and re.match(r'^\d+\.\d+\.\d+$', tgt)):
        add('FAIL', '包里的源/目标版本格式不对')
        return
    if vnum(tgt) <= vnum(src):
        add('FAIL', f'目标版本 {tgt} 必须高于源版本 {src}')
    else:
        add('PASS', f'目标版本 {tgt} 高于源版本 {src}')

    if a.url:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(a.url).query)
        url_md5 = (q.get('md5') or [''])[0].lower()
        data = urllib.request.urlopen(a.url, timeout=90).read()
        got = hashlib.md5(data).hexdigest()
        local = hashlib.md5(zp.read_bytes()).hexdigest()
        add('PASS' if got == url_md5 else 'FAIL', f'平台文件 MD5 {got}（地址里写的 {url_md5}）')
        add('PASS' if got == local else 'FAIL', f'平台文件与本地包{"字节一致" if got == local else "不一致，本地 MD5 " + local}')
        Path(tempfile.gettempdir(), 'ota_check_dl.zip').write_bytes(data)

    tool = find_tool()
    auth = Path(a.auth) if a.auth else zp.with_name('ota_authorization.json')
    pub = ROOT / 'OTA_keys' / 'OTA_TEST_PUBLIC.xml'
    if tool and auth.is_file() and pub.is_file():
        r = subprocess.run([str(tool), 'verify', '--zip', str(zp), '--public', str(pub), '--auth', str(auth)], capture_output=True)
        add('PASS' if r.returncode == 0 else 'FAIL', f'3 号工具验证压缩包（授权 {auth.name}）{"通过" if r.returncode == 0 else "失败，请单独运行 verify 看原因"}')
    else:
        add('WARN', '没有做 3 号工具验证（找不到工具、授权文件或公钥）：请手工点"④ 验证压缩包"')

    if a.no_device:
        add('INFO', '按要求没有读设备')
        return
    d = device_probe.probe(reset=not a.no_reset)
    gv, cv = d.get('gr_version'), d.get('cat1_version')
    add('INFO', f'设备：GR {gv}/b{d.get("gr_build")}，CAT1 {cv}，IMEI {d.get("imei")}')
    if gv != src or cv != src:
        add('FAIL', f'包的源版本是 {src}，但设备 GR={gv}、CAT1={cv}：设备会拒绝（SOURCE_VERSION_MISMATCH），要重新打包，源版本填设备真实版本')
    else:
        add('PASS', f'设备两端都是 {src}，和包的源版本一致')
    add('PASS' if d.get('fota_state') == 'IDLE' else 'FAIL', f'设备 OTA 状态 {d.get("fota_state")}（要求 IDLE）')
    add('PASS' if d.get('outbox') == 0 else 'WARN', f'OTA_OUTBOX={d.get("outbox")}（0 最好；1 是结果消息在排队，一般等一会儿会清空）')
    free = d.get('fs_free')
    need = gr_size + 16384 * 2
    if free is None:
        add('WARN', '没读到 CAT1 可用空间')
    else:
        add('PASS' if free >= need else 'FAIL', f'CAT1 可用空间 {free}，需要 ≥ {need}（GR 镜像 {gr_size} + 保留 16384 + 余量 16384）')
        typed = b.get('cat_free_operator_input')
        if isinstance(typed, int) and typed > free:
            add('FAIL', f'打包时填的可用空间 {typed} 比设备实际的 {free} 多：打包检查被放宽了，要用真实值重新打包')


def post(a):
    tgt = a.target
    d = device_probe.probe(reset=not a.no_reset)
    gv, cv = d.get('gr_version'), d.get('cat1_version')
    add('PASS' if gv == tgt else 'FAIL', f'GR 版本 {gv}/b{d.get("gr_build")}（目标 {tgt}）')
    add('PASS' if cv == tgt else 'FAIL', f'CAT1 版本 {cv}（目标 {tgt}）')
    add('PASS' if d.get('fota_state') == 'IDLE' else 'FAIL', f'OTA 状态 {d.get("fota_state")}（要求 IDLE）')
    add('PASS' if d.get('outbox') == 0 else 'WARN', f'OTA_OUTBOX={d.get("outbox")}（刚升完可能是 1，稍后应为 0）')
    if 'fs_free' in d:
        add('INFO', f'CAT1 已用 {d["fs_used"]} 块，可用 {d["fs_free"]} 字节')
    if a.no_jlink:
        add('INFO', '按要求没有用 J-Link 读 owner 和 Boot')
        return
    r = subprocess.run([sys.executable, str(HERE.parent / 'gr_ota_probe.py')], capture_output=True, text=True, timeout=150)
    try:
        j = json.loads(r.stdout)
        o, jr = j['owner_latest'], j['journal_latest']
    except Exception:
        add('FAIL', 'J-Link 没读到 owner/Boot（J-Link 没接好，或 GR 正在复位）')
        return
    ok = o['phase'] == 'COMPLETE' and o['target'] == 'CAT1' and o['outcome'] == 'success' and o['actual'] == tgt
    add('PASS' if ok else 'FAIL', f'owner：{o["phase"]} / {o["target"]} / {o["outcome"]}，实际版本 {o["actual"]}，源 {o["source"]}，代号 {o["generation"]}')
    add('PASS' if jr['state'] == 'CONFIRMED' else 'FAIL', f'Boot 日志：{jr["state"]}（代号 {jr["generation"]}）')
    add('PASS' if not j.get('install_error') else 'FAIL', f'安装错误：{j.get("install_error")}')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pre')
    p.add_argument('--zip', required=True)
    p.add_argument('--url')
    p.add_argument('--auth')
    p.add_argument('--no-device', action='store_true')
    p.add_argument('--no-reset', action='store_true')
    q = sub.add_parser('post')
    q.add_argument('--target', required=True)
    q.add_argument('--no-jlink', action='store_true')
    q.add_argument('--no-reset', action='store_true')
    a = ap.parse_args()
    try:
        (pre if a.cmd == 'pre' else post)(a)
    except Exception as e:  # noqa: BLE001 - one readable line instead of a traceback
        add('FAIL', f'检查没能做完：{type(e).__name__}: {e}')
    bad = [t for lv, t in results if lv == 'FAIL']
    print('\n结论：' + ('全部通过' + ('，可以推送' if a.cmd == 'pre' else '，OTA 成功') if not bad else f'有 {len(bad)} 项失败，' + ('不要推送' if a.cmd == 'pre' else 'OTA 没有确认成功')))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
