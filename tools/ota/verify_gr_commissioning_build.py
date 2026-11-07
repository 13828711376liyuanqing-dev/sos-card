"""SAM | 2026-10-24 +08:00 | Check user-built Boot and prepare one target-matched download project; never builds or downloads."""
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from gr_first_deploy import read_hex

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'firmware_releases/GR_BOOT_COMMISSIONING_20261024'
def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    evidence=json.loads((OUT/'commissioning_evidence.json').read_text())
    axf=OUT/'Objects/YP001_OTA_BOOT_CANDIDATE.axf'
    log=(OUT/'Objects/YP001_OTA_BOOT_CANDIDATE.build_log.htm').read_text(errors='replace')
    if '0 Error(s), 0 Warning(s).' not in log:raise ValueError('BUILD_NOT_CLEAN')
    text=(OUT/'Listings/YP001_OTA_BOOT_CANDIDATE.map').read_text(errors='replace')
    load=re.search(r'Load Region LR_FLASH \(Base: 0x002ec000, Size: (0x[0-9a-f]+), Max: 0x0000a000',text)
    if not load or int(load[1],16)>0xa000:raise ValueError('LOAD_RANGE')
    binary=(OUT/'BOOT_COMMISSIONING.bin').read_bytes()
    memory=read_hex(OUT/'BOOT_COMMISSIONING.hex')
    if not binary or len(binary)>0xa000 or memory!={0x2ec000+i:b for i,b in enumerate(binary)}:
        raise ValueError('BOOT_HEX_BIN_RANGE')
    descriptor=(struct.pack('<3I',1,1,1)+bytes.fromhex(evidence['layout_pin']+evidence['data_pin']+evidence['public_pin'])
        +struct.pack('<2I',evidence['payload_bytes'],1000002)+bytes.fromhex(evidence['baseline_sha256'])+bytes(8))
    if binary.count(descriptor)!=1:raise ValueError('APPROVED_BASELINE_DESCRIPTOR')
    if sha((OUT/'yp001_boot_provision.c').read_bytes())!=evidence['provision_sha256']:
        raise ValueError('PROVISION_SOURCE_CHANGED')
    if sha((ROOT/'tools/ota/boot/yp001_ota_flash.c').read_bytes())!=evidence['flash_adapter_sha256']:
        raise ValueError('PROTECTION_SOURCE_CHANGED')
    project=OUT/'BOOT_DOWNLOAD_ONLY.uvprojx'
    if project.exists():raise ValueError('DOWNLOAD_PROJECT_EXISTS')
    tree=ET.parse(OUT/'GR_BOOT_COMMISSIONING.uvprojx')
    for group in tree.findall('.//Groups'):group.clear()
    tree.find('.//OutputDirectory').text=str(OUT/'Objects')+'\\'
    tree.find('.//OutputName').text='YP001_OTA_BOOT_CANDIDATE'
    master=ET.parse(ROOT/'ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx')
    tree.find('.//FlashDriverDll').text=master.find('.//FlashDriverDll').text
    options=ET.parse(ROOT/'ble_app_uart_c/Keil_6/YP001_GR5526.uvoptx')
    options.find('.//TargetName').text=tree.find('.//TargetName').text
    raw=ET.tostring(options.getroot(),encoding='utf-8',xml_declaration=True)
    if b'Segger\\JL2CM3.dll' not in raw or b'-FO7 ' not in raw or b'-FC8000 ' not in raw:
        raise ValueError('JLINK_OPTIONS_CHANGED')
    tree.write(project,encoding='utf-8',xml_declaration=True)
    project.with_suffix('.uvoptx').write_bytes(raw)
    report=dict(build_errors=0,build_warnings=0,load_region_bytes=int(load[1],16),
        boot_bytes=len(binary),boot_start=0x2ec000,boot_end_exclusive=0x2ec000+len(binary),
        expected_erase_end=0x2ec000+(len(binary)+4095)//4096*4096,
        baseline_descriptor_matched=True,baseline_payload_bytes=evidence['payload_bytes'],
        axf_sha256=sha(axf.read_bytes()),boot_sha256=sha(binary),
        project_sha256=sha(project.read_bytes()),options_sha256=sha(raw),
        target_name=tree.find('.//TargetName').text,reset_and_run=False,
        data_protection_readback_required=True,startup_authorized=False,
        production_approved=False,device_written=False)
    (OUT/'boot_download_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));print(project)

if __name__=='__main__':main()
