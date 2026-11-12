"""SAM | 2026-11-04 +08:00 | Headless test of backend/姓名字形生成器_后台版.html through its ?auto= hook (Chrome or Edge):
Seq is the generation time (the 2024 value 1730600000 of the old hook is refused), the room may only use the built-in 28px
characters, and the generated file passes check_platform_json.py (all Name/Campus glyphs, CRC, size). Needs a local Chrome/Edge."""
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = (HERE / 'backend' / '姓名字形生成器_后台版.html').as_uri()
BROWSERS = [Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),
            Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')]


def run(browser, query):
    r = subprocess.run([str(browser), '--headless=new', '--disable-gpu', '--enable-logging=stderr', '--v=0',
                        '--virtual-time-budget=20000', '--dump-dom', PAGE + '?' + urllib.parse.urlencode(query)],
                       capture_output=True, timeout=120)
    m = re.search(r'<pre id="auto-out"[^>]*>(.*?)</pre>', r.stdout.decode('utf-8', 'replace'), re.S)
    errs = [l for l in r.stderr.decode('utf-8', 'replace').splitlines() if 'Uncaught' in l]
    assert not errs, errs[0]
    return html.unescape(m.group(1)) if m else ''


def main():
    browser = next((b for b in BROWSERS if b.exists()), None)
    if not browser:
        print('SKIP: no Chrome/Edge'); return 0
    out = run(browser, {'auto': '张秀珺', 'room': '1#1-102', 'campus': '泰康之家·燕园'})
    msg = json.loads(out)
    now = int(time.time())
    assert abs(msg['Seq'] - now) < 600, msg['Seq']
    assert len(msg['Glyphs']) == 13, len(msg['Glyphs'])
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / 'm.json'; f.write_text(out, encoding='utf-8')
        r = subprocess.run([sys.executable, str(HERE / 'check_platform_json.py'), str(f)], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        assert r.returncode == 0 and 'WARN' not in r.stdout, r.stdout
    print('PASS generated file: Seq = now, 13 glyphs (all Name/Campus characters), check_platform_json clean')
    assert run(browser, {'auto': '张秀珺', 'campus': '泰康之家·燕园', 'seq': '1730600000'}).startswith('ERROR Seq 1730600000')
    print('PASS a 2024 Seq (the old hook value) is refused')
    assert run(browser, {'auto': '张秀珺', 'room': 'A区2幢1203', 'campus': '泰康之家·燕园'}).startswith('ERROR 房号')
    print('PASS a room with characters the device cannot show is refused')
    seq = str(now - 100)
    assert json.loads(run(browser, {'auto': '张秀珺', 'campus': '泰康之家·燕园', 'seq': seq}))['Seq'] == int(seq)
    print('PASS explicit &seq= (bench) is kept when valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
