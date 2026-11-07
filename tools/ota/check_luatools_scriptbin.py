"""SAM | 2026-10-28 20:55 +08:00 | Parse the LuaDB v2 script.bin that Luatools actually generated and compare every member with a frozen USB import set (main.lua compiled with luac -s), because a GUI import is not proof of what was flashed.
Usage: python check_luatools_scriptbin.py <script.bin> <USB_IMPORT dir>"""
from pathlib import Path
import hashlib, struct, subprocess, sys, tempfile

LUAC = r'D:\Installers\_temp\tools\luac_64bit.exe'
CRC = '.airm2m_all_crc#.bin'


def read(b):
    assert b[:4] == bytes([1, 4, 0x5a, 0xa5]) and b[20] == 254, 'NOT_LUADB_V2'
    count = struct.unpack_from('<H', b, 18)[0]; pos = 24; out = {}
    for i in range(count):
        start = pos; n = b[pos + 7]; pos += 8; name = b[pos:pos + n].decode(); pos += n + 2
        size = struct.unpack_from('<I', b, pos)[0]; pos += 4 + 4; data = b[pos:pos + size]; pos += size
        if name == CRC: assert data == hashlib.md5(b[:pos - size]).digest() and i == count - 1, 'LUADB_MD5'
        else: out[name] = data
    assert not any(b[pos:]), 'TRAILING_NONZERO'  # Luatools zero-pads to the full partition
    return out


def main(binfile, usb):
    b = Path(binfile).read_bytes(); members = read(b); usb = Path(usb); bad = []
    expected = {}
    for p in usb.iterdir():
        if p.name == 'main.lua':
            with tempfile.TemporaryDirectory() as t:
                o = Path(t) / 'm.luac'; subprocess.run([LUAC, '-s', '-o', str(o), str(p)], check=True); expected['main.luac'] = o.read_bytes()
        else: expected[p.name] = p.read_bytes()
    for k in sorted(set(members) | set(expected)):
        if members.get(k) != expected.get(k): bad.append(k)
    print(f'script.bin bytes={len(b)} members={len(members)} expected={len(expected)} mismatched={bad}')
    raise SystemExit(0 if not bad else 1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
