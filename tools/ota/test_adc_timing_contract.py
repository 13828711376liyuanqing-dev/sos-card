"""SAM | 2026-10-26 +08:00 | Execute the production ADC timing wrapper against a register model before manual GR compilation."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/r6_causal_audit_20261026/adc_timing"


def main():
    source = (ROOT / "ble_app_uart_c/Src/user/yp001_battery.c").read_text(encoding="utf-8-sig")
    start = source.find("typedef struct {\n    uint32_t sequence, count, status, clock_hz, cycles, last_us, max_us, valid;")
    assert start >= 0, "ADC_RUNTIME_TIMING_EVIDENCE_MISSING"
    end = source.index("\nyp001_battery_result_t yp001_battery_read", start)
    fragment = source[start:end]
    harness = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {uint32_t DEMCR;} coredebug_t;
typedef struct {uint32_t CTRL,CYCCNT;} dwt_t;
static coredebug_t coredebug;
static dwt_t dwt;
#define CoreDebug (&coredebug)
#define DWT (&dwt)
#define CoreDebug_DEMCR_TRCENA_Msk (1u<<24)
#define DWT_CTRL_CYCCNTENA_Msk 1u
static uint32_t SystemCoreClock=96000000;
static unsigned calls,mode;
static uint16_t app_adc_conversion_sync(uint16_t *raw,uint32_t length,uint32_t timeout){
 CHECK(raw&&length==36&&timeout==100);
 CHECK(CoreDebug->DEMCR&CoreDebug_DEMCR_TRCENA_Msk);
 CHECK(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk);
 ++calls;DWT->CYCCNT+=57600;
 if(mode==1)SystemCoreClock=64000000;
 if(mode==2)return 1;
 if(mode==3)DWT->CYCCNT-=57600;
 return 0;
}
'''
    harness += fragment
    harness += r'''
int main(void){uint16_t raw[36]={0};
 CoreDebug->DEMCR=0x80;DWT->CTRL=0x20;DWT->CYCCNT=123;
 CHECK(battery_conversion_sync(raw)==0);
 CHECK(calls==1&&DWT->CYCCNT==57723);
 CHECK(CoreDebug->DEMCR==0x80&&DWT->CTRL==0x20);
 CHECK(g_yp001_adc_timing.valid&&g_yp001_adc_timing.last_us==600&&g_yp001_adc_timing.max_us==600);
 CHECK(g_yp001_adc_timing.sequence==2&&g_yp001_adc_timing.count==1);
 CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;DWT->CTRL|=1;
 uint32_t demcr=CoreDebug->DEMCR,ctrl=DWT->CTRL;DWT->CYCCNT=0xfffffff0u;
 CHECK(battery_conversion_sync(raw)==0);
 CHECK(CoreDebug->DEMCR==demcr&&DWT->CTRL==ctrl&&g_yp001_adc_timing.cycles==57600);
 mode=1;CHECK(battery_conversion_sync(raw)==0);CHECK(!g_yp001_adc_timing.valid);
 CHECK(g_yp001_adc_timing.last_us==0&&g_yp001_adc_timing.max_us==600);
 mode=2;SystemCoreClock=96000000;CHECK(battery_conversion_sync(raw)==1);
 CHECK(g_yp001_adc_timing.status==1&&g_yp001_adc_timing.valid);
 mode=3;CHECK(battery_conversion_sync(raw)==0);CHECK(!g_yp001_adc_timing.valid);
 CHECK(g_yp001_adc_timing.count==5&&g_yp001_adc_timing.sequence==10);
 CHECK(CoreDebug->DEMCR==demcr&&DWT->CTRL==ctrl);
 puts("PASS actual ADC wrapper: one unchanged conversion, error preserved, DWT/DEMCR restored, no counter reset, wrap, changed-clock and stopped-counter rejection");
 return 0;
}
'''
    OUT.mkdir(exist_ok=True)
    cfile = OUT / "adc_timing_contract.c"
    cfile.write_text(harness, encoding="utf-8")
    gcc = Path("D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe")
    env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get("PATH", ""))
    exe = OUT / "adc_timing_contract.exe"
    log = []
    for cmd in ([str(gcc), "-std=c99", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(exe)], [str(exe)]):
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        log.append(result.stdout+result.stderr+f"exit={result.returncode}\n")
        (OUT / "test.log").write_text("".join(log), encoding="utf-8")
        print(result.stdout+result.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
