"""SAM | 2026-10-23 +08:00 | Compile candidate entry gating tests without device access."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2];o=r/'logs/ota_gr_entry_20261023';o.mkdir(exist_ok=True)
g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(g),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(r/'tools/ota/boot'),'-I'+str(r/'ble_app_uart_c/Src/user/ota'),str(r/'tools/ota/test_gr_entry.c'),str(r/'tools/ota/boot/yp001_ota_entry.c'),'-o',str(o/'test.exe')],env=env,check=True)
subprocess.run([str(o/'test.exe')],env=env,check=True)
