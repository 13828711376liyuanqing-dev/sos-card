"""SAM | 2026-11-10 +08:00 | Build the standalone OTA monitor folder: YpOtaMonitor.exe + 使用说明.txt (.NET Framework 4 ships with Windows; no Python needed)."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'YpOtaMonitor_Tool')
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Management.dll', 'System.Core.dll']

os.makedirs(OUT, exist_ok=True)
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:winexe', '-out:' + os.path.join(OUT, 'YpOtaMonitor.exe')] +
                   ['-reference:' + x for x in REFS] + [os.path.join(HERE, 'src', 'YpOtaMonitor.cs')],
                   capture_output=True, text=True, errors='replace')
errors = [l for l in r.stdout.splitlines() if ' error ' in l or 'warning' in l.lower() and 'C# 5' not in l and 'language versions' not in l]
print('\n'.join(errors))
if r.returncode:
    sys.exit(r.returncode)
shutil.copy2(os.path.join(HERE, '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
print('built', OUT)
