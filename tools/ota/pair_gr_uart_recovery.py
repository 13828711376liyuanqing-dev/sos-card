"""SAM | 2026-10-25 +08:00 | Validate manual GR build, sign it, and patch only the proven 40-byte Boot descriptor; no firmware compilation or device access."""
from pathlib import Path
import hashlib,json,re,struct,subprocess,xml.etree.ElementTree as E
from gr_project_image import verify_image
from gr_signed_carrier import build as carrier
from gr_first_deploy import read_hex
from prepare_gr_first_deploy import LAYOUT_PIN,DATA_PIN
r=Path(__file__).resolve().parents[2];out=r/'firmware_releases/gr_uart_recovery_20261025';app=out/'baseline'
m=json.loads((app/'source_manifest.json').read_text())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for p,h in m['sources'].items():assert digest(r/'ble_app_uart_c/Src'/p)==h,'SOURCE_CHANGED: '+p
assert re.search(r'0 Error\(s\), 0 Warning\(s\)',(app/'Objects/YP001_GR5526.build_log.htm').read_text(errors='replace'))
hexf=app/'Objects/YP001_GR5526.hex';axf=hexf.with_suffix('.axf')
assert min(axf.stat().st_mtime,hexf.stat().st_mtime)>=max((r/'ble_app_uart_c/Src'/p).stat().st_mtime for p in m['sources'])
tools=Path('C:/Keil_v5/ARM/ARMCC/bin')
symbols=subprocess.run([str(tools/'fromelf.exe'),'--text','-s',str(axf)],capture_output=True,text=True,errors='replace',check=True).stdout
(app/'uart_recovery_symbols.txt').write_text(symbols)
for name,n in [('g_cat_uart_first_fault',44),('g_cat_uart_recovery',28),('yp001_ota_rx_denial',116)]:
 rows=[x for x in symbols.splitlines() if name in x and 'Data' in x];assert len(rows)==1 and int(rows[0].split()[-1],16)==n,name
signed=app/'baseline_final_signed.bin';assert not signed.exists(),'PRESERVE_SIGNED_IMAGE'
subprocess.run([str(r/'logs/ota_first_trial_live_20261024/GrBaselineSign_current.exe'),str(hexf),str(r/'tools/toolkit/test_keys'),
 str(r/'tools/toolkit/contracts/layout_candidate.json'),str(r/'tools/toolkit/contracts/data_contract_candidate.json'),'1.0.2',str(signed)],capture_output=True,check=True)
data=signed.read_bytes();verified=verify_image(data,(r/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes(),
 '6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1',LAYOUT_PIN,DATA_PIN)
assert verified['version']=='1.0.2' and verified['build']==3
carrier(signed,app/'SIGNED_DOWNLOAD_FINAL')
old=r/'firmware_releases/gr_uart_first_fault_20261025/boot';bm=json.loads((old/'binding_manifest.json').read_text())
previous=(old/'BOOT_UART_FIRST_FAULT_BOUND.bin').read_bytes();at=bm['provision_offset']
assert hashlib.sha256(previous).hexdigest()==bm['boot_sha256'] and previous[at:at+40].hex()==bm['new_descriptor_hex']
payload=data[:-904];desc=struct.pack('<II',len(payload),1000002)+hashlib.sha256(payload).digest()
boot=out/'boot_final';boot.mkdir();new=previous[:at]+desc+previous[at+40:]
assert len(new)==len(previous) and new[:at]==previous[:at] and new[at+40:]==previous[at+40:]
(boot/'BOOT_UART_RECOVERY_BOUND.bin').write_bytes(new)
entry=(struct.unpack_from('<I',new,4)[0]&~1)-0x2ec000
assert 0<=entry<len(new)-2
(boot/'BEFORE_ENTRY.bin').write_bytes(new[:entry]);(boot/'AFTER_ENTRY.bin').write_bytes(new[entry+2:])
name='PAIRED_BOOT_EXACT'
(boot/(name+'.s')).write_text('; SAM | 2026-10-25 +08:00 | Exact verified Boot bytes; no Boot source compilation.\n'
 ' AREA PAIRED_BOOT,CODE,READONLY,ALIGN=2\n THUMB\n INCBIN BEFORE_ENTRY.bin\n EXPORT paired_reset\npaired_reset\n'
 ' DCI.N 0x%04X\n INCBIN AFTER_ENTRY.bin\n END\n'%struct.unpack_from('<H',new,entry)[0])
(boot/(name+'.sct')).write_text('; SAM | 2026-10-25 +08:00 | Fixed existing Boot interval only.\nLR_BOOT 0x002EC000 0x9000 { ER_BOOT 0x002EC000 { *.o (PAIRED_BOOT) } }\n')
commands=[['armasm.exe','--cpu','Cortex-M4','-o',name+'.o',name+'.s'],
 ['armlink.exe','--scatter',name+'.sct','--no_remove','--entry=paired_reset','--datacompressor=off','--no_scanlib','--output',name+'.axf',name+'.o'],
 ['fromelf.exe','--bin','--output',name+'.bin',name+'.axf'],['fromelf.exe','--i32','--output',name+'.hex',name+'.axf']]
logs=[]
for c in commands:
 p=subprocess.run([str(tools/c[0])]+c[1:],cwd=boot,capture_output=True,text=True,errors='replace',check=True);logs.append(p.stdout+p.stderr)
(boot/'carrier_build.log').write_text('\n'.join(logs))
assert (boot/(name+'.bin')).read_bytes()==new
assert read_hex(boot/(name+'.hex'))=={0x2ec000+i:b for i,b in enumerate(new)}
template=r/'firmware_releases/gr_uart_first_fault_20261025/baseline/SIGNED_DOWNLOAD/DOWNLOAD_SIGNED_APP_ONLY.uvprojx'
projects=[]
for folder,filename,output in [(app/'SIGNED_DOWNLOAD_FINAL','DOWNLOAD_SIGNED_APP_ONLY.uvprojx','STAGE1_SIGNED_BASELINE_ONLY'),(boot,'DOWNLOAD_PAIRED_BOOT_ONLY.uvprojx',name)]:
 t=E.parse(template)
 for g in t.findall('.//Groups'):g.clear()
 t.find('.//OutputDirectory').text=str(folder)+'\\';t.find('.//OutputName').text=output
 project=folder/filename;t.write(project,encoding='utf-8',xml_declaration=True)
 project.with_suffix('.uvoptx').write_bytes(template.with_suffix('.uvoptx').read_bytes())
 projects.append(str(project))
report=dict(app_verified=verified,app_bytes=len(data),slot_spare=442368-len(data),app_sha256=digest(signed),
 boot_bytes=len(new),boot_sha256=hashlib.sha256(new).hexdigest(),old_boot_sha256=bm['boot_sha256'],provision_offset=at,
 new_descriptor_hex=desc.hex(),only_boot_descriptor_changed=True,boot_firmware_recompiled=False,
 carrier_roundtrip_exact=True,download_ready=True,device_written=False,seventh_attempt_authorized=True,projects=projects)
(out/'paired_downloads_final.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:report[k] for k in ('app_bytes','slot_spare','only_boot_descriptor_changed','boot_firmware_recompiled','projects')},indent=2))
