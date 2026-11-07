"""SAM | 2026-10-24 +08:00 | One bounded software preflight for the three connected gaps; never labels host inputs as physical OTA acceptance."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'logs/ota_first_trial_live_20261024'
GCC=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')

def main():
    env=dict(os.environ,PATH=str(GCC.parent)+os.pathsep+os.environ.get('PATH',''))
    report={'scope':'USB_BENCH_SOFTWARE_PREFLIGHT','device_actions':False,
            'physical_installation_accepted':False,'gr_build_required':True,
            'final_bundle_exists':False,'checks':[]}
    sources=[ROOT/'Air780EGH'/n for n in ('ota_runtime.lua','ota_manager.lua','ota_seq_zip.lua','update.lua')]
    sources += [ROOT/'ble_app_uart_c/Src'/n for n in ('platform/bsp.c','platform/user_periph_setup.c',
        'user/ota/yp001_ota.c','user/ota/yp001_ota_port.c','user/ota/yp001_ota_port.h','user/ota/yp001_ota_usb_bench.h')]
    snapshot=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    before=snapshot();logs=[]
    def run(name,args):
        r=subprocess.run([str(a) for a in args],cwd=ROOT,env=env,capture_output=True,text=True,
                         encoding='utf8',errors='replace',timeout=60)
        logs.append(name+'\n'+r.stdout+r.stderr+'\nexit='+str(r.returncode)+'\n')
        report['checks'].append({'name':name,'passed':r.returncode==0})
        print(name+(': PASS' if not r.returncode else ': FAIL'),flush=True)
        if r.returncode:raise RuntimeError(name)
    try:
        for role in ('BASELINE','TARGET'):
            p=ROOT/f'ble_app_uart_c/Keil_6/YP001_{role}_USB_BENCH_20261024.uvprojx'
            old=ROOT/f'ble_app_uart_c/Keil_6/YP001_{role}_STORAGE_FIX_20261024.uvprojx'
            newxml,oldxml=ET.parse(p),ET.parse(old)
            defines=' '.join(x.text or '' for x in newxml.findall('.//Define'))
            if 'YP001_OTA_USB_BENCH_TEST=1' not in defines:raise ValueError(role+' bench flag missing')
            for tag in ('FlashDriverDll','ScatterFile','IncludePath'):
                a=[x.text for x in newxml.findall('.//'+tag)]
                b=[x.text for x in oldxml.findall('.//'+tag)]
                if a!=b:raise ValueError(role+' unexpected configuration change: '+tag)
            report['checks'].append({'name':role+'_isolated_config','passed':True})
        for mode in (0,1):
            exe=OUT/f'test_usb_bench_power_{mode}.exe'
            run(f'power_policy_{mode}_compile',[GCC,'-std=c99','-Wall','-Wextra','-Werror',
                f'-DYP001_OTA_USB_BENCH_TEST={mode}','-Ible_app_uart_c/Src/user/ota',
                'tools/ota/test_usb_bench_power.c','-o',exe])
            run(f'power_policy_{mode}',[exe])
        exe=OUT/'test_usb_bench_coordinator.exe'
        run('real_coordinator_bench_compile',[GCC,'-std=c99','-Wall','-Wextra','-Werror',
            '-DYP001_OTA_USB_BENCH_TEST=1','-Ible_app_uart_c/Src/user/ota',
            '-Ible_app_uart_c/Src/external/cJSON-1.7.19','tools/ota/test_gr_coordinator.c',
            'ble_app_uart_c/Src/user/ota/yp001_ota.c','ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c','-o',exe])
        run('real_coordinator_bench',[exe])
        for name in ('test_usb_bench_chain.py','test_manual_trial.py','test_cancel_empty.py',
                     'test_storage_repair_bridge.py','test_default_native_path.py','test_trial_wiring.py'):
            run(name,[sys.executable,ROOT/'tools/ota'/name])
        report['software_preflight_passed']=True
    except Exception as e:
        report.update(software_preflight_passed=False,error_kind=type(e).__name__)
    finally:
        report['source_unchanged']=before==snapshot();report['sources']=before
        if not report['source_unchanged']:report['software_preflight_passed']=False
        (OUT/'usb_bench_preflight.log').write_text('\n'.join(logs),encoding='utf8')
        (OUT/'usb_bench_preflight.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    return 0 if report['software_preflight_passed'] else 1

if __name__=='__main__':raise SystemExit(main())
