"""SAM | 2026-10-25 +08:00 | Verify manually built Boot against exact descriptor-only expectation and prepare paired download carriers."""
from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as E
r=Path(__file__).resolve().parents[2];out=r/'firmware_releases/gr_uart_first_fault_20261025';boot=out/'boot';app=out/'baseline/SIGNED_DOWNLOAD'
m=json.loads((boot/'binding_manifest.json').read_text())
log=(boot/'Objects/YP001_OTA_BOOT_CANDIDATE.build_log.htm').read_text(errors='replace')
assert re.search(r'0 Error\(s\), 0 Warning\(s\)',log),'BOOT_BUILD_NOT_PASSED'
axf=boot/'Objects/YP001_OTA_BOOT_CANDIDATE.axf'
assert axf.stat().st_mtime>=(boot/'yp001_boot_provision.c').stat().st_mtime,'STALE_BOOT'
binary=boot/'BOOT_UART_FIRST_FAULT_BOUND.bin'
subprocess.run(['C:/Keil_v5/ARM/ARMCC/bin/fromelf.exe','--bin','--output',str(binary),str(axf)],check=True)
data=binary.read_bytes();old=(r/'firmware_releases/gr_observation_fix_20261025/boot/BOOT_OBSERVATION_BOUND.bin').read_bytes();at=m['provision_offset']
assert hashlib.sha256(old).hexdigest()==m['old_boot_sha256']
assert len(data)==len(old) and data[:at]==old[:at] and data[at+40:]==old[at+40:]
assert data[at:at+40].hex()==m['new_descriptor_hex']
assert hashlib.sha256(data).hexdigest()==m['expected_boot_sha256']
template=r/'firmware_releases/gr_usb_bench_20261024/baseline/SIGNED_DOWNLOAD_AFTER_CAT_HOLD/STAGE1_DOWNLOAD.uvprojx'
def carrier(folder,name,output,directory):
 t=E.parse(template)
 for g in t.findall('.//Groups'):g.clear()
 t.find('.//OutputDirectory').text=str(directory)+'\\';t.find('.//OutputName').text=output
 p=folder/name;t.write(p,encoding='utf-8',xml_declaration=True)
 opt=E.parse(template.with_suffix('.uvoptx'));opt.find('.//TargetName').text=t.findtext('.//TargetName')
 assert '-FO7 ' in E.tostring(opt.getroot(),encoding='unicode')
 assert '-FC8000 ' in E.tostring(opt.getroot(),encoding='unicode')
 opt.write(p.with_suffix('.uvoptx'),encoding='utf-8',xml_declaration=True)
 return str(p)
signed=(out/'baseline/baseline_signed.bin').read_bytes()
assert (app/'STAGE1_SIGNED_BASELINE_ONLY.bin').read_bytes()==signed
assert hashlib.sha256(signed).hexdigest()==m['app_signed_sha256']
projects=[carrier(app,'DOWNLOAD_SIGNED_APP_ONLY.uvprojx','STAGE1_SIGNED_BASELINE_ONLY',app),carrier(boot,'DOWNLOAD_PAIRED_BOOT_ONLY.uvprojx','YP001_OTA_BOOT_CANDIDATE',boot/'Objects')]
m.update(compiled=True,only_baseline_descriptor_changed=True,boot_sha256=hashlib.sha256(data).hexdigest(),boot_bytes=len(data),download_ready=True)
(boot/'binding_manifest.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
report=dict(projects=projects,device_written=False,seventh_attempt_authorized=False,boot_bytes=len(data),app_bytes=len(signed),boot_sha256=m['boot_sha256'],app_sha256=m['app_signed_sha256'])
(out/'paired_downloads.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
