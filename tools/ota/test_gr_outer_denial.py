"""SAM | 2026-10-26 +08:00 | Host-only outer-gate diagnostic check; no firmware build or device writes."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[2]
out = root / "logs/r6_causal_audit_20261026"
out.mkdir(exist_ok=True)
gcc = Path("D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe")
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get("PATH", ""))
exe = out / "outer_denial.exe"
command = [str(gcc), "-std=c99", "-Wall", "-Wextra", "-Werror",
           "-Ible_app_uart_c/Src/user/ota", "-Ible_app_uart_c/Src/external/cJSON-1.7.19",
           "tools/ota/test_gr_outer_denial.c", "ble_app_uart_c/Src/user/ota/yp001_ota.c",
           "ble_app_uart_c/Src/user/ota/yp001_ota_wire.c",
           "ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c", "-o", str(exe)]
for cmd in (command, [str(exe)]):
    p = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True, timeout=60)
    print(p.stdout+p.stderr)
    if p.returncode:
        raise SystemExit(p.returncode)
