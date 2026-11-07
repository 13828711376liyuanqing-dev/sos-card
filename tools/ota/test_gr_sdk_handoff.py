"""SAM | 2026-10-21 +08:00 | Host-only SDK adapter and incompatible configuration checks."""
from pathlib import Path
import os
import subprocess

r = Path(__file__).resolve().parents[2]
o = r / 'logs/ota_preflight_20261021/sdk_handoff_test'
o.mkdir(parents=True, exist_ok=True)
(o / 'user_periph_setup.h').write_text('void app_periph_deinit(void);\nint bootloader_wdt_service(void *ctx);\n')
(o / 'gr55xx_sys.h').write_text('#include <stdint.h>\nvoid sys_firmware_jump(uint32_t,uint32_t);\n')
(o / 'gr_includes.h').write_text('void hal_nvic_system_reset(void);\n')
gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH', ''))
base = [str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I'+str(o), '-I'+str(r/'tools/ota/boot'), '-I'+str(r/'ble_app_uart_c/Src/user/ota')]
config = dict(BOOTLOADER_DFU_UART_ENABLE=0, BOOTLOADER_DFU_BLE_ENABLE=0,
              BOOTLOADER_DFU_ENABLE=0, BOOTLOADER_WDT_ENABLE=1, APP_LOG_ENABLE=0)
def headers(values):
    (o/'bootloader_config.h').write_text(''.join(f'#define {k} {v}\n' for k,v in values.items() if k!='APP_LOG_ENABLE'))
    (o/'custom_config.h').write_text(f'#define APP_LOG_ENABLE {values["APP_LOG_ENABLE"]}\n')
headers(config)
source = str(r/'tools/ota/boot/yp001_ota_sdk_handoff.c')
subprocess.run(base+[str(r/'tools/ota/test_gr_sdk_handoff.c'), source, '-o', str(o/'test.exe')], env=env, check=True)
subprocess.run([str(o/'test.exe')], env=env, check=True)
for key in config:
    invalid = dict(config)
    invalid[key] = 1-config[key]
    headers(invalid)
    result = subprocess.run(base+['-c', source, '-o', str(o/'invalid.o')], env=env, capture_output=True, text=True)
    assert result.returncode and 'YP_BOOT_MINIMAL_CONFIG_REQUIRED' in result.stderr, (key, result.stderr)
headers(config)
print('PASS all five incompatible Boot configuration guards')
