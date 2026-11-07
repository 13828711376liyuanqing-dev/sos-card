"""SAM | 2026-10-26 +08:00 | Bind the completed manual GR build and unchanged Boot logic; never compile application sources or access the device."""
from pathlib import Path
import hashlib,json,re,struct,subprocess,xml.etree.ElementTree as E
from gr_project_image import verify_image
from gr_signed_carrier import build as carrier
from gr_first_deploy import read_hex
from prepare_gr_first_deploy import LAYOUT_PIN,DATA_PIN
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'firmware_releases/gr_r6_retire_recovery_20261026'
PROJECT=ROOT/'ble_app_uart_c/Keil_6/YP001_BASELINE_UART_RECOVERY_20261025.uvprojx'
OBJECTS=ROOT/'firmware_releases/gr_uart_recovery_20261025/baseline/Objects'
TOOLS=Path('C:/Keil_v5/ARM/ARMCC/bin')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not OUT.exists(),'PRESERVE_FROZEN_OUTPUT'
    tree=E.parse(PROJECT)
    assert Path(tree.find('.//OutputDirectory').text).resolve()==OBJECTS.resolve(),'OUTPUT_CHANGED'
    log=OBJECTS/'YP001_GR5526.build_log.htm'
    assert '0 Error(s), 0 Warning(s)' in log.read_text(errors='replace')
    hexf=OBJECTS/'YP001_GR5526.hex';axf=hexf.with_suffix('.axf')
    dependencies={};objects={}
    for dep in OBJECTS.glob('*.d'):
        obj=dep.with_suffix('.o')
        if not obj.exists():continue
        text=dep.read_text(errors='replace').partition(': ')[2].replace('\\\n',' ')
        assert text,dep
        for token in re.findall(r'"[^"]+"|(?:\\ |[^\s])+',text):
            token=token.strip('"').replace('\\ ',' ')
            if token=='\\':continue
            p=Path(token);p=p if p.is_absolute() else PROJECT.parent/p;p=p.resolve()
            assert p.is_file(),('MISSING_DEPENDENCY',dep,token)
            assert p.stat().st_mtime<=obj.stat().st_mtime,('SOURCE_NEWER_THAN_OBJECT',p,obj)
            if str(p) not in dependencies:dependencies[str(p)]=sha(p)
        assert obj.stat().st_mtime<=axf.stat().st_mtime,('OBJECT_NEWER_THAN_LINK',obj)
        objects[obj.name]=sha(obj)
    assert all((OBJECTS/(name+'.d')).exists() for name in ('yp001_ota','yp001_ota_port','yp001_ota_wire'))
    header=str((ROOT/'ble_app_uart_c/Src/user/ota/yp001_ota_retirement.h').resolve())
    assert header in dependencies,'RETIREMENT_HEADER_NOT_COMPILED'
    assert hexf.stat().st_mtime>=axf.stat().st_mtime
    symbols=subprocess.run([str(TOOLS/'fromelf.exe'),'--text','-s',str(axf)],capture_output=True,text=True,errors='replace',check=True).stdout
    for name,size in [('g_cat_uart_first_fault',44),('g_cat_uart_recovery',36),('yp001_ota_rx_denial',116)]:
        rows=[x for x in symbols.splitlines() if name in x and 'Data' in x]
        assert len(rows)==1 and int(rows[0].split()[-1],16)==size,(name,rows)
    OUT.mkdir();app=OUT/'baseline';app.mkdir()
    (app/'symbols.txt').write_text(symbols)
    frozen=dict(project=str(PROJECT),project_sha256=sha(PROJECT),axf_sha256=sha(axf),hex_sha256=sha(hexf),
                build_log_sha256=sha(log),dependencies=dependencies,object_hashes=objects,device_written=False)
    (OUT/'frozen_build.json').write_text(json.dumps(frozen,indent=2))
    signed=app/'baseline_signed.bin'
    subprocess.run([str(ROOT/'logs/ota_first_trial_live_20261024/GrBaselineSign_current.exe'),str(hexf),str(ROOT/'tools/toolkit/test_keys'),
        str(ROOT/'tools/toolkit/contracts/layout_candidate.json'),str(ROOT/'tools/toolkit/contracts/data_contract_candidate.json'),'1.0.2',str(signed)],capture_output=True,check=True)
    data=signed.read_bytes()
    verified=verify_image(data,(ROOT/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes(),
        '6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1',LAYOUT_PIN,DATA_PIN)
    assert verified['version']=='1.0.2' and verified['build']==3
    carrier(signed,app/'SIGNED_DOWNLOAD')
    old=ROOT/'firmware_releases/gr_uart_window_20261025';bm=json.loads((old/'paired_downloads_final.json').read_text())
    previous=(old/'boot_final/BOOT_UART_WINDOW_BOUND.bin').read_bytes();at=bm['provision_offset']
    assert hashlib.sha256(previous).hexdigest()==bm['boot_sha256'] and previous[at:at+40].hex()==bm['new_descriptor_hex']
    payload=data[:-904];desc=struct.pack('<II',len(payload),1000002)+hashlib.sha256(payload).digest()
    new=previous[:at]+desc+previous[at+40:]
    assert new[:at]==previous[:at] and new[at+40:]==previous[at+40:] and len(new)==len(previous)
    boot=OUT/'boot';boot.mkdir();(boot/'BOOT_BOUND.bin').write_bytes(new)
    entry=(struct.unpack_from('<I',new,4)[0]&~1)-0x2ec000;assert 0<=entry<len(new)-2
    (boot/'BEFORE_ENTRY.bin').write_bytes(new[:entry]);(boot/'AFTER_ENTRY.bin').write_bytes(new[entry+2:])
    name='PAIRED_BOOT_EXACT'
    (boot/(name+'.s')).write_text('; SAM | 2026-10-26 +08:00 | Binary-only carrier; Boot logic unchanged.\n AREA PAIRED_BOOT,CODE,READONLY,ALIGN=2\n THUMB\n INCBIN BEFORE_ENTRY.bin\n EXPORT paired_reset\npaired_reset\n DCI.N 0x%04X\n INCBIN AFTER_ENTRY.bin\n END\n'%struct.unpack_from('<H',new,entry)[0])
    (boot/(name+'.sct')).write_text('LR_BOOT 0x002EC000 0x9000 { ER_BOOT 0x002EC000 { *.o (PAIRED_BOOT) } }\n')
    commands=[['armasm.exe','--cpu','Cortex-M4','-o',name+'.o',name+'.s'],['armlink.exe','--scatter',name+'.sct','--no_remove','--entry=paired_reset','--datacompressor=off','--no_scanlib','--output',name+'.axf',name+'.o'],['fromelf.exe','--bin','--output',name+'.bin',name+'.axf'],['fromelf.exe','--i32','--output',name+'.hex',name+'.axf']]
    logs=[]
    for c in commands:
        p=subprocess.run([str(TOOLS/c[0])]+c[1:],cwd=boot,capture_output=True,text=True,errors='replace',check=True);logs.append(p.stdout+p.stderr)
    (boot/'carrier_build.log').write_text('\n'.join(logs))
    assert (boot/(name+'.bin')).read_bytes()==new
    assert read_hex(boot/(name+'.hex'))=={0x2ec000+i:b for i,b in enumerate(new)}
    template=old/'baseline/SIGNED_DOWNLOAD_FINAL/DOWNLOAD_SIGNED_APP_ONLY.uvprojx'
    projects=[]
    for folder,filename,output in [(app/'SIGNED_DOWNLOAD','DOWNLOAD_SIGNED_APP_ONLY.uvprojx','STAGE1_SIGNED_BASELINE_ONLY'),(boot,'DOWNLOAD_PAIRED_BOOT_ONLY.uvprojx',name)]:
        t=E.parse(template)
        for g in t.findall('.//Groups'):g.clear()
        t.find('.//OutputDirectory').text=str(folder)+'\\';t.find('.//OutputName').text=output
        project=folder/filename;t.write(project,encoding='utf-8',xml_declaration=True)
        project.with_suffix('.uvoptx').write_bytes(template.with_suffix('.uvoptx').read_bytes());projects.append(str(project))
    report=dict(app_verified=verified,app_bytes=len(data),slot_spare=442368-len(data),app_sha256=sha(signed),boot_sha256=hashlib.sha256(new).hexdigest(),old_boot_sha256=bm['boot_sha256'],provision_offset=at,new_descriptor_hex=desc.hex(),only_boot_descriptor_changed=True,boot_firmware_recompiled=False,carrier_roundtrip_exact=True,device_written=False,projects=projects,immutable_r6_target_unchanged=True)
    (OUT/'paired_downloads.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(app_bytes=len(data),slot_spare=442368-len(data),dependency_files=len(dependencies),only_boot_descriptor_changed=True,projects=projects),indent=2))
if __name__=='__main__':main()
