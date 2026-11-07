"""SAM | 2026-10-27 16:30 +08:00 | Read-only comparison after R6 repair downloads, before running the new Boot."""
from pathlib import Path
import argparse,hashlib,json,struct

def check(before,after,app,boot):
    if len(before)!=0x100000 or len(after)!=0x100000: raise ValueError('SNAPSHOT_SIZE')
    if not 912<=len(app)<=0x6c000 or not 0<len(boot)<=0xa000: raise ValueError('IMAGE_SIZE')
    if before[32:0x2000]!=b'\xff'*(0x2000-32) or after[32:0x2000]!=b'\xff'*(0x2000-32): raise ValueError('SCA_EXTRA_DATA')
    old=struct.unpack_from('<8I',before); info=struct.unpack_from('<8I',after)
    if old[2:5]!=(0x2ec000,0x2ec000,11): raise ValueError('OLD_BOOT_ROUTE')
    if len(boot)<0x21c or struct.unpack_from('<5I',boot,0x200)!=(0x47525858,1,0x5526,0x2ec000,0x2ec000): raise ValueError('BOOT_INFO')
    check_flag,delay,security=boot[0x218:0x21b]
    if check_flag!=1 or delay not in (0,1) or security!=0: raise ValueError('BOOT_INFO_POLICY')
    config=(old[5]&~0x300)|(check_flag<<8)|(delay<<9)
    if info!=(len(boot),sum(boot)&0xffffffff,0x2ec000,0x2ec000,11,config,old[6],old[7]): raise ValueError('NEW_BOOT_ROUTE')
    append=0x2000+(len(app)+4095)//4096*4096; bootend=0xec000+(len(boot)+4095)//4096*4096
    if after[0x2000:0x2000+len(app)]!=app or after[0x2000+len(app):append]!=b'\xff'*(append-0x2000-len(app)): raise ValueError('APP_BYTES_OR_TAIL')
    if after[0xec000:0xec000+len(boot)]!=boot or after[0xec000+len(boot):bootend]!=b'\xff'*(bootend-0xec000-len(boot)): raise ValueError('BOOT_BYTES_OR_TAIL')
    if before[append:0xec000]!=after[append:0xec000] or before[bootend:]!=after[bootend:]: raise ValueError('PROTECTED_REGION_CHANGED')
    return {'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest(),'app_sha256':hashlib.sha256(app).hexdigest(),'boot_sha256':hashlib.sha256(boot).hexdigest(),'sca_routes_boot':True,'protected_regions_unchanged':True,'running_boot_or_device_health_verified':False}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--app',type=Path,required=True);p.add_argument('--boot',type=Path,required=True);p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    if a.output.exists():raise ValueError('OUTPUT_EXISTS')
    report=check(*(x.read_bytes() for x in (a.before,a.after,a.app,a.boot)));a.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
