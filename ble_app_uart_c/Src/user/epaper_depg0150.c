#include "epaper_depg0150.h"

#include "app_io.h"
#include "app_log.h"
#include "gr55xx_delay.h"

#include <stdbool.h>

#include "epaper_depg0150_image.h"

#define EPAPER_GPIOA APP_IO_TYPE_GPIOA
#define EPAPER_GPIOB APP_IO_TYPE_GPIOB
#define EPAPER_GPIOC APP_IO_TYPE_GPIOC
#define EPAPER_AON   APP_IO_TYPE_AON
#define EPAPER_BUSY_PIN APP_IO_PIN_8  /* SoC GPIO8, J27-12 */
#define EPAPER_RES_PIN  APP_IO_PIN_2  /* AON_GPIO2, J27-18 */
#define EPAPER_SDA_PIN  APP_IO_PIN_14 /* SoC GPIO30 */
#define EPAPER_SCL_PIN  APP_IO_PIN_15 /* SoC GPIO31 */
#define EPAPER_DC_PIN   APP_IO_PIN_0  /* SoC GPIO32 */
#define EPAPER_CS_PIN   APP_IO_PIN_1  /* SoC GPIO33 */
#define EPAPER_GPIO_MUX APP_IO_MUX  /* SDK-selected GPIO mux for the target chip */
#define EPAPER_GPIOB_OUTPUT_PINS (EPAPER_SDA_PIN | EPAPER_SCL_PIN)
#define EPAPER_GPIOC_OUTPUT_PINS (EPAPER_DC_PIN | EPAPER_CS_PIN)

#define EPAPER_WIDTH_BYTES  25U
#define EPAPER_HEIGHT       200U
#define EPAPER_IMAGE_BYTES  (EPAPER_WIDTH_BYTES * EPAPER_HEIGHT)
#define EPAPER_REFRESH_BUSY_ASSERT_TIMEOUT_MS 500U

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
        epaper_write_pin(EPAPER_GPIOB, EPAPER_SDA_PIN,
                         (value & 0x80U) ? APP_IO_PIN_SET : APP_IO_PIN_RESET);
        epaper_write_pin(EPAPER_GPIOB, EPAPER_SCL_PIN, APP_IO_PIN_SET);
        delay_us(5U);
        epaper_write_pin(EPAPER_GPIOB, EPAPER_SCL_PIN, APP_IO_PIN_RESET);
        value <<= 1;
        delay_us(5U);
    }
}

