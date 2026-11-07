"""SAM | 2026-10-27 +08:00 | Verify normal-start gen2->gen3 repair exactly; no device writes or installation authority."""
from pathlib import Path
import argparse,json,struct,zlib
from check_r6_control_preboot_readback import check as check_download

def check(before,after,app,boot):
    if len(before)!=0x100000 or len(after)!=0x100000:raise ValueError('SNAPSHOT_SIZE')
    j=before[0xf8000:0xf8000+124];w=list(struct.unpack('<31I',j))
    if w[0]!=0x59504231 or w[1]!=2 or w[3:7]!=[1,0,0,0] or w[29]!=zlib.crc32(j[:116]) or w[30]!=0:raise ValueError('EXPECTED_PREPARED_GEN2')
    import hashlib
    descriptor=struct.pack('<II',len(app)-904,1000002)+hashlib.sha256(app[:-904]).digest()
    w[1]=3;w[7:17]=struct.unpack('<10I',descriptor);w[29]=zlib.crc32(struct.pack('<29I',*w[:29]));page=struct.pack('<31I',*w)+b'\xff'*(4096-124)
    if after[0xf7000:0xf8000]!=page:raise ValueError('EXACT_PREPARED_GEN3_REPAIR')
    adjusted=bytearray(before);adjusted[0xf7000:0xf8000]=page
    result=check_download(bytes(adjusted),after,app,boot)
    result.update(before_sha256=hashlib.sha256(before).hexdigest(),prepared_generation=3,repair_did_not_activate=True,owner_candidate_nvds_preserved=True)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--before',required=True,type=Path);p.add_argument('--after',required=True,type=Path);p.add_argument('--app',required=True,type=Path);p.add_argument('--boot',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise ValueError('OUTPUT_EXISTS')
    v=check(*(x.read_bytes() for x in (a.before,a.after,a.app,a.boot)));a.output.write_text(json.dumps(v,indent=2),encoding='utf-8');print(json.dumps(v,indent=2))
if __name__=='__main__':main()
