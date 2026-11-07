"""SAM | 2026-11-04 +08:00 | NameCheck.exe (run from a copied folder) agrees with tools/glyph_maker/check_platform_json.py on the
same samples: the first platform file (2024 Seq), a correct file from our generator, a missing glyph, a tampered CRC, a room
with characters the device cannot show, an oversize set; and it writes the explanation Markdown (timestamp = Seq)."""
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'glyph_maker'))
import glyphlib as G  # noqa: E402

FIRST = ROOT / 'logs' / 'name_check_20261104' / 'residentNameMsg_张秀珺.json'


def run_exe(exe, f):
    r = subprocess.run([str(exe), str(f)], capture_output=True)
    return r.returncode, r.stdout.decode('utf-8', 'replace')


def run_py(f):
    r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'glyph_maker' / 'check_platform_json.py'), str(f)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, r.stdout


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tool = tmp / 'tool'; shutil.copytree(HERE / 'NameCheck_Tool', tool)
        exe = tool / 'NameCheck.exe'
        good = G.platform_msg('张秀珺', '1#1-102', '泰康之家·燕园', int(time.time()), G.resident_glyphs('张秀珺', '泰康之家·燕园'))
        cases = {'first_platform_file': (json.loads(FIRST.read_text(encoding='utf-8')), 1, 'Seq 1730600000'),
                 'good': (good, 0, '可以下发')}
        m = json.loads(json.dumps(good)); m['Glyphs'] = m['Glyphs'][1:]; cases['missing_glyph'] = (m, 1, '缺少字形')
        m = json.loads(json.dumps(good)); m['Glyphs'][0]['C'] = '0000'; cases['bad_crc'] = (m, 1, 'CRC 不对')
        m = json.loads(json.dumps(good)); m['Room'] = 'A区2幢1203'; cases['bad_room'] = (m, 1, 'Room')
        big = [G.Glyph(0x4E00 + i, 32, [[1] * 40 for _ in range(40)], 0, 0, 512) for i in range(28)]
        m = G.platform_msg('张秀珺', '1#1-102', '', int(time.time()), big, max_store=0); cases['oversize'] = (m, 1, '4000')
        for name, (msg, want, needle) in cases.items():
            f = tmp / f'residentNameMsg_{name}.json'
            f.write_text(json.dumps(msg, ensure_ascii=False), encoding='utf-8')
            code, out = run_exe(exe, f)
            pcode, pout = run_py(f)
            assert code == want and needle in out, (name, code, out)
            assert pcode == want, (name, 'python checker disagrees', pcode, pout)
            md = (tmp / f'residentNameMsg_{name}_核对.md').read_text(encoding='utf-8')
            assert '时间戳是 **`Seq`** 字段' in md and '## 五、结论' in md, md[:300]
            print(f'PASS {name}: exit {code}, same verdict as check_platform_json.py, explanation written')
        assert subprocess.run([str(exe), '--version'], capture_output=True).returncode == 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
