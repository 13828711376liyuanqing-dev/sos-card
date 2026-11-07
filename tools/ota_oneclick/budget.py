"""SAM | 2026-11-04 +08:00 | YP001 OTA size red lines (tools/toolkit/budget.json): GR signed image, CAT1 LuaDB, CAT1 .sota, CAT1 free
space at OTA precheck, and growth against the last board-verified release. Used by oneclick.py (red = stop packaging) and
standalone after a build:
    python budget.py --gr-hex <未签名 HEX> --cat1-src <CAT1 源码目录> [--free <cat_at OTA_FS 可用字节>]
Exit 0 = no red line crossed, 1 = red."""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# SAM | 2026-11-04 +08:00 | One master file for the one-click tool and the toolkit exes (make_toolkit copies it to the toolkit root).
BUDGET_FILE = HERE.parent / 'toolkit' / 'budget.json'
SIGNATURE = 904


def load():
    b = json.loads(BUDGET_FILE.read_text(encoding='utf-8'))
    derived = b['cat1_fs_bytes'] - b['cat1_resident_max'] - b['ota_reserve'] - b['ota_growth_margin']
    if b['gr_signed_red'] > derived:
        raise SystemExit(f'budget.json 不自洽：gr_signed_red {b["gr_signed_red"]} > 文件区 − 常驻 − 保留 − 余量 = {derived}')
    return b


def level(value, yellow, red):
    return 'red' if value > red else 'yellow' if value > yellow else 'ok'


def kib(n):
    return f'{n / 1024:.1f} KiB'


def checks(b, gr_body=None, luadb=None, sota=None, free=None, prev=None):
    """Return [(level, text)] for every known size; prev = sizes of the last board-verified release."""
    out = []
    sizes = {}
    if gr_body is not None:
        signed = gr_body + SIGNATURE
        sizes['gr_signed'] = signed
        out.append((level(signed, b['gr_signed_yellow'], b['gr_signed_red']),
                    f'GR 签名镜像 {signed}（{kib(signed)}），红线 {b["gr_signed_red"]}（{kib(b["gr_signed_red"])}），'
                    f'余 {b["gr_signed_red"] - signed}'))
    if luadb is not None:
        sizes['cat1_luadb'] = luadb
        out.append((level(luadb, b['cat1_luadb_yellow'], b['cat1_luadb_red']),
                    f'CAT1 脚本区 {luadb}，红线 {b["cat1_luadb_red"]}（保留 {b["cat1_fs_bytes"] - b["cat1_luadb_red"]}），'
                    f'余 {b["cat1_luadb_red"] - luadb}'))
    if sota is not None:
        sizes['cat1_sota'] = sota
        out.append((level(sota, b['cat1_sota_yellow'], b['cat1_sota_red']),
                    f'CAT1 升级包 .sota {sota}，红线 {b["cat1_sota_red"]}，余 {b["cat1_sota_red"] - sota}'))
    if free is not None:
        used = b['cat1_fs_bytes'] - free
        # The precheck reading still includes app logs (up to 2 x 16 KiB, deleted by the device at the OTA command), so
        # over-budget resident data is a warning to find what grew; the red line is the free-space check below.
        out.append(('yellow' if used > b['cat1_resident_max'] else 'ok',
                    f'CAT1 已用 {used}（{used // 4096} 块，含日志），常驻预算 {b["cat1_resident_max"]}（{b["cat1_resident_max"] // 4096} 块）' +
                    ('：超预算，查是什么数据在增长' if used > b['cat1_resident_max'] else '')))
        if gr_body is not None:
            need = gr_body + SIGNATURE + b['ota_reserve'] + b['ota_growth_margin']
            out.append(('red' if free < need else 'ok',
                        f'CAT1 可用 {free}，需要 ≥ {need}（GR 镜像 + 保留 {b["ota_reserve"]} + 余量 {b["ota_growth_margin"]}）'))
    for key, name in (('gr_signed', 'GR 签名镜像'), ('cat1_luadb', 'CAT1 脚本区'), ('cat1_sota', 'CAT1 .sota')):
        if prev and key in prev and key in sizes:
            d = sizes[key] - prev[key]
            out.append(('yellow' if d > b['growth_yellow'] else 'ok',
                        f'{name}比上次实板成功版本 {"+" if d >= 0 else ""}{d}' +
                        (f'（超过 {b["growth_yellow"]}，报告里要写清楚为什么变大）' if d > b['growth_yellow'] else '')))
    return out, sizes


def main():
    ap = argparse.ArgumentParser(description='YP001 OTA 大小红线检查')
    ap.add_argument('--gr-hex'); ap.add_argument('--gr-body', type=int)
    ap.add_argument('--cat1-src'); ap.add_argument('--luadb', type=int)
    ap.add_argument('--sota', type=int); ap.add_argument('--free', type=int)
    a = ap.parse_args()
    b = load()
    gr_body, luadb = a.gr_body, a.luadb
    if a.gr_hex or a.cat1_src:
        sys.path.insert(0, str(HERE))
        import oneclick as oc
        tmp = Path(tempfile.mkdtemp(prefix='budget_'))
        if a.gr_hex:
            rc, text = oc.sh([oc.GR_TOOL, 'check', a.gr_hex], tmp / 'gr.txt')
            m = re.search(r'应用正文 (\d+) 字节', text)
            if rc or not m:
                raise SystemExit('GR 固件检查失败：' + text[-300:])
            gr_body = int(m.group(1))
        if a.cat1_src:
            # Measure the receiver form like oneclick (trial range = own version), the raw tree may carry an old range.
            probe = tmp / 'probe'
            oc.copy_cat1(Path(a.cat1_src), probe)
            v, bld, _ = oc.main_info(probe)
            oc.set_versions(probe, v, int(bld), v, v, 'f' * 32)
            rc, text = oc.sh([oc.CAT_TOOL, '--source', probe, '--check-only'], tmp / 'cat.txt')
            m = re.search(r'LuaDB (\d+)/(\d+)', text)
            if not m:
                raise SystemExit('CAT1 检查失败：' + text[-300:])
            luadb = int(m.group(1))
    state = json.loads((HERE / 'state.json').read_text(encoding='utf-8')) if (HERE / 'state.json').exists() else {}
    out, _ = checks(b, gr_body, luadb, a.sota, a.free, (state.get('last_success') or {}).get('sizes'))
    mark = {'ok': '  ✓ ', 'yellow': '  ! ', 'red': '  ✗ 红线 '}
    for lv, text in out:
        print(mark[lv] + text)
    red = any(lv == 'red' for lv, _ in out)
    print('结论：' + ('超过红线，不能打包' if red else '没有超过红线'))
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
