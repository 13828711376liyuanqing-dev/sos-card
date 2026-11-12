"""SAM | 2026-10-30 15:55 +08:00 | Test YpVersionTool.exe from a copied folder: show/set rules (no going back, build rules, both firmwares equal, backup, json sync),
GR size/version checks on synthetic HEX/BIN, CAT1 script size through the sibling tool, OTA_FS parsing and the sufficiency decision, a missing COM port."""
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOL = HERE / 'YpVersionTool_Tool'
# SAM | 2026-11-04 +08:00 | the 1.5.2 image is above the OTA red line; use the board-verified 1.5.10 b14 image
SIGNED_152 = next((ROOT / 'firmware_releases').glob('ota_1.5.9_to_1.5.10_20261104_1201/1_GR*/*_signed.bin'))
CAT1 = ROOT / 'tools/cat1_release/CAT1_USB_IMPORT_Tool'


def ihex(data, base=0x202000):
    out, hi = [], None
    for off in range(0, len(data), 16):
        a = base + off
        if a >> 16 != hi:
            hi = a >> 16
            r = bytes([2, 0, 0, 4, hi >> 8, hi & 255]); out.append(':' + r.hex().upper() + '%02X' % (-sum(r) & 255))
        c = data[off:off + 16]; r = bytes([len(c), (a >> 8) & 255, a & 255, 0]) + c
        out.append(':' + r.hex().upper() + '%02X' % (-sum(r) & 255))
    out.append(':00000001FF')
    return '\n'.join(out) + '\n'


