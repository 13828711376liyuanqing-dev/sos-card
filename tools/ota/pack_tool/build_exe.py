"""SAM | 2026-10-30 10:46 +08:00 | Build the standalone OTA packager folder (development PC only).
Output: tools/ota/pack_tool/YpOtaPack_Tool/ = YpOtaPack.exe + luatools/ (the 6 vendor files the packager needs, sha256-pinned in the code)
+ contracts/ (public layout/data pins) + 使用说明.txt. Runs on any Windows 10/11 PC without installing anything.
The signing private key is NOT included; the operator imports it at run time."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(HERE, 'YpOtaPack_Tool')
PORTABLE = os.path.join(ROOT, 'tools', 'ota', 'portable')
TOOLKIT = os.path.join(ROOT, 'tools', 'toolkit')
LUATOOLS = os.path.join(TOOLKIT, 'luatools_bundle')   # SAM | 2026-10-30 11:08 +08:00 | repo-controlled copy; no Luatools install needed on the build PC
CSC = os.path.join(os.environ.get('WINDIR', 'C:' + os.sep + 'Windows'), 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe')
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll',
        'System.Web.Extensions.dll', 'System.Numerics.dll']
SOURCES = [os.path.join(PORTABLE, n) for n in ('PackCore.cs', 'Cat1Native.cs', 'BundleSigning.cs', 'FirmwareIdentity.cs', 'StoredZipWriter.cs', 'GrProjectNative.cs')]
SOURCES.append(os.path.join(HERE, 'src', 'YpOtaPack.cs'))
SOURCES.extend([os.path.join(TOOLKIT, 'src', 'Deps.cs'), os.path.join(TOOLKIT, 'src', 'Budget.cs')])  # SAM | 2026-11-04 +08:00 | + OTA red lines
VENDOR = [('_temp/tools/luac_64bit.exe',), ('_temp/tools/soc_tools.exe',), ('_temp/uis_download/7zip/32/7z.exe',), ('_temp/uis_download/7zip/32/7z.dll',)] + \
         [('resource/soc_script/v2026.10.13.20/lib/%s.lua' % n,) for n in ('air1103', 'es8311', 'exsipclient', 'exsipproto')]

os.makedirs(OUT, exist_ok=True)
r = subprocess.run([CSC, '-nologo', '-codepage:65001', '-optimize+', '-target:exe', '-out:' + os.path.join(OUT, 'YpOtaPack.exe')] +
                   ['-reference:' + x for x in REFS] + SOURCES, capture_output=True, text=True, errors='replace')
print('\n'.join(l for l in r.stdout.splitlines() if ' error ' in l))
if r.returncode:
    sys.exit(r.returncode)
for (rel,) in VENDOR:
    dst = os.path.join(OUT, 'luatools', *rel.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(os.path.join(LUATOOLS, *rel.split('/')), dst)
os.makedirs(os.path.join(OUT, 'contracts'), exist_ok=True)
for n in ('layout_candidate.json', 'data_contract_candidate.json'):
    shutil.copy2(os.path.join(ROOT, 'tools', 'toolkit', 'contracts', n), os.path.join(OUT, 'contracts', n))
if os.path.exists(os.path.join(HERE, '使用说明.txt')):
    shutil.copy2(os.path.join(HERE, '使用说明.txt'), os.path.join(OUT, '使用说明.txt'))
subprocess.run([sys.executable, os.path.join(TOOLKIT, 'gen_deps.py'), '--out', os.path.join(OUT, 'luatools_deps.json')], check=True)
print('built', OUT)
