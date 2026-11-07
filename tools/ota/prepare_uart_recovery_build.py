"""SAM | 2026-10-25 +08:00 | Freeze the approved UART repair for manual GR compilation; keep validated Keil settings."""
from pathlib import Path
import hashlib,json,re
root=Path(__file__).resolve().parents[2]
out=root/'firmware_releases/gr_uart_recovery_20261025/baseline'
original=root/'ble_app_uart_c/Keil_6/YP001_BASELINE_UART_FIRST_FAULT_20261025.uvprojx'
project=original.with_name('YP001_BASELINE_UART_RECOVERY_20261025.uvprojx')
assert not project.exists() and not out.exists(),'PRESERVE_EXISTING_OUTPUT'
for sub in ('Objects','Listings'):(out/sub).mkdir(parents=True)
raw=original.read_bytes();text=raw.decode('utf-8-sig')
for tag,sub in [('OutputDirectory','Objects'),('ListingPath','Listings')]:
 text,n=re.subn('<'+tag+'>[^<]*</'+tag+'>',lambda m:'<'+tag+'>'+str(out/sub)+'\\</'+tag+'>',text);assert n==1
project.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+text.encode())
# SAM | 2026-10-25 +08:00 | Keep the option-side listing path consistent too;
# a copied legacy path must not silently replace the project path on IDE save.
opt_raw=original.with_suffix('.uvoptx').read_bytes();opt=opt_raw.decode('utf-8-sig')
opt,n=re.subn('<ListingPath>[^<]*</ListingPath>',lambda m:'<ListingPath>'+str(out/'Listings')+'\\</ListingPath>',opt)
assert n==1
project.with_suffix('.uvoptx').write_bytes((b'\xef\xbb\xbf' if opt_raw.startswith(b'\xef\xbb\xbf') else b'')+opt.encode())
prior=json.loads((root/'firmware_releases/gr_uart_first_fault_20261025/baseline/source_manifest.json').read_text())
paths=set(prior['sources'])|{'user/ota/yp001_ota_receive.c','user/ota/yp001_ota_wire.c'}
manifest=dict(status='SOURCE_READY_MANUAL_BUILD_REQUIRED',project=str(project),device_written=False,
 seventh_attempt_authorized=True,download_ready=False,requires_paired_boot=True,
 sources={p:hashlib.sha256((root/'ble_app_uart_c/Src'/p).read_bytes()).hexdigest() for p in sorted(paths)})
(out/'source_manifest.json').write_text(json.dumps(manifest,indent=2))
print(project)
