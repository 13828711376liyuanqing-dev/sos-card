"""SAM | 2026-11-12 22:40 +08:00 | Exercise real diagnostic helpers and entry ordering before board tests."""
from pathlib import Path
import os
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ble_app_uart_c/Src"


def source(relative):
    return (SRC / relative).read_text(encoding="utf-8")


def function(text, signature):
    start = text.index(signature)
    body = text.index("{", start)
    depth = 1
    end = body + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class SleepDiagnostic(unittest.TestCase):
    def test_reg00_is_preserved_and_printed(self):
        driver = source("user/charger/yp001_charger.c")
        self.assertIn("uint8_t input_raw;", source("user/charger/yp001_charger.h"))
        self.assertIn("status->input_raw = input;", driver)
        self.assertIn("REG00=%02X", source("user/charger/yp001_charger_cli.c"))

    def test_raw_snapshot_keeps_fault_latch_and_precedes_boot_writes(self):
        driver = source("user/charger/yp001_charger.c")
        self.assertIn("bool yp001_charger_power_snapshot(", driver)
        snap = function(driver, "bool yp001_charger_power_snapshot(")
        self.assertNotIn("REG_FAULT", snap)
        self.assertNotIn("write_field", snap)
        self.assertNotIn("write_reg", snap)
        bsp = source("platform/bsp.c")
        boot = function(bsp, "void BSP_init(void)")
        self.assertLess(boot.index('yp001_charger_power_snapshot("boot")'),
                        boot.index('cli_execute_string("charger prepare")'))

    def test_psram_option_uses_normal_gate_and_same_long_window(self):
        cmd = function(source("platform/bsp.c"), "static int cmd_sleep_test(")
        self.assertIn('!strcmp(argv[2], "psram")', cmd)
        self.assertIn("s_sleep_psram_half = psram;", cmd)
        self.assertIn("argc == 4 || force || psram", cmd)
        self.assertIn("if (!force &&", cmd)
        self.assertIn("st->alarm_active || st->searching", cmd)

    def test_half_sleep_is_after_final_gate_and_resumes_before_watchdog(self):
        idle = function(source("platform/bsp.c"), "void QV_onIdle(void)")
        self.assertIn("yp_psram_sleep_test_suspend()", idle)
        branch = idle[idle.index("if (s_sleep_test)"):]
        self.assertLess(branch.index("if (s_sleep_ready && !s_sleep_source && !s_sleep_timeout)"),
                        branch.index("yp_psram_sleep_test_suspend()"))
        self.assertLess(branch.index("yp001_ota_power_change_allowed()"),
                        branch.index("yp_psram_sleep_test_suspend()"))
        self.assertLess(branch.index("yp_psram_sleep_test_suspend()"),
                        branch.index("pwr_mgmt_ultra_sleep("))
        self.assertLess(branch.index("pwr_mgmt_ultra_sleep("),
                        branch.index("yp_psram_sleep_test_resume()"))
        self.assertLess(branch.index("yp_psram_sleep_test_resume()"),
                        branch.index("app_aon_wdt_init("))
        prepare = function(source("platform/bsp.c"), "static void sleep_test_prepare(void)")
        self.assertIn("[SLEEP FINAL]", prepare)
        self.assertLess(prepare.index("[SLEEP FINAL]"), prepare.rindex("g_devices_state"))

    def test_diagnostic_charge_matches_measured_100ma(self):
        driver = source("user/charger/yp001_charger.c")
        self.assertRegex(driver, r"#define FAST_CHARGE_CURRENT_VALUE\s+100U")
        self.assertNotIn("(setpoints 100mA/4200mV)", driver)
        self.assertIn("status.charge_limit_ma, status.charge_voltage_mv", driver)

    def test_real_c_readback_and_psram_transitions(self):
        driver = source("user/charger/yp001_charger.c")
        psram = source("user/yp001_psram_mem.c")
        self.assertIn("bool yp_psram_sleep_test_suspend(void)", psram)
        self.assertIn("void yp_psram_sleep_test_resume(void)", psram)
        self.assertIn("uint8_t input_raw;", source("user/charger/yp001_charger.h"))
        defines = "\n".join(re.findall(r"^#define (?:REG_\w+|PART_ID_\w+)\s+.*$", driver, re.M))
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "yp001_charger.h"
static uint8_t regs[256];
static int fail_reg = -1;
static bool s_display_valid, s_psram_ready;
static yp001_charger_status_t s_display_status;
static uint32_t s_display_ms, s_test_clock_ms;
static bool read_reg(uint8_t reg, uint8_t *value) {
    if (reg == fail_reg) return false;
    *value = regs[reg];
    return true;
}
enum { OSPI_STATE_HALF_SLEEP = 1, OSPI_STATE_ACTIVE = 2 };
static int modes[4], mode_count;
static void app_graphics_ospi_set_power_state(int state) { modes[mode_count++] = state; }
static bool s_sleep_ready, s_sleep_psram_half, s_sleep_ultra_returned, power_allowed;
static uint32_t s_sleep_rescue_ms = 300000;
static int s_sleep_ultra_wdt_result, s_params, ultra_calls, wdt_restores;
#define APP_DRV_SUCCESS 0
#define APP_DRV_ERR_NOT_INIT 233
static bool yp001_ota_power_change_allowed(void) { return power_allowed; }
static void app_aon_wdt_evt_handler(void) {}
static void pwr_mgmt_ultra_sleep(uint32_t duration) {
    assert(duration == 300000);
    if (s_sleep_psram_half) assert(mode_count == 1 && modes[0] == OSPI_STATE_HALF_SLEEP);
    ++ultra_calls;
}
static int app_aon_wdt_init(int *params, void (*handler)(void)) {
    (void)params; (void)handler;
    if (s_sleep_psram_half && mode_count) assert(mode_count == 2 && modes[1] == OSPI_STATE_ACTIVE);
    ++wdt_restores;
    return 0;
}
'''
        code += "\n" + defines + "\n"
        code += function(driver, "bool yp001_charger_read_status(") + "\n"
        code += function(psram, "bool yp_psram_sleep_test_suspend(void)") + "\n"
        code += function(psram, "void yp_psram_sleep_test_resume(void)") + "\n"
        idle = function(source("platform/bsp.c"), "void QV_onIdle(void)")
        guarded = function(idle, "if (s_sleep_ultra_wdt_result == APP_DRV_SUCCESS")
        code += "void actual_sdk_entry(void) {\n" + guarded + "\n}\n"
        code += r'''
