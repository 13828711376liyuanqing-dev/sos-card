"""SAM | 2026-10-25 +08:00 | Compile the real GR business module; no firmware build or device writes."""
from pathlib import Path
import os
import subprocess

root=Path(__file__).resolve().parents[2]
out=root/'logs/ota_peer_sync_20261025'
out.mkdir(exist_ok=True)
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
cmd=[str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-DYP_BUSINESS_HOST_TEST',
     '-I'+str(root/'ble_app_uart_c/Src/user/business'),
     '-I'+str(root/'ble_app_uart_c/Src/external/cJSON-1.7.19'),
     str(root/'tools/business/test_gr_peer_evidence.c'),
     str(root/'ble_app_uart_c/Src/user/business/yp001_business.c'),
     str(root/'ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c'),
     '-o',str(out/'gr_peer_evidence.exe')]
subprocess.run(cmd,check=True,env=env)
subprocess.run([str(out/'gr_peer_evidence.exe')],check=True,env=env)
