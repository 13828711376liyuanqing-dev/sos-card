#include "yp001_psram_mem.h"
#include "app_graphics_ospi.h"
#include "app_graphics_mem.h"
#include "platform_sdk.h"
#include "app_drv_error.h"
#include "cli.h"

extern uint32_t Image$$GFX_MEM_HEAP$$Base;
#define YP_PSRAM_HEAP_BASE ((uint32_t)&Image$$GFX_MEM_HEAP$$Base)
#define YP_PSRAM_OTA_BASE   (0x30880000UL - 0x00080000UL)
#define YP_PSRAM_OTA_SIZE   (0x00080000UL)
#define YP_PSRAM_HEAP_SIZE  (YP_PSRAM_OTA_BASE - YP_PSRAM_HEAP_BASE)

static bool s_psram_ready;

/* ---------------------------------------------------------------------------
 * Public API
 * ------------------------------------------------------------------------- */
bool yp_psram_mem_init(void)
{
    if (s_psram_ready) {
        return true;
    }
    app_graphics_ospi_params_t params = PSRAM_INIT_PARAMS_Default;
    if (app_graphics_ospi_init(&params) != APP_DRV_SUCCESS) {
        cli_printf("[PSRAM] app_graphics_ospi_init failed\r\n");
        return false;
    }
    //mem_pwr_mgmt_mode_set(MEM_POWER_FULL_MODE);
    app_graphics_mem_init((void *)YP_PSRAM_HEAP_BASE, YP_PSRAM_HEAP_SIZE);
    cli_printf("[PSRAM] ready, heap 0x%08X %u B\r\n",
           (unsigned)YP_PSRAM_HEAP_BASE, (unsigned)YP_PSRAM_HEAP_SIZE);
    s_psram_ready = true;
    return true;
}

void *yp_psram_alloc(uint32_t size)
{
    if (!s_psram_ready || size == 0) {
        return NULL;
    }
    return app_graphics_mem_malloc(size);
}

void yp_psram_free(void *buf_ptr) {
    if (s_psram_ready && buf_ptr) {
        app_graphics_mem_free(buf_ptr);
    }    
}

bool yp_psram_ota_region(void **base, uint32_t *size)
{
    if (base != NULL) {
        *base = (void *)YP_PSRAM_OTA_BASE;
    }
    if (size != NULL) {
        *size = YP_PSRAM_OTA_SIZE;
    }
    return true;
}