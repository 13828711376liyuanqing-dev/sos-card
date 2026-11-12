"""SAM | 2026-11-10 | Host checks for the OTA bench helpers (no device): device_probe.parse on real captured text and ota_check.py pre on synthetic packages."""
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'bench'))
import device_probe  # noqa: E402

SAMPLE = '''
[FW_VERSION] YP001_FW|GR5526|001.005.031|35|END product=1.5.31 app_numeric=35 ota_provisioned=1 usb_bench_test=1
[CAT1 RX] [AT_INFO]  === CAT1 STATUS ===
[CAT1 RX] [AT_INFO]  LuatOS Ver:  001.005.031
[CAT1 RX] [AT_INFO]  Model:  Air780EGH
[CAT1 RX] [AT_INFO]  IMEI:  864317088496529
[CAT1 RX] [FOTA_STATUS]  IDLE
[CAT1 RX] [FOTA_STATUS]  OTA_OUTBOX=0
[CAT1 RX] [FOTA_STATUS]  OTA_IO=nil/0 TRIAL=RUNNING
[CAT1 RX] [OTA_FS]  OTA_FS total=128 used=15 block=4096
'''
d = device_probe.parse(SAMPLE)
assert d['gr_version'] == '1.5.31' and d['gr_build'] == 35 and d['cat1_version'] == '1.5.31' and d['imei'] == '864317088496529', d
assert d['fota_state'] == 'IDLE' and d['outbox'] == 0 and d['trial'] == 'RUNNING' and d['ota_io'] == 'nil/0', d
assert d['fs_free'] == (128 - 15) * 4096 and d['fs_used'] == 15, d
assert device_probe.norm('001.005.031') == '1.5.31' and device_probe.norm('1.5.31') == '1.5.31' and device_probe.norm('x') is None
assert device_probe.parse('nothing') == {}
print('PASS device_probe.parse reads GR/CAT1 versions, OTA state, outbox and file-system use; norm 001.005.031 -> 1.5.31')


def make_zip(tmp, name, source, target, gr_size=1000):
    p = tmp / name
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('bundle.json', json.dumps({'source_version': source, 'target_version': target, 'cat_free_operator_input': 462848}))
        z.writestr('GR5526/payload.bin', b'x' * gr_size)
    return p


def run_pre(zp):
    r = subprocess.run([sys.executable, str(HERE / 'bench' / 'ota_check.py'), 'pre', '--zip', str(zp), '--no-device'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, r.stdout + r.stderr


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    code, out = run_pre(make_zip(tmp, 'YP001_1.5.30---1.5.31_FIRST.zip', '1.5.30', '1.5.31'))
    assert code == 0 and '目标版本 1.5.31 高于源版本 1.5.30' in out and '没有做 3 号工具验证' in out and '结论：全部通过' in out, out
    code, out = run_pre(make_zip(tmp, 'YP001_1.5.30---1.5.31_FIRST.zip.x', '1.5.30', '1.5.31'))     # name does not carry the range -> still named wrongly
    code, out = run_pre(make_zip(tmp, 'YP001_1.5.28---1.5.29_FIRST.zip', '1.5.30', '1.5.31'))
    assert code == 1 and '包名和包里的版本范围不一致' in out and '不要推送' in out, out
    code, out = run_pre(make_zip(tmp, 'YP001_1.5.31---1.5.30_FIRST.zip', '1.5.31', '1.5.30'))
    assert code == 1 and '必须高于源版本' in out, out
    code, out = run_pre(tmp / 'no_such.zip')
    assert code == 1 and '找不到本地包' in out, out
print('PASS ota_check.py pre: accepts a well-formed package; rejects a name that disagrees with the range, a target not higher than the source, a missing file')
