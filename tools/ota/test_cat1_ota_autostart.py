"""SAM | 2026-10-28 19:00 +08:00 | Host-test the bench CAT1 OTA autostart decision because a GR reset during an active GR OTA leaves CAT1 unpowered and the PWRKEY gate blocks manual start, so TRIAL health/MQTT can never complete."""
from pathlib import Path
import os, subprocess
root = Path(__file__).resolve().parents[2]
gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
out = root/'logs/cat1_ota_autostart_20261028'; out.mkdir(parents=True, exist_ok=True)
src = out/'harness.c'
src.write_text(r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "yp001_cat1_autostart.h"
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
int main(void) {
    yp001_cat1_autostart_t s = {0}; uint32_t t; int asserts = 0;
    /* Active GR owner, CAT1 silent: wait the full boot grace, then exactly one 1600ms pulse. */
    for (t = 0; t < 15000; t += 100) CHECK(yp001_cat1_autostart_step(&s, t, true, false) == YP001_CAT1_AS_NONE);
    CHECK(yp001_cat1_autostart_step(&s, 15000, true, false) == YP001_CAT1_AS_ASSERT);
    for (t = 15100; t < 16600; t += 100) CHECK(yp001_cat1_autostart_step(&s, t, true, false) == YP001_CAT1_AS_NONE);
    CHECK(yp001_cat1_autostart_step(&s, 16600, true, false) == YP001_CAT1_AS_RELEASE);
    for (t = 16700; t < 120000; t += 100) { int a = yp001_cat1_autostart_step(&s, t, true, false); if (a == YP001_CAT1_AS_ASSERT) ++asserts; CHECK(a == YP001_CAT1_AS_NONE); }
    CHECK(asserts == 0);                                   /* never a second press in one boot */
    /* CAT1 already alive (VBUS kept it up): never press, which would switch it off. */
    s = (yp001_cat1_autostart_t){0};
    CHECK(yp001_cat1_autostart_step(&s, 3000, true, true) == YP001_CAT1_AS_NONE);
    for (t = 3000; t < 60000; t += 100) CHECK(yp001_cat1_autostart_step(&s, t, true, false) == YP001_CAT1_AS_NONE);
    /* No active GR owner: normal manual policy, never press. */
    s = (yp001_cat1_autostart_t){0};
    for (t = 0; t < 60000; t += 100) CHECK(yp001_cat1_autostart_step(&s, t, false, false) == YP001_CAT1_AS_NONE);
    /* Owner disappears after the press: release still happens on time. */
    s = (yp001_cat1_autostart_t){0};
    CHECK(yp001_cat1_autostart_step(&s, 20000, true, false) == YP001_CAT1_AS_ASSERT);
    CHECK(yp001_cat1_autostart_step(&s, 21600, false, true) == YP001_CAT1_AS_RELEASE);
    /* Clock not yet past grace when owner first seen late: still waits for 15s since boot. */
    s = (yp001_cat1_autostart_t){0};
    CHECK(yp001_cat1_autostart_step(&s, 14999, true, false) == YP001_CAT1_AS_NONE);
    puts("PASS cat1 OTA autostart: one delayed pulse only when GR owner active and CAT1 silent; never when alive or idle");
    return 0;
}
''', encoding='utf-8')
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
r = subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror', '-I'+str(root/'ble_app_uart_c/Src/user/ota'), str(src), '-o', str(out/'harness.exe')], env=env, capture_output=True, text=True)
log = r.stdout + r.stderr
if r.returncode == 0:
    r = subprocess.run([str(out/'harness.exe')], capture_output=True, text=True, timeout=20); log += r.stdout + r.stderr
(out/'harness.log').write_text(log, encoding='utf-8'); print(log); raise SystemExit(r.returncode)
