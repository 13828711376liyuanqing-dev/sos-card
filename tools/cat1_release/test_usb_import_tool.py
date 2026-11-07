"""SAM | 2026-10-30 10:21 +08:00 | Self-test of the standalone tool (CAT1_USB_IMPORT_Tool/Cat1UsbImport.exe), run from a copy of the
tool folder in a temp location (as on another PC). A clean build matches the board-verified ota153 USB_IMPORT (same
.luac/vendor/asset bytes, same main body and anchor set); every check refuses its fault case without writing output."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# SAM | 2026-11-04 +08:00 | The 1.5.2 snapshot predates the mandatory OTA log-clear / power-hold code that the tool now
# requires; use the receiver of the board-verified 1.5.10 -> 1.5.11 OTA (2026-11-06 16:03, also clears /log/ble.ini) and the USB_IMPORT built from it.
SRC = ROOT / 'firmware_releases/ota_1.5.10_to_1.5.11_20261106_1531/work/receiver_source'
REF = ROOT / 'firmware_releases/ota_1.5.10_to_1.5.11_20261106_1531/2_CAT1刷机目录/USB_IMPORT'


def edit(p, a, b):
    s = p.read_bytes().decode('utf-8'); assert a in s, a; p.write_bytes(s.replace(a, b, 1).encode('utf-8'))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tool = tmp / 'tool'
        shutil.copytree(HERE / 'CAT1_USB_IMPORT_Tool', tool)
        exe = tool / 'Cat1UsbImport.exe'

        def run(src, out, *extra):
            r = subprocess.run([str(exe), '--source', str(src), '--out', str(out)] + list(extra), capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
            return r.returncode, r.stdout

        def copy_source(name):
            s = tmp / name / 'src'
            shutil.copytree(SRC, s, ignore=shutil.ignore_patterns('_*', 'soc', 'README.md'))
            shutil.copytree(ROOT / 'Air780EGH/vendor_luac', s / 'vendor_luac')     # the receiver snapshot has no vendor libs of its own
            return s

        # 1. clean build equals the board-verified set
        code, log = run(SRC, tmp / 'ok')
        assert code == 0, log
        out = tmp / 'ok/USB_IMPORT'
        assert sorted(p.name for p in out.iterdir()) == sorted(p.name for p in REF.iterdir())
        for p in REF.iterdir():
            if p.name != 'main.lua':
                assert p.read_bytes() == (out / p.name).read_bytes(), p.name
        anchors = lambda b: set(re.findall(r'require\("([^"]+)"\)', b.split('\nend', 1)[0]))
        ref_main, new_main = (REF / 'main.lua').read_text(encoding='utf-8'), (out / 'main.lua').read_text(encoding='utf-8')
        assert anchors(ref_main) == anchors(new_main) and ref_main.split('\nend', 1)[1] == new_main.split('\nend', 1)[1]
        assert 'LuaDB 498724/524288' in log and '脚本区红线 507904' in log and (tmp / 'ok/integrity.json').exists(), log
        # 2. existing output is kept unless --force
        code, _ = run(SRC, tmp / 'ok')
        assert code == 1
        code, _ = run(SRC, tmp / 'ok', '--force')
        assert code == 0
        # 3. fault cases: refused, nothing written
        cases = {
            'syntax': lambda s: (s / 'ota_trust.lua').write_bytes(b'return {\r\n'),
            'long_name': lambda s: shutil.copy(s / 'ntp.lua', s / 'a_very_long_module_name.lua'),
            'vendor_hash': lambda s: (s / 'vendor_luac/es8311.luac').write_bytes(b'x'),
            'receiver_version': lambda s: edit(s / 'main.lua', "OTA_TRIAL_SOURCE='1.5.10'", "OTA_TRIAL_SOURCE='1.5.9'"),
            'bad_md5': lambda s: edit(s / 'main.lua', "OTA_TRIAL_MD5='18ada1de6be255ff0a8f60da2e995c77'", "OTA_TRIAL_MD5='xyz'"),
            # SAM | 2026-11-04 +08:00 | red line (under the 524288 hard limit) and the mandatory OTA log-clear / power-hold code
            'red_line': lambda s: (s / 'big.lua').write_bytes(b'local s=[[' + b'a' * 14000 + b']]\r\nreturn s\r\n'),
            'no_log_clear': lambda s: edit(s / 'update.lua', '[OTA] LOG_CLEARED', '[OTA] LOG_X'),
            # SAM | 2026-11-06 +08:00 | the temporary BLE location cache must be cleared before an OTA as well
            'no_ble_clear': lambda s: edit(s / 'update.lua', "'/log/ble.ini'", "'/log/x.ini'"),
            # the platform entry holds power early too (11-06), so ota_hold(true) appears twice: replace every occurrence
            'no_power_hold': lambda s: (s / 'update.lua').write_bytes((s / 'update.lua').read_bytes().replace(b'ota_hold(true)', b'ota_hold(false)')),
            'no_log_pause': lambda s: edit(s / 'fs_log.lua', 'if ota_paused() then buf, buf_len = {}, 0; return true end', 'if false then end'),
            'capacity': lambda s: (s / 'big.lua').write_bytes(b'local s=[[' + b'a' * 34000 + b']]\r\nreturn s\r\n'),
            'not_utf8': lambda s: (s / 'tts.lua').write_bytes(b'-- \xff\xfe\r\nreturn 1\r\n'),
        }
        for name, fault in cases.items():
            s = copy_source(name)
            fault(s)
            code, log = run(s, tmp / ('out_' + name), '--vendor', s / 'vendor_luac')
            assert code == 1 and 'ERROR' in log and not (tmp / ('out_' + name) / 'USB_IMPORT').exists(), (name, log)
        # 4. luac must be the verified one
        (tool / 'luac_64bit.exe').write_bytes(b'MZ')
        code, log = run(SRC, tmp / 'badluac')
        assert code == 1 and 'luac_64bit.exe' in log
        shutil.copy2(HERE / 'CAT1_USB_IMPORT_Tool/luac_64bit.exe', tool / 'luac_64bit.exe')
        # 5. check-only writes nothing
        code, log = run(SRC, tmp / 'check', '--check-only')
        assert code == 0 and not (tmp / 'check/USB_IMPORT').exists()
    print('PASS Cat1UsbImport.exe (run from a copied folder): clean build == board-verified 1.5.11 receiver USB_IMPORT '
          '(identical files, same main body/anchors, LuaDB 498724, red line 507904), dir+integrity; keeps existing output without --force; '
          'refuses syntax error, >23-byte name, vendor hash, receiver version, bad MD5, over capacity, over the red line, missing OTA '
          'log-clear / log-pause / power-hold code, non-UTF-8, unverified luac; check-only writes nothing')


if __name__ == '__main__':
    main()