def image(size, marker='YP001_FW|GR5526|001.005.004|9|END'):
    b = bytearray(size)
    b[0:4] = (0x20010000).to_bytes(4, 'little'); b[4:8] = (0x00202101).to_bytes(4, 'little'); b[100:100 + len(marker)] = marker.encode()
    return bytes(b)


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        tool = tmp / 'tool'; shutil.copytree(TOOL, tool)
        shutil.copy2(CAT1 / 'Cat1UsbImport.exe', tool)       # the sibling the CAT1 size check calls
        shutil.copy2(CAT1 / 'luac_64bit.exe', tool); shutil.copy2(CAT1 / 'luatools_deps.json', tool)
        shutil.copytree(CAT1 / 'vendor_luac', tool / 'vendor_luac')
        exe = str(tool / 'YpVersionTool.exe')

        def run(*a):
            r = subprocess.run([exe, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            return r.returncode, r.stdout + r.stderr

        proj = tmp / 'proj'; cfg = proj / 'ble_app_uart_c/Src/config'; cfg.mkdir(parents=True); (proj / 'logs').mkdir()
        header = cfg / 'yp001_fw_version.h'; lua = proj / 'Air780EGH/main.lua'; lua.parent.mkdir()
        shutil.copy2(ROOT / 'ble_app_uart_c/Src/config/yp001_fw_version.h', header); shutil.copy2(ROOT / 'Air780EGH/main.lua', lua)
        for extra in ('ota_trial.lua', 'ota_native_fota.lua'):        # SAM | 2026-11-08: the OTA range is set in all three files together
            shutil.copy2(ROOT / 'Air780EGH' / extra, lua.parent / extra)
        shutil.copy2(ROOT / 'firmware_version.json', proj / 'firmware_version.json')
        # the test must not depend on which version the repository is at today: pin the copies to 1.5.2 / build 6
        import re
        hh = header.read_text(encoding='utf-8')
        hh = re.sub(r'(?m)^#define YP001_FW_VERSION "[0-9.]+"', '#define YP001_FW_VERSION "001.005.002"', hh)
        hh = re.sub(r'(?m)^#define YP001_PRODUCT_VERSION "[0-9.]+"', '#define YP001_PRODUCT_VERSION "1.5.2"', hh)
        hh = re.sub(r'(?m)^#define YP001_FW_BUILD \d+U', '#define YP001_FW_BUILD 6U', hh)
        hh = re.sub(r'(?m)^#define YP001_FW_BUILD_TEXT "\d+"', '#define YP001_FW_BUILD_TEXT "6"', hh)
        header.write_text(hh, encoding='utf-8')
        ll = lua.read_text(encoding='utf-8')
        ll = re.sub(r'(?m)^VERSION = "[0-9.]+"', 'VERSION = "001.005.002"', ll)
        ll = re.sub(r'(?m)^PRODUCT_VERSION = "[0-9.]+"', 'PRODUCT_VERSION = "1.5.2"', ll)
        ll = re.sub(r'(?m)^FW_RELEASE_BUILD = \d+', 'FW_RELEASE_BUILD = 6', ll)
        lua.write_text(ll, encoding='utf-8')
        jj = (proj / 'firmware_version.json').read_text(encoding='utf-8')
        jj = re.sub(r'"release_version"\s*:\s*"[0-9.]+"', '"release_version":  "1.5.2"', jj)
        jj = re.sub(r'"component_version"\s*:\s*"[0-9.]+"', '"component_version":  "001.005.002"', jj)
        jj = re.sub(r'"gr_build"\s*:\s*\d+', '"gr_build":  6', jj)
        (proj / 'firmware_version.json').write_text(jj, encoding='utf-8')
        orig_h, orig_l = header.read_bytes(), lua.read_bytes()

        code, log = run('--version'); assert code == 0 and 'YpVersionTool v' in log, log
        # 1. show / set rules
        code, log = run('show', '--header', header, '--lua', lua); assert code == 0 and '1.5.2' in log and 'build 6' in log, log
        for args, text in ((('--version', '1.5.1'), '倒退'), (('--version', '1.5.3', '--build', '6'), '必须大于'), (('--version', 'x.y'), '格式不对'),
                           (('--version', '1.5.2', '--build', '9'), '构建号不能改')):
            code, log = run('set', '--header', header, '--lua', lua, *args)
            assert code == 1 and text in log, (args, log)
        assert header.read_bytes() == orig_h and lua.read_bytes() == orig_l                    # refusals wrote nothing
        code, log = run('set', '--header', header, '--lua', lua, '--version', '1.5.3'); assert code == 0 and '1.5.3' in log, log
        h, l = header.read_text(encoding='utf-8'), lua.read_text(encoding='utf-8')
        j = (proj / 'firmware_version.json').read_text(encoding='utf-8')
        assert '#define YP001_FW_VERSION "001.005.003"' in h and '#define YP001_PRODUCT_VERSION "1.5.3"' in h, h
        assert '#define YP001_FW_BUILD 7U' in h and '#define YP001_FW_BUILD_TEXT "7"' in h, h
        assert 'VERSION = "001.005.003"' in l and 'PRODUCT_VERSION = "1.5.3"' in l and 'FW_RELEASE_BUILD = 7' in l, l[:600]
        assert l.count('Source identity set by YpVersionTool') == 1, l[:600]
        assert '"release_version":  "1.5.3"' in j and '"gr_build":  7' in j and '"component_version":  "001.005.003"' in j, j
        old_lines = orig_l.decode('utf-8').splitlines()
        diff = [x for x in l.splitlines() if x not in old_lines]
        assert len(diff) == 4, diff                                                            # 3 identity lines + the stamp line; no device version given -> range untouched
        # SAM | 2026-11-10 | OTA is ready from the factory: no OTA range / MD5 / device version lives in the source any more, so set touches only the identity
        assert 'OTA_TRIAL' not in l and 'OTA_TRIAL' not in log and '范围' not in log, log
        for extra in ('ota_trial.lua', 'ota_native_fota.lua'):
            assert (lua.parent / extra).read_bytes() == (ROOT / 'Air780EGH' / extra).read_bytes(), extra
        backups = list((proj / 'logs/firmware_versions').glob('set_*'))
        assert len(backups) == 1 and (backups[0] / 'gr_version_before.h').read_bytes() == orig_h and (backups[0] / 'cat1_main_before.lua').read_bytes() == orig_l
        code, log = run('set', '--header', header, '--lua', lua, '--version', '1.5.3'); assert code == 0 and '没有改动' in log, log
        # --from is gone (ignored with a note); a script that still carries the old three lines is told so and the tool leaves them alone
        code, log = run('set', '--header', header, '--lua', lua, '--version', '1.5.3', '--from', '1.5.2')
        assert code == 0 and '已经不需要' in log, log
        clean = lua.read_bytes()
        lua.write_bytes(clean + b"\r\nOTA_TRIAL_MD5='00000000000000000000000000000000'\r\nOTA_TRIAL_SOURCE='1.5.2'\r\nOTA_TRIAL_TARGET='1.5.3'\r\n")
        code, log = run('set', '--header', header, '--lua', lua, '--version', '1.5.3')
        assert code == 0 and '还留着' in log and "OTA_TRIAL_SOURCE='1.5.2'" in lua.read_text(encoding='utf-8'), log
        lua.write_bytes(clean)
        code, log = run('set', '--header', header, '--lua', lua, '--version', '1.5.4', '--build', '9'); assert code == 0 and 'build 9' in log, log

        # 2. GR size / version checks (synthetic images carrying the version marker)
        # SAM | 2026-11-04 +08:00 | sizes follow the OTA red line (signed image <= 393216, yellow above 376832)
        good = tmp / 'good.hex'; good.write_text(ihex(image(370000)), encoding='ascii')
        code, log = run('check', '--gr', good, '--header', header)
        # SAM | 2026-11-10 | the wording says which number is the Keil output and which is the signed image, and gives the CAT1 free-space THRESHOLD (not a device value)
        assert '你选的是【Keil 编译出来的、还没签名的文件】' in log and '签名后才得到，这是预计值' in log and '正文 370000 + 签名尾部 904' in log, log
        assert '门槛）≥ 403672 字节' in log and '不要把这个门槛当实际值填' in log, log
        assert code == 0 and '370000 字节' in log and '余 71464' in log and '离红线 22312' in log and '001.005.004' in log, log
        yellow = tmp / 'yellow.bin'; yellow.write_bytes(image(380000))
        code, log = run('check', '--gr', yellow); assert code == 0 and 'WARN' in log and '接近GR 签名镜像 380904' in log, log
        red = tmp / 'red.bin'; red.write_bytes(image(400000))
        code, log = run('check', '--gr', red); assert code == 1 and '超过GR 签名镜像 400904' in log and '离红线 -7688' in log, log
        mism = tmp / 'mism.hex'; mism.write_text(ihex(image(370000, 'YP001_FW|GR5526|001.005.003|7|END')), encoding='ascii')
        code, log = run('check', '--gr', mism, '--header', header); assert code == 1 and '不一致' in log, log
        nomark = tmp / 'nomark.bin'; nomark.write_bytes(bytes(1000))
        code, log = run('check', '--gr', nomark); assert code == 1 and '有且只有一个' in log, log
        big = tmp / 'big.hex'; big.write_text(ihex(image(441464 + 100)), encoding='ascii')
        code, log = run('check', '--gr', big); assert code == 1 and '441564' in log and '超过上限 441464' in log and '100 字节' in log, log
        near = tmp / 'near.bin'; near.write_bytes(image(441000))      # fits the slot but is far over the OTA red line
        code, log = run('check', '--gr', near); assert code == 1 and '余 464' in log and '超过GR 签名镜像 441904' in log, log
        low = tmp / 'low.hex'; low.write_text(ihex(image(64), base=0x200000), encoding='ascii')
        code, log = run('check', '--gr', low); assert code == 1 and '应用区之前' in log, log
        code, log = run('check', '--gr', SIGNED_152)
        assert code == 0 and '372064 字节' in log and '已签名的 .bin' in log and '正文 372064 + 签名尾部 904；已签名' in log and '001.005.010' in log and '离红线 20248' in log, log
        # 3. CAT1 script size through the sibling tool
        # SAM | 2026-11-04 +08:00 | the repo tree carries whatever trial range it was last packed with; use the pinned, board-verified 1.5.10 receiver
        # SAM | 2026-11-08 +08:00 | the 1.5.9 sample predates the 11-06 must-have (clear /log/ble.ini); use the board-verified 1.5.11 receiver like the other tests
        receiver = ROOT / 'firmware_releases/ota_1.5.10_to_1.5.11_20261106_1531/work/receiver_source'
        code, log = run('check', '--cat1', receiver); assert code == 0 and '上限 524288' in log and 'CAT1 脚本' in log and 'CAT1 脚本红线 507904' in log, log
        # 3b. SAM | 2026-11-10 | a new-style source (no OTA_TRIAL lines) is checked plainly and still reports its size; an old-style script keeps its old checks
        pkg_src = tmp / 'pkg_src'; shutil.copytree(ROOT / 'Air780EGH', pkg_src, ignore=shutil.ignore_patterns('_ota_release', '_archive', 'vendor_luac', '.git'))
        m = (pkg_src / 'main.lua').read_text(encoding='utf-8')
        m = re.sub(r'(?m)^VERSION = "[0-9.]+"', 'VERSION = "001.005.003"', m)
        m = re.sub(r'(?m)^PRODUCT_VERSION = "[0-9.]+"', 'PRODUCT_VERSION = "1.5.3"', m)
        m = re.sub(r'(?m)^FW_RELEASE_BUILD = \d+', 'FW_RELEASE_BUILD = 7', m)
        (pkg_src / 'main.lua').write_text(m, encoding='utf-8')
        code, log = run('check', '--cat1', pkg_src); assert code == 0 and '上限 524288' in log and '升级包的目标版本' not in log, log
        old_style = m + "\nOTA_TRIAL_MD5='00000000000000000000000000000000'\nOTA_TRIAL_SOURCE='1.5.2'\nOTA_TRIAL_TARGET='1.5.3'\n"
        (pkg_src / 'main.lua').write_text(old_style, encoding='utf-8')
        code, log = run('check', '--cat1', pkg_src); assert code == 0 and '升级包的目标版本 1.5.3' in log and '上限 524288' in log, log
        # a wrong range is a hard error only for an old receiver that can start an OTA (frozen MD5); zero MD5 only warns
        bad = old_style.replace("OTA_TRIAL_TARGET='1.5.3'", "OTA_TRIAL_TARGET='1.5.4'")
        (pkg_src / 'main.lua').write_text(bad.replace("OTA_TRIAL_MD5='00000000000000000000000000000000'", "OTA_TRIAL_MD5='18ada1de6be255ff0a8f60da2e995c77'"), encoding='utf-8')
        code, log = run('check', '--cat1', pkg_src); assert code == 1 and '不一致' in log, log
        (pkg_src / 'main.lua').write_text(bad, encoding='utf-8')
        code, log = run('check', '--cat1', pkg_src); assert code == 0 and '不一致' not in log and 'CAT1 脚本' in log, log
        # 3c. SAM | 2026-11-10 | `set` on a new-style source changes the identity only, and the result passes the plain CAT1 check
        pkg2 = tmp / 'pkg2'; shutil.copytree(ROOT / 'Air780EGH', pkg2, ignore=shutil.ignore_patterns('_ota_release', '_archive', 'vendor_luac', 'soc'))
        proj2 = tmp / 'proj2'; cfg2 = proj2 / 'ble_app_uart_c/Src/config'; cfg2.mkdir(parents=True); (proj2 / 'logs').mkdir()
        header2 = cfg2 / 'yp001_fw_version.h'; shutil.copy2(header, header2)       # own header: the later tests keep using the first one untouched
        code, log = run('set', '--header', header2, '--lua', pkg2 / 'main.lua', '--version', '1.5.99', '--build', '99')
        assert code == 0 and '范围' not in log, log
        mtxt = (pkg2 / 'main.lua').read_text(encoding='utf-8')
        assert 'PRODUCT_VERSION = "1.5.99"' in mtxt and 'OTA_TRIAL' not in mtxt, mtxt[:800]
        code, log = run('check', '--cat1', pkg2)
        assert code == 0 and '上限 524288' in log and '不一致' not in log, log
        # 3d. SAM | 2026-11-09 | backups go to --backup-dir (or the project's logs), never into the tool's own (possibly read-only) folder
        bk = tmp / 'bk'
        code, log = run('set', '--header', header2, '--lua', pkg2 / 'main.lua', '--version', '1.5.100', '--build', '100', '--backup-dir', bk)
        assert code == 0 and list(bk.glob('set_*/gr_version_before.h')), log
        assert not (Path(exe).parent / 'version_backup').exists(), 'tool wrote a backup into its own folder'
        # 3e. SAM | 2026-11-10 | the source version for the 3 号工具 is read from the device (fw_version), here parsed from text; no hardware needed
        code, log = run('devver', '--parse-text', '[FW_VERSION] YP001_FW|GR5526|001.005.031|35|END product=1.5.31 app_numeric=35 ota_provisioned=1')
        assert code == 0 and '设备 GR 当前版本 1.5.31' in log and 'build 35' in log and '源版本' in log, log
        code, log = run('devver', '--parse-text', 'nothing here'); assert code == 1 and '[FW_VERSION]' in log, log
        # 4. OTA_FS: parse, sufficiency, no hardware needed
        text = 'OTA_FS total=128 used=15 block=4096'
        # SAM | 2026-11-04 +08:00 | red line: signed image + 16384 reserve + 16384 growth margin (no extra 904 on a signed image)
        code, log = run('fs', '--parse-text', text); assert code == 0 and '462848 字节' in log and '够用' in log and '425984' in log and '余 36864' in log, log   # red-line image 393216
        code, log = run('fs', '--parse-text', text, '--gr', SIGNED_152); assert code == 0 and '405736' in log and '余 57112' in log, log   # 1.5.10 image 372968
        code, log = run('fs', '--parse-text', 'OTA_FS total=128 used=30 block=4096', '--gr', SIGNED_152); assert code == 1 and '不够' in log and '差 4328' in log and '超过常驻数据预算' in log, log
        code, log = run('fs', '--parse-text', 'OTA_FS total=128 used=25 block=4096\nF yp001_ota_state_0 1701 0\nF yp001_ota_state_1 1726 0', '--gr', SIGNED_152)
        assert code == 0 and 'OTA 状态记录 1726 字节' in log and 'WARN' in log, log       # the real 11-03 reading: 25 blocks is over the 24-block resident budget
        code, log = run('fs', '--parse-text', 'OTA_FS total=128 used=18 block=4096\nF yp001_ota_state_0 5000 0', '--gr', SIGNED_152)
        assert code == 0 and 'OTA 状态记录 5000 字节' in log and '多次升级在累积' in log, log
        code, log = run('prune', '--port', 'COM99'); assert code == 2 and '--yes' in log, log                    # writing to the device needs an explicit --yes
        code, log = run('prune', '--port', 'COM99', '--yes'); assert code == 1 and 'COM99' in log, log
        code, log = run('fs', '--parse-text', 'garbage'); assert code == 1 and '没有 OTA_FS' in log, log
        code, log = run('fs', '--port', 'COM99'); assert code == 1 and 'COM99' in log, log
        code, log = run('--ports'); assert code == 0
    print('PASS YpVersionTool.exe (copied folder): set refuses going back / wrong build / bad version without writing; sets GR header + CAT1 main.lua + firmware_version.json, '
          'backs up, changes only identity lines, is idempotent; GR size, version-marker and HEX address checks; CAT1 script size via the sibling tool; OTA_FS parse and '
          'sufficiency (red line: signed image + 16384 reserve + 16384 margin; GR/CAT1 OTA red lines; resident budget and OTA state record growth warnings); unreachable COM port reported (real serial read not tested here)')


if __name__ == '__main__':
    main()
