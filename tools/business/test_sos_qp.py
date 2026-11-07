"""SAM | 2026-11-04 +08:00 | Compile the actual GR business source with the existing NVDS/Flash test fixture."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[2]
GCC=Path(r"D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe")
OUT=ROOT/"logs/sos_qp_fix_20261104"
OUT.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(GCC.parent)+os.pathsep+os.environ["PATH"])
for variant,defines in (("production",[]),("bench",["-DYP001_OTA_USB_BENCH_TEST=1"])):
    exe=OUT/("test_sos_qp_"+variant+".exe")
    cmd=[str(GCC),"-std=c99","-Wall","-Wextra","-Werror","-Wno-error=unused-variable","-DYP_BUSINESS_HOST_TEST",*defines]
    cmd += ["-I"+str(ROOT/x) for x in ("tools/name_push/stubs","ble_app_uart_c/Src/user/business","ble_app_uart_c/Src/external/cJSON-1.7.19")]
    cmd += [str(ROOT/x) for x in ("tools/business/test_sos_qp.c","ble_app_uart_c/Src/user/business/yp001_business.c","ble_app_uart_c/Src/user/business/yp_name_glyphs.c","ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c")]
    result=subprocess.run(cmd+["-o",str(exe)],env=env,capture_output=True)
    text=result.stdout+result.stderr
    if result.returncode==0:
        result=subprocess.run([str(exe)],env=env,capture_output=True,timeout=20)
        text+=result.stdout+result.stderr
    (OUT/(variant+".log")).write_bytes(text)
    print(text.decode("utf-8","replace"))
    if result.returncode: raise SystemExit(result.returncode)
