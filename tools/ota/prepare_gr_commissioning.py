"""SAM | 2026-10-24 +08:00 | Evidence-bound local first-Boot preparation; no build, download or production approval."""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from gr_first_deploy import inspect, provision
from gr_project_image import verify_image
from prepare_gr_first_deploy import LAYOUT_PIN, DATA_PIN, PUBLIC_PIN

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'firmware_releases/boot_bound_verify_cli_20261024_NOT_FLASHABLE'
OUT=ROOT/'firmware_releases/GR_BOOT_COMMISSIONING_20261024'
def sha(data):return hashlib.sha256(data).hexdigest()

def validate(root,snapshot,signed,binding,runtime):
    # These immutable candidate files identify content, not an approval signal.
    # Local commissioning approval below supersedes their historical deployment
    # status only for this recorded board; packaging/production gates stay closed.
    layout_bytes=(root/'tools/toolkit/contracts/layout_candidate.json').read_bytes()
    data_bytes=(root/'tools/toolkit/contracts/data_contract_candidate.json').read_bytes()
    if sha(layout_bytes)!=LAYOUT_PIN or sha(data_bytes)!=DATA_PIN:raise ValueError('CONTRACT_CHANGED')
    data=json.loads(data_bytes)
    if data.get('mode')!='NO_MIGRATION_NO_RESET' or data.get('preserve_latest_business_data') is not True:
        raise ValueError('DATA_POLICY_CHANGED')
    public=(root/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes()
    verified=verify_image(signed,public,'6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1',LAYOUT_PIN,DATA_PIN)
    if verified['version']!='1.0.2' or verified['build']!=3:raise ValueError('BASELINE_VERSION')
    size=len(signed)-904
    if (runtime.get('version')!='1.0.2' or runtime.get('build')!=3 or
        runtime.get('signature_ok') is not True or runtime.get('normal_context') is not True or
        runtime.get('wdt_running')!=1 or runtime.get('wdt_refresh')!=0 or runtime.get('payload_bytes')!=size):
        raise ValueError('RUNTIME_NOT_VERIFIED')
    raw=(root/'logs/ota_wdt_fix_20261024/normal_cli_verify_followup.txt').read_bytes()
    line=('refresh=0x0000 result=0 signature_ok=1 bytes=%d version=1000002'%size).encode()
    if line not in raw:raise ValueError('RUNTIME_RAW_EVIDENCE')
    if len(snapshot)!=0x100000 or snapshot[8192:8192+len(signed)]!=signed:raise ValueError('CURRENT_BASELINE')
    if struct.unpack_from('<5I',snapshot)!=(len(signed),sum(signed)&0xffffffff,0x202000,0x202000,11):
        raise ValueError('CURRENT_SCA')
    if snapshot[32:8192]!=b'\xff'*8160:raise ValueError('UNKNOWN_SCA_DATA')
    # inspect checks every future writable area is empty and fingerprints both
    # permanently excluded user areas. Unknown preserved bytes stay protected.
    inventory=inspect(snapshot,binding['snapshot_sha256'],{0x202000+i:b for i,b in enumerate(signed[:-904])})
    protected=inventory['protected']
    if protected!=binding.get('protected'):raise ValueError('PROTECTED_IDENTITY_CHANGED')
    return dict(scope='THIS_BOARD_FIRST_BOOT_ONLY',layout_checked=True,inventory_checked=True,
        baseline_checked=True,contract_content_unchanged=True,contract_history_status='CANDIDATE',
        production_approved=False,device_ota_accepted=False,download_ready=False,
        build_required=True,snapshot_is_atomic=False,snapshot_sha256=sha(snapshot),
        baseline_sha256=sha(signed[:-904]),signed_sha256=sha(signed),payload_bytes=size,
        runtime_evidence_sha256=sha(raw),protected=protected,
        policy='No user migration/reset; preserve unknown range; fresh pre/post readback before startup',
        layout_pin=LAYOUT_PIN,data_pin=DATA_PIN,public_pin=PUBLIC_PIN,
        flash_adapter_sha256=sha((root/'tools/ota/boot/yp001_ota_flash.c').read_bytes()))

def main():
    signed=(ROOT/'firmware_releases/baseline_wdt_fix_20261024/baseline_verify_cli_signed.bin').read_bytes()
    report=validate(ROOT,(EVIDENCE/'current_before_boot.bin').read_bytes(),signed,
        json.loads((EVIDENCE/'current_device_binding.json').read_text()),
        json.loads((ROOT/'logs/ota_wdt_fix_20261024/normal_runtime_acceptance.json').read_text()))
    if OUT.exists():raise ValueError('OUTPUT_EXISTS')
    OUT.mkdir()
    c=provision(signed[:-904],LAYOUT_PIN,DATA_PIN,PUBLIC_PIN)
    if c.count(' 0,0,1,')!=1:raise ValueError('PROVISION_TEMPLATE_CHANGED')
    c=c.replace(' 0,0,1,',' 1,1,1,',1)
    c=c.replace('Bind compact baseline; approvals remain closed. NOT FLASHABLE.',
        'Recorded local first-Boot commissioning approval only; no production/OTA acceptance.')
    provision_path=OUT/'yp001_boot_provision.c';provision_path.write_text(c,encoding='ascii')
    source=EVIDENCE/'BOOT_NOT_FLASHABLE.uvprojx';tree=ET.parse(source)
    for node in tree.iter('FilePath'):
        if node.text.endswith('yp001_boot_provision.c'):node.text=str(provision_path)
    for tag,folder in [('OutputDirectory','Objects'),('ListingPath','Listings')]:
        (OUT/folder).mkdir();tree.find('.//'+tag).text=str(OUT/folder)+'\\'
    project=OUT/'GR_BOOT_COMMISSIONING.uvprojx';tree.write(project,encoding='utf-8',xml_declaration=True)
    options=(ROOT/'ble_app_uart_c/Keil_6/YP001_GR5526.uvoptx').read_bytes()
    if b'-FO7 ' not in options or b'-FC8000 ' not in options or b'Segger\\JL2CM3.dll' not in options:
        raise ValueError('SAVED_DOWNLOAD_SETTINGS_CHANGED')
    # SAM | 2026-10-24 +08:00 | uVision discards options when TargetName differs;
    # align copied J-Link options with the isolated Boot target, not the App.
    option_tree=ET.fromstring(options)
    option_tree.find('.//TargetName').text=tree.find('.//TargetName').text
    options=ET.tostring(option_tree,encoding='utf-8',xml_declaration=True)
    project.with_suffix('.uvoptx').write_bytes(options)
    report.update(project_sha256=sha(project.read_bytes()),options_sha256=sha(options),
        provision_sha256=sha(provision_path.read_bytes()),compiled=False,device_written=False)
    (OUT/'commissioning_evidence.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('COMPILE ONLY; do not download until new AXF/map and first-deploy readback plan are checked:')
    print(project)

if __name__=='__main__':main()
