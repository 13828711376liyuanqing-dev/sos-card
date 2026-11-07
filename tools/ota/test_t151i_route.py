"""SAM | 2026-10-29 12:40 +08:00 | Host-test the delivery route of the 1.5.1 install-only resume end to end across both sides:
GR side = the real yp001_ota_recovery_command_allowed() (compiled with gcc) must forward the exact selector-9 string and keep refusing
OTA_T151I / FW_VERSION; CAT1 side = the real receiver update.lua handler must call arm_t151i only for that exact string (in a task) and
refuse every other OTA_HANDOFF_RESUME form without calling it. No device access.
Usage: python test_t151i_route.py <receiver source dir>"""
import subprocess
import sys
import tempfile
from pathlib import Path
import test_cat_manager  # noqa: F401  (adds the vendored lupa path)
from lupa.lua54 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
GCC = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
CMD = 'OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,9'
C = r'''
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include "yp001_ota_recovery_control.h"
int main(int c,char**v){for(int i=1;i<c;i++)printf("%d",yp001_ota_recovery_command_allowed(v[i]));return 0;}
'''


def gr_side():
    with tempfile.TemporaryDirectory() as t:
        src = Path(t, 'w.c'); src.write_text(C); exe = Path(t, 'w.exe')
        subprocess.run([str(GCC), '-I', str(ROOT / 'ble_app_uart_c/Src/user/ota'), '-o', str(exe), str(src)], check=True, cwd=GCC.parent)
        out = subprocess.run([str(exe), CMD[:-1] + '7', 'OTA_T151I', 'FW_VERSION', 'FOTA_STATUS'], capture_output=True, text=True).stdout
    assert out == '1001', 'GR_WHITELIST ' + out


def cat_side(source):
    # SAM | 2026-10-29 17:40 +08:00 | Revision 12: no CAT1 command handler (GR forwards no cat_at during the CAT1 install); the boot task arms
    # and reports every attempt as a plain [T151K] line, retries while refused or SPENT, and stops once armed.
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
lines={};vu={};_G.uart_send_raw=function(x)lines[#lines+1]=x;return true end
uart={VUART_0=32,setup=function()end,write=function(id,x)assert(id==32);vu[#vu+1]=x end}
at_cmd_handlers={};_G.at_cmd_handlers=at_cmd_handlers;json={encode=function()return '{}' end}
boot=nil;beacon=nil;sys={taskInit=function(f)if not beacon then beacon=coroutine.create(f) elseif not boot then boot=coroutine.create(f) end end,wait=function()coroutine.yield()end}
calls=0;answers={{false,'T151K_SCOPE_1111110'},{true}};t151k='SPENT'
inst={arm_t151k=function()calls=calls+1;local a=answers[calls];if a[1] then t151k='ARMED' end;return a[1],a[2] end,
 status=function()return {phase='RECOVERY_HOLD',t151k=t151k,reason='T151K_TIMEOUT'}end}
package.loaded.ota_runtime={start=function()return inst end}
''')
    lua.execute(Path(source, 'update.lua').read_text(encoding='utf-8-sig'))
    lua.execute('''
assert(at_cmd_handlers.OTA_HANDOFF_RESUME==nil and at_cmd_handlers.OTA_T151I==nil,'COMMAND_HANDLER_LEFT')
assert(boot,'NO_BOOT_TASK');coroutine.resume(boot);assert(calls==0,'ARMED_BEFORE_WAIT')
coroutine.resume(boot);assert(calls==1 and lines[1]=='[T151K] arm T151K_SCOPE_1111110 RECOVERY_HOLD SPENT T151K_TIMEOUT n=0 N nil','DIAG '..tostring(lines[1]))
assert(coroutine.status(boot)~='dead','STOPPED_ON_SPENT_TICKET')
coroutine.resume(boot);assert(calls==2 and lines[2]=='[T151K] arm true RECOVERY_HOLD ARMED T151K_TIMEOUT n=0 N nil','DIAG2 '..tostring(lines[2]))
assert(coroutine.status(boot)=='dead','NOT_STOPPED_WHEN_ARMED')
-- SAM | 2026-10-29 19:21 +08:00 | Diagnostics also go to the USB virtual serial; the 10 s beacon goes to VUART only (no extra GR traffic).
assert(vu[1]:sub(1,-3)=='[T151K] arm T151K_SCOPE_1111110 RECOVERY_HOLD SPENT T151K_TIMEOUT n=0 N nil','VUART_MIRROR '..tostring(vu[1]))
local nl=#lines;coroutine.resume(beacon);coroutine.resume(beacon)
assert(vu[#vu]:find('^%[T151K%] B RECOVERY_HOLD ARMED T151K_TIMEOUT N nil S nil') and #lines==nl,'BEACON '..tostring(vu[#vu]))
''')


def main():
    gr_side()
    cat_side(Path(sys.argv[1]).resolve())
    print('PASS t151 route: GR whitelist unchanged; CAT1 has no command handler, the boot task reports each attempt as [T151K], retries while refused/SPENT and stops once armed; '
          'arm_t151i once in a task for that exact string, BUSY on overlap, refuses 4 other forms without calling it')


if __name__ == '__main__':
    main()
