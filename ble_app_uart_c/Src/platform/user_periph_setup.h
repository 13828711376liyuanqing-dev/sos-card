/**
 ****************************************************************************************
 *
 * @file user_periph_setup.h
 *
 * @brief Header file - User Periph Init
 *
 ****************************************************************************************
 * @attention
  #####Copyright (c) 2019 GOODIX
  All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:
  * Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
  * Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.
  * Neither the name of GOODIX nor the names of its contributors may be used
    to endorse or promote products derived from this software without
    specific prior written permission.

  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
  ARE DISCLAIMED. IN NO EVENT SHALL COPYRIGHT HOLDERS AND CONTRIBUTORS BE
  LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
  POSSIBILITY OF SUCH DAMAGE.
 *****************************************************************************************
 */


#ifndef _USER_PERIPH_SETUP_H__
#define _USER_PERIPH_SETUP_H__

/*
 * INCLUDE FILES
 *****************************************************************************************
 */
#include "grx_hal.h"
#include "../user/yp001_board_config.h"
#include <stdint.h>
#include "../user/cli.h"
#include "app_rtc.h"

/*
 * GLOBAL FUNCTION DECLARATION
 *****************************************************************************************
 */
/**
 *****************************************************************************************
 * @brief Init User Periph (GPIO SPI IIC ...)
 *****************************************************************************************
 */
void app_periph_init(void);
void debug_uart_boot_init(void);
void uart_tx_data_send_force(uint8_t *p_data, uint16_t length);
/* Drain debug UART input in thread context, never in the UART ISR. */
void debug_uart_cli_poll(void);
/* SAM | 2026-10-16 17:00 +08:00 | Release asynchronous RX ownership for the attended deep-sleep test. */
bool yp001_test_uart_pause(void);
bool yp001_test_uart_resume(void);
/* SAM | 2026-10-25 +08:00 | IRQ-safe monotonic tick observation for UART
 * recovery; no business state refresh or peripheral access. */
uint32_t yp001_uart_clock_ms(void);

/**
 *****************************************************************************************
 * @brief  Send data via uart.
 *
 * @param[in] p_data: Pointer to data need to be sent.
 * @param[in] length: Length to data need to be sent.
 *****************************************************************************************
 */
void uart_tx_data_send(uint8_t *p_data, uint16_t length);

/**
 *****************************************************************************************
 * @brief Write string data to uart transmit buffer.
 *****************************************************************************************
 */
void uart_data_push(char* format,...);

/**
 *****************************************************************************************
 * @brief user uart irq handler.
 *****************************************************************************************
 */
void user_uart_irq_handler(void);

/**
 *****************************************************************************************
 * @brief user DMS irq handler.
 *****************************************************************************************
 */
void user_dma_irq_handler(void);

/**
 *****************************************************************************************
 * @brief  Send data via UART4.
 *
 * @param[in] p_data: Pointer to data need to be sent.
 * @param[in] length: Length to data need to be sent.
 *****************************************************************************************
 */
void uart4_send_data(uint8_t *p_data, uint16_t length);

uint64_t get_current_unix_timestamp(void);
uint64_t rtc_time_to_unix(const app_rtc_time_t *rtc);
void unix_to_rtc_time(uint64_t unix_sec, app_rtc_time_t *rtc);

void gpio_init(void);
uint8_t charge_ic_init(void);

#define LED_R_IO_TYPE YP001_LED_RED_TYPE
#define LED_R_IO_PIN YP001_LED_RED_PIN
#define LED_G_IO_TYPE YP001_LED_GREEN_TYPE
#define LED_G_IO_PIN YP001_LED_GREEN_PIN
#define LED_B_IO_TYPE YP001_LED_BLUE_TYPE
#define LED_B_IO_PIN YP001_LED_BLUE_PIN

