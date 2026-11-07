/* SAM | 2026-10-13 08:36 +08:00 | Keep business foreground responsive during synchronous EPD waits; no display recursion. */
extern void yp001_business_service(void);
#include "epaper_depg0150.h"
#include "yp001_psram_mem.h"

#include "app_io.h"
#include "app_log.h"
#include "app_aon_wdt.h"
#include "gr55xx_delay.h"
#include "cli.h"
/* SAM | 2026-10-09 15:15 +08:00 | Keep charger safety polling alive
 * because EPD BUSY can hold foreground execution for many seconds. */
#include "charger/yp001_charger.h"

#include <stdbool.h>
#include <string.h>

#include "epaper_depg0150_logo_yp01.h"
#include "yp001_board_config.h"
#include "gui/epaper_lvgl.h"

#define EPAPER_BUSY_PIN YP001_LCD_BUSY_PIN
#define EPAPER_RES_PIN  YP001_LCD_RESET_PIN
#define EPAPER_SDA_PIN  YP001_LCD_DATA_PIN
#define EPAPER_SCL_PIN  YP001_LCD_CLK_PIN
#define EPAPER_DC_PIN   YP001_LCD_RS_PIN
#define EPAPER_CS_PIN   YP001_LCD_CS_PIN
#define EPAPER_GPIO_MUX YP001_GPIO_GPIO_MUX

#define EPAPER_WIDTH_BYTES  25U
#define EPAPER_HEIGHT       200U
#define EPAPER_IMAGE_BYTES  (EPAPER_WIDTH_BYTES * EPAPER_HEIGHT)
#define EPAPER_REFRESH_BUSY_ASSERT_TIMEOUT_MS 500U

/* SAM | 2026-10-07 10:34 +08:00 | Default to partial refresh for bench validation;
 * retain full refresh as a runtime CLI option and as the mandatory first-frame fallback.
 */
#ifndef EPAPER_DEFAULT_PARTIAL_REFRESH
#define EPAPER_DEFAULT_PARTIAL_REFRESH 1U
#endif

#if EPAPER_DEFAULT_PARTIAL_REFRESH
#define EPAPER_INITIAL_REFRESH_MODE 1U
#else
#define EPAPER_INITIAL_REFRESH_MODE 0U
#endif

#define EPAPER_REFRESH_MODE_FULL    0U
#define EPAPER_REFRESH_MODE_PARTIAL 1U

static uint8_t s_refresh_mode = EPAPER_INITIAL_REFRESH_MODE;
static bool s_previous_frame_valid;
/* SAM | 2026-10-09 17:51 +08:00 | Keep a one-shot full request until success
 * because partial refresh left the first valid battery fields blank. */
static bool s_force_full_next;
/* SAM | 2026-10-09 22:21 +08:00 | Bound consecutive partial updates because
 * repeated EPD transitions can accumulate visible ghost pixels. */
#define EPAPER_PARTIALS_BEFORE_FULL 8U
static uint8_t s_partial_refresh_count;
static uint8_t *s_previous_frame;
static uint8_t *s_effective_frame;

static bool epaper_display_buffer(const uint8_t *image);

/* SAM | 2026-10-20 12:47 +08:00 | Use the teammate-provided YP_01 boot logo
 * and remove the temporary TEST OK overlay because the customer logo is the
 * requested startup screen. */

static void epaper_write_pin(app_io_type_t type, uint32_t pin, app_io_pin_state_t state)
{
    app_io_write_pin(type, pin, state);
}

static uint16_t epaper_gpio_init(app_io_type_t type, uint32_t pin, app_io_mode_t mode)
{
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;

    io_init.mode = mode;
    io_init.pull = APP_IO_NOPULL;
    io_init.mux = EPAPER_GPIO_MUX;
    io_init.pin = pin;
    return app_io_init(type, &io_init);
}

