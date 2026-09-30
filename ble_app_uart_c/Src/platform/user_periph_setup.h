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

#define LED_R_IO_TYPE APP_IO_TYPE_MSIO
#define LED_R_IO_PIN APP_IO_PIN_2
#define LED_G_IO_TYPE APP_IO_TYPE_MSIO
#if (TK_Board_UART_DBG == 1)
#if defined(__GNUC__)
#pragma message "LED_G_IO_PIN APP_IO_PIN_4"
#endif
#define LED_G_IO_PIN APP_IO_PIN_4
#endif
#if ((TK_Board_1_1_UART_DBG == 1)||(TK_Board_PAD_UART_DBG == 1))
#define LED_G_IO_PIN APP_IO_PIN_0
#if defined(__GNUC__)
#pragma message "LED_G_IO_PIN APP_IO_PIN_0"
#endif
#endif
#define LED_B_IO_TYPE APP_IO_TYPE_MSIO
#define LED_B_IO_PIN APP_IO_PIN_3

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

#if (TK_Board_PAD_UART_DBG == 1)
#pragma message "LDO_PWR_PAD Board"
#define LDO2_IO_TYPE APP_IO_TYPE_GPIOA
#define LDO2_IO_PIN APP_IO_PIN_9
#define LDO3_IO_TYPE APP_IO_TYPE_GPIOA
#define LDO3_IO_PIN APP_IO_PIN_7
#define CAT1_IO_TYPE APP_IO_TYPE_GPIOA
#define CAT1_IO_PIN APP_IO_PIN_6
#else
#define LDO2_IO_TYPE APP_IO_TYPE_GPIOB
#define LDO2_IO_PIN APP_IO_PIN_0
#define LDO3_IO_TYPE APP_IO_TYPE_GPIOB
#define LDO3_IO_PIN APP_IO_PIN_1
#define CAT1_IO_TYPE APP_IO_TYPE_GPIOB
#define CAT1_IO_PIN APP_IO_PIN_2
#endif

#define Pwr_Jkb(ldo2_state, ldo3_state, cat1_state) \
  do                                                                                                                                              \
  {                                                                                                                                               \
     app_io_init(LDO2_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LDO2_IO_PIN, .mux = APP_IO_MUX}); \
     app_io_init(LDO3_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = LDO3_IO_PIN, .mux = APP_IO_MUX}); \
     app_io_init(CAT1_IO_TYPE, &(app_io_init_t){.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_OUTPUT, .pin = CAT1_IO_PIN, .mux = APP_IO_MUX}); \
     app_io_write_pin(LDO2_IO_TYPE, LDO2_IO_PIN, (ldo2_state) ? APP_IO_PIN_SET : APP_IO_PIN_RESET); \
     app_io_write_pin(LDO3_IO_TYPE, LDO3_IO_PIN, (ldo3_state) ? APP_IO_PIN_SET : APP_IO_PIN_RESET); \
     app_io_write_pin(CAT1_IO_TYPE, CAT1_IO_PIN, (cat1_state) ? APP_IO_PIN_SET : APP_IO_PIN_RESET); \
  } while(0)
// ==================== 通用宏（支持变长） ====================
// 单个按键配置辅助宏
#define KEY_CFG_Jkb(type, pin, mode, trigger_pull, id) \
    { .gpio_type = type, .gpio_pin = pin, .trigger_mode = mode, .pull = trigger_pull, .key_id = id }

// 按键配置
#define APP_KEY_INIT_Jkb(name, cb, ...) \
    static const app_key_gpio_t name##_gpios[] = {__VA_ARGS__}; \
    app_key_init((app_key_gpio_t*)name##_gpios, sizeof(name##_gpios)/sizeof(app_key_gpio_t), cb)


#endif
