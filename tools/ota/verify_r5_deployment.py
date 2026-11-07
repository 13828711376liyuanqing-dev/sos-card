"""SAM | 2026-10-25 +08:00 | Compare only the new paired deployment to exact R5 bytes and the preserved seventh snapshot; no writes."""
from pathlib import Path
import hashlib,json,struct,zlib
r=Path(__file__).resolve().parents[2];d=r/'logs/r5_live_20261025';g=r/'firmware_releases/gr_uart_window_20261025'
f=(d/'deployed_flash.bin').read_bytes();app=(g/'baseline/baseline_final_signed.bin').read_bytes();boot=(g/'boot_final/BOOT_UART_WINDOW_BOUND.bin').read_bytes()
old=(r/'logs/uart_recovery_20261025/seventh_after_flash.bin').read_bytes()
assert len(f)==len(old)==0x100000 and len(set(f))>1,'FLASH_MAPPING_INVALID'
result={'app_matches':f[0x2000:0x2000+len(app)]==app,'boot_matches':f[0xec000:0xec000+len(boot)]==boot,
 'boot_tail_ff':all(v==255 for v in f[0xec000+len(boot):0xf5000]),'sca_routes_boot':struct.unpack_from('<2I',f,8)==(0x2ec000,0x2ec000),
 'b_preserved':f[0x80000:0xec000]==old[0x80000:0xec000],'coordinator_preserved':f[0xf9000:0xfb000]==old[0xf9000:0xfb000],
 'protected_preserved':f[0x6e000:0x80000]==old[0x6e000:0x80000],'nvds_preserved':f[0xfe000:]==old[0xfe000:]}
result['outside_deployment_changes']=sum(a!=b for i,(a,b) in enumerate(zip(old,f)) if not(i<0x6e000 or 0xec000<=i<0xf5000))
pages=[]
for off in (0xf9000,0xfa000):
 p=f[off:off+4096];magic,gen,epoch=struct.unpack_from('<3I',p);total,durable,crc,commit=struct.unpack_from('<4I',p,352)
 if magic!=0x594f5432 or zlib.crc32(p[:360])!=crc or commit!=0:continue
 text=lambda a,n:p[a:a+n].split(b'\0')[0].decode()
 pages.append({'generation':gen,'epoch':epoch,'phase':p[12],'job':text(13,65),'hash':text(78,65),'total':total&0x7fffffff,'durable':durable})
result.update(pages=pages,flash_sha256=hashlib.sha256(f).hexdigest(),ota_started=False)
latest=max(pages,key=lambda p:p['generation']) if pages else {}
result['readback_accepted']=all(result[k] for k in ('app_matches','boot_matches','boot_tail_ff','sca_routes_boot','b_preserved','coordinator_preserved','protected_preserved','nvds_preserved')) and result['outside_deployment_changes']==0 and latest.get('durable')==299008 and latest.get('epoch')==2
(d/'deployment_identity.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2));assert result['readback_accepted'],'DEPLOYMENT_NOT_ACCEPTED'
