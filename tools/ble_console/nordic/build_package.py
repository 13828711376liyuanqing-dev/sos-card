# SAM | 2026-11-05 +08:00 | Build a self-contained per-user installer payload with bundled Python/Tk and vendor runtime.
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / 'package' / 'YP001BleConsole'
PAYLOAD.mkdir(parents=True, exist_ok=True)
python_root = Path(sys.executable).parent
for name in ['python.exe', 'pythonw.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt']:
    target = PAYLOAD / 'python' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(python_root / name, target)
for name in ['DLLs', 'tcl', 'Lib']:
    shutil.copytree(python_root / name, PAYLOAD / 'python' / name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'site-packages', 'test', 'tests', 'idlelib', 'ensurepip', 'tkinter.test'))
import serial
shutil.copytree(Path(serial.__file__).parent, PAYLOAD / 'python' / 'Lib' / 'site-packages' / 'serial', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT / 'runtime', PAYLOAD / 'runtime', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('app'))
for name in ['com31_console.py', 'worker.js', 'protocol.js', '使用说明.md', 'pyserial-LICENSE.txt']:
    shutil.copy2(ROOT / name, PAYLOAD / name)
compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
subprocess.run([str(compiler), '/nologo', '/target:winexe', '/reference:System.Windows.Forms.dll',
                '/out:' + str(PAYLOAD / 'YP001_COM31_BLE.exe'), str(ROOT / 'Launcher.cs')], check=True)
subprocess.run([str(PAYLOAD / 'python' / 'python.exe'), '-I', str(PAYLOAD / 'com31_console.py'), '--self-test'], check=True)
files = sorted(p.relative_to(PAYLOAD) for p in PAYLOAD.rglob('*') if p.is_file())
with (ROOT / 'uninstall_files.nsh').open('w', encoding='utf-8-sig') as output:
    for file in files:
        output.write('Delete "$INSTDIR\\' + str(file) + '"\n')
    dirs = sorted((p.relative_to(PAYLOAD) for p in PAYLOAD.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
    for directory in dirs:
        output.write('RMDir "$INSTDIR\\' + str(directory) + '"\n')
print('PAYLOAD_READY', len(files), 'files')
