"""SAM | 2026-11-07 12:17 +08:00 | Exercise actual scheduler stop functions with shared radio users and SDK failures."""
from pathlib import Path
import argparse
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.find(signature)
    if start < 0:
        return ''
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    out = ROOT / 'logs/svn_integration_20261107/scan_stop' / args.label
    out.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'ble_app_uart_c/Src/user/yp001_scan_sched.c').read_text(encoding='utf-8')
    hold = function(source, 'void yp_scan_sched_radio_hold(')
    unit = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#define BLE_SUCCESS 0U
typedef unsigned sdk_err_t;
typedef struct { bool alarm_active; } yp_business_status_t;
static yp_business_status_t business;
static bool s_scanning, s_enabled, s_active, s_stop_deferred;
static uint8_t s_radio_holds;
static volatile bool s_radio_stop_pending;
static volatile bool s_radio_restart_due;
static uint32_t s_next_attempt_ms, s_scan_start_ms;
static struct { unsigned count, timestamp; } s_cur;
#define __disable_irq() ((void)0)
#define __enable_irq() ((void)0)
static bool phone;
static unsigned stop_calls, errors;
static unsigned start_calls;
static sdk_err_t stop_result;
static sdk_err_t start_result;
static bool stop_completes_during_start;
void yp_scan_sched_on_radio_stop(bool stopped);
static yp_business_status_t *yp_business_status(void) { return &business; }
static bool ble_phone_connected(void) { return phone; }
static sdk_err_t ble_scanner_stop(void) { ++stop_calls; return stop_result; }
static sdk_err_t ble_scanner_start(void) {
    ++start_calls;
    if (stop_completes_during_start) {
        stop_completes_during_start=false;
        yp_scan_sched_on_radio_stop(true);
    }
    return start_result;
}
static void cli_printf(char const *fmt, ...) { if (strstr(fmt,"failed")) ++errors; }
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
'''
    unit += hold + function(source, 'void yp_scan_sched_on_radio_stop(')
    unit += function(source, 'static void radio_restart_poll(')
    unit += function(source, 'static void start_scan(')
    if hold:
        app = (ROOT / 'ble_app_uart_c/Src/user/user_app.c').read_text(encoding='utf-8')
        unit += '#define YP_SCAN_HOLD_MANUAL 2U\n'
        unit += function(app, 'static int cmd_ble_scan(')
    unit += function(source, 'static void stop_scan(')
    unit += function(source, 'void yp_scan_sched_set_enabled(')
    unit += r'''
int main(void) {
'''
    if hold:
        unit += r'''
    s_radio_stop_pending=true;
    start_scan(100); CHECK(start_calls==0 && s_next_attempt_ms==1100);
    s_radio_stop_pending=false;
    start_scan(1100); CHECK(start_calls==1 && s_scanning && s_scan_start_ms==1100);
'''
    unit += r'''
    s_active=s_scanning=true;
    yp_scan_sched_set_enabled(false);
    CHECK(!s_enabled && !s_active && !s_scanning);
    CHECK(stop_calls==1);
    stop_scan(); CHECK(stop_calls==1);
'''
    if hold:
        unit += r'''
    CHECK(s_radio_stop_pending);
    yp_scan_sched_on_radio_stop(false); CHECK(s_radio_stop_pending);
    yp_scan_sched_on_radio_stop(true); CHECK(!s_radio_stop_pending);
    for (unsigned owner=1; owner<=2; ++owner) {
        s_scanning=true;
        yp_scan_sched_radio_hold((uint8_t)owner,true);
        stop_scan(); CHECK(stop_calls==owner && s_stop_deferred && !s_scanning);
        yp_scan_sched_radio_hold((uint8_t)owner,false);
        stop_scan(); CHECK(stop_calls==owner+1 && !s_stop_deferred);
        CHECK(s_radio_stop_pending);
        yp_scan_sched_on_radio_stop(true);
    }
    s_scanning=true;
    yp_scan_sched_radio_hold(1,true); yp_scan_sched_radio_hold(2,true);
    stop_scan(); CHECK(stop_calls==3 && s_stop_deferred);
    yp_scan_sched_radio_hold(1,false);
    stop_scan(); CHECK(stop_calls==3 && s_stop_deferred);
    yp_scan_sched_radio_hold(2,false);
    stop_scan(); CHECK(stop_calls==4);
    yp_scan_sched_on_radio_stop(true);
    s_scanning=true; business.alarm_active=true;
    stop_scan(); CHECK(stop_calls==4 && s_stop_deferred);
    business.alarm_active=false; phone=true;
    stop_scan(); CHECK(stop_calls==4 && s_stop_deferred);
    phone=false; stop_scan(); CHECK(stop_calls==5 && !s_stop_deferred);
    yp_scan_sched_on_radio_stop(true);
    s_scanning=true; stop_result=0x0f;
    stop_scan(); CHECK(stop_calls==6 && errors==1 && !s_stop_deferred && !s_radio_stop_pending);
    stop_scan(); CHECK(stop_calls==6); /* no unbounded request flood after refusal */
    /* SOS/manual acquisition while the periodic stop is already in flight must resume after completion. */
    s_radio_stop_pending=true;
    yp_scan_sched_radio_hold(1,true);
    yp_scan_sched_on_radio_stop(true);
    CHECK(s_radio_restart_due && !s_radio_stop_pending);
    unsigned old_starts=start_calls;
    radio_restart_poll(); CHECK(start_calls==old_starts+1 && !s_radio_restart_due);
    yp_scan_sched_radio_hold(1,false);
    s_radio_stop_pending=true; yp_scan_sched_radio_hold(2,true);
    yp_scan_sched_on_radio_stop(true);
    yp_scan_sched_radio_hold(2,false); /* released before the foreground ran */
    old_starts=start_calls;
    radio_restart_poll(); CHECK(start_calls==old_starts && !s_radio_restart_due);
    char *manual_start[] = {"ble_scan", "start"};
    char *manual_stop[] = {"ble_scan", "stop"};
    s_radio_stop_pending=true; stop_completes_during_start=true; start_result=0x0f;
    CHECK(cmd_ble_scan(2,manual_start)==0x0f);
    CHECK(s_radio_holds==2 && s_radio_restart_due);
    start_result=0; radio_restart_poll();
    stop_result=0; CHECK(cmd_ble_scan(2,manual_stop)==0 && s_radio_holds==0);
'''
    unit += 'puts("PASS actual scan stop: normal disable, idempotence, shared holds, deferred release, alarm/phone guards, SDK refusal"); return 0; }\n'
    c = out / 'scan_stop.c'
    c.write_text(unit, encoding='utf-8')
    gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
    env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ['PATH'])
    exe = out / 'scan_stop.exe'
    build = subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', '-Wno-unused-variable', str(c), '-o', str(exe)],
                           capture_output=True, env=env, timeout=30)
    log = build.stdout + build.stderr
    result = build
    if build.returncode == 0:
        result = subprocess.run([str(exe)], capture_output=True, env=env, timeout=10)
        log += result.stdout + result.stderr
    log += f'\nexit_code={result.returncode}\n'.encode()
    (out / 'result.log').write_bytes(log)
    print(log.decode('utf-8', 'replace'))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
