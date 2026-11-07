"""SAM | 2026-11-04 +08:00 | Build the GR J-Link wired flashing window tool (was compiled by hand on 11-01).
Output: tools/gr_release/GR_JLink_Flash/GR_JLink_Flash_Tool/ = GrJLinkFlash.exe + GR5xxx_16MB_Flash.FLM + 使用说明.txt."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'GR_JLink_Flash_Tool')
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll']

os.makedirs(OUT, exist_ok=True)
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:winexe', '-out:' + os.path.join(OUT, 'GrJLinkFlash.exe')] +
                   ['-reference:' + x for x in REFS] + [os.path.join(HERE, 'src', 'GrJLinkFlash.cs')],
                   capture_output=True, text=True, errors='replace')
errors = [l for l in r.stdout.splitlines() if ' error ' in l or 'warning' in l.lower() and 'C# 5' not in l and 'language versions' not in l]
print('\n'.join(errors))
if r.returncode:
    sys.exit(r.returncode)
shutil.copy2(os.path.join(HERE, 'GR5xxx_16MB_Flash.FLM'), os.path.join(OUT, 'GR5xxx_16MB_Flash.FLM'))
# The window tool has its own manual (src/使用说明.txt); ../使用说明.txt is the Python script's.
shutil.copy2(os.path.join(HERE, 'src', '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
print('built', OUT)
