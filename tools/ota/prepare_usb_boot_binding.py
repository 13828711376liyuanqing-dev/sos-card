"""SAM | 2026-10-24 +08:00 | Rebind only the already-commissioned Boot's immutable baseline descriptor to the verified USB baseline; no automatic build, flash or journal edits."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'firmware_releases/GR_BOOT_COMMISSIONING_20261024'
OUT=ROOT/'firmware_releases/GR_BOOT_USB_BASELINE_20261024'

def sha(b):return hashlib.sha256(b).hexdigest()

def prepare():
    if OUT.exists():raise ValueError('Preserve existing Boot binding output')
    evidence=json.loads((OLD/'commissioning_evidence.json').read_text())
    accepted=json.loads((OLD/'first_boot_acceptance.json').read_text())
    if accepted['boot_first_entry_passed'] is not True:raise ValueError('No existing Boot acceptance')
    boot=(OLD/'BOOT_COMMISSIONING.bin').read_bytes()
    observed=(ROOT/'logs/ota_first_trial_live_20261024/r4_boot_readback.bin').read_bytes()
    journal=(ROOT/'logs/ota_first_trial_live_20261024/r4_boot_journal.bin').read_bytes()
    if observed[:len(boot)]!=boot or any(v!=255 for v in observed[len(boot):]):raise ValueError('Physical Boot differs')
    if len(journal)!=8192 or journal!=bytes([255])*8192:raise ValueError('Boot transaction exists; do not rebind')
    builds=json.loads((ROOT/'firmware_releases/gr_usb_bench_20261024/BUILD_VERIFIED.json').read_text())
    current=builds['baseline'];payload=(ROOT/current['payload_file']).read_bytes()
    if current['version']!='1.0.2' or current['build']!=3 or sha(payload)!=current['payload_sha256']:
        raise ValueError('Baseline identity mismatch')
    old_desc=struct.pack('<2I',evidence['payload_bytes'],1000002)+bytes.fromhex(evidence['baseline_sha256'])
    prefix=struct.pack('<3I',1,1,1)+bytes.fromhex(evidence['layout_pin']+evidence['data_pin']+evidence['public_pin'])
    if boot.count(prefix+old_desc+bytes(8))!=1:raise ValueError('Original provisioning mismatch')
    new_desc=struct.pack('<2I',len(payload),1000002)+hashlib.sha256(payload).digest()
    OUT.mkdir();(OUT/'Objects').mkdir();(OUT/'Listings').mkdir()
    text=(OLD/'yp001_boot_provision.c').read_text()
    replacement='{'+str(len(payload))+'u,1000002u,{'+','.join('0x%08xu'%v for v in struct.unpack('<8I',hashlib.sha256(payload).digest()))+'}}'
    text,n=re.subn(r'\{427328u,1000002u,\{[^}]+\}\}',replacement,text)
    if n!=1:raise ValueError('Original source descriptor changed')
    text='/* SAM | 2026-10-24 +08:00 | Bind the installed signed USB baseline; preserve existing Boot code, approval flags, pins and user regions. */\n'+text
    provision=OUT/'yp001_boot_provision.c';provision.write_text(text,encoding='ascii')
    tree=ET.parse(OLD/'GR_BOOT_COMMISSIONING.uvprojx');changed=0
    for p in tree.findall('.//FilePath'):
        if p.text and Path(p.text).name=='yp001_boot_provision.c':p.text=str(provision);changed+=1
    if changed!=1:raise ValueError('Provision source binding missing')
    tree.find('.//OutputDirectory').text=str(OUT/'Objects')+'\\'
    tree.find('.//ListingPath').text=str(OUT/'Listings')+'\\'
    project=OUT/'BOOT_BIND_USB_BASELINE.uvprojx';tree.write(project,encoding='utf8',xml_declaration=True)
    project.with_suffix('.uvoptx').write_bytes((OLD/'GR_BOOT_COMMISSIONING.uvoptx').read_bytes())
    report={'role':'BOOT_BASELINE_DESCRIPTOR_UPDATE_ONLY','baseline_version':'1.0.2','baseline_build':3,
        'old_payload_bytes':evidence['payload_bytes'],'new_payload_bytes':len(payload),
        'new_payload_sha256':sha(payload),'old_boot_sha256':sha(boot),
        'old_descriptor_hex':old_desc.hex(),'new_descriptor_hex':new_desc.hex(),
        'provision_offset':boot.index(prefix+old_desc+bytes(8))+len(prefix),
        'physical_boot_matches_commissioned':True,'physical_boot_journal_empty':True,
        'approval_flags_unchanged':True,'trust_pins_unchanged':True,'layout_unchanged':True,
        'compiled':False,'device_written':False,'r4_reupload_required':False,'app_rebuild_required':False}
    (OUT/'binding_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(project)

def verify():
    from gr_first_deploy import read_hex
    r=json.loads((OUT/'binding_manifest.json').read_text())
    log=(OUT/'Objects/YP001_OTA_BOOT_CANDIDATE.build_log.htm').read_text(errors='replace')
    if '0 Error(s), 0 Warning(s)' not in log:raise ValueError('Boot build not clean')
    memory=read_hex(OUT/'Objects/YP001_OTA_BOOT_CANDIDATE.hex')
    if min(memory)!=0x2ec000 or max(memory)>=0x2f6000:raise ValueError('Boot output extent')
    data=bytes(memory[i] for i in range(min(memory),max(memory)+1))
    old=(OLD/'BOOT_COMMISSIONING.bin').read_bytes();at=r['provision_offset']
    expected=old[:at]+bytes.fromhex(r['new_descriptor_hex'])+old[at+40:]
    if data!=expected:raise ValueError('Boot code or other bytes changed; refuse deployment')
    r.update(compiled=True,only_baseline_descriptor_changed=True,boot_bytes=len(data),boot_sha256=sha(data))
    (OUT/'BOOT_USB_BOUND.bin').write_bytes(data)
    (OUT/'binding_manifest.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))

if __name__=='__main__':
    if sys.argv[1:] == ['--verify']:verify()
    elif not sys.argv[1:]:prepare()
    else:raise SystemExit('Usage: prepare_usb_boot_binding.py [--verify]')
