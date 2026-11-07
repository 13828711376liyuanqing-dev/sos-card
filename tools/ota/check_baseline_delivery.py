"""SAM | 2026-10-23 +08:00 | Refuse baseline HEX touching unknown B or user regions; this does not authorize a full-chip erase."""
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'firmware_releases/baseline_review_20261023'

def inspect(path):
    data={};upper=0;ended=False
    for line in path.read_text().splitlines():
        if not line.strip():continue
        assert line.startswith(':') and not ended
        r=bytes.fromhex(line[1:]);assert len(r)==r[0]+5 and sum(r)%256==0
        n,a,t=r[0],int.from_bytes(r[1:3],'big'),r[3]
        if t==4:
            assert n==2;upper=int.from_bytes(r[4:6],'big')<<16
        elif t==0:
            for i,v in enumerate(r[4:-1]):
                address=upper+a+i
                assert 0x202000<=address<0x277000, 'Protected address in baseline'
                assert address not in data or data[address]==v
                data[address]=v
        elif t==1:assert n==0;ended=True
        else:assert t==5 and n==4
    assert ended and data
    low,high=min(data),max(data)
    image=bytes(data.get(a,255) for a in range(low,high+1))
    assert b'YP001_FW|GR5526|001.000.002|3|END' in image
    return data,{'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                 'first_address':hex(low),'last_address':hex(high),
                 'erase_first':hex(low//4096*4096),'erase_end_exclusive':hex((high+4096)//4096*4096),
                 'image_sha256':hashlib.sha256(image).hexdigest(),'image_bytes':len(image)}

main,report=inspect(OUT/'main_YP001_GR5526.hex')
delivery,_=inspect(OUT/'delivery_YP001_GR5526.hex')
# SAM | 2026-10-23 +08:00 | Independent builds embed __TIME__ in the boot
# banner. Permit only its eight ASCII bytes after matching the exact Build prefix.
assert main.keys()==delivery.keys(),'Address maps differ'
low,high=min(main),max(main)
left=bytes(main.get(a,255) for a in range(low,high+1))
right=bytes(delivery.get(a,255) for a in range(low,high+1))
pattern=rb'Build: [A-Z][a-z]{2} [ 0-9][0-9] [0-9]{4} ([0-2][0-9]:[0-5][0-9]:[0-5][0-9])\r\n'
lm,rm=list(re.finditer(pattern,left)),list(re.finditer(pattern,right))
assert len(lm)==len(rm)==1 and lm[0].span()==rm[0].span(),'Build banner differs'
first,last=lm[0].span(1)
assert left[:first]==right[:first] and left[last:]==right[last:],'Non-time firmware bytes differ'
final=OUT/'YP001_GR5526_BASELINE_1.0.2.hex'
source=(OUT/'main_YP001_GR5526.hex').read_bytes()
if final.exists():assert final.read_bytes()==source,'Refuse replacement'
else:final.write_bytes(source)
report.update({'main_delivery_equal':main==delivery,'only_build_time_differs':True,
               'main_build_time':left[first:last].decode(),'delivery_build_time':right[first:last].decode(),
               'ota_installable':False,'flash_performed':False,
               'requires_sector_erase':True,'protected_from':'0x277000',
               'note':'Application baseline only. No Boot deployment or backup-slot erase.'})
(OUT/'address_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
