"""SAM | 2026-11-04 +08:00 | Build the resident-name file check tool (toolkit 5_姓名字库核对).
Output: tools/name_check/NameCheck_Tool/ = NameCheck.exe + 使用说明.txt."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'NameCheck_Tool')
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Web.Extensions.dll']

os.makedirs(OUT, exist_ok=True)
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:exe', '-out:' + os.path.join(OUT, 'NameCheck.exe')] +
                   ['-reference:' + x for x in REFS] + [os.path.join(HERE, 'src', 'NameCheck.cs')],
                   capture_output=True, text=True, errors='replace')
errors = [l for l in r.stdout.splitlines() if ' error ' in l or 'warning' in l.lower() and 'C# 5' not in l and 'language versions' not in l]
print('\n'.join(errors))
if r.returncode:
    sys.exit(r.returncode)
shutil.copy2(os.path.join(HERE, '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
print('built', OUT)
