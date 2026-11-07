"""SAM | 2026-10-28 20:50 +08:00 | Exact LuaDB v2 image size of a CAT1 USB import set (mirrors tools/ota/portable/Cat1Native.LuaDb) because the 512 KiB script partition has only a few hundred bytes spare.
Usage: python luadb_size.py <USB_IMPORT dir>   (main.lua is compiled with Luatools luac -s, as the merge does)"""
from pathlib import Path
import subprocess, sys, tempfile

LUAC = r'D:\Installers\_temp\tools\luac_64bit.exe'
CAPACITY = 0x80000


def size(usb):
    files = {}
    for p in Path(usb).iterdir():
        if p.name == 'main.lua':
            with tempfile.TemporaryDirectory() as t:
                out = Path(t) / 'main.luac'
                subprocess.run([LUAC, '-s', '-o', str(out), str(p)], check=True)
                files['main.luac'] = out.stat().st_size
        else:
            files[p.name] = p.stat().st_size
    total = 24 + sum(18 + len(k.encode()) + v for k, v in files.items()) + 18 + len(b'.airm2m_all_crc#.bin') + 16
    return total, len(files)


if __name__ == '__main__':
    total, n = size(sys.argv[1])
    print(f'files={n} luadb_bytes={total} capacity={CAPACITY} spare={CAPACITY - total}')
    raise SystemExit(0 if total <= CAPACITY else 1)
