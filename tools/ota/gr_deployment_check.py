"""SAM | 2026-10-24 +08:00 | Compare complete first-stage readbacks, never restore old user data or authorize Boot activation."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

def baseline_readback(before,after,signed):
    if len(before)!=0x100000 or len(after)!=len(before):raise ValueError('SNAPSHOT_SIZE')
    if len(signed)<912 or len(signed)>442368:raise ValueError('SIGNED_SIZE')
    # Known non-CAIRO BootInfo is 32 bytes. Any additional data must be
    # classified before using a loader which erases both SCA sectors.
    if before[32:8192]!=b'\xff'*(8192-32):raise ValueError('SCA_EXTRA_DATA')
    info=struct.unpack_from('<8I',after)
    if info[:5]!=(len(signed),sum(signed)&0xffffffff,0x202000,0x202000,11):
        raise ValueError('SCA_ROUTE_LENGTH_CHECKSUM')
    if info[5:]!=struct.unpack_from('<3I',before,20):raise ValueError('SCA_CONFIG_CHANGED')
    if after[32:8192]!=b'\xff'*(8192-32):raise ValueError('SCA_EXTRA_DATA_AFTER')
    if after[8192:8192+len(signed)]!=signed:raise ValueError('BASELINE_BYTES')
    erase_end=8192+(len(signed)+4095)//4096*4096
    if erase_end>0x6e000:raise ValueError('BASELINE_ERASE_RANGE')
    if after[8192+len(signed):erase_end]!=b'\xff'*(erase_end-8192-len(signed)):
        raise ValueError('BASELINE_ERASE_TAIL')
    if before[erase_end:]!=after[erase_end:]:raise ValueError('UNPLANNED_REGION_CHANGED')
    return dict(baseline_bytes_verified=True,user_regions_unchanged=True,
        boot_activation_authorized=False,device_health_verified=False,
        before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(after).hexdigest(),
        baseline_sha256=hashlib.sha256(signed).hexdigest(),erase_end_exclusive=0x200000+erase_end)

# SAM | 2026-10-24 +08:00 | Boot download can rewrite SCA implicitly; compare
# every other byte and require the latest signed app before any startup decision.
def boot_readback(before,after,signed,boot):
    if len(before)!=0x100000 or len(after)!=len(before):raise ValueError('SNAPSHOT_SIZE')
    if len(signed)<912 or len(signed)>442368:raise ValueError('SIGNED_SIZE')
    if not boot or len(boot)>0xa000:raise ValueError('BOOT_SIZE')
    if before[32:8192]!=b'\xff'*8160:raise ValueError('SCA_EXTRA_DATA')
    if before[0xec000:0xf6000]!=b'\xff'*0xa000:raise ValueError('BOOT_AREA_NOT_EMPTY')
    if before[8192:8192+len(signed)]!=signed:raise ValueError('PREEXISTING_BASELINE_BYTES')
    old=struct.unpack_from('<8I',before)
    if old[:5]!=(len(signed),sum(signed)&0xffffffff,0x202000,0x202000,11):
        raise ValueError('PREEXISTING_SCA_ROUTE')
    info=struct.unpack_from('<8I',after)
    if info[:5]!=(len(boot),sum(boot)&0xffffffff,0x2ec000,0x2ec000,11):
        raise ValueError('BOOT_SCA_ROUTE_LENGTH_CHECKSUM')
    # SAM | 2026-10-24 +08:00 | SDK APP_INFO supplies check_img/boot_delay
    # (gr_plat.h bytes24/25 -> gr5xx_dfu.h SCA bits8/9). Keep every other bit.
    if len(boot)<0x21c or struct.unpack_from('<5I',boot,0x200)!=(0x47525858,1,0x5526,0x2ec000,0x2ec000):
        raise ValueError('BOOT_APP_INFO')
    check,delay,security=boot[0x218:0x21b]
    if check!=1 or delay not in (0,1) or security!=0:raise ValueError('BOOT_APP_INFO_POLICY')
    expected_config=(old[5]&~0x300)|(check<<8)|(delay<<9)
    if info[5:]!=(expected_config,old[6],old[7]):raise ValueError('SCA_CONFIG_CHANGED')
    if after[32:8192]!=b'\xff'*8160:raise ValueError('SCA_EXTRA_DATA_AFTER')
    end=0xec000+(len(boot)+4095)//4096*4096
    if after[0xec000:0xec000+len(boot)]!=boot:raise ValueError('BOOT_BYTES')
    if after[0xec000+len(boot):end]!=b'\xff'*(end-0xec000-len(boot)):
        raise ValueError('BOOT_ERASE_TAIL')
    if before[8192:0xec000]!=after[8192:0xec000] or before[end:]!=after[end:]:
        raise ValueError('UNPLANNED_REGION_CHANGED')
    return dict(boot_bytes_verified=True,baseline_bytes_verified=True,user_regions_unchanged=True,
        sca_routes_boot=True,boot_activation_authorized=False,device_health_verified=False,
        before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(after).hexdigest(),
        baseline_sha256=hashlib.sha256(signed).hexdigest(),boot_sha256=hashlib.sha256(boot).hexdigest(),
        erase_end_exclusive=0x200000+end)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',required=True,type=Path)
    p.add_argument('--after',required=True,type=Path)
    p.add_argument('--signed',required=True,type=Path)
    p.add_argument('--boot',type=Path,help='Boot-only stage; no activation authorization')
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    before,after,signed=args.before.read_bytes(),args.after.read_bytes(),args.signed.read_bytes()
    report=boot_readback(before,after,signed,args.boot.read_bytes()) if args.boot else baseline_readback(before,after,signed)
    if args.output.exists():raise ValueError('OUTPUT_EXISTS')
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
