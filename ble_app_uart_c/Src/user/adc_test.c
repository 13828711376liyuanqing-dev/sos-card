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
#include <stdio.h>
#include <string.h>
#include "app_log.h"
#include "app_adc.h"
#include "app_adc_dma.h"
#include "app_io.h"
#include "board_SK.h"

/*
 * DEFINES
 *****************************************************************************************
 */
// Note: Note: TEST_CONV_LENGTH must be aligned on a four-byte boundary.
#define TEST_CONV_LENGTH      (1)
volatile uint16_t covn_done = 0;
uint16_t conversion[TEST_CONV_LENGTH];
double   voltage[TEST_CONV_LENGTH];
app_adc_params_t adc_params = {
    .pin_cfg = {
        .channel_p = {
            .type = APP_IO_TYPE_MSIO,
            .mux  = APP_ADC_P_INPUT_PIN_MUX,
            .pin  = APP_ADC_P_INPUT_PIN,
        },
        .channel_n = {
            .type = APP_IO_TYPE_MSIO,
            .mux  = APP_ADC_N_INPUT_PIN_MUX,
            .pin  = APP_ADC_N_INPUT_PIN,
        },
    },
    .dma_cfg = {
        .dma_instance = DMA0,
        .dma_channel  = DMA_Channel0,
    },
    .init = {
        .channel_p  = APP_ADC_P_INPUT_SRC,
        .channel_n  = APP_ADC_N_INPUT_SRC,
        .input_mode = ADC_INPUT_SINGLE,
        .ref_source = ADC_REF_SRC_BUF_INT,
        .ref_value  = ADC_REF_VALUE_1P6,
        .clock      = ADC_CLK_1M,
    },
};

/*
 * GLOBAL FUNCTION DEFINITIONS
 ****************************************************************************************
 */
void app_adc_evt_handler(app_adc_evt_t * p_evt)
{
    if (p_evt->type == APP_ADC_EVT_CONV_CPLT)
    {
        covn_done = 1;
    }
}
#include "app_log.h"
#include "app_io.h"
#include "app_i2c.h"
#include "app_gpiote.h"
static uint8_t trigger_adc = 0;

// 分压电阻值：R1=100K（上拉电阻），R2=33K（下拉电阻）
#define R1_100K 100.0f
#define R2_33K  33.0f
// 分压系数 = R2 / (R1 + R2)
#define VOLTAGE_DIVIDER_RATIO (R2_33K / (R1_100K + R2_33K))
// 反向计算系数 = (R1 + R2) / R2
#define VBAT_CALC_FACTOR ((R1_100K + R2_33K) / R2_33K)

void adc_single(void)
{
    // 使用同步方式读取ADC，适合定时循环
    app_adc_dma_conversion_async(conversion, TEST_CONV_LENGTH);
    
    // 简单等待转换完成（不阻塞太久）
    for (volatile uint32_t i = 0; i < 100000; i++); // 短暂等待
    
    if (covn_done)
    {
        covn_done = 0;
        app_adc_voltage_intern(conversion, voltage, TEST_CONV_LENGTH);
        
        for(uint32_t i = 0; i < TEST_CONV_LENGTH; i++)
        {
            float adc_read = voltage[i];  // ADC读到的分压后电压
            float vbat = adc_read * VBAT_CALC_FACTOR;  // 计算实际输入电压
            
            // 打印两种电压值
            printf("ADC:%.3fV, VBAT:%.3fV  ", adc_read, vbat);
        }
    }
    else
    {
        printf("ADC转换中...  ");
    }
}

int adc_init(void)
{
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;
    app_io_pin_state_t pin_val;

    // LDO_EN2
    io_init.pull = APP_IO_NOPULL;
    io_init.mode = APP_IO_MODE_OUTPUT;
    io_init.pin = APP_IO_PIN_5;
    io_init.mux = APP_IO_MUX;
    app_io_init(APP_IO_TYPE_MSIO, &io_init);
    app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_5, APP_IO_PIN_SET);

    uint16_t ret = APP_DRV_SUCCESS;

    ret = app_adc_init(&adc_params, app_adc_evt_handler);
    if (ret != APP_DRV_SUCCESS)
    {
        printf("\r\nADC initial failed! Please check the input parameters.\r\n");
        return 1;
    }

    ret = app_adc_dma_init(&adc_params);
    if (ret != APP_DRV_SUCCESS)
    {
        printf("\r\nADC initial dma failed! Please check the input parameters.\r\n");
        return 1;
    }
    return 0;
}

