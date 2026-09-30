/**
 *****************************************************************************************
 *
 * @file user_periph_setup.c
 *
 * @brief  User Periph Init Function Implementation.
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
#include "user_periph_setup.h"
#include "transport_scheduler.h"
#include "gr_includes.h"
#include "hal_flash.h"
#include "grx_hal.h"
#include "board_SK.h"
#include "app_uart.h"
#include "app_uart_dma.h"
#include "app_log.h"
#include "app_assert.h"
#include "../user/cli.h"
#include "../user/slre.h"
#include "string.h"
#include "stdio.h"


/* 日志输出全局开关，默认开启 */
bool g_log_output_enabled = true;
/*
 * DEFINES
 *****************************************************************************************
 */
#define UART_TX_BUFFER_SIZE      0x2000
#define UART_RX_BUFFER_SIZE      244


/*
 * LOCAL VARIABLE DEFINITIONS
 *****************************************************************************************
 */
static const uint8_t s_bd_addr[SYS_BD_ADDR_LEN] = {0x06, 0x01, 0xcf, 0x3e, 0xcb, 0xea};
static app_uart_tx_buf_t s_uart_buffer;
static app_uart_params_t s_uart_param;

static uint8_t s_uart_tx_buffer[UART_TX_BUFFER_SIZE];
static uint8_t s_uart_rx_buffer[UART_RX_BUFFER_SIZE];

/* UART4 (外部设备) */
static app_uart_tx_buf_t s_uart4_buffer;
static app_uart_params_t s_uart4_param;
#define UART4_BUFFER_SIZE 512
static uint8_t s_uart4_tx_buffer[UART4_BUFFER_SIZE];
static uint8_t s_uart4_rx_buffer[UART4_BUFFER_SIZE];

/*
 * LOCAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */
/* Debugger-visible results for bring-up when the wire has no output. */
volatile uint16_t g_debug_uart_init_status = 0xFFFFU;
volatile uint16_t g_debug_uart_tx_status = 0xFFFFU;
static bool s_debug_uart_ready;

static void uart_init(void)
{
    s_uart_buffer.tx_buf       = s_uart_tx_buffer;
    s_uart_buffer.tx_buf_size  = UART_TX_BUFFER_SIZE;

    s_uart_param.id                   = APP_UART_ID;
    s_uart_param.init.baud_rate       = APP_UART_BAUDRATE;
    s_uart_param.init.data_bits       = UART_DATABITS_8;
    s_uart_param.init.stop_bits       = UART_STOPBITS_1;
    s_uart_param.init.parity          = UART_PARITY_NONE;
    s_uart_param.init.hw_flow_ctrl    = UART_HWCONTROL_NONE;
    s_uart_param.init.rx_timeout_mode = UART_RECEIVER_TIMEOUT_ENABLE;
    s_uart_param.pin_cfg.rx.type      = APP_UART_RX_IO_TYPE;
    s_uart_param.pin_cfg.rx.pin       = APP_UART_RX_PIN;
    s_uart_param.pin_cfg.rx.mux       = APP_UART_RX_PINMUX;
    s_uart_param.pin_cfg.rx.pull      = APP_UART_RX_PULL;
    s_uart_param.pin_cfg.tx.type      = APP_UART_TX_IO_TYPE;
    s_uart_param.pin_cfg.tx.pin       = APP_UART_TX_PIN;
    s_uart_param.pin_cfg.tx.mux       = APP_UART_TX_PINMUX;
    s_uart_param.pin_cfg.tx.pull      = APP_UART_TX_PULL;
    s_uart_param.dma_cfg.tx_dma_instance = DMA0;
    s_uart_param.dma_cfg.rx_dma_instance = DMA0;
    s_uart_param.dma_cfg.tx_dma_channel = DMA_Channel0;
    s_uart_param.dma_cfg.rx_dma_channel = DMA_Channel1;

    g_debug_uart_init_status = app_uart_init(&s_uart_param, app_uart_evt_handler, &s_uart_buffer);
    s_debug_uart_ready = (g_debug_uart_init_status == APP_DRV_SUCCESS);
    if (s_debug_uart_ready)
    {
        uint8_t banner[] = "\r\n=== GR5526 LCD BOOT / J5 UART3 CDC ===\r\n";
        g_debug_uart_tx_status = app_uart_transmit_sync(APP_UART_ID, banner, sizeof(banner) - 1U, 1000U);
    }
}