#define Led_Jkb(R, G, B)                                                                                                                            \
  do                                                                                                                                            \
  {                                                                                                                                             \
    app_io_init(LED_R_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LED_R_IO_PIN, .mux = APP_IO_MUX}); \
    app_io_init(LED_G_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LED_G_IO_PIN, .mux = APP_IO_MUX}); \
    app_io_init(LED_B_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LED_B_IO_PIN, .mux = APP_IO_MUX}); \
    app_io_write_pin(LED_R_IO_TYPE, LED_R_IO_PIN, !((R) ? APP_IO_PIN_SET : APP_IO_PIN_RESET));                                                  \
    app_io_write_pin(LED_G_IO_TYPE, LED_G_IO_PIN, !((G) ? APP_IO_PIN_SET : APP_IO_PIN_RESET));                                                  \
    app_io_write_pin(LED_B_IO_TYPE, LED_B_IO_PIN, !((B) ? APP_IO_PIN_SET : APP_IO_PIN_RESET));                                                  \
  } while (0)

#define LDO2_IO_TYPE YP001_SENSOR_POWER_TYPE
#define LDO2_IO_PIN YP001_SENSOR_POWER_PIN
#define LDO3_IO_TYPE YP001_LCD_POWER_TYPE
#define LDO3_IO_PIN YP001_LCD_POWER_PIN
#define CAT1_IO_TYPE YP001_CAT1_POWER_TYPE
#define CAT1_IO_PIN YP001_CAT1_POWER_PIN

/* SAM | 2026-10-12 19:23 +08:00 | Preserve CAT1 install power because normal sleep uses this macro. */
#include "ota/yp001_ota.h"
#define Pwr_Jkb(sensor_power_state, lcd_power_state, cat1_power_state) \
  do                                                                                                                                              \
  {                                                                                                                                               \
     app_io_init(LDO2_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LDO2_IO_PIN, .mux = YP001_GPIO_GPIO_MUX}); \
     app_io_init(LDO3_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LDO3_IO_PIN, .mux = YP001_GPIO_GPIO_MUX}); \
     if (!yp001_cat1_factory_hold_active() && yp001_ota_power_change_allowed()) app_io_init(CAT1_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = CAT1_IO_PIN, .mux = YP001_GPIO_GPIO_MUX}); \
     app_io_write_pin(LDO2_IO_TYPE, LDO2_IO_PIN, (sensor_power_state) ? APP_IO_PIN_SET : APP_IO_PIN_RESET); \
     app_io_write_pin(LDO3_IO_TYPE, LDO3_IO_PIN, (lcd_power_state) ? APP_IO_PIN_SET : APP_IO_PIN_RESET); \
     if (!yp001_cat1_factory_hold_active() && yp001_ota_power_change_allowed()) app_io_write_pin(CAT1_IO_TYPE, CAT1_IO_PIN, (cat1_power_state) ? YP001_CAT1_POWER_ON : YP001_CAT1_POWER_OFF); \
  } while(0)
// ==================== 通用宏（支持变长） ====================
// 单个按键配置辅助宏
#define KEY_CFG_Jkb(type, pin, mode, trigger_pull, id) \
    { .gpio_type = type, .gpio_pin = pin, .trigger_mode = mode, .pull = trigger_pull, .key_id = id }

// 按键配置
#define APP_KEY_INIT_Jkb(name, cb, ...) \
    static const app_key_gpio_t name##_gpios[] = {__VA_ARGS__}; \
    app_key_init((app_key_gpio_t*)name##_gpios, sizeof(name##_gpios)/sizeof(app_key_gpio_t), cb)


/* SAM | 2026-10-10 18:06 +08:00 | Manual power control is independent of USB flashing and UART. */
/* SAM | 2026-11-06 +08:00 | Independent RAM-only factory hold must guard every CAT1 power-cut owner. */
bool yp001_cat1_factory_hold_active(void);
int cat1_debug_power(int argc, char *argv[]);
/* SAM | 2026-10-28 19:00 +08:00 | Bench-only foreground service: start a silent CAT1 once per boot while a GR OTA owner is active. */
void yp001_cat1_ota_autostart_poll(uint32_t now_ms);

/* SAM | 2026-10-13 08:36 +08:00 | Foreground service during panel BUSY because emergency work cannot wait for pixels. */
void yp001_business_uart_poll(void);
/* SAM | 2026-10-25 +08:00 | Observe real safety inputs without pumping UART or rendering. */
void yp001_safety_observation_poll(void);
void yp001_business_service(void);
#endif
