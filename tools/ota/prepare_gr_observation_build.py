"""SAM | 2026-10-25 +08:00 | Prepare compile-only entry without changing proven Keil/Flash settings or touching devices."""
from pathlib import Path
import hashlib,json,re
r=Path(__file__).resolve().parents[2]
src=r/'ble_app_uart_c/Keil_6/YP001_BASELINE_MOTION_SERVICE_FIX_20261024.uvprojx'
dst=src.with_name('YP001_BASELINE_OBSERVATION_FIX_20261025.uvprojx')
out=r/'firmware_releases/gr_observation_fix_20261025/baseline'
for d in ('Objects','Listings'): (out/d).mkdir(parents=True,exist_ok=True)
raw=src.read_bytes(); text=raw.decode('utf-8-sig')
for tag,sub in [('OutputDirectory','Objects'),('ListingPath','Listings')]:
 text,n=re.subn(r'<'+tag+r'>[^<]*</'+tag+r'>',lambda m:'<'+tag+'>'+str(out/sub)+'\\</'+tag+'>',text)
 assert n==1
dst.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+text.encode())
dst.with_suffix('.uvoptx').write_bytes(src.with_suffix('.uvoptx').read_bytes())
files=['platform/bsp.c','platform/user_periph_setup.c','platform/user_periph_setup.h','user/gsensor_probe.c','user/business/yp001_business.c','user/business/yp001_business.h','user/ota/yp001_ota_port.c','user/ota/yp001_ota_port.h']
manifest={'status':'SOURCE_READY_MANUAL_BUILD_REQUIRED','project':str(dst),'download_ready':False,'fifth_attempt_authorized':False,
 'requires_paired_boot':True,'sources':{p:hashlib.sha256((r/'ble_app_uart_c/Src'/p).read_bytes()).hexdigest() for p in files}}
(out/'source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(dst)
