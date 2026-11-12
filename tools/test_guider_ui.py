"""SAM | 2026-10-11 00:48 +08:00 | Build the actual project LVGL and UI
on Windows because page switching, pixels and heap need runtime evidence.
This is host evidence, not device acceptance.
"""
import os
import hashlib
import ctypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'tmp/guider_host'
GCC = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
PROJECT = ROOT / 'ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx'


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    # SAM | 2026-10-12 13:24 +08:00 | Suppress Windows child-process crash
    # dialogs because a failed GUI test must return an error to the script.
    if os.name == 'nt':
        ctypes.windll.kernel32.SetErrorMode(0x0002)
    env = dict(os.environ)
    env.pop('GUIDER_TEST_FORCE_FAIL', None)
    env['PATH'] = str(GCC.parent) + os.pathsep + env['PATH']
    project = ET.parse(PROJECT)
    sources = []
    for node in project.findall('.//FilePath'):
        path = (PROJECT.parent / node.text.replace('\\', '/')).resolve()
        if path.suffix == '.c' and ('lvgl_8.3.1' in path.parts or 'guider' in path.parts or path.name in ('epaper_ui.c', 'epaper_lvgl.c')):
            sources.append(path)
    # SAM | 2026-10-13 09:04 +08:00 | Include the QR encoder in host rendering until project XML lists it. 
    qr_encoder = ROOT / 'ble_app_uart_c/Src/external/lvgl_8.3.1/src/extra/libs/qrcode/qrcodegen.c'
    if qr_encoder not in sources:
        sources.append(qr_encoder)
    sources.append(ROOT / 'tools/test_guider_ui.c')
    args = ['-std=c99', '-O0', '-g', '-DEPAPER_UI_HOST_TEST', '-DLV_LVGL_H_INCLUDE_SIMPLE', '-DLV_CONF_INCLUDE_SIMPLE']
    for rel in ['Src/external/lvgl_8.3.1', 'Src/user', 'Src/user/gui', 'Src/user/gui/guider', 'Src/user/gui/guider/custom']:
        args.append('-I' + (ROOT / 'ble_app_uart_c' / rel).as_posix())
    # SAM | 2026-10-11 01:14 +08:00 | Cache compiled host objects because
    # a test-only assertion repair must not rebuild 186 unchanged LVGL units.
    headers = sorted((ROOT / 'ble_app_uart_c/Src/external/lvgl_8.3.1').rglob('*.h'))
    headers += sorted((ROOT / 'ble_app_uart_c/Src/user').rglob('*.h'))
    common = hashlib.sha256(repr(args).encode())
    common.update(str(GCC.stat().st_mtime_ns).encode())
    for path in headers:
        common.update(path.as_posix().encode())
        common.update(path.read_bytes())
    objects = WORK / 'objects'
    objects.mkdir(exist_ok=True)

    def compile_one(path):
        obj = objects / (path.stem + '_' + hashlib.sha256(str(path).encode()).hexdigest()[:10] + '.o')
        stamp = obj.with_suffix('.sha256')
        key = hashlib.sha256(common.digest() + path.read_bytes()).hexdigest()
        if obj.exists() and stamp.exists() and stamp.read_text() == key:
            return obj, 0, ''
        result = subprocess.run([str(GCC)] + args + ['-c', str(path), '-o', str(obj)], env=env, capture_output=True, text=True, errors='replace')
        if result.returncode == 0:
            stamp.write_text(key)
        return obj, result.returncode, result.stdout + result.stderr

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(compile_one, sources))
    output = ''.join(item[2] for item in results)
    (WORK / 'build.log').write_text(output, encoding='utf-8')
    if any(item[1] != 0 for item in results):
        print(output, flush=True)
        raise SystemExit(1)
    response = WORK / 'link.rsp'
    link_args = [item[0].as_posix() for item in results] + ['-o', (WORK / 'guider_ui_test.exe').as_posix(), '-lm']
    response.write_text('\n'.join('"' + arg + '"' for arg in link_args), encoding='utf-8')
    result = subprocess.run([str(GCC), '@' + str(response)], env=env, capture_output=True, text=True, errors='replace')
    output += result.stdout + result.stderr
    (WORK / 'build.log').write_text(output, encoding='utf-8')
    print(output, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    # SAM | 2026-10-12 13:24 +08:00 | Exercise the failure path explicitly
    # because a modal CRT assertion used to block every debugging run.
    failure_env = dict(env, GUIDER_TEST_FORCE_FAIL='1')
    failed = subprocess.run([str(WORK / 'guider_ui_test.exe')], cwd=WORK,
                            env=failure_env, capture_output=True, text=True, timeout=5)
    if failed.returncode != 1 or 'CHECK failed:' not in failed.stderr:
        print(f'Failure-path check failed: exit={failed.returncode} {failed.stderr}', flush=True)
        raise SystemExit(1)
    print('PASS: host-test failure returns a diagnostic without a modal dialog', flush=True)
    result = subprocess.run([str(WORK / 'guider_ui_test.exe')], cwd=WORK, env=env, capture_output=True, text=True, timeout=60)
    (WORK / 'run.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    print(result.stdout + result.stderr, flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
