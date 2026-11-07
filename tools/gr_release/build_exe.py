"""SAM | 2026-10-30 10:42 +08:00 | Build the standalone GR5526 file tool folder (development PC only).
Output: tools/gr_release/GR5526_Tool/ = Gr5526Tool.exe + contracts/ (public layout/data pins) + 使用说明.txt.
The folder runs on any Windows 10/11 PC without installing anything (.NET Framework 4.x is part of Windows).
The signing private key is NOT included; the operator imports it at run time."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, 'GR5526_Tool')
PORTABLE = os.path.join(ROOT, 'tools', 'ota', 'portable')
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll',
        'System.Web.Extensions.dll', 'System.Numerics.dll']
SOURCES = [os.path.join(PORTABLE, n) for n in ('PackCore.cs', 'Cat1Native.cs', 'BundleSigning.cs', 'FirmwareIdentity.cs', 'StoredZipWriter.cs', 'GrProjectNative.cs')]
SOURCES.append(os.path.join(HERE, 'src', 'Gr5526Tool.cs'))
SOURCES.append(os.path.join(ROOT, 'tools', 'toolkit', 'src', 'Budget.cs'))  # SAM | 2026-11-04 +08:00 | OTA size red lines

os.makedirs(os.path.join(OUT, 'contracts'), exist_ok=True)
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:exe', '-out:' + os.path.join(OUT, 'Gr5526Tool.exe')] +
                   ['-reference:' + x for x in REFS] + SOURCES, capture_output=True, text=True, errors='replace')
bad = [l for l in r.stdout.splitlines() if ' error ' in l]
print('\n'.join(bad))
if r.returncode:
    sys.exit(r.returncode)
for n in ('layout_candidate.json', 'data_contract_candidate.json'):
    shutil.copy2(os.path.join(ROOT, 'tools', 'toolkit', 'contracts', n), os.path.join(OUT, 'contracts', n))
shutil.copy2(os.path.join(HERE, '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
print('built', OUT)
