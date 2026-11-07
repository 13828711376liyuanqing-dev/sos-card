"""SAM | 2026-10-30 15:50 +08:00 | Build the standalone version/space tool folder: YpVersionTool.exe + 使用说明.txt (nothing else needed; .NET Framework 4 ships with Windows)."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'YpVersionTool_Tool')
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll']

os.makedirs(OUT, exist_ok=True)
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:exe', '-out:' + os.path.join(OUT, 'YpVersionTool.exe')] +
                   ['-reference:' + x for x in REFS] + [os.path.join(HERE, 'src', 'YpVersionTool.cs'),
                    os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools', 'toolkit', 'src', 'Budget.cs')],  # SAM | 2026-11-04 +08:00 | red lines
                   capture_output=True, text=True, errors='replace')
errors = [l for l in r.stdout.splitlines() if ' error ' in l or 'warning' in l.lower() and 'C# 5' not in l and 'language versions' not in l]
print('\n'.join(errors))
if r.returncode:
    sys.exit(r.returncode)
if os.path.exists(os.path.join(HERE, '使用说明.txt')):
    shutil.copy2(os.path.join(HERE, '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
print('built', OUT)