static void uart4_evt_handler(app_uart_evt_t *p_evt);

void debug_uart_boot_init(void)
{
    uart_init();
}

/*与cat1通信*/
int parse_uart_command(const char *cmd, char *tag, size_t tag_sz,
                       char *content, size_t cont_sz) {
    struct slre_cap caps[2];   // 两个捕获组：标签、内容
    int len = slre_match("^\\[([A-Z]+)\\]\\s*(.*)$", cmd, strlen(cmd), caps, 2);
    if (len <= 0) return 0;    // 匹配失败

    // 提取标签（捕获组 0）
    size_t tag_len = caps[0].len;
    if (tag_len >= tag_sz) tag_len = tag_sz - 1;
    memcpy(tag, caps[0].ptr, tag_len);
    tag[tag_len] = '\0';

    // 提取内容（捕获组 1）
    size_t cont_len = caps[1].len;
    if (cont_len >= cont_sz) cont_len = cont_sz - 1;
    memcpy(content, caps[1].ptr, cont_len);
    content[cont_len] = '\0';

    return 1;
}
static void uart4_init(void)
{
    s_uart4_buffer.tx_buf       = s_uart4_tx_buffer;
    s_uart4_buffer.tx_buf_size  = UART4_BUFFER_SIZE;
    s_uart4_param.id                   = APP_UART4_ID;
    s_uart4_param.init.baud_rate       = APP_UART4_BAUDRATE;
    s_uart4_param.init.data_bits       = UART_DATABITS_8;
    s_uart4_param.init.stop_bits       = UART_STOPBITS_1;
    s_uart4_param.init.parity          = UART_PARITY_NONE;
    s_uart4_param.init.hw_flow_ctrl    = UART_HWCONTROL_NONE;
    s_uart4_param.init.rx_timeout_mode = UART_RECEIVER_TIMEOUT_ENABLE;
    s_uart4_param.pin_cfg.rx.type      = APP_UART4_RX_IO_TYPE;
    s_uart4_param.pin_cfg.rx.pin       = APP_UART4_RX_PIN;
    s_uart4_param.pin_cfg.rx.mux       = APP_UART4_RX_PINMUX;
    s_uart4_param.pin_cfg.rx.pull      = APP_UART4_RX_PULL;
    s_uart4_param.pin_cfg.tx.type      = APP_UART4_TX_IO_TYPE;
    s_uart4_param.pin_cfg.tx.pin       = APP_UART4_TX_PIN;
    s_uart4_param.pin_cfg.tx.mux       = APP_UART4_TX_PINMUX;
    s_uart4_param.pin_cfg.tx.pull      = APP_UART4_TX_PULL;

    app_uart_init(&s_uart4_param, uart4_evt_handler, &s_uart4_buffer);
    app_uart_receive_async(APP_UART4_ID, s_uart4_rx_buffer, UART4_BUFFER_SIZE);
    printf("UART4 initialized\r\n");
}

