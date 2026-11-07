"""SAM | 2026-10-24 +08:00 | Prepare isolated, non-flashable Boot inputs from pinned read-only evidence."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import gr_first_deploy as deploy
from gr_project_image import verify_image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'firmware_releases/gr_first_deploy_20261024_NOT_FLASHABLE'
SNAPSHOT_PIN = '6c1be47366f3b226759d9dff3b106a3aa5c261929a9ab8e9c05083f417c9226f'
HEX_PIN = '3f68f4c3eb1b59fe52363fb3a4641cb22ed91d9f78c00d0132f73fa8d475cf4b'
LAYOUT_PIN = '4f46b271bc865a8f5b1d3c74083d3645bfb8f281e0700dd29014ba6e5c6fb527'
DATA_PIN = '1c5ef5151909da84307b9f6ba894fbaee1250c21d43377f3c8a094e3e4e6a50c'
PUBLIC_PIN = '711e5a13985e3edaed4b4913928bd0583640557e0959af0dffbd0ac893733b8d'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    baseline=ROOT/'firmware_releases/baseline_candidate_20261024_usbfix/GR5526/YP001_GR5526.hex'
    if sha(baseline.read_bytes()) != HEX_PIN:
        raise ValueError('BASELINE_IDENTITY')
    for name,pin in [('layout_candidate.json',LAYOUT_PIN),('data_contract_candidate.json',DATA_PIN)]:
        if sha((ROOT/'tools/toolkit/contracts'/name).read_bytes()) != pin:
            raise ValueError('CONTRACT_IDENTITY')
    memory=deploy.read_hex(baseline)
    snapshot=(ROOT/'logs/ota_sequential_20261024/device_readonly/gr_current_flash_1m.bin').read_bytes()
    report=deploy.inspect(snapshot,SNAPSHOT_PIN,memory)
    payload=bytes(memory[a] for a in range(min(memory),max(memory)+1))
    signed=(OUT/'GR_BASELINE_1.0.2_signed.bin').read_bytes()
    public=(ROOT/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes()
    # Independent Python verifier reads public material only; never exports the private key.
    signature_report=verify_image(signed,public,
        '6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1',LAYOUT_PIN,DATA_PIN)
    if len(signed)!=len(payload)+904 or signed[:len(payload)]!=payload:
        raise ValueError('SIGNED_PAYLOAD_IDENTITY')
    header=signed[len(payload):len(payload)+128]
    if (header[:4]!=b'YPGR' or header[32:64]!=bytes.fromhex(LAYOUT_PIN)
            or header[64:96]!=hashlib.sha256(payload).digest()
            or header[96:128]!=bytes.fromhex(DATA_PIN)
            or sha(signed[len(payload)+128:len(payload)+648])!=PUBLIC_PIN):
        raise ValueError('SIGNED_BINDING')
    encoded=deploy.hex_image(signed,deploy.START)
    if deploy.decode_hex(encoded)!={deploy.START+i:b for i,b in enumerate(signed)}:
        raise ValueError('HEX_READBACK')
    (OUT/'GR_BASELINE_1.0.2_signed.hex').write_text(encoded,encoding='ascii')
    provision=OUT/'yp001_boot_provision.c'
    provision.write_text(deploy.provision(payload,LAYOUT_PIN,DATA_PIN,PUBLIC_PIN),encoding='ascii')
    # Keep original Keil source/config/outputs untouched. No download actions.
    original=ROOT/'tools/ota/gr_boot/YP001_OTA_BOOT.uvprojx'
    tree=ET.parse(original)
    for node in tree.iter('FilePath'):
        if node.text.endswith('yp001_boot_provision.c'):
            node.text=str(provision)
    for tag,folder in [('OutputDirectory','Objects'),('ListingPath','Listings')]:
        (OUT/folder).mkdir(exist_ok=True)
        tree.find('.//'+tag).text=str(OUT/folder)+'\\'
    tree.write(OUT/'BOOT_NOT_FLASHABLE.uvprojx',encoding='utf-8',xml_declaration=True)
    report.update(schema='YP001_FIRST_DEPLOY_PREPARATION_V1',
        source_version='1.0.2', baseline_sha256=sha(payload), signed_sha256=sha(signed),
        signed_bytes=len(signed),signed_start=deploy.START,signed_end_exclusive=deploy.START+len(signed),
        snapshot_sha256=SNAPSHOT_PIN, original_project_sha256=sha(original.read_bytes()),
        layout_pin=LAYOUT_PIN,data_pin=DATA_PIN,public_block_pin=PUBLIC_PIN,
        approvals=dict(layout_approved=False,inventory_complete=False,baseline_approved=True),
        device_written=False,sca_routing_verified=False,signature_verification=signature_report,
        blockers=['Immutable layout/data approvals closed',
                  'Flash algorithm implicit SCA updates/order not validated',
                  'Need fresh protected-region readback before and after deployment',
                  'Signed compact baseline and Boot health not device-tested'])
    (OUT/'preparation_manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(signed_bytes=len(signed),flash_ready=False,output=str(OUT))))

if __name__=='__main__':
    main()
