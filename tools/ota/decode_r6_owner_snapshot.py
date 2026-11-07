"""SAM | 2026-10-27 +08:00 | Decode immutable owner/RAM snapshots with ARM short-enum ABI and CRC; never write or authorize a device."""
from pathlib import Path
import ctypes,struct,zlib,json,sys

class Record(ctypes.LittleEndianStructure):
    _fields_=[('epoch',ctypes.c_uint32),('phase',ctypes.c_uint8),('job',ctypes.c_char*65),('hash',ctypes.c_char*65),('target',ctypes.c_char*8),('version',ctypes.c_char*64),('source',ctypes.c_char*64),('actual',ctypes.c_char*64),('outcome',ctypes.c_char*8)]
class Page(ctypes.LittleEndianStructure):
    _fields_=[('magic',ctypes.c_uint32),('generation',ctypes.c_uint32),('record',Record),('total',ctypes.c_uint32),('durable',ctypes.c_uint32),('crc',ctypes.c_uint32),('commit',ctypes.c_uint32)]

def decode(folder):
    assert ctypes.sizeof(Record)==344 and ctypes.sizeof(Page)==368
    data=(folder/'owner.bin').read_bytes();assert len(data)==8192
    rows=[]
    for n in (0,1):
        block=data[n*4096:(n+1)*4096];v=Page.from_buffer_copy(block[:ctypes.sizeof(Page)])
        rows.append({'page':n,'valid':v.magic==0x594f5432 and v.commit==0 and v.crc==zlib.crc32(block[:Page.crc.offset]),
            'generation':v.generation,'epoch':v.record.epoch,'phase':v.record.phase,'total':v.total&0x7fffffff,'durable':v.durable,
            'job_matches':bytes(v.record.job)==b'1a092304771d1850f747237e3964fc5e071c63618f661c349494efe75e14b752',
            'hash_matches':bytes(v.record.hash)==b'eaf020f7a88d368d3017cd2c093535beb20b35f6001a71a505cf54662ad659f4'})
    valid=[r for r in rows if r['valid'] and r['job_matches'] and r['hash_matches']]
    result={'pages':rows,'latest':max(valid,key=lambda r:r['generation']) if valid else None}
    q=(folder/'quiet.bin').read_bytes()
    result['quiet']={'phase':q[0],'kind':q[1],'token':struct.unpack_from('<I',q,1044)[0],'at_ms':struct.unpack_from('<I',q,1048)[0],
        'length':struct.unpack_from('<I',q,1056)[0],'granted':q[1060],'allowed':q[1061],
        'request_type':q[23],'request_session':struct.unpack_from('<I',q,26)[0],'request_sequence':struct.unpack_from('<I',q,30)[0],
        'request_offset':struct.unpack_from('<I',q,34)[0]}
    result['uart_fault_words']=list(struct.unpack('<11I',(folder/'uart_first_fault.bin').read_bytes()))
    result['outer_denial_words']=list(struct.unpack('<10I',(folder/'outer_denial.bin').read_bytes()))
    result['measure_words']=list(struct.unpack('<12I',(folder/'measure.bin').read_bytes()))
    (folder/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':print(json.dumps(decode(Path(sys.argv[1])),indent=2))
