"""SAM | 2026-11-07 +08:00 | Exercise actual business inputs and OTA gates under control events in both builds."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/business"))
from test_scan_stop_shared import function

out = ROOT / "logs/ota_control_events_20261107"
out.mkdir(exist_ok=True)
port = (ROOT / "ble_app_uart_c/Src/user/ota/yp001_ota_port.c").read_text(encoding="utf-8")
unit = r'''
#include "yp001_business.h"
#include <string.h>
static yp_business_status_t s;
static bool ota_battery_seen, ota_keys_seen, ota_motion_seen, ota_moving, ota_key_down;
static uint32_t ota_battery_ms, ota_keys_ms, ota_motion_ms, ota_quiet_ms;
static uint32_t key_requests, consumed_keys, call_request, consumed_call;
void yp_business_init(void) { memset(&s, 0, sizeof s); ota_battery_seen=false; }
const yp_business_status_t *yp_business_status(void) { return &s; }
void yp_business_observation_clock(uint32_t now) { s.now_ms=now; }
void yp_business_battery(bool known, uint8_t percent, bool charging) {
 s.battery_known=known; s.battery_percent=percent; s.charging=charging;
 ota_battery_seen=true; ota_battery_ms=s.now_ms;
}
void yp_business_motion(bool known, bool moving, uint32_t now) {
 ota_motion_seen=known; ota_moving=moving; ota_motion_ms=now;
}
void yp_business_keys(bool left, bool right, uint32_t now) {
 ota_keys_seen=true; ota_key_down=left||right; ota_keys_ms=now; ++key_requests;
}
void yp_business_call_action(bool accept) { (void)accept; ++call_request; }
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while (0)
bool yp_business_port_send(const char *line, size_t n) { (void)line; return n > 0; }
bool yp_business_port_time(uint32_t epoch) { return epoch > 0; }
bool yp_business_port_sos(bool start) { (void)start; return true; }
static bool usb_power;
bool yp001_ota_port_usb_power(void) { return usb_power; }
typedef struct { bool known, stable, activity, alarm, charging, call, peer_stable; unsigned battery; } yp001_ota_gates;
'''
business = (ROOT / "ble_app_uart_c/Src/user/business/yp001_business.c").read_text(encoding="utf-8")
unit += function(business, "static bool ota_fresh(")
unit += function(business, "void yp_business_ota_inputs_with_usb(")
unit += function(port, "void yp001_ota_port_gates(")
unit += "\ntypedef struct { uint32_t new_image; } yp_boot;\nstatic struct { uint32_t actual; } health_check;\nstatic bool result_check_started, health_started;\nstatic uint32_t result_check_at, health_since;\n"
unit += function(port, "static bool health_observe(")
unit += r'''
int main(void) {
    yp_business_ota_inputs_t inputs;
    yp001_ota_gates gates;
    yp_boot boot={7};health_check.actual=7;
    yp_business_init();
    ota_quiet_ms=1000; consumed_call=0;
    yp_business_observation_clock(1000);
    yp_business_battery(true, 90, true);
    s.call = YP_CALL_IDLE; s.transport_ready = true; s.network = YP_NET_MQTT;
    /* No key/motion samples, no quiet delay: fresh actual power qualifies OTA. */
    yp_business_ota_inputs_with_usb(&inputs, false);
    CHECK(inputs.known && inputs.stable && !inputs.activity);
    for (unsigned i = 0; i <= 130; ++i) {
        uint32_t now = 1000 + i * 1000;
        yp_business_observation_clock(now);
        yp_business_battery(true, 90, true);
        yp_business_motion((i % 3) != 0, true, now);
        yp_business_keys(true, false, now);
        yp_business_call_action(true);
        s.searching = true; s.sleeping = true;
        yp001_ota_port_gates(&gates);
        CHECK(gates.known && gates.stable && !gates.activity);
        CHECK(!gates.alarm && !gates.call && gates.peer_stable);
        CHECK(health_observe(&boot) == (i >= 120));
    }
    /* The extracted input function leaves the modeled business/control state intact. */
    CHECK(s.searching && s.sleeping && key_requests != consumed_keys);
    CHECK(call_request != consumed_call && ota_quiet_ms == 1000);
    s.alarm_active = true; yp001_ota_port_gates(&gates); CHECK(gates.alarm); CHECK(!health_observe(&boot) && !health_started);
    s.alarm_active = false;
    for (unsigned call = YP_CALL_DIALING; call <= YP_CALL_CONNECTED; ++call) {
        s.call = (yp_call_t)call; yp001_ota_port_gates(&gates); CHECK(gates.call); CHECK(!health_observe(&boot));
    }
    s.call = YP_CALL_UNKNOWN; yp001_ota_port_gates(&gates); CHECK(gates.call && !gates.known); CHECK(!health_observe(&boot));
    s.call = YP_CALL_IDLE; s.transport_ready = false;
    yp001_ota_port_gates(&gates); CHECK(!gates.peer_stable); CHECK(!health_observe(&boot));
    s.transport_ready = true; s.network = YP_NET_OFFLINE;
    yp001_ota_port_gates(&gates); CHECK(!gates.peer_stable); CHECK(!health_observe(&boot));
    yp_business_observation_clock(s.now_ms + 3001);
    yp_business_ota_inputs_with_usb(&inputs, true); CHECK(!inputs.known && !inputs.stable);
    yp_business_battery(false, 0, false);
    yp_business_ota_inputs_with_usb(&inputs, true); CHECK(inputs.known && inputs.stable);
    yp_business_ota_inputs_with_usb(&inputs, false); CHECK(!inputs.known && !inputs.stable);
    puts("PASS actual OTA inputs/gates/health: 130s controls ignored; alarm/call/link and fresh power retained");
    return 0;
}
'''
source = out / "control_events.c"
source.write_text(unit, encoding="utf-8")
gcc = Path("D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe")
env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ["PATH"])
for mode in (0, 1):
    exe = out / f"control_events_{mode}.exe"
    command = [str(gcc), "-std=c99", "-Wall", "-Wextra", "-Werror", "-DYP_BUSINESS_HOST_TEST",
               f"-DYP001_OTA_USB_BENCH_TEST={mode}",
               "-I" + str(ROOT / "ble_app_uart_c/Src/user/business"),
               "-I" + str(ROOT / "ble_app_uart_c/Src/external/cJSON-1.7.19"), str(source),
               "-o", str(exe)]
    build = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    result = build if build.returncode else subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=15)
    log = build.stdout + build.stderr
    if result is not build:
        log += result.stdout + result.stderr
    (out / f"mode_{mode}.log").write_text(log, encoding="utf-8")
    print(log, end="")
    if result.returncode:
        raise SystemExit(result.returncode)
