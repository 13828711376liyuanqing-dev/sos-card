"""SAM | 2026-10-28 17:43 +08:00 | Run the real gsensor background-read functions against a simulated DA215 because per-sample reconfigure/restore produced bench outliers that reset OTA stillness."""
from pathlib import Path
import os, re, subprocess
root = Path(__file__).resolve().parents[2]
gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
out = root/'logs/gsensor_background_20261028'
out.mkdir(parents=True, exist_ok=True)
text = (root/'ble_app_uart_c/Src/user/gsensor_probe.c').read_text(encoding='utf-8-sig')

def function(signature):
    start = text.find(signature)
    if start < 0: return ''
    return text[start:text.index('\n}\n', start)+3]

names = ['static int16_t gsensor_decode14(', 'static int gsensor_capture(',
         'static bool gsensor_background_config(', 'bool gsensor_read_mg(']
body = '\n'.join(function(n) for n in names)
prefix = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int i2c_handle_t; static i2c_handle_t handle;
#define APP_I2C_ID_0 0
#define HAL_I2C_STATE_READY 1
static int i2c_state = HAL_I2C_STATE_READY;
static i2c_handle_t *app_i2c_get_handle(int id) { (void)id; return &handle; }
static int hal_i2c_get_state(i2c_handle_t *h) { (void)h; return i2c_state; }
static struct { bool active; } s_wait;
static uint8_t reg[256]; static unsigned writes, reads; static bool fail_reads;
static void delay_ms(unsigned ms) { (void)ms; }
static void cli_printf(const char *f, ...) { (void)f; }
static bool gsensor_xyz_read(uint8_t r, uint8_t *d, uint16_t n) {
    ++reads; if (fail_reads) return false;
    for (uint16_t i = 0; i < n; ++i) d[i] = reg[(uint8_t)(r + i)];
    return true;
}
static bool gsensor_xyz_write_check(uint8_t r, uint8_t v) { ++writes; reg[r] = v; return true; }
'''
suffix = r'''
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static void sample(int16_t x, int16_t y, int16_t z) {
    int16_t v[3] = {x, y, z};
    for (int i = 0; i < 3; ++i) { uint16_t u = (uint16_t)(v[i] << 2); reg[2 + 2*i] = (uint8_t)u; reg[3 + 2*i] = (uint8_t)(u >> 8); }
}
int main(void) {
    int32_t xyz[3];
    /* Awake power-on style config: suspend (0x80), other ODR, reserved bits set. */
    reg[0x01] = 0x13; reg[0x0F] = 0x41; reg[0x10] = 0x1A; reg[0x11] = 0x80; sample(-205, -78, -3075);
    CHECK(!gsensor_read_mg(xyz));                      /* reconfigure round discards its sample */
    CHECK(reg[0x0F] == 0x40 && reg[0x10] == 0x17 && reg[0x11] == 0x34);
    writes = 0;
    for (int i = 0; i < 20; ++i) { CHECK(gsensor_read_mg(xyz)); }
    CHECK(writes == 0);                                /* steady state never rewrites/restores config */
    CHECK(xyz[0] == -205*1000/4096 && xyz[1] == -78*1000/4096 && xyz[2] == -3075*1000/4096);
    /* Sleep-motion arm config (0x00/0x07/0x34) already satisfies the target: no writes while armed. */
    reg[0x0F] = 0x00; reg[0x10] = 0x07; reg[0x11] = 0x34; writes = 0;
    CHECK(gsensor_read_mg(xyz) && writes == 0);
    /* Something restored suspend: rewrite once, discard, then resume plain reads. */
    reg[0x11] = 0x80; CHECK(!gsensor_read_mg(xyz)); CHECK(reg[0x11] == 0x34); CHECK(gsensor_read_mg(xyz));
    /* Wrong chip ID: never write, never report. */
    reg[0x11] = 0x80; reg[0x01] = 0x00; writes = 0; CHECK(!gsensor_read_mg(xyz) && writes == 0 && reg[0x11] == 0x80);
    reg[0x01] = 0x13; CHECK(!gsensor_read_mg(xyz)); CHECK(gsensor_read_mg(xyz));
    /* Diagnostic ownership, busy I2C and read failure: no sample, zeroed output, no writes. */
    writes = 0; s_wait.active = true; xyz[2] = 7; CHECK(!gsensor_read_mg(xyz)); s_wait.active = false;
    i2c_state = 0; CHECK(!gsensor_read_mg(xyz)); i2c_state = HAL_I2C_STATE_READY;
    fail_reads = true; CHECK(!gsensor_read_mg(xyz) && xyz[0] == 0 && xyz[1] == 0 && xyz[2] == 0); fail_reads = false;
    CHECK(writes == 0);
    CHECK(!gsensor_read_mg(NULL));
    puts("PASS gsensor background read: one-time vendor normal config, no per-sample reconfigure, fail-closed");
    return 0;
}
'''
src = out/'harness.c'
src.write_text(prefix + body + suffix, encoding='utf-8')
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
r = subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', str(src), '-o', str(out/'harness.exe')], env=env, capture_output=True, text=True)
log = r.stdout + r.stderr
if r.returncode == 0:
    r = subprocess.run([str(out/'harness.exe')], capture_output=True, text=True, timeout=20)
    log += r.stdout + r.stderr
(out/'harness.log').write_text(log, encoding='utf-8')
print(log)
raise SystemExit(r.returncode)
