"""SAM | 2026-11-07 +08:00 | Compile the actual QF startup and verify the ROM BLE critical-section mask contract."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
label = sys.argv[1]
out = ROOT / 'logs/svn_integration_20261107/ble_irq_fix' / label
out.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'ble_app_uart_c/Src/platform/bsp.c').read_text(encoding='utf-8')
startup = source[source.index('void QF_onStartup(void)'):source.index('void QF_onCleanup(void)')]
unit = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#undef assert
#define assert(v) do { if (!(v)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#v); exit(1); } } while (0)
enum { BLE_SDK_IRQn=1, BLE_IRQn=2, SysTick_IRQn=-1 };
#define QF_AWARE_ISR_CMSIS_PRI 0x3fU
#define BSP_TICKS_PER_SEC 100U
static uint32_t SystemCoreClock=64000000U;
static unsigned priorities[3]={0x3f,0x3f,0x3f};
static unsigned systick;
static void SysTick_Config(unsigned ticks) { assert(ticks>0); }
static void NVIC_SetPriority(int irq,unsigned value) {
    if (irq==SysTick_IRQn) systick=value;
    else { assert(irq>0 && irq<3); priorities[irq]=value; }
}
'''
unit += startup + r'''
int main(void) {
    QF_onStartup();
    unsigned group=0;
    unsigned rom_basepri=priorities[BLE_IRQn]+(1U<<(group+1U));
    assert(priorities[BLE_SDK_IRQn]>=rom_basepri);
    assert(priorities[BLE_SDK_IRQn]>=QF_AWARE_ISR_CMSIS_PRI);
    assert(priorities[BLE_IRQn]==0x3f && systick==0x7f);
    printf("PASS ROM mask 0x%x blocks SDK priority 0x%x; QP-aware and SysTick contract retained\n",
           rom_basepri,priorities[BLE_SDK_IRQn]);
    return 0;
}
'''
c = out / 'irq_startup.c'
c.write_text(unit, encoding='utf-8')
gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ['PATH'])
exe = out / 'irq_startup.exe'
result = subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror',
                         str(c), '-o', str(exe)], env=env, capture_output=True)
log = result.stdout + result.stderr
if result.returncode == 0:
    result = subprocess.run([str(exe)], env=env, capture_output=True, timeout=10)
    log += result.stdout + result.stderr
(out / 'result.log').write_bytes(log + f'\nexit_code={result.returncode}\n'.encode())
print(log.decode('utf-8', 'replace'))
raise SystemExit(result.returncode)