static void uart4_evt_handler(app_uart_evt_t *p_evt) {
    if (APP_UART_EVT_RX_DATA == p_evt->type) {
        // 确保字符串以 '\0' 结尾
        s_uart4_rx_buffer[p_evt->data.size] = '\0';

        // 可选：去除末尾的换行符（\r, \n）
        size_t len = strlen((const char *)s_uart4_rx_buffer);
        while (len > 0 && (s_uart4_rx_buffer[len-1] == '\r' ||
                           s_uart4_rx_buffer[len-1] == '\n')) {
            s_uart4_rx_buffer[--len] = '\0';
        }

        // 解析命令
        char tag[32];
        char content[512];
        if (parse_uart_command((const char *)s_uart4_rx_buffer, tag, sizeof(tag),
                               content, sizeof(content))) {
            printf("parse ok: tag=[%s], content=[%s]\r\n", tag, content);

            // 根据 tag 执行不同操作
            if (strcmp(tag, "NTPSYNC") == 0) {
                // content 形如 "OK 1781004532"
                // 可进一步用 sscanf 解析数值
                char status[16];
                unsigned int timestamp;
                if (sscanf(content, "%s %u", status, &timestamp) == 2) {
                    if (strcmp(status, "OK") == 0) {
                        printf("NTP: %u\r\n", timestamp);
                    }
                }
            }
        } else {
            printf("---: %s\r\n", s_uart4_rx_buffer);
        }

        // 重新启动接收
        app_uart_receive_async(APP_UART4_ID, s_uart4_rx_buffer, UART4_BUFFER_SIZE);
    }
}

static void log_flush(void)
{
    app_uart_flush(APP_UART_ID);
}

static void app_log_assert_init(void)
{
    app_log_init_t log_init = {0};

    log_init.filter.level                 = APP_LOG_LVL_DEBUG;
    log_init.fmt_set[APP_LOG_LVL_ERROR]   = APP_LOG_FMT_ALL & (~APP_LOG_FMT_TAG);
    log_init.fmt_set[APP_LOG_LVL_WARNING] = APP_LOG_FMT_LVL;
    log_init.fmt_set[APP_LOG_LVL_INFO]    = APP_LOG_FMT_LVL;
    log_init.fmt_set[APP_LOG_LVL_DEBUG]   = APP_LOG_FMT_LVL;

    app_log_init(&log_init,uart_tx_data_send, log_flush);
    app_assert_init();
}

/*
 * GLOBAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */
void app_uart_evt_handler(app_uart_evt_t *p_evt)
{
    if (APP_UART_EVT_RX_DATA == p_evt->type)
    {
        /* J5 CDC is dedicated to debug/CLI during LCD bring-up. */

        /* CLI 处理：逐字符喂给 CLI 解析器 */
        for (uint16_t i = 0; i < p_evt->data.size; i++) {
            cli_process_char(s_uart_rx_buffer[i]);
        }

        /* 重新启动 DMA 接收 */
        app_uart_receive_async(APP_UART_ID, s_uart_rx_buffer, UART_RX_BUFFER_SIZE);
    }
}

void uart_tx_data_send(uint8_t *p_data, uint16_t length)
{
    if (g_log_output_enabled && s_debug_uart_ready) {
        g_debug_uart_tx_status = app_uart_transmit_sync(APP_UART_ID, p_data, length, 1000U);
    }
    /* 开关关闭时，数据被丢弃 */
}

/**
 * @brief 强制发送数据，不受日志开关影响（供 CLI 使用）
 */
void uart_tx_data_send_force(uint8_t *p_data, uint16_t length)
{
    if (s_debug_uart_ready)
    {
        g_debug_uart_tx_status = app_uart_transmit_sync(APP_UART_ID, p_data, length, 1000U);
    }
}

void uart4_send_data(uint8_t *p_data, uint16_t length)
{
    app_uart_transmit_async(APP_UART4_ID, p_data, length);
}

#include <stdint.h>
#include "app_rtc.h"

// 判断闰年
static int is_leap_year(uint16_t year) {
    return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}

// 每月天数（平年）
static const uint8_t month_days[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};

/**
 * @brief 将 RTC 日历时间转换为 Unix 秒级时间戳（UTC）
 * @param rtc   指向 app_rtc_time_t 结构体的指针
 * @return Unix 时间戳（从 1970-01-01 00:00:00 UTC 开始的秒数）
 */
