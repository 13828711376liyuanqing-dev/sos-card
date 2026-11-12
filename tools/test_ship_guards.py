"""SAM | 2026-10-13 14:26 +08:00 | Regression for output-latch and read-only rejection."""
from pathlib import Path
import os, subprocess, sys
r=Path(__file__).resolve().parents[1]
out=r/'logs/shipping_20261013'; out.mkdir(parents=True,exist_ok=True)
src=(r/'ble_app_uart_c/Src/user/charger/yp001_charger.c').read_text(encoding='utf-8')
def function(signature):
    start=src.index(signature+'\n{'); end=src.index('\n}',start)+2
    return src[start:end]
guard=function('static bool ship_business_guard(void)')+'\n'+function('static const char *ship_auto_guard(void)')+'\n'+function('static void ship_force_cat1_off(void)')
if '--old-input-guard' in sys.argv:
    guard=guard.replace('(GPIO0->DATAOUT & YP001_CAT1_POWER_PIN) == 0U',
        'app_io_read_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN) == YP001_CAT1_POWER_OFF')
text=(r/'tools/test_ship_guards.c').read_text().replace('/* GUARD SOURCE */',guard).replace(
    '/* PREPARE SOURCE */',function('bool yp001_charger_ship_prepare(void)'))
fixture=out/'guard_fixture.c'; fixture.write_text(text,encoding='utf-8')
gcc=Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
exe=out/'guard_test.exe'
cmd=[str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(r/'ble_app_uart_c/Src/user/charger'),str(fixture),'-o',str(exe)]
result=subprocess.run(cmd,env=env,capture_output=True,text=True)
log=result.stdout+result.stderr
if result.returncode==0:
    result=subprocess.run([str(exe)],env=env,capture_output=True,text=True,timeout=10)
    log+=result.stdout+result.stderr
(out/('guard_red.log' if '--old-input-guard' in sys.argv else 'guard_green.log')).write_text(log,encoding='utf-8')
print(log); raise SystemExit(result.returncode)
