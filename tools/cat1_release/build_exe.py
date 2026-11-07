"""SAM | 2026-10-30 10:21 +08:00 | Build the standalone CAT1 USB_IMPORT tool folder (only needed on a development PC).
Output: tools/cat1_release/CAT1_USB_IMPORT_Tool/ = Cat1UsbImport.exe + luac_64bit.exe + 使用说明.txt.
Copy that folder to any Windows 10/11 PC; nothing needs to be installed there (.NET Framework 4.x is built into Windows)."""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'CAT1_USB_IMPORT_Tool')
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOLKIT = os.path.join(ROOT, 'tools', 'toolkit')
# SAM | 2026-10-30 11:08 +08:00 | luac from the repo-controlled Luatools bundle; no Luatools install needed on the build PC.
LUAC = os.path.join(TOOLKIT, 'luatools_bundle', '_temp', 'tools', 'luac_64bit.exe')
LUAC_SHA256 = 'e4180102b388a09153c416ca2aa80dd90df257a10efe8abbbd5bcc5285ab0957'
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll',
        'System.Web.Extensions.dll', 'System.Numerics.dll']

os.makedirs(OUT, exist_ok=True)
assert hashlib.sha256(open(LUAC, 'rb').read()).hexdigest() == LUAC_SHA256, 'unexpected luac_64bit.exe'
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:exe', '-out:' + os.path.join(OUT, 'Cat1UsbImport.exe')] +
                   ['-reference:' + x for x in REFS] + [os.path.join(HERE, 'src', 'Cat1UsbImport.cs'), os.path.join(TOOLKIT, 'src', 'Deps.cs'),
                    os.path.join(TOOLKIT, 'src', 'Budget.cs')],  # SAM | 2026-11-04 +08:00 | OTA size red lines
                   capture_output=True, text=True, errors='replace')
errors = [l for l in r.stdout.splitlines() if ' error ' in l or 'warning' in l.lower() and 'C# 5' not in l and 'language versions' not in l]
print('\n'.join(errors))
if r.returncode:
    sys.exit(r.returncode)
shutil.copy2(LUAC, os.path.join(OUT, 'luac_64bit.exe'))
shutil.copy2(os.path.join(HERE, '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
vendor = os.path.join(OUT, 'vendor_luac')
shutil.rmtree(vendor, ignore_errors=True)
shutil.copytree(os.path.join(ROOT, 'Air780EGH', 'vendor_luac'), vendor)
subprocess.run([sys.executable, os.path.join(TOOLKIT, 'gen_deps.py'), '--out', os.path.join(OUT, 'luatools_deps.json')], check=True)
print('built', OUT)
