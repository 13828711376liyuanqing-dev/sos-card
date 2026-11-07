"""SAM | 2026-10-24 +08:00 | Bind new Boot outputs to the closed provision and exact signed baseline; never permit flashing."""
import hashlib
import json
import re
import struct
from pathlib import Path
from gr_first_deploy import read_hex
from prepare_gr_first_deploy import ROOT, OUT, LAYOUT_PIN, DATA_PIN, PUBLIC_PIN
from gr_project_image import verify_image

def main():
    report=json.loads((OUT/'preparation_manifest.json').read_text(encoding='utf-8'))
    log=(OUT/'boot_build.log').read_text(errors='replace')
    if '0 Error(s), 0 Warning(s).' not in log:
        raise ValueError('BUILD_NOT_CLEAN')
    original=ROOT/'tools/ota/gr_boot/YP001_OTA_BOOT.uvprojx'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=report['original_project_sha256']:
        raise ValueError('ORIGINAL_PROJECT_CHANGED')
    memory=read_hex(OUT/'BOOT_NOT_FLASHABLE.hex')
    if min(memory)!=0x2ec000 or max(memory)>=0x2f6000:
        raise ValueError('BOOT_RANGE')
    binary=(OUT/'BOOT_NOT_FLASHABLE.bin').read_bytes()
    if memory!={0x2ec000+i:b for i,b in enumerate(binary)}:
        raise ValueError('BOOT_HEX_BIN_MISMATCH')
    descriptor=(struct.pack('<3I',0,0,1)+bytes.fromhex(LAYOUT_PIN+DATA_PIN+PUBLIC_PIN)
        +struct.pack('<2I',report['baseline_bytes'],1000002)+bytes.fromhex(report['baseline_sha256'])
        +bytes(8))
    if binary.count(descriptor)!=1:
        raise ValueError('BOOT_PROVISION_BINARY_MISMATCH')
    maptext=(OUT/'Listings/YP001_OTA_BOOT_CANDIDATE.map').read_text(errors='replace')
    match=re.search(r'Load Region LR_FLASH \(Base: 0x002ec000, Size: (0x[0-9a-f]+), Max: 0x0000a000',maptext)
    if not match or int(match[1],16)>40960:
        raise ValueError('BOOT_LOAD_REGION')
    image=(OUT/'GR_BASELINE_1.0.2_signed.bin').read_bytes()
    public=(ROOT/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes()
    publicpin='6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1'
    rejected=[]
    for name,offset in [('payload',100),('header',len(image)-904),('signature',len(image)-1)]:
        changed=bytearray(image);changed[offset]^=1
        try:
            verify_image(bytes(changed),public,publicpin,LAYOUT_PIN,DATA_PIN)
        except ValueError:
            rejected.append(name)
        else:
            raise ValueError('TAMPER_ACCEPTED:'+name)
    result=dict(flash_ready=False,build_errors=0,build_warnings=0,
        boot_load_region_bytes=int(match[1],16),boot_file_bytes=len(binary),
        boot_end_exclusive=0x2ec000+len(binary),boot_budget_bytes=40960,
        boot_budget_free=40960-int(match[1],16),provision_binary_matched=True,
        signature_tampering_rejected=rejected,original_project_unchanged=True,files={})
    for relative in ['BOOT_NOT_FLASHABLE.bin','BOOT_NOT_FLASHABLE.hex',
            'GR_BASELINE_1.0.2_signed.bin','GR_BASELINE_1.0.2_signed.hex',
            'yp001_boot_provision.c','Objects/YP001_OTA_BOOT_CANDIDATE.axf']:
        content=(OUT/relative).read_bytes()
        result['files'][relative]=dict(bytes=len(content),sha256=hashlib.sha256(content).hexdigest())
    (OUT/'build_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
