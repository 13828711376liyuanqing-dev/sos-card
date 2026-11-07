"""SAM | 2026-10-30 11:08 +08:00 | Generate luatools_deps.json: the Luatools-derived files the standalone tools bundle, their sha256 (of the real bytes),
the Luatools version they were taken from (tools/toolkit/luatools_version.json) and where each lives in a Luatools install, which the tools'
"check dependencies" uses after a Luatools upgrade.
Sources of record: tools/toolkit/luatools_bundle (tools + 4 vendor lib sources) and Air780EGH/vendor_luac (4 precompiled libs).
With --luatools <dir> it also confirms that install still equals the bundle (informational for maintainers).
Usage: python gen_deps.py --out <file> [--toolkit-version 2026.10.30-1] [--luatools D:/Installers]"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUNDLE = HERE / 'luatools_bundle'
VENDOR = ROOT / 'Air780EGH/vendor_luac'
CAT1 = (ROOT / 'tools/ota/portable/Cat1Native.cs').read_text(encoding='utf-8')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(toolkit_version, luatools=None):
    ver = json.loads((HERE / 'luatools_version.json').read_text(encoding='utf-8'))
    res = re.search(r'resource.soc_script.(v[0-9.]+).lib', CAT1).group(1)
    if res != ver['resource_version']:
        sys.exit(f'STOP: Cat1Native.cs pins resource {res} but luatools_version.json says {ver["resource_version"]}')
    soc_name = re.search(r'SocName="([^"]+)"', CAT1).group(1)
    soc_hash = re.search(r'SocHash="([0-9a-f]{64})"', CAT1).group(1)
    files = []

    def add(name, kind, role, luatools_path, used_by, bundled, source_file):
        if not Path(source_file).exists():
            sys.exit(f'STOP: missing {source_file}')
        files.append({'name': name, 'kind': kind, 'role': role, 'luatools_path': luatools_path, 'sha256': sha(source_file),
                      'used_by': used_by, 'bundled': bundled})

    for rel, role, users in (('_temp/tools/luac_64bit.exe', 'Lua 编译器', ['Cat1UsbImport', 'YpOtaPack']),
                             ('_temp/tools/soc_tools.exe', 'CAT1 升级包生成工具', ['YpOtaPack']),
                             ('_temp/uis_download/7zip/32/7z.exe', '解压（读回校验）', ['YpOtaPack']),
                             ('_temp/uis_download/7zip/32/7z.dll', '解压库', ['YpOtaPack'])):
        name = rel.split('/')[-1]
        bundled = {'YpOtaPack': 'luatools/' + rel}
        if name == 'luac_64bit.exe':
            bundled['Cat1UsbImport'] = name
        add(name, 'tool', role, rel, users, bundled, BUNDLE / rel)
    for n in ('air1103', 'es8311', 'exsipclient', 'exsipproto'):
        rel = f'resource/soc_script/{res}/lib/{n}.lua'
        add(n + '.lua', 'lib', '厂商库源码（打包时编译进 CAT1 升级包）', 'resource/soc_script/{resource}/lib/' + n + '.lua', ['YpOtaPack'],
            {'YpOtaPack': 'luatools/' + rel}, BUNDLE / rel)
    for n in ('air1103', 'es8311', 'exsipclient', 'exsipproto'):
        add(n + '.luac', 'precompiled', '厂商库预编译件（刷机目录 USB_IMPORT 里的同名文件；由上面的库源码编译，随脚本资源版本更新）', '', ['Cat1UsbImport'],
            {'Cat1UsbImport': 'vendor_luac/' + n + '.luac'}, VENDOR / (n + '.luac'))
    if luatools:
        lt = Path(luatools)
        for f in files:
            if f['luatools_path']:
                p = lt / f['luatools_path'].replace('{resource}', res)
                state = 'same' if p.exists() and sha(p) == f['sha256'] else 'DIFFERENT'
                print(f'  vs {lt}: {f["name"]:20s} {state}')
    return {'schema': 1, 'toolkit_version': toolkit_version, 'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'luatools': {k: ver[k] for k in ('version', 'build', 'exe_size', 'resource_version', 'exe_sha256', 'note')},
            'soc': {'name': soc_name, 'sha256': soc_hash, 'where': 'Air780EGH/soc（项目源码），由 YpOtaPack 核对'}, 'files': files}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--toolkit-version', default=datetime.now().strftime('%Y.%m.%d') + '-1')
    ap.add_argument('--luatools')
    a = ap.parse_args()
    doc = build(a.toolkit_version, a.luatools)
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
    print('written', a.out, doc['luatools']['version'], doc['luatools']['resource_version'], len(doc['files']), 'files')


if __name__ == '__main__':
    main()
