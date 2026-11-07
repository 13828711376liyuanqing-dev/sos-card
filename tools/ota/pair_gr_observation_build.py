"""SAM | 2026-10-25 +08:00 | Validate manual app build, sign, prepare matching Boot source; no compilation or device access."""
from pathlib import Path
import hashlib,json,re,struct,subprocess,xml.etree.ElementTree as E
from gr_project_image import verify_image
from prepare_gr_first_deploy import LAYOUT_PIN,DATA_PIN
r=Path(__file__).resolve().parents[2]
out=r/'firmware_releases/gr_observation_fix_20261025/baseline'
m=json.loads((out/'source_manifest.json').read_text())
for p,h in m['sources'].items():
 assert hashlib.sha256((r/'ble_app_uart_c/Src'/p).read_bytes()).hexdigest()==h,'SOURCE_CHANGED: '+p
log=(out/'Objects/YP001_GR5526.build_log.htm').read_text(errors='replace')
assert re.search(r'0 Error\(s\), 0 Warning\(s\)',log),'MANUAL_BUILD_NOT_PASSED'
hexf=out/'Objects/YP001_GR5526.hex';axf=hexf.with_suffix('.axf')
assert hexf.is_file() and axf.is_file()
assert min(hexf.stat().st_mtime,axf.stat().st_mtime)>=max((r/'ble_app_uart_c/Src'/p).stat().st_mtime for p in m['sources']),'STALE_BUILD'
signed=out/'baseline_signed.bin'
assert not signed.exists(),'PRESERVE_EXISTING_SIGNED_ARTIFACT'
subprocess.run([str(r/'logs/ota_first_trial_live_20261024/GrBaselineSign_current.exe'),str(hexf),str(r/'tools/toolkit/test_keys'),str(r/'tools/toolkit/contracts/layout_candidate.json'),str(r/'tools/toolkit/contracts/data_contract_candidate.json'),'1.0.2',str(signed)],check=True,capture_output=True)
data=signed.read_bytes()
v=verify_image(data,(r/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes(),'6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1',LAYOUT_PIN,DATA_PIN)
assert v['version']=='1.0.2' and v['build']==3
old=r/'firmware_releases/GR_BOOT_MOTION_BASELINE_20261024'
bm=json.loads((old/'binding_manifest.json').read_text());boot=(old/'BOOT_MOTION_BOUND.bin').read_bytes();at=bm['provision_offset']
assert hashlib.sha256(boot).hexdigest()==bm['boot_sha256']
assert boot[at:at+40].hex()==bm['new_descriptor_hex']
payload=data[:-904];desc=struct.pack('<II',len(payload),1000002)+hashlib.sha256(payload).digest()
dest=out.parent/'boot';dest.mkdir(exist_ok=False);(dest/'Objects').mkdir();(dest/'Listings').mkdir()
text=(old/'yp001_boot_provision.c').read_text()
replacement='{%du,1000002u,{'%len(payload)+','.join('0x%08xu'%w for w in struct.unpack('<8I',hashlib.sha256(payload).digest()))+'}}'
text,n=re.subn(r'\{%du,1000002u,\{[^}]+\}\}'%bm['baseline_payload_bytes'],replacement,text);assert n==1
provision=dest/'yp001_boot_provision.c';provision.write_text('/* SAM | 2026-10-25 +08:00 | Bind only the verified observation-fix baseline descriptor. */\n'+text,encoding='ascii')
source=old/'BOOT_BIND_MOTION_BASELINE_FPU_FIX.uvprojx';t=E.parse(source);changed=0
for f in t.findall('.//FilePath'):
 if f.text and Path(f.text).name=='yp001_boot_provision.c':f.text=str(provision);changed+=1
assert changed==1
t.find('.//OutputDirectory').text=str(dest/'Objects')+'\\';t.find('.//ListingPath').text=str(dest/'Listings')+'\\'
p=dest/'BOOT_BIND_OBSERVATION_BASELINE.uvprojx';t.write(p,encoding='utf-8',xml_declaration=True)
p.with_suffix('.uvoptx').write_bytes(source.with_suffix('.uvoptx').read_bytes())
report=dict(app_verified=v,app_signed_sha256=hashlib.sha256(data).hexdigest(),app_signed_bytes=len(data),slot_spare=442368-len(data),
 boot_project=str(p),old_boot_sha256=bm['boot_sha256'],provision_offset=at,new_descriptor_hex=desc.hex(),baseline_payload_bytes=len(payload),baseline_sha256=hashlib.sha256(payload).hexdigest(),
 expected_boot_sha256=hashlib.sha256(boot[:at]+desc+boot[at+40:]).hexdigest(),compiled=False,device_written=False,download_ready=False,fifth_attempt_authorized=False)
(dest/'binding_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'signed_bytes':len(data),'slot_spare':report['slot_spare'],'boot_project':str(p),'download_ready':False},indent=2))
