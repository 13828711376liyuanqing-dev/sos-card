"""SAM | 2026-10-25 +08:00 | Compiler syntax-only checks; no object, firmware build, Keil setting changes or device access."""
from pathlib import Path
import xml.etree.ElementTree as E,subprocess,json
r=Path(__file__).resolve().parents[2];p=r/'ble_app_uart_c/Keil_6/YP001_BASELINE_UART_RECOVERY_20261025.uvprojx';x=E.parse(p).getroot();v=x.find('.//Cads/VariousControls')
a=['C:/Keil_v5/ARM/ARMCLANG/bin/armclang.exe','--target=arm-arm-none-eabi','-mcpu=cortex-m4','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-std=c99','-fsyntax-only','-Wall','-Werror=implicit-function-declaration']
a+=['-D'+d.strip() for d in v.findtext('Define').split(',') if d.strip()]
incs=x.findtext('.//TargetCommonOption/IncludePath','')+';'+v.findtext('IncludePath','')
a+=['-I'+str((p.parent/i).resolve()) for i in incs.split(';') if i]
results={}
for f in ['platform/user_periph_setup.c','platform/bsp.c','user/ota/yp001_ota.c','user/ota/yp001_ota_port.c']:
 q=subprocess.run(a+[str(r/'ble_app_uart_c/Src'/f)],capture_output=True,text=True,errors='replace',timeout=60,cwd=p.parent)
 results[f]={'exit':q.returncode,'output':q.stdout+q.stderr};print(f,q.returncode,q.stdout,q.stderr)
(r/'logs/uart_window_20261025/syntax.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if any(v['exit'] for v in results.values()):raise SystemExit(1)
