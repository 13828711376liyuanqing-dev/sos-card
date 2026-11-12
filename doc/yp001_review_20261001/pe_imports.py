import struct
import sys
from pathlib import Path

def imports(path):
    data = Path(path).read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    count = struct.unpack_from('<H', data, pe + 6)[0]
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    directory = opt + (96 if magic == 0x10b else 112)
    import_rva = struct.unpack_from('<I', data, directory + 8)[0]
    sections = []
    sec = opt + optional_size
    for i in range(count):
        off = sec + i * 40
        virt_size, virt_addr, raw_size, raw_ptr = struct.unpack_from('<IIII', data, off + 8)
        sections.append((virt_addr, max(virt_size, raw_size), raw_ptr))
    def file_off(rva):
        for base, size, raw in sections:
            if base <= rva < base + size:
                return raw + rva - base
        raise ValueError(hex(rva))
    result = []
    off = file_off(import_rva)
    while True:
        fields = struct.unpack_from('<IIIII', data, off)
        if not any(fields):
            break
        name_off = file_off(fields[3])
        end = data.index(b'\0', name_off)
        result.append(data[name_off:end].decode('ascii'))
        off += 20
    return result

for name in sys.argv[1:]:
    print(name)
    for dll in imports(name):
        print(' ', dll)
