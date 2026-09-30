/**
 *****************************************************************************************
 *
 * @file main.c
 *
 * @brief main function Implementation.
 *
 *****************************************************************************************
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

/*
 * INCLUDE FILES
 *****************************************************************************************
 */
#include "user_app.h"
#include "user_periph_setup.h"
#include "transport_scheduler.h"
#include "gr_includes.h"
#include "scatter_common.h"
#include "flash_scatter_config.h"
#include "patch.h"
#include "app_log.h"
#include "app_io.h"
#include "app_i2c.h"
#include "app_gpiote.h"
#include "board_SK.h"

/*
 * LOCAL VARIABLE DEFINITIONS
 *****************************************************************************************
 */
/**@brief Stack global variables for Bluetooth protocol stack. */

volatile uint16_t timer_5s_counter = 0;
volatile uint8_t flag_5s = 0;
volatile uint8_t flag_1s = 0;
extern volatile uint8_t sos_press;
extern volatile uint8_t flag_1s_uart4;
extern void charge_ic_read_status(void);
extern void charge_ic_set_voltage(uint16_t voltage_mv);
extern void charge_ic_set_current(uint16_t current_ma);
extern void charge_ic_apply_settings(void);
extern void uart4_send_data(uint8_t *p_data, uint16_t length);
#define FLAG_5S (flag_5s == 1U ? ((flag_5s = 0), 1U) : 0U)
#define FLAG_1S (flag_1s == 1U ? ((flag_1s = 0), 1U) : 0U)

#define TK_USE_QP 1
#ifdef TK_USE_QP
#include "qpc.h"                 // QP/C real-time embedded framework
#include "blinky.h"              // Blinky Application interface
#include "bsp.h"                 // Board Support Package

//............................................................................
int main() {
    debug_uart_boot_init(); // Direct UART banner before QP and other peripherals.
    QF_init();       // initialize the framework and the underlying RT kernel
    BSP_init();      // initialize the BSP
    BSP_start();     // start the AOs/Threads
    return QF_run(); // run the QF application
}
#else
STACK_HEAP_INIT(heaps_table);

void LedBlinkJkb_Headl(){
        static uint8_t color_state = 0x01;

        Led_Jkb((color_state & 0x04) ? 1 : 0,
            (color_state & 0x02) ? 1 : 0,
            (color_state & 0x01) ? 1 : 0);

        color_state = (color_state + 1) % 8;
}
// 按键回调 —— 将 SDK 按键事件转换为 QP 事件发布
static void MyKey_Callback(uint8_t key_id, app_key_click_type_t click_type)
{
    switch (key_id) {
        case 0:  // UP 键 (SW1) → SOP键: 单击=PAUSE, 长按=SERVE
            if (click_type == APP_KEY_SINGLE_CLICK) {
                 cli_printf("0:APP_KEY_SINGLE_CLICK");
            } else if (click_type == APP_KEY_LONG_CLICK) {
                 cli_printf("0:APP_KEY_LONG_CLICK");
            }
            LedBlinkJkb_Headl();
            break;

        case 1:  // OK 键 (SW2) → 单击=SERVE
            LedBlinkJkb_Headl();
            if (click_type == APP_KEY_SINGLE_CLICK) {
                  cli_printf("1:APP_KEY_SINGLE_CLICK");
            }
            break;

        default:
            break;
    }
}



int main(void)
{
    app_periph_init(); // 硬件 + CLI 初始化
    gpio_init();
    charge_ic_init();
    ble_stack_init(ble_evt_handler, &heaps_table);
    SysTick_Config(SystemCoreClock / 1000U);
    cli_execute_string("help");
    LedBlinkJkb_Headl();
    Pwr_Jkb(1,1,1);
    APP_KEY_INIT_Jkb(board_keys, MyKey_Callback,
        KEY_CFG_Jkb(APP_IO_TYPE_AON, APP_IO_PIN_1, APP_IO_MODE_IT_FALLING, APP_IO_PULLUP, 0),
    );
    while (1)
    {
        app_log_flush();
        transport_schedule();
        pwr_mgmt_schedule();
    }
}

void SysTick_Handler(void)
{
    static uint16_t tick_cnt = 0;
    static uint16_t tick_1s_cnt = 0;
    tick_cnt++;
    tick_1s_cnt++;
    if (tick_cnt >= 5000) // 5秒 = 5000次中断 @ 1000Hz
    {
        tick_cnt = 0;
        flag_5s = 1;
    }
    if (tick_1s_cnt >= 1000) // 1秒 = 1000次中断 @ 1000Hz
    {
        tick_1s_cnt = 0;
        flag_1s = 1;
        flag_1s_uart4 = 1;
    }
}

/**
 * @brief 命令行函数：初始化 BLE 协议栈
 * @param argc 参数个数
 * @param argv 参数列表
 * @return 0 成功，负值表示错误
 */
static int cmd_ble_init(int argc, char *argv[])
{
    int ret = ble_stack_init(ble_evt_handler, &heaps_table);
    if (ret == 0)
    {
        cli_printf("BLE stack initialized successfully\r\n");
    }
    else
    {
        cli_printf("BLE stack initialization failed, error: %d\r\n", ret);
    }
    return ret;
}

/* 注册命令：命令名 "ble_init"，描述 "Initialize BLE stack"，执行函数 cmd_ble_init */
CLI_CMD_REGISTER("ble_init", "Initialize BLE stack", cmd_ble_init);
#endif
