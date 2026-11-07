"""SAM | 2026-10-24 +08:00 | Offline first-deploy checks; never authorize device writes."""
import hashlib
import struct
from pathlib import Path

START = 0x202000
LIMIT = 0x26E000

def decode_hex(text):
    memory, base, ended = {}, 0, False
    for line in text.splitlines():
        if not line.strip():
            continue
        if ended or not line.startswith(':'):
            raise ValueError('HEX_RECORD')
        b = bytes.fromhex(line[1:])
        if len(b) < 5 or len(b) != b[0]+5 or sum(b) & 255:
            raise ValueError('HEX_CHECKSUM')
        size, address, kind = b[0], int.from_bytes(b[1:3], 'big'), b[3]
        data = b[4:-1]
        if kind == 0:
            for i, value in enumerate(data):
                at = base+address+i
                if at in memory:
                    raise ValueError('HEX_OVERLAP')
                memory[at] = value
        elif kind == 4 and size == 2 and address == 0:
            base = int.from_bytes(data, 'big') << 16
        elif kind == 1 and size == 0 and address == 0:
            ended = True
        elif kind == 5 and size == 4 and address == 0:
            pass  # Execution entry metadata, not a flash write.
        else:
            raise ValueError('HEX_TYPE')
    if not ended or not memory:
        raise ValueError('HEX_INCOMPLETE')
    return memory

def read_hex(path):
    return decode_hex(Path(path).read_text(encoding='ascii'))

def inspect(snapshot, expected_sha256, baseline_memory):
    if len(snapshot) != 0x100000 or hashlib.sha256(snapshot).hexdigest() != expected_sha256:
        raise ValueError('SNAPSHOT_IDENTITY')
    if not baseline_memory or min(baseline_memory) != START or max(baseline_memory) >= LIMIT:
        raise ValueError('BASELINE_RANGE')
    if len(baseline_memory) != max(baseline_memory)-START+1:
        raise ValueError('BASELINE_GAP')
    for name, address, size in [('B',0x280000,0x6c000),('boot',0x2ec000,0xa000),
            ('scratch',0x2f6000,0x1000),('journal0',0x2f7000,0x1000),
            ('journal1',0x2f8000,0x1000),('coordinator0',0x2f9000,0x1000),
            ('coordinator1',0x2fa000,0x1000)]:
        if snapshot[address-0x200000:address-0x200000+size] != b'\xff'*size:
            raise ValueError('AREA_NOT_ERASED:'+name)
    protected = []
    for name,address,size in [('preserved',0x26e000,0x12000),('nvds',0x2fe000,0x2000)]:
        protected.append(dict(name=name,start=address,bytes=size,
            sha256=hashlib.sha256(snapshot[address-0x200000:address-0x200000+size]).hexdigest()))
    current_size = struct.unpack_from('<I', snapshot)[0]
    return dict(baseline_bytes=len(baseline_memory), flash_ready=False,
                compact_baseline_required=current_size > LIMIT-START,
                protected=protected, snapshot_is_atomic=False)

def hex_image(payload, start):
    if start != START or not payload or start+len(payload) > LIMIT:
        raise ValueError('SIGNED_RANGE')
    def record(address,kind,data):
        b=bytes([len(data)])+address.to_bytes(2,'big')+bytes([kind])+data
        return ':'+(b+bytes([-sum(b)&255])).hex().upper()
    lines, upper = [], None
    for offset in range(0,len(payload),16):
        address=start+offset
        if address >> 16 != upper:
            upper=address >> 16
            lines.append(record(0,4,upper.to_bytes(2,'big')))
        lines.append(record(address&65535,0,payload[offset:offset+16]))
    lines.append(record(0,1,b''))
    return '\n'.join(lines)+'\n'

def provision(payload, layout_hash, data_hash, public_hash):
    if not payload or len(payload)+904 > LIMIT-START:
        raise ValueError('SIGNED_RANGE')
    def digest(value):
        if len(value)!=64 or value=='0'*64:
            raise ValueError('PIN')
        return '{'+','.join('0x%02x'%b for b in bytes.fromhex(value))+'}'
    words=struct.unpack('<8I',hashlib.sha256(payload).digest())
    return ('/* SAM | 2026-10-24 +08:00 | Bind compact baseline; approvals remain closed. NOT FLASHABLE. */\n'
            '#include "yp001_ota_entry.h"\nconst yp_boot_provision yp001_boot_provision = {\n 0,0,1,\n '
            +',\n '.join(map(digest,[layout_hash,data_hash,public_hash]))+',\n '
            +'{%du,1000002u,{'%len(payload)+','.join('0x%08xu'%w for w in words)+'}},\n 0,0\n};\n')