int main(void) {
    yp001_charger_status_t status = {0};
    s_ready = true;
    regs[REG_PART_ID] = PART_ID_VALUE;
    regs[REG_INPUT] = 0x24;
    assert(yp001_charger_read_status(&status));
    assert(status.input_raw == 0x24 && status.input_limit_ma == 500);
    regs[REG_INPUT] = 0x04;
    assert(yp001_charger_read_status(&status));
    assert(status.input_raw == 0x04 && status.input_limit_ma == 500);
    fail_reg = REG_INPUT;
    assert(!yp001_charger_read_status(&status) && !s_display_valid);
    assert(!yp_psram_sleep_test_suspend() && mode_count == 0);
    yp_psram_sleep_test_resume();
    assert(mode_count == 0);
    s_psram_ready = true;
    assert(yp_psram_sleep_test_suspend());
    yp_psram_sleep_test_resume();
    assert(mode_count == 2 && modes[0] == OSPI_STATE_HALF_SLEEP && modes[1] == OSPI_STATE_ACTIVE);
    mode_count = 0; s_sleep_ready = true; s_sleep_psram_half = true;
    power_allowed = false;
    actual_sdk_entry();
    assert(!s_sleep_ready && mode_count == 0 && ultra_calls == 0 && wdt_restores == 1);
    s_psram_ready = false; power_allowed = true; wdt_restores = 0;
    actual_sdk_entry();
    assert(!s_sleep_ready && mode_count == 0 && ultra_calls == 0 && wdt_restores == 1);
    s_psram_ready = true; wdt_restores = 0;
    actual_sdk_entry();
    assert(s_sleep_ready && s_sleep_ultra_returned && ultra_calls == 1 && wdt_restores == 1);
    assert(mode_count == 2 && modes[0] == OSPI_STATE_HALF_SLEEP && modes[1] == OSPI_STATE_ACTIVE);
    mode_count = 0; s_sleep_psram_half = false; ultra_calls = wdt_restores = 0;
    s_sleep_ultra_wdt_result = APP_DRV_ERR_NOT_INIT;
    actual_sdk_entry();
    assert(ultra_calls == 1 && mode_count == 0 && wdt_restores == 0);
    return 0;
}
'''
        code = code.replace("static bool s_display_valid, s_psram_ready;",
                            "static bool s_ready, s_display_valid, s_psram_ready;")
        out = ROOT / "logs/sleep_20261112/host_diagnostic"
        out.mkdir(exist_ok=True)
        cfile = out / "actual_helpers.c"
        cfile.write_text(code, encoding="utf-8")
        gcc = Path("D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe")
        env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ["PATH"])
        exe = out / "actual_helpers.exe"
        built = subprocess.run([str(gcc), "-std=c99", "-Wall", "-Wextra", "-Werror",
                                "-I" + str(SRC / "user/charger"), str(cfile), "-o", str(exe)],
                               env=env, capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        subprocess.run([str(exe)], env=env, check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
