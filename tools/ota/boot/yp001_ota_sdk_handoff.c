/* SAM | 2026-10-21 +08:00 | Follow SDK104 deinit/jump sequence while preserving watchdog and rejecting a returning jump. Isolated candidate only. */
#include "yp001_ota_sdk_handoff.h"
#include "custom_config.h"
#include "bootloader_config.h"
#include "gr_includes.h"
#include "gr55xx_sys.h"
#include "user_periph_setup.h"
#if !defined(BOOTLOADER_DFU_UART_ENABLE) || !defined(BOOTLOADER_DFU_BLE_ENABLE) || !defined(BOOTLOADER_DFU_ENABLE) || !defined(BOOTLOADER_WDT_ENABLE) || !defined(APP_LOG_ENABLE)
#error YP_BOOT_MINIMAL_CONFIG_REQUIRED
#endif
#if BOOTLOADER_DFU_UART_ENABLE || BOOTLOADER_DFU_BLE_ENABLE || BOOTLOADER_DFU_ENABLE || !BOOTLOADER_WDT_ENABLE || APP_LOG_ENABLE
#error YP_BOOT_MINIMAL_CONFIG_REQUIRED
#endif
static int sdk_quiesce(void *ctx){
 (void)ctx;
 /* SAM | 2026-10-21 +08:00 | Propagate real refresh failure before dismantling peripherals. */
 if(bootloader_wdt_service(0))return -1;
 app_periph_deinit();
 return 0;
}
static void sdk_jump(void *ctx,uint32_t address,uint32_t size){
 (void)ctx;
 /* SAM | 2026-10-21 +08:00 | A failed final refresh must reset, never enter the app. */
 if(!bootloader_wdt_service(0)){
 /* Leave the SDK to perform its firmware interrupt/context transition. */
 sys_firmware_jump(address,size);
 }
 hal_nvic_system_reset();
 /* If the reset request returns, do not resume services or feed the watchdog. */
 for(;;){}
}
yp_boot_handoff yp_boot_minimal_sdk_handoff(void){
 yp_boot_handoff h;
 h.ctx=0;h.quiesce=sdk_quiesce;h.jump=sdk_jump;
 return h;
}