uint64_t rtc_time_to_unix(const app_rtc_time_t *rtc) {
    uint16_t year = 2000 + rtc->year;   // 实际年份
    uint8_t month = rtc->mon;           // 1~12
    uint8_t day   = rtc->date;          // 1~31，注意是 date 不是 day
    uint8_t hour  = rtc->hour;
    uint8_t min   = rtc->min;
    uint8_t sec   = rtc->sec;

    // 计算从 1970 年到 year-1 年的总天数
    uint32_t days = 0;
    for (uint16_t y = 1970; y < year; y++) {
        days += is_leap_year(y) ? 366 : 365;
    }

    // 加上当年已过月份的天数
    for (uint8_t m = 1; m < month; m++) {
        days += month_days[m - 1];
        if (m == 2 && is_leap_year(year)) {
            days += 1;   // 闰年二月多一天
        }
    }

    // 加上当月已过的天数
    days += (day - 1);

    // 转换为秒，并加上时分秒
    uint64_t timestamp = days * 86400ULL;
    timestamp += hour * 3600;
    timestamp += min * 60;
    timestamp += sec;

    return timestamp;
}
/**
 * @brief 将 Unix 秒级时间戳 (UTC) 转换为 RTC 日历时间 (UTC)
 * @param unix_sec  Unix 秒级时间戳（从 1970-01-01 00:00:00 UTC 开始）
 * @param rtc       输出：RTC 时间结构体（年份范围 2000~2099）
 */
void unix_to_rtc_time(uint64_t unix_sec, app_rtc_time_t *rtc) {
    const uint64_t SEC_2000 = 946684800;   // 2000-01-01 00:00:00 UTC
    uint64_t sec_since_2000 = unix_sec - SEC_2000;

    uint32_t days = sec_since_2000 / 86400;
    uint32_t secs = sec_since_2000 % 86400;

    // 计算年
    uint16_t year = 2000;
    while (days >= (is_leap_year(year) ? 366 : 365)) {
        days -= is_leap_year(year) ? 366 : 365;
        year++;
    }
    rtc->year = year - 2000;

    // 计算月
    uint8_t month;
    for (month = 1; month <= 12; month++) {
        uint8_t mdays = month_days[month - 1];
        if (month == 2 && is_leap_year(year)) mdays = 29;
        if (days < mdays) break;
        days -= mdays;
    }
    rtc->mon = month;

    // 计算日
    rtc->date = days + 1;

    // 时分秒毫秒
    rtc->hour = secs / 3600;
    rtc->min  = (secs % 3600) / 60;
    rtc->sec  = secs % 60;
    rtc->ms   = 0;

    // 星期几（可选）
    rtc->week = (days + 6) % 7;
}
/**
 * @brief 获取当前 Unix 秒级时间戳（UTC）
 * @return 当前 Unix 时间戳，读取失败返回 0
 */
uint64_t get_current_unix_timestamp(void) {
    app_rtc_time_t now;
    if (app_rtc_get_time(&now) != APP_DRV_SUCCESS) {
        return 0;
    }
    return rtc_time_to_unix(&now);
}


void app_periph_init(void)
{
    SYS_SET_BD_ADDR(s_bd_addr);
    if (!s_debug_uart_ready)
    {
        uart_init();
    }
    app_log_assert_init();
    APP_LOG_INFO("BOOT stage 1: UART init=0x%04X TX=0x%04X baud=%u", g_debug_uart_init_status, g_debug_uart_tx_status, APP_UART_BAUDRATE);
    pwr_mgmt_mode_set(PMR_MGMT_ACTIVE_MODE);
    APP_LOG_INFO("BOOT stage 2: power mode ready; RTC init");
    app_rtc_init(NULL);
    APP_LOG_INFO("BOOT stage 3: RTC returned; CLI init");
    cli_init();
    /* Enable RX only after CLI state exists. */
    if (s_debug_uart_ready)
    {
        uint16_t status = app_uart_receive_async(APP_UART_ID, s_uart_rx_buffer, UART_RX_BUFFER_SIZE);
        APP_LOG_INFO("BOOT stage 4: CLI ready; UART RX=0x%04X", status);
    }
}