static void epaper_write_command(uint8_t command)
{
    epaper_write_pin(EPAPER_GPIOC, EPAPER_CS_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(EPAPER_GPIOC, EPAPER_DC_PIN, APP_IO_PIN_RESET);
    delay_us(5U);
    epaper_spi_write_byte(command);
    delay_us(5U);
    epaper_write_pin(EPAPER_GPIOC, EPAPER_CS_PIN, APP_IO_PIN_SET);
}

static void epaper_write_data(uint8_t data)
{
    epaper_write_pin(EPAPER_GPIOC, EPAPER_CS_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(EPAPER_GPIOC, EPAPER_DC_PIN, APP_IO_PIN_SET);
    delay_us(5U);
    epaper_spi_write_byte(data);
    delay_us(5U);
    epaper_write_pin(EPAPER_GPIOC, EPAPER_CS_PIN, APP_IO_PIN_SET);
}

static bool epaper_wait_ready(const char *stage)
{
    uint32_t timeout_ms = 30000U;

    while ((app_io_read_pin(EPAPER_GPIOA, EPAPER_BUSY_PIN) == APP_IO_PIN_SET)
           && (timeout_ms > 0U))
    {
        delay_ms(1U);
        --timeout_ms;
    }
    delay_ms(1U);
    if (timeout_ms == 0U)
    {
        APP_LOG_ERROR("EPD BUSY timeout at %s, pin=%d", stage,
                      app_io_read_pin(EPAPER_GPIOA, EPAPER_BUSY_PIN));
        return false;
    }
    return true;
}

static bool epaper_wait_refresh_complete(void)
{
    uint32_t timeout_ms = EPAPER_REFRESH_BUSY_ASSERT_TIMEOUT_MS;

    while ((app_io_read_pin(EPAPER_GPIOA, EPAPER_BUSY_PIN) == APP_IO_PIN_RESET)
           && (timeout_ms > 0U))
    {
        delay_ms(1U);
        --timeout_ms;
    }
    if (app_io_read_pin(EPAPER_GPIOA, EPAPER_BUSY_PIN) == APP_IO_PIN_RESET)
    {
        APP_LOG_ERROR("EPD BUSY did not assert after refresh command");
        return false;
    }
    return epaper_wait_ready("after refresh");
}

static bool epaper_controller_init(void)
{
    /* VCI/VDDIO are supplied directly from 3P3V; this board has no EPD power-enable IO. */
    delay_ms(10U);
    epaper_write_pin(EPAPER_AON, EPAPER_RES_PIN, APP_IO_PIN_RESET);
    delay_ms(10U);
    epaper_write_pin(EPAPER_AON, EPAPER_RES_PIN, APP_IO_PIN_SET);
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

static bool epaper_display_buffer(const uint8_t *image)
{
    uint32_t i;

    APP_LOG_INFO("EPD loading demo image (%d bytes)", EPAPER_IMAGE_BYTES);
    if (!epaper_controller_init()) return false;
    epaper_write_command(0x24U);
    for (i = 0U; i < EPAPER_IMAGE_BYTES; ++i)
    {
        epaper_write_data(image[i]);
    }

    epaper_write_command(0x26U);
    for (i = 0U; i < EPAPER_IMAGE_BYTES; ++i)
    {
        epaper_write_data(image[i]);
    }

    epaper_write_command(0x22U);
    epaper_write_data(0xF7U);
    epaper_write_command(0x20U);
    APP_LOG_INFO("EPD refresh command sent; waiting for BUSY");
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

    APP_LOG_INFO("EPD GPIO init: BUSY=GPIO8 RES=AON_GPIO2 SDA=GPIO30 SCL=GPIO31 DC=GPIO32 CS=GPIO33");
    status = epaper_gpio_init(EPAPER_GPIOA, EPAPER_BUSY_PIN, APP_IO_MODE_INPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD BUSY GPIO init failed: 0x%04X", status);
        return false;
    }

    status = epaper_gpio_init(EPAPER_AON, EPAPER_RES_PIN, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD RES GPIO init failed: 0x%04X", status);
        return false;
    }

    status = epaper_gpio_init(EPAPER_GPIOB, EPAPER_GPIOB_OUTPUT_PINS, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD GPIOB output init failed: 0x%04X", status);
        return false;
    }

    status = epaper_gpio_init(EPAPER_GPIOC, EPAPER_GPIOC_OUTPUT_PINS, APP_IO_MODE_OUTPUT);
    if (status != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("EPD GPIOC output init failed: 0x%04X", status);
        return false;
    }

    epaper_write_pin(EPAPER_AON, EPAPER_RES_PIN, APP_IO_PIN_SET);
    epaper_write_pin(EPAPER_GPIOB, EPAPER_SDA_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(EPAPER_GPIOB, EPAPER_SCL_PIN, APP_IO_PIN_RESET);
    epaper_write_pin(EPAPER_GPIOC, EPAPER_DC_PIN, APP_IO_PIN_SET);
    epaper_write_pin(EPAPER_GPIOC, EPAPER_CS_PIN, APP_IO_PIN_SET);
    APP_LOG_INFO("EPD GPIO init complete; BUSY=%d",
                 app_io_read_pin(EPAPER_GPIOA, EPAPER_BUSY_PIN));
    return true;
}

bool epaper_depg0150_display_demo_image(void)
{
    bool success = epaper_display_buffer(epaper_depg0150_demo_image);
    if (!success)
    {
        APP_LOG_ERROR("EPD demo image display failed");
    }
    return success;
}
