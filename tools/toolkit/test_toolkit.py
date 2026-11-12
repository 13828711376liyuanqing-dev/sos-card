"""SAM | 2026-10-30 11:06 +08:00 | Test of the YP001 toolkit folder, run from a copy of it (as on another PC): complete, intact, no private key material, every tool
shows its version and the Luatools version it depends on, and "check dependencies" reports exactly what differs in a Luatools install after an upgrade
(version, changed tools, newer script resources with different vendor libs, wrong folder, a tampered bundled file). Fake Luatools folders are built
from the bundled files, so the test needs no real Luatools install."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import make_toolkit as mk

LOG = '2026-10-30 09:28:15.699 ui_main.py:249 INFO LuaTools version:  {v} - Windows10 - x - y, build time: 2026.10.16, UI resource: packaged\n'


def run(exe, *args):
    r = subprocess.run([str(exe)] + [str(a) for a in args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, r.stdout


def fake_luatools(tmp, name, bundle, version='v3.4.14'):
    d = tmp / name
    shutil.copytree(bundle, d)
    (d / 'log').mkdir()
    (d / 'log' / 'tools_20261030.txt').write_text(LOG.format(v=version), encoding='utf-8')
    (d / 'Luatools_v3.exe').write_bytes(b'x')
    return d


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        built = tmp / 'built'
        subprocess.run([sys.executable, str(HERE / 'make_toolkit.py'), '--no-build', '--out', str(built), '--toolkit-version', 'test-1'], check=True, capture_output=True)
        kit = tmp / 'other_pc' / 'YP001_工具包'
        shutil.copytree(built, kit)
        usb, gr, pack = kit / '1_CAT1刷机目录生成/Cat1UsbImport.exe', kit / '2_GR5526固件检查签名/Gr5526Tool.exe', kit / '3_整机OTA打包/YpOtaPack.exe'
        ver = kit / '4_固件版本与空间/YpVersionTool.exe'

        # 1. complete, intact, no private key
        for rel in ('budget.json', '5_姓名字库核对/NameCheck.exe', '5_姓名字库核对/使用说明.txt', 'GR_JLink_Flash_Tool/GrJLinkFlash.exe', 'GR_JLink_Flash_Tool/GR5xxx_16MB_Flash.FLM', 'GR_JLink_Flash_Tool/使用说明.txt',
                    '先看这里.txt', 'luatools依赖版本.txt', '维护人员-升级Luatools步骤.txt', 'MANIFEST.sha256', 'luatools_deps.json',
                    '1_CAT1刷机目录生成/vendor_luac/vendor.json', '1_CAT1刷机目录生成/luac_64bit.exe', '1_CAT1刷机目录生成/使用说明.txt',
                    '2_GR5526固件检查签名/contracts/layout_candidate.json', '2_GR5526固件检查签名/使用说明.txt',
                    '3_整机OTA打包/luatools/_temp/tools/soc_tools.exe', '3_整机OTA打包/contracts/data_contract_candidate.json', '3_整机OTA打包/使用说明.txt', '4_固件版本与空间/使用说明.txt'):
            assert (kit / rel).exists(), rel
        for line in (kit / 'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
            h, name = line.split(' *', 1)
            assert hashlib.sha256((kit / name).read_bytes()).hexdigest() == h, name
        assert not mk.private_material(kit)
        # the guard itself refuses key material
        leak = tmp / 'leak'; (leak / 'a').mkdir(parents=True); (leak / 'a' / 'x.key').write_text('k', encoding='utf-8')
        (leak / 'a' / 'p.xml').write_text('<RSAKeyValue><Modulus>AQ==</Modulus><D>AQ==</D><P>AQ==</P></RSAKeyValue>', encoding='utf-8')
        assert len(mk.private_material(leak)) == 2

        code, log = run(ver, '--version'); assert code == 0 and 'YpVersionTool' in log, log
        # SAM | 2026-11-04 +08:00 | pinned board-verified 1.5.11 receiver (also clears /log/ble.ini) (the repo tree carries whatever trial range it was last packed with)
        receiver = ROOT / 'firmware_releases/ota_1.5.10_to_1.5.11_20261106_1531/work/receiver_source'
        code, log = run(ver, 'check', '--cat1', receiver); assert code == 0 and '上限 524288' in log, log          # finds the sibling CAT1 tool in the kit
        # 2. versions are explicit
        for exe, name in ((usb, 'Cat1UsbImport'), (pack, 'YpOtaPack')):
            code, log = run(exe, '--version')
            assert code == 0 and name in log and 'Luatools v3.4.14' in log and 'v2026.10.13.20' in log and 'V2052_Air780EGH_113' in log, log
        code, log = run(gr, '--version'); assert code == 0 and '不依赖 Luatools' in log, log

        # 3. dependency check without a Luatools folder: files match the table
        for exe in (usb, pack):
            code, log = run(exe, '--deps'); assert code == 0 and '[与依赖表一致]' in log and '不符' not in log and '缺失' not in log, log
        bundle = kit / '3_整机OTA打包/luatools'

        # 4. against Luatools installs
        d = fake_luatools(tmp, 'same', bundle)
        code, log = run(pack, '--deps', '--luatools', d); assert code == 0 and '无需升级' in log, log
        code, log = run(usb, '--deps', '--luatools', d); assert code == 0 and '无需升级' in log, log
        d = fake_luatools(tmp, 'newer_version', bundle, 'v3.9.9')
        code, log = run(pack, '--deps', '--luatools', d); assert code == 0 and 'v3.9.9' in log and '未经验证' in log and '不影响使用，不用升级' in log, log
        d = fake_luatools(tmp, 'tool_changed', bundle); (d / '_temp/tools/soc_tools.exe').write_bytes(b'changed')
        code, log = run(pack, '--deps', '--luatools', d); assert code == 0 and 'soc_tools.exe：本机 Luatools 的版本已变化' in log and '不影响使用，不用升级' in log, log
        code, log = run(usb, '--deps', '--luatools', d); assert code == 0 and 'soc_tools' not in log, log        # the USB tool does not use it
        d = fake_luatools(tmp, 'luac_changed', bundle); (d / '_temp/tools/luac_64bit.exe').write_bytes(b'changed')
        code, log = run(usb, '--deps', '--luatools', d); assert code == 0 and 'luac_64bit.exe' in log and '不影响使用，不用升级' in log, log
        d = fake_luatools(tmp, 'newer_resource', bundle)
        new = d / 'resource/soc_script/v2026.10.22.19/lib'; shutil.copytree(d / 'resource/soc_script/v2026.10.13.20/lib', new)
        (new / 'air1103.lua').write_text('-- new', encoding='utf-8'); (new / 'exsipproto.lua').write_text('-- new', encoding='utf-8')
        code, log = run(pack, '--deps', '--luatools', d)
        assert code == 0 and '不影响现有设备和工具' in log and '较新的脚本资源 v2026.10.22.19' in log and 'air1103.lua、exsipproto.lua' in log and 'es8311.lua' not in log.split('较新的脚本资源')[1].split('\n')[0], log
        d = fake_luatools(tmp, 'newer_resource_same_libs', bundle)
        shutil.copytree(d / 'resource/soc_script/v2026.10.13.20', d / 'resource/soc_script/v2026.10.22.19')
        code, log = run(pack, '--deps', '--luatools', d); assert code == 0 and '较新的脚本资源 v2026.10.22.19 的厂商库与工具包相同' in log, log
        empty = tmp / 'empty'; empty.mkdir()
        code, log = run(pack, '--deps', '--luatools', empty); assert code == 1 and '不像是 Luatools 目录' in log, log

        # 5. a bundled file that was altered after the toolkit was built is reported
        (bundle / '_temp/tools/luac_64bit.exe').write_bytes(b'tampered')
        code, log = run(pack, '--deps'); assert code == 1 and '与依赖表不符' in log, log

        # 6. the tools still work from the toolkit folder
        code, log = run(usb, '--source', receiver, '--out', tmp / 'usb_out', '--check-only')
        assert code == 0 and 'LuaDB 498724' in log and 'OTA 必检功能齐全' in log, log   # SAM | 2026-11-08: size of the pinned 1.5.11 receiver sample (was the older 1.5.10 number)
        # SAM | 2026-11-04 +08:00 | the tools read the red lines from the kit's own budget.json
        assert '脚本区红线 507904' in log and str(kit / 'budget.json') in log, log
    print('PASS toolkit (run from a copy): all files present and equal to MANIFEST, no private key material (guard also refuses a leaked key); --version shows tool, Luatools, '
          'script-resource and SoC versions; --deps matches the table, reports a newer Luatools, changed tools (only for the tools that use them), newer script resources with '
          'different vendor libs (air1103, exsipproto), a wrong folder and a tampered bundled file; the USB tool works from the toolkit with its own vendor libraries and reads the kit budget.json; budget.json and the J-Link tool are shipped')


if __name__ == '__main__':
    main()
