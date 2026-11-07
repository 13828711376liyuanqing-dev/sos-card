"""SAM | 2026-10-24 +08:00 | Wrap verified bytes in a download-only AXF; assembling a binary carrier never recompiles or changes the application."""
import argparse
import hashlib
import json
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from gr_project_image import verify_image
from gr_first_deploy import read_hex
from prepare_gr_first_deploy import ROOT, LAYOUT_PIN, DATA_PIN

TOOLS=Path('C:/Keil_v5/ARM/ARMCC/bin')

def make_download_project(out):
    """Clone saved target settings; source projects and their outputs stay intact."""
    out=out.resolve();source=ROOT/'ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx'
    options=source.with_suffix('.uvoptx');project=out/'STAGE1_DOWNLOAD.uvprojx'
    if project.exists() or project.with_suffix('.uvoptx').exists():raise ValueError('PROJECT_EXISTS')
    manifest=json.loads((out/'carrier_manifest.json').read_text(encoding='utf-8'))
    axf=out/'STAGE1_SIGNED_BASELINE_ONLY.axf'
    if hashlib.sha256(axf.read_bytes()).hexdigest()!=manifest['carrier_axf_sha256']:
        raise ValueError('CARRIER_IDENTITY')
    tree=ET.parse(source)
    tree.find('.//OutputDirectory').text=str(out)+'\\'
    tree.find('.//OutputName').text='STAGE1_SIGNED_BASELINE_ONLY'
    # Download-only container: no application source can accidentally be rebuilt
    # into this output while the debugger still uses the original saved settings.
    for groups in tree.findall('.//Groups'):
        groups.clear()
    tree.write(project,encoding='utf-8',xml_declaration=True)
    project.with_suffix('.uvoptx').write_bytes(options.read_bytes())
    (out/'download_project_manifest.json').write_text(json.dumps(dict(
        role='BASELINE_ONLY_DOWNLOAD_NO_BUILD',project=str(project),
        source_project_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        saved_options_sha256=hashlib.sha256(options.read_bytes()).hexdigest(),
        project_sha256=hashlib.sha256(project.read_bytes()).hexdigest(),
        user_confirmed_erase_and_no_autorun_required=True,
        boot_included=False,full_deployment_ready=False),indent=2),encoding='utf-8')
    return project

def build(source,out):
    source=source.resolve();out=out.resolve()
    payload=source.read_bytes()
    public=(ROOT/'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes()
    identity=verify_image(payload,public,
        '6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1',LAYOUT_PIN,DATA_PIN)
    if identity['version']!='1.0.2' or identity['build']!=3:
        raise ValueError('FIRST_BASELINE_IDENTITY')
    out.mkdir(parents=True,exist_ok=True)
    name='STAGE1_SIGNED_BASELINE_ONLY'
    if any((out/(name+suffix)).exists() for suffix in ['.s','.sct','.axf','.o','.bin','.hex']):
        raise ValueError('CARRIER_OUTPUT_EXISTS')
    asm=out/(name+'.s');scatter=out/(name+'.sct')
    staged=out/'SIGNED_INPUT.bin'
    if staged.exists():raise ValueError('CARRIER_OUTPUT_EXISTS')
    staged.write_bytes(payload)
    entry=(struct.unpack_from('<I',payload,4)[0]&~1)-0x202000
    (out/'BEFORE_ENTRY.bin').write_bytes(payload[:entry])
    (out/'AFTER_ENTRY.bin').write_bytes(payload[entry+2:])
    asm.write_text('; SAM | 2026-10-24 +08:00 | Exact signed bytes for download only. No Boot or SCA records.\n'
        '        AREA SIGNED_BASELINE, CODE, READONLY, ALIGN=2\n'
        '        THUMB\n        EXPORT signed_baseline_start\nsigned_baseline_start\n'
        '        INCBIN BEFORE_ENTRY.bin\n'
        '        EXPORT signed_carrier_reset\nsigned_carrier_reset\n'
        '        DCI.N 0x%04X\n'%struct.unpack_from('<H',payload,entry)[0]
        +'        INCBIN AFTER_ENTRY.bin\n        END\n',encoding='ascii')
    scatter.write_text('; SAM | 2026-10-24 +08:00 | Carrier bounded to fixed A slot.\n'
        'LR_SIGNED 0x00202000 0x0006C000 {\n FLASH_SIGNED 0x00202000 {\n *.o (SIGNED_BASELINE)\n }\n}\n',encoding='ascii')
    commands=[['armasm.exe','--cpu','Cortex-M4','-o',str(out/(name+'.o')),str(asm)],
        ['armlink.exe','--scatter',str(scatter),'--no_remove','--entry=signed_carrier_reset',
         '--datacompressor=off','--no_scanlib','--output',str(out/(name+'.axf')),str(out/(name+'.o'))],
        ['fromelf.exe','--bin','--output',str(out/(name+'.bin')),str(out/(name+'.axf'))],
        ['fromelf.exe','--i32','--output',str(out/(name+'.hex')),str(out/(name+'.axf'))]]
    logs=[]
    for command in commands:
        result=subprocess.run([str(TOOLS/command[0])]+command[1:],capture_output=True,timeout=30,cwd=out)
        logs.append(result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
        if result.returncode:
            (out/'carrier_build.log').write_text('\n'.join(logs),encoding='utf-8')
            raise ValueError('CARRIER_BUILD_FAILED:'+logs[-1])
    (out/'carrier_build.log').write_text('\n'.join(logs),encoding='utf-8')
    memory=read_hex(out/(name+'.hex'))
    if (out/(name+'.bin')).read_bytes()!=payload or memory!={0x202000+i:b for i,b in enumerate(payload)}:
        raise ValueError('CARRIER_CHANGED_SIGNED_BYTES')
    report=dict(role='STAGE1_BASELINE_ONLY_NOT_FULL_OTA_DEPLOYMENT',
        payload_bytes=len(payload),start=0x202000,end_exclusive=0x202000+len(payload),
        roundtrip_equal=True,full_deployment_ready=False,device_written=False,
        link_warning=any('Warning:' in log for log in logs),
        warning='FLM may rewrite SCA; fresh full pre/post readback and explicit stage execution are still required.',
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        carrier_axf_sha256=hashlib.sha256((out/(name+'.axf')).read_bytes()).hexdigest())
    (out/'carrier_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--signed',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();print(json.dumps(build(args.signed,args.out),indent=2))

if __name__=='__main__':main()