static void epaper_spi_write_byte(uint8_t value)
{
    uint8_t bit;

    for (bit = 0U; bit < 8U; ++bit)
    {
        epaper_write_pin(YP001_LCD_DATA_TYPE, EPAPER_SDA_PIN,
                         (value & 0x80U) ? APP_IO_PIN_SET : APP_IO_PIN_RESET);
        epaper_write_pin(YP001_LCD_CLK_TYPE, EPAPER_SCL_PIN, APP_IO_PIN_SET);
        delay_us(5U);
        epaper_write_pin(YP001_LCD_CLK_TYPE, EPAPER_SCL_PIN, APP_IO_PIN_RESET);
        value <<= 1;
        delay_us(5U);
    }
}

static void epaper_write_command(uint8_t command)
{
    epaper_write_pin(YP001_LCD_CS_TYPE, EPAPER_CS_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(YP001_LCD_RS_TYPE, EPAPER_DC_PIN, APP_IO_PIN_RESET);
    delay_us(5U);
    epaper_spi_write_byte(command);
    delay_us(5U);
    epaper_write_pin(YP001_LCD_CS_TYPE, EPAPER_CS_PIN, APP_IO_PIN_SET);
}

static void epaper_write_data(uint8_t data)
{
    epaper_write_pin(YP001_LCD_CS_TYPE, EPAPER_CS_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(YP001_LCD_RS_TYPE, EPAPER_DC_PIN, APP_IO_PIN_SET);
    delay_us(5U);
    epaper_spi_write_byte(data);
    delay_us(5U);
    epaper_write_pin(YP001_LCD_CS_TYPE, EPAPER_CS_PIN, APP_IO_PIN_SET);
}

static bool epaper_wait_ready(const char *stage)
{
    uint32_t timeout_ms = 30000U;

    while ((app_io_read_pin(YP001_LCD_BUSY_TYPE, EPAPER_BUSY_PIN) == APP_IO_PIN_SET)
           && (timeout_ms > 0U))
    {
        app_aon_wdt_refresh();
        yp001_charger_poll();
        yp001_business_service();
        delay_ms(1U);
        --timeout_ms;
    }
    delay_ms(1U);
    if (timeout_ms == 0U)
    {
        APP_LOG_ERROR("EPD BUSY timeout at %s, pin=%d", stage,
                      app_io_read_pin(YP001_LCD_BUSY_TYPE, EPAPER_BUSY_PIN));
        return false;
    }
    APP_LOG_INFO("EPD ready at %s, waited=%lu ms", stage, (unsigned long)(30000U-timeout_ms));
    app_log_flush();
    return true;
}

static bool epaper_wait_refresh_complete(void)
{
    uint32_t timeout_ms = EPAPER_REFRESH_BUSY_ASSERT_TIMEOUT_MS;

    while ((app_io_read_pin(YP001_LCD_BUSY_TYPE, EPAPER_BUSY_PIN) == APP_IO_PIN_RESET)
           && (timeout_ms > 0U))
    {
        app_aon_wdt_refresh();
        /* SAM | 2026-10-09 15:15 +08:00 | Service charge stop while waiting. */
        yp001_charger_poll();
        yp001_business_service();
        delay_ms(1U);
        --timeout_ms;
    }
    if (app_io_read_pin(YP001_LCD_BUSY_TYPE, EPAPER_BUSY_PIN) == APP_IO_PIN_RESET)
    {
        APP_LOG_ERROR("EPD BUSY did not assert after refresh command");
        return false;
    }
    APP_LOG_INFO("EPD BUSY asserted after %lu ms", (unsigned long)(EPAPER_REFRESH_BUSY_ASSERT_TIMEOUT_MS-timeout_ms));
    app_log_flush();
    return epaper_wait_ready("after refresh");
}

static bool epaper_controller_init(void)
{
    /* YP001 GPIO10 rail enabled by BSP before calling the display driver. */
    delay_ms(100U); /* Let the GPIO10-controlled EPD_VDD regulator settle. */
    app_aon_wdt_refresh();
    epaper_write_pin(YP001_LCD_RESET_TYPE, EPAPER_RES_PIN, APP_IO_PIN_RESET);
    delay_ms(10U);
    epaper_write_pin(YP001_LCD_RESET_TYPE, EPAPER_RES_PIN, APP_IO_PIN_SET);
    delay_ms(10U);
    if (!epaper_wait_ready("after hardware reset")) return false;

    epaper_write_command(0x12U);
    if (!epaper_wait_ready("after software reset")) return false;

    epaper_write_command(0x01U);
    epaper_write_data(0xC7U);
    epaper_write_data(0x00U);
    epaper_write_data(0x00U);

    epaper_write_command(0x11U);
    epaper_write_data(0x01U);

    epaper_write_command(0x44U);
    epaper_write_data(0x00U);
    epaper_write_data(0x18U);

    epaper_write_command(0x45U);
    epaper_write_data(0xC7U);
    epaper_write_data(0x00U);
    epaper_write_data(0x00U);
    epaper_write_data(0x00U);

    epaper_write_command(0x4EU);
    epaper_write_data(0x00U);

    epaper_write_command(0x4FU);
    epaper_write_data(0xC7U);
    epaper_write_data(0x00U);

    epaper_write_command(0x3CU);
    epaper_write_data(0x05U);

    epaper_write_command(0x21U);
    epaper_write_data(0x00U);
    epaper_write_data(0x00U);

    epaper_write_command(0x3CU);
    epaper_write_data(0x80U);

    return true;
}

/* Partial refresh follows the vendor sequence: hardware reset without 0x12,
 * then border setup. A software reset here clears the panel's partial state.
 */
/* SAM | 2026-10-07 10:34 +08:00 | Add the vendor's no-soft-reset partial init
 * sequence because 0x12 clears the partial-update controller state.
 */
static bool epaper_controller_partial_init(void)
{
    epaper_write_pin(YP001_LCD_RESET_TYPE, EPAPER_RES_PIN, APP_IO_PIN_RESET);
    delay_ms(10U);
    epaper_write_pin(YP001_LCD_RESET_TYPE, EPAPER_RES_PIN, APP_IO_PIN_SET);
    delay_ms(10U);
    if (!epaper_wait_ready("before partial refresh")) return false;
    epaper_write_command(0x3CU);
    epaper_write_data(0x80U);
    return true;
}

/* SAM | 2026-10-09 22:08 +08:00 | Send the complete frame for partial refresh
 * because changed-window updates left stale voltage and mixed status glyphs;
 * the vendor's Display_image_new_partial_update also writes all 5000 bytes. */
static bool epaper_display_partial(const uint8_t *frame)
{
    uint32_t i;

    if (!s_previous_frame_valid || s_previous_frame == NULL) return false;
    if (frame == NULL) return false;
    if (memcmp(frame, s_previous_frame, EPAPER_IMAGE_BYTES) == 0)
    {
        APP_LOG_INFO("EPD partial refresh skipped: frame unchanged");
        return true;
    }
    if (!epaper_controller_partial_init()) return false;
    epaper_write_command(0x24U);
    for (i = 0U; i < EPAPER_IMAGE_BYTES; ++i)
    {
        epaper_write_data(frame[i]);
        if ((i & 63U) == 0U) {
            app_aon_wdt_refresh();
            yp001_charger_poll();
        yp001_business_service();
        }
    }

    epaper_write_command(0x22U);
    epaper_write_data(0xFFU);
    epaper_write_command(0x20U);
    if (!epaper_wait_refresh_complete()) return false;
    epaper_write_command(0x10U);
    epaper_write_data(0x01U);
    delay_ms(100U);
    APP_LOG_INFO("EPD partial refresh complete: full frame %u bytes",
                 (unsigned)EPAPER_IMAGE_BYTES);
    if (s_partial_refresh_count < EPAPER_PARTIALS_BEFORE_FULL)
        ++s_partial_refresh_count;
    return true;
}

/* SAM | 2026-10-07 10:34 +08:00 | Select full/partial per build default and CLI,
 * forcing a full baseline after reset or any failed refresh.
 */
static bool epaper_display_selected_frame(const uint8_t *frame)
{
    bool success;
    bool use_partial = !s_force_full_next &&
        s_refresh_mode == EPAPER_REFRESH_MODE_PARTIAL && s_previous_frame_valid &&
        s_partial_refresh_count < EPAPER_PARTIALS_BEFORE_FULL;

    if (use_partial)
    {
        success = epaper_display_partial(frame);
    }
    else
    {
        APP_LOG_INFO("EPD full refresh (%s)", s_previous_frame_valid ? "selected" : "initial baseline");
        success = epaper_display_buffer(frame);
    }

    if (success)
    {
        /* SAM | 2026-10-09 22:21 +08:00 | A successful full update restores
         * the optical baseline before the next group of partial updates. */
        if (!use_partial)
            s_partial_refresh_count = 0U;
        if (s_previous_frame != NULL) {
            memcpy(s_previous_frame, frame, EPAPER_IMAGE_BYTES);
            s_previous_frame_valid = true;
        } else {
            s_previous_frame_valid = false;
        }
        /* SAM | 2026-10-09 17:51 +08:00 | Restore normal partial selection
         * only after the requested full frame was accepted. */
        s_force_full_next = false;
    }
    else
    {
        s_previous_frame_valid = false;
    }
    return success;
}

/* SAM | 2026-10-07 10:34 +08:00 | Add UART CLI override for bench use and
 * colleague selection without changing the compile-time default.
 */
static int cmd_epd_refresh(int argc, char *argv[])
{
    if (argc != 2)
    {
        cli_printf("Usage: epd_refresh <full|partial|status>\r\n");
        return -1;
    }
    if (strcmp(argv[1], "status") == 0)
    {
        cli_printf("EPD refresh mode: %s; baseline: %s\r\n",
                   s_refresh_mode == EPAPER_REFRESH_MODE_PARTIAL ? "partial" : "full",
                   s_previous_frame_valid ? "valid" : "not set");
        return 0;
    }
    if (strcmp(argv[1], "full") == 0)
        s_refresh_mode = EPAPER_REFRESH_MODE_FULL;
    else if (strcmp(argv[1], "partial") == 0)
        s_refresh_mode = EPAPER_REFRESH_MODE_PARTIAL;
    else
    {
        cli_printf("Invalid mode. Use full, partial, or status.\r\n");
        return -1;
    }
    cli_printf("EPD refresh mode set to %s; applies to next frame update.\r\n",
               s_refresh_mode == EPAPER_REFRESH_MODE_PARTIAL ? "partial" : "full");
    return 0;
}
CLI_CMD_REGISTER("epd_refresh", "Select/status e-paper refresh mode (full|partial|status)", cmd_epd_refresh);

static bool epaper_display_buffer(const uint8_t *image)
{
    uint32_t i;

    APP_LOG_INFO("EPD loading full frame (%d bytes)", EPAPER_IMAGE_BYTES);
    app_log_flush();
    if (!epaper_controller_init()) return false;
    epaper_write_command(0x24U);
    for (i = 0U; i < EPAPER_IMAGE_BYTES; ++i)
    {
        /* SAM | 2026-10-09 15:15 +08:00 | Service safety checks during frame TX. */
        if ((i & 63U) == 0U) {
            app_aon_wdt_refresh();
            yp001_charger_poll();
        yp001_business_service();
        }
        epaper_write_data(image[i]);
    }

    epaper_write_command(0x26U);
    for (i = 0U; i < EPAPER_IMAGE_BYTES; ++i)
    {
        /* SAM | 2026-10-09 15:15 +08:00 | Service safety checks during frame TX. */
        if ((i & 63U) == 0U) {
            app_aon_wdt_refresh();
            yp001_charger_poll();
        yp001_business_service();
        }
        epaper_write_data(image[i]);
    }

    epaper_write_command(0x22U);
    epaper_write_data(0xF7U);
    epaper_write_command(0x20U);
    /* Sample BUSY immediately: flushing UART here can delay edge detection. */
    if (!epaper_wait_refresh_complete()) return false;

    epaper_write_command(0x10U);
    epaper_write_data(0x01U);
    delay_ms(100U);
    APP_LOG_INFO("EPD refresh complete");
    return true;
}

bool epaper_depg0150_init(void)
{
    uint16_t status;
    uint8_t *psram_frames;

    if (s_previous_frame == NULL) {
        psram_frames = (uint8_t *)yp_psram_alloc(EPAPER_IMAGE_BYTES * 2U);
        if (psram_frames != NULL) {
            s_previous_frame = psram_frames;
            s_effective_frame = psram_frames + EPAPER_IMAGE_BYTES;
        } else {
            APP_LOG_ERROR("EPD frames PSRAM alloc failed, display disabled");
        }
    }

    APP_LOG_INFO("EPD GPIO init: BUSY=GPIO24 RES=GPIO25 DATA=GPIO30 CLK=GPIO31 RS=GPIO32 CS=GPIO33");
    status = epaper_gpio_init(YP001_LCD_BUSY_TYPE, EPAPER_BUSY_PIN, APP_IO_MODE_INPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD BUSY GPIO init failed: 0x%04X", status);
        return false;
    }

    status = epaper_gpio_init(YP001_LCD_RESET_TYPE, EPAPER_RES_PIN, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD RES GPIO init failed: 0x%04X", status);
        return false;
    }

    status = epaper_gpio_init(YP001_LCD_DATA_TYPE, EPAPER_SDA_PIN, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS) return false;
    status = epaper_gpio_init(YP001_LCD_CLK_TYPE, EPAPER_SCL_PIN, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS) return false;
    status = epaper_gpio_init(YP001_LCD_RS_TYPE, EPAPER_DC_PIN, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS) return false;
    status = epaper_gpio_init(YP001_LCD_CS_TYPE, EPAPER_CS_PIN, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD control GPIO init failed: 0x%04X", status);
        return false;
    }

    epaper_write_pin(YP001_LCD_RESET_TYPE, EPAPER_RES_PIN, APP_IO_PIN_SET);
    epaper_write_pin(YP001_LCD_DATA_TYPE, EPAPER_SDA_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(YP001_LCD_CLK_TYPE, EPAPER_SCL_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(YP001_LCD_RS_TYPE, EPAPER_DC_PIN, APP_IO_PIN_SET);
    epaper_write_pin(YP001_LCD_CS_TYPE, EPAPER_CS_PIN, APP_IO_PIN_SET);
    APP_LOG_INFO("EPD GPIO init complete; BUSY=%d",
                 app_io_read_pin(YP001_LCD_BUSY_TYPE, EPAPER_BUSY_PIN));
    return true;
}

/* SAM | 2026-10-20 12:50 +08:00 | Keep the existing startup API name while
 * routing the YP_01 boot logo through the common refresh selector.
 */
bool epaper_depg0150_display_demo_image(void)
{
    bool success;
	uint8_t *logo_fb;
	logo_fb = get_rotated_fb(epaper_depg0150_logo_yp01,90);
    //success = epaper_display_selected_frame(epaper_depg0150_logo_yp01);
     success = epaper_display_selected_frame(logo_fb);
    if (!success)
    {
        APP_LOG_ERROR("EPD boot logo display failed");
    }
    else
    {
        /* SAM | 2026-10-20 12:47 +08:00 | Force a full home refresh after the
         * new startup logo so no pixels from the prior panel frame remain. */
        s_previous_frame_valid = false;
    }
    return success;
}

bool epaper_depg0150_display_home(const epaper_home_status_t *status)
{
    if (status == NULL || s_effective_frame == NULL) return false;
    epaper_home_render(s_effective_frame, status);
    return epaper_display_selected_frame(s_effective_frame);
}

bool epaper_depg0150_display_frame(const uint8_t frame[EPAPER_HOME_FRAME_BYTES])
{
    if (frame == NULL || s_effective_frame == NULL) return false;
    memcpy(s_effective_frame, frame, EPAPER_IMAGE_BYTES);
    return epaper_display_selected_frame(s_effective_frame);
}

/* SAM | 2026-10-09 17:51 +08:00 | Queue exactly the next successful frame
 * for full refresh without changing the user's partial/full mode choice. */
void epaper_depg0150_force_full_next(void)
{
    s_force_full_next = true;
}
