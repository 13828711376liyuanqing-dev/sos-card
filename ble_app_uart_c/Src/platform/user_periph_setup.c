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
/* SAM | 2026-11-06 +08:00 | Mirror output into the bounded maintenance stream. */
#include "factory/yp001_factory_ble.h"
#include "charger/yp001_charger.h"
#include "transport_scheduler.h"
#include "gr_includes.h"
#include "hal_flash.h"
/* SAM | 2026-10-20 19:50 +08:00 | Use the SDK runtime NVDS-address declaration for read-only OTA geometry diagnostics. */
#include "gr_soc.h"
#include "grx_hal.h"
#include "board_SK.h"
#include "app_uart.h"
#include "app_uart_dma.h"
#include "app_log.h"
#include "app_assert.h"
#include "../user/cli.h"
#include "../user/slre.h"
#include "../user/AOs.h"
#include "string.h"
#include "stdio.h"
#if APP_LOG_STORE_ENABLE
#include "flash_scatter_config.h"
#endif


/* 日志输出全局开关，默认开启 */
bool g_log_output_enabled = true;
/*
 * DEFINES
 *****************************************************************************************
 */
#define UART_TX_BUFFER_SIZE      0x2000
#define UART_RX_BUFFER_SIZE      244

#if defined(YP001_BOARD)
#define YP001_DEBUG_UART_ID APP_UART_ID_0
#else
#define YP001_DEBUG_UART_ID APP_UART_ID
#endif


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
#define UART4_TX_BUFFER_SIZE 2048
static uint8_t s_uart4_tx_buffer[UART4_TX_BUFFER_SIZE];
static uint8_t s_uart4_rx_buffer[UART4_BUFFER_SIZE + 1U];

/*
 * LOCAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */
/* Debugger-visible results for bring-up when the wire has no output. */
volatile uint16_t g_debug_uart_init_status = 0xFFFFU;
volatile uint16_t g_debug_uart_tx_status = 0xFFFFU;
static bool s_debug_uart_ready;
/* SAM | 2026-10-10 16:58 +08:00 | Share RX failure state with foreground because UART callbacks run in IRQ context. */
static volatile bool s_uart4_ready;
/* SAM | 2026-10-19 17:00 +08:00 | Latch explicit bench isolation because foreground transport automatically recreates UART4 after deinit. */
static bool s_cat1_isolated;
/* SAM | 2026-10-10 16:52 +08:00 | Buffer complete CAT1 lines because 460800 RX
 * can split antenna records across interrupts; UART0 remains 115200. */
static uint32_t s_cat_uart_baud = YP001_CAT1_UART_BAUDRATE;
static uint8_t s_cat_diag_rx[4096];
static volatile uint16_t s_cat_diag_read, s_cat_diag_write;
static volatile uint32_t s_cat_diag_dropped;
static volatile bool s_cat_diag_overflow;
static volatile uint32_t s_cat_uart_error;
/* SAM | 2026-10-25 +08:00 | Keep original driver error separate from rearm
 * failure because the working error flag is overwritten and consumed. */
#define YP_UART_FAULT_BARRIER() __DMB()
#include "yp001_uart_fault.h"
/* SAM | 2026-10-25 +08:00 | DWT measures the whole foreground Flash transaction across PRIMASK; no SysTick-derived physical timing claim. */
volatile uint32_t g_ota_window_trace[12];
static uint32_t ota_demcr,ota_dwt_ctrl,ota_clock_hz;
void yp001_ota_measure_begin(uint32_t kind,uint32_t token)
{
    ota_demcr=CoreDebug->DEMCR;ota_dwt_ctrl=DWT->CTRL;
    hal_dwt_enable(ota_demcr,ota_dwt_ctrl);ota_clock_hz=SystemCoreClock;
    g_ota_window_trace[0]=1;g_ota_window_trace[1]=kind;g_ota_window_trace[2]=token;
    g_ota_window_trace[3]=DWT->CYCCNT;g_ota_window_trace[6]=ota_clock_hz;
}
void yp001_ota_measure_end(void)
{
    uint32_t end=DWT->CYCCNT,delta=end-g_ota_window_trace[3];
    g_ota_window_trace[4]=end;g_ota_window_trace[5]=delta;
    if(ota_clock_hz&&ota_clock_hz==SystemCoreClock){
        uint32_t us=(uint32_t)(((uint64_t)delta*1000000u)/ota_clock_hz);
        g_ota_window_trace[7]=us;if(us>g_ota_window_trace[8])g_ota_window_trace[8]=us;
        g_ota_window_trace[0]=2;
    }else g_ota_window_trace[0]=3;
    hal_dwt_disable(ota_demcr,ota_dwt_ctrl);
}
volatile yp_uart_fault g_cat_uart_first_fault;
static volatile uint32_t s_cat_uart_rx_bytes;
static uart_handle_t *s_cat_uart_diag_handle;
/* SAM | 2026-10-25 +08:00 | Defer error recovery until abort completion AND
 * app_uart_abort_receive return, because its flush flag is set after HAL returns.
 * phase: 0 normal, 1 requested, 2 waiting for abort, 3 failed until reset. */
volatile yp_uart_recovery g_cat_uart_recovery;
static void cat_uart_recovery_poll(void);
/* SAM | 2026-10-12 19:23 +08:00 | Dispatch bounded OTA controls in foreground because JSON must never run in IRQ. */
#include "ota/yp001_ota.h"
/* SAM | 2026-10-21 +08:00 | Use actual compiled version/provisioning declarations for the read-only version command. */
#include "custom_config.h"
#include "ota/yp001_ota_port.h"
#include "ota/yp001_cat1_autostart.h" /* SAM | 2026-10-28 19:00 +08:00 | Bench CAT1 restart decision during an active GR OTA. */
#include "ota/yp001_ota_recovery_control.h" /* SAM | 2026-10-27 +08:00 | Exact protected-recovery command grammar, no reset or quota bypass. */
/* SAM | 2026-10-24 +08:00 | Verify in normal CLI context; SWD halt can change WDT running state. */
#include "ota/yp001_ota_app_crypto.h"
#include "app_aon_wdt.h"
/* SAM | 2026-10-13 08:36 +08:00 | Single bounded foreground dispatcher for business and OTA. */
#include "business/yp001_business.h"
static uint8_t s_cat_line[YP001_OTA_FRAME_MAX];
static uint16_t s_cat_line_used;
static bool s_cat_line_discard;
#ifdef FEATURE_USE_CAT1_SVC
extern void Cat1Svr_uart_callback_1(app_uart_evt_t *  p_evt,uint8_t *buf,uint16_t len);
#endif

/* SAM | 2026-10-23 +08:00 | Demultiplex binary before text because NUL/newlines in OTA images are not business commands. */
#include "ota/yp001_ota_wire.h"
static yp001_ota_mux s_cat_mux;
volatile uint32_t g_ota_wire_received;
static void cat_wire_frame(const uint8_t *bytes, size_t length, void *context)
{
    (void)context;
    /* SAM | 2026-10-23 +08:00 | Dispatch real control frames so missing bindings produce a correlated NACK instead of a silent counter. */
    ++g_ota_wire_received;
    /* SAM | 2026-10-25 +08:00 | Queue Flash-capable frames behind the peer silence handshake. */
    yp001_ota_dispatch_wire(bytes,length);
}
static void cat_text_bytes(const uint8_t *bytes, size_t length, void *context)
{
    (void)context;
    while (length--) {
        uint8_t ch = *bytes++;
        if (ch == '\n') {
            /* SAM | 2026-10-31 15:08 +08:00 | CAT1 OTA power hold: "[OTA_HOLD] 1" keeps CAT1 powered until "[OTA_HOLD] 0". The line still continues to
             * the normal handlers below, so the colleague's low-power state machine also sees CAT1 activity. */
            if (s_cat_line_used >= 12U && !s_cat_line_discard && !memcmp(s_cat_line, "[OTA_HOLD] ", 11U) &&
                yp001_ota_cat1_hold(s_cat_line[11] == '1'))
                cli_printf("\r\n[OTA_HOLD] %s\r\n", s_cat_line[11] == '1' ? "on: CAT1 power kept until the OTA ends" : "off");
            if (s_cat_line_used && !s_cat_line_discard &&
                !yp001_ota_handle_line((const char *)s_cat_line, s_cat_line_used) &&
                !yp_business_handle_line((const char *)s_cat_line, s_cat_line_used)) {
                uart_tx_data_send_force((uint8_t *)"\r\n[CAT1 RX] ", 12U);
                uart_tx_data_send_force(s_cat_line, s_cat_line_used);
                uart_tx_data_send_force((uint8_t *)"\r\n", 2U);
#ifdef FEATURE_USE_CAT1_SVC
                Cat1Svr_uart_callback_1(NULL,s_cat_line,s_cat_line_used);
#endif
            }
            s_cat_line_used = 0U;
            s_cat_line_discard = false;
        } else if (ch != '\r' && !s_cat_line_discard) {
            if (ch == 0U || s_cat_line_used >= sizeof(s_cat_line)) {
                s_cat_line_used = 0U;
                s_cat_line_discard = true;
                cli_printf("\r\n[CAT1 ERROR] binary_or_long_line_discarded\r\n");
            } else {
                s_cat_line[s_cat_line_used++] = ch;
            }
        }
    }
}
static void cat_diag_poll(void)
{
    /* SAM | 2026-10-25 +08:00 | Common entry covers CLI and EPD RX before any frame can check permission. */
    yp001_safety_observation_poll();
    /* SAM | 2026-10-25 +08:00 | Recovery never parses quarantined bytes or
     * grants transport readiness; a new business handshake must do that. */
    cat_uart_recovery_poll();
    for (unsigned budget = 0; budget < 512U; ++budget) {
        uint32_t mask = __get_PRIMASK();
        __disable_irq();
        if (s_cat_diag_overflow || s_cat_uart_error) {
            uint32_t error = s_cat_uart_error;
            s_cat_diag_read = s_cat_diag_write;
            s_cat_diag_overflow = false;
            s_cat_uart_error = 0U;
            s_cat_line_used = 0U;
            s_cat_line_discard = false;
            yp001_ota_mux_lost(&s_cat_mux);
            __set_PRIMASK(mask);
            /* SAM | 2026-10-13 08:36 +08:00 | Lost bytes invalidate readiness, not alarm state. */
            /* SAM | 2026-10-25 +08:00 | Mark actual dropped/error RX separately from business heartbeat timeout. */
            yp_business_transport_lost_from(YP_PEER_UART_RX_LOST);
            cli_printf("\r\n[CAT1 ERROR] rx_lost dropped=%lu driver=0x%08lX\r\n",
                       (unsigned long)s_cat_diag_dropped, (unsigned long)error);
            return;
        }
        if (g_cat_uart_recovery.phase) {
            __set_PRIMASK(mask);
            return;
        }
        if (s_cat_diag_read == s_cat_diag_write) {
            __set_PRIMASK(mask);
            return;
        }
        uint8_t ch = s_cat_diag_rx[s_cat_diag_read];
        s_cat_diag_read = (s_cat_diag_read + 1U) % sizeof(s_cat_diag_rx);
        __set_PRIMASK(mask);
        yp001_ota_mux_feed(&s_cat_mux, ch, yp_business_status()->now_ms,
                           cat_text_bytes, cat_wire_frame, NULL);
    }
}
/* SAM | 2026-10-13 08:36 +08:00 | Expose only RX pumping for display waits; never recursively render UI. */
void yp001_business_uart_poll(void) { cat_diag_poll(); }
#define CLI_RX_RING_SIZE 2048U
static uint8_t s_cli_rx_ring[CLI_RX_RING_SIZE];
static volatile uint16_t s_cli_read, s_cli_write;
static volatile bool s_cli_overflow;

/* ISR produces bytes; foreground executes commands. */
void debug_uart_cli_poll(void)
{
    cat_diag_poll();
    for (unsigned budget = 0; budget < 244U; ++budget) {
        uint32_t mask = __get_PRIMASK();
        __disable_irq();
        if (s_cli_overflow) {
            s_cli_read = s_cli_write;
            s_cli_overflow = false;
            __set_PRIMASK(mask);
            cli_discard_input();
            return;
        }
        if (s_cli_read == s_cli_write) {
            __set_PRIMASK(mask);
            return;
        }
        uint8_t ch = s_cli_rx_ring[s_cli_read];
        s_cli_read = (s_cli_read + 1U) % CLI_RX_RING_SIZE;
        __set_PRIMASK(mask);
        cli_process_char(ch);
    }
}

#if YP001_CAT1_UART_HW_SUPPORTED
static void yp001_board_uart_init(app_uart_params_t *p_uart)
{
    p_uart->id = APP_UART_ID_4;
    p_uart->init.baud_rate = YP001_CAT1_UART_BAUDRATE;
    p_uart->init.data_bits = UART_DATABITS_8;
    p_uart->init.stop_bits = UART_STOPBITS_1;
    p_uart->init.parity = UART_PARITY_NONE;
    p_uart->init.hw_flow_ctrl = UART_HWCONTROL_NONE;
    p_uart->init.rx_timeout_mode = UART_RECEIVER_TIMEOUT_ENABLE;
    p_uart->pin_cfg.rx.type = YP001_CAT1_UART_TYPE;
    p_uart->pin_cfg.rx.pin = YP001_CAT1_UART_RX_PIN;
    p_uart->pin_cfg.rx.mux = YP001_CAT1_UART_MUX;
    p_uart->pin_cfg.rx.pull = APP_IO_PULLUP;
    p_uart->pin_cfg.tx.type = YP001_CAT1_UART_TYPE;
    p_uart->pin_cfg.tx.pin = YP001_CAT1_UART_TX_PIN;
    p_uart->pin_cfg.tx.mux = YP001_CAT1_UART_MUX;
    p_uart->pin_cfg.tx.pull = APP_IO_NOPULL;
}
#endif

static void yp001_debug_uart_init(app_uart_params_t *p_uart)
{
    p_uart->id = YP001_DEBUG_UART_ID;
    p_uart->init.baud_rate = YP001_DEBUG_UART_BAUDRATE;
    p_uart->init.data_bits = UART_DATABITS_8;
    p_uart->init.stop_bits = UART_STOPBITS_1;
    p_uart->init.parity = UART_PARITY_NONE;
    p_uart->init.hw_flow_ctrl = UART_HWCONTROL_NONE;
    p_uart->init.rx_timeout_mode = UART_RECEIVER_TIMEOUT_ENABLE;
    p_uart->pin_cfg.rx.type = YP001_DEBUG_UART_TYPE;
    p_uart->pin_cfg.rx.pin = YP001_DEBUG_UART_RX_PIN;
    p_uart->pin_cfg.rx.mux = YP001_DEBUG_UART_MUX;
    p_uart->pin_cfg.rx.pull = APP_IO_PULLUP;
    p_uart->pin_cfg.tx.type = YP001_DEBUG_UART_TYPE;
    p_uart->pin_cfg.tx.pin = YP001_DEBUG_UART_TX_PIN;
    p_uart->pin_cfg.tx.mux = YP001_DEBUG_UART_MUX;
    p_uart->pin_cfg.tx.pull = APP_IO_NOPULL;
}

static void uart_init(void)
{
    s_uart_buffer.tx_buf       = s_uart_tx_buffer;
    s_uart_buffer.tx_buf_size  = UART_TX_BUFFER_SIZE;

#if defined(YP001_BOARD)
    yp001_debug_uart_init(&s_uart_param);
#else
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
#endif

    g_debug_uart_init_status = app_uart_init(&s_uart_param, app_uart_evt_handler, &s_uart_buffer);
    s_debug_uart_ready = (g_debug_uart_init_status == APP_DRV_SUCCESS);
    if (s_debug_uart_ready)
    {
        uint8_t banner[] = "\r\n=== YP001 GR5526 BOOT / UART0 ===\r\n"
                           "UART0: TX=GPIO28 RX=GPIO29, 115200 8N1\r\n"
                           "Build: " __DATE__ " " __TIME__ "\r\n";
        g_debug_uart_tx_status = app_uart_transmit_sync(YP001_DEBUG_UART_ID, banner, sizeof(banner) - 1U, 1000U);
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
    if (!cmd || !tag || !content || !tag_sz || !cont_sz) return 0;
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
    /* SAM | 2026-10-25 +08:00 | Sending during recovery must not reinitialize
     * the driver, reset its TX ring or replace a pending abort operation. */
    if (g_cat_uart_recovery.phase) return;
    /* SAM | 2026-10-19 17:00 +08:00 | Block every local lazy-init path until successful explicit cat1_power on. */
    if (s_cat1_isolated) return;
#if !YP001_CAT1_UART_HW_SUPPORTED
    APP_LOG_ERROR("YP001 CAT1 UART disabled: board UART route not configured");
    return;
#else
    /* SAM | 2026-10-10 16:52 +08:00 | Refuse a second UART4 owner because
     * initializing diagnostics must not replace a running Cat1Svr callback. */
    uart_handle_t *owner = app_uart_get_handle(APP_UART_ID_4);
    if (owner != NULL && owner != &s_uart4_param.uart_dev.handle) {
        cli_printf("[CAT1 ERROR] UART4_owned_by_other_service\r\n");
        return;
    }
    s_uart4_buffer.tx_buf       = s_uart4_tx_buffer;
    s_uart4_buffer.tx_buf_size  = UART4_TX_BUFFER_SIZE;
#if defined(YP001_BOARD)
    yp001_board_uart_init(&s_uart4_param);
#else
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
#endif

    /* SAM | 2026-10-10 16:52 +08:00 | Select baud explicitly for LuatOS;
     * manual UART uses 460800 for the Air780EGH Lua application. */
    s_uart4_param.init.baud_rate = s_cat_uart_baud;
    s_uart4_ready = (app_uart_init(&s_uart4_param, uart4_evt_handler, &s_uart4_buffer) == APP_DRV_SUCCESS);
    if (!s_uart4_ready) return;
    /* SAM | 2026-10-25 +08:00 | Cache the public handle during init because
     * get_handle may invoke SDK wakeup hooks; diagnostics must not add IRQ wakeups. */
    s_cat_uart_diag_handle = app_uart_get_handle(APP_UART_ID_4);
    uint16_t ret = app_uart_receive_async(s_uart4_param.id, s_uart4_rx_buffer, UART4_BUFFER_SIZE);
    if (ret != APP_DRV_SUCCESS) {
        s_uart4_ready = false;
        cli_printf("[CAT1 ERROR] RX_init=0x%04X\r\n", ret);
        return;
    }
    cli_printf("[CAT1] UART4 initialized baud=%lu\r\n", (unsigned long)s_cat_uart_baud);
    cli_execute_string("cat1_power on");
    cli_execute_string("cat1_power key");
#endif
}

/* SAM | 2026-10-16 17:00 +08:00 | Abort idle RX before sleep because a pending receive keeps HAL peripheral state busy. */
/* SAM | 2026-10-19 11:30 +08:00 | Release UART4 pads before CAT1 rail-off because an idle-high TX can back-power the module. */
static bool s_sleep_uart4_restore;
bool yp001_test_uart_pause(void) {
    /* SAM | 2026-10-25 +08:00 | Keep the owned handle alive while recovery
     * is pending; sleep cannot deinitialize an outstanding abort. */
    if (g_cat_uart_recovery.phase) return false;
    bool ok = true;
    if (s_debug_uart_ready && app_uart_abort_receive(YP001_DEBUG_UART_ID) != APP_DRV_SUCCESS) ok = false;
    /* SAM | 2026-10-19 11:30 +08:00 | Refuse another UART4 owner rather than changing its mux behind an active service. */
    uart_handle_t *owner = app_uart_get_handle(APP_UART_ID_4);
    if (owner != NULL && owner != &s_uart4_param.uart_dev.handle) return false;
    s_sleep_uart4_restore = s_uart4_ready;
    if (s_uart4_ready) {
        if (app_uart_abort_receive(APP_UART_ID_4) != APP_DRV_SUCCESS) return false;
        if (app_uart_deinit(APP_UART_ID_4) != APP_DRV_SUCCESS) return false;
        s_uart4_ready = false;
    }
    app_io_init_t pads = {.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_INPUT,
        .pin = YP001_CAT1_UART_TX_PIN | YP001_CAT1_UART_RX_PIN, .mux = YP001_AON_GPIO_MUX};
    if (app_io_init(YP001_CAT1_UART_TYPE, &pads) != APP_DRV_SUCCESS) ok = false;
    return ok;
}
bool yp001_test_uart_resume(void) {
    bool ok = true;
    if (s_debug_uart_ready && app_uart_receive_async(YP001_DEBUG_UART_ID, s_uart_rx_buffer, UART_RX_BUFFER_SIZE) != APP_DRV_SUCCESS) ok = false;
    /* SAM | 2026-10-19 11:30 +08:00 | Recreate the prior UART4 owner on aborted/returning sleep; uart4_init also rearms RX. */
    if (s_sleep_uart4_restore) {
        if (!s_uart4_ready) uart4_init();
        else if (app_uart_receive_async(APP_UART_ID_4, s_uart4_rx_buffer, UART4_BUFFER_SIZE) != APP_DRV_SUCCESS) ok = false;
        if (!s_uart4_ready) ok = false;
    }
    s_sleep_uart4_restore = false;
    /* Discard incomplete CAT1 frames because bytes may be lost while RX is stopped. */
    s_cat_diag_read = s_cat_diag_write;
    s_cat_line_used = 0U;
    /* SAM | 2026-10-23 +08:00 | Reset binary and text together after sleep RX loss. */
    s_cat_line_discard = false;
    yp001_ota_mux_lost(&s_cat_mux);
    /* SAM | 2026-10-25 +08:00 | Sleep RX restoration invalidates partial frames; retain that diagnostic source. */
    yp_business_transport_lost_from(YP_PEER_SLEEP_RESTORE);
    return ok;
}

static void uart4_evt_handler(app_uart_evt_t *p_evt) {
    /* SAM | 2026-10-25 +08:00 | Completion may be synchronous inside abort;
     * only foreground after the wrapper returns is allowed to rearm. */
    if (p_evt->type == APP_UART_EVT_ABORT_RX) {
        if (g_cat_uart_recovery.phase == 2U) {
            /* SAM | 2026-10-25 +08:00 | Publish completion time before done;
             * the first subsequent foreground poll may be delayed by EPD/Flash. */
            g_cat_uart_recovery.abort_completed_ms = yp001_uart_clock_ms();
            __DMB();
            g_cat_uart_recovery.abort_done = 1U;
        }
        return;
    }
    if (p_evt->type != APP_UART_EVT_RX_DATA && p_evt->type != APP_UART_EVT_ERROR) return;
    /* SAM | 2026-10-25 +08:00 | Snapshot SDK public RX state before rearm;
     * this IRQ only reads business time and never sends/prints/writes Flash. */
    uart_handle_t *handle = s_cat_uart_diag_handle;
    uint32_t rx_before = handle ? (uint32_t)handle->rx_state : UINT32_MAX;
    /* SAM | 2026-10-25 +08:00 | Read the monotonic tick directly; business
     * observation time can be stale while foreground work is in progress. */
    uint32_t fault_time = yp001_uart_clock_ms();
    bool driver_event = p_evt->type == APP_UART_EVT_ERROR;
    if(driver_event&&!g_ota_window_trace[9]){
        g_ota_window_trace[10]=DWT->CYCCNT;g_ota_window_trace[11]=g_ota_window_trace[0];
        __DMB();g_ota_window_trace[9]=1;
    }
    uint32_t driver_error = driver_event ? p_evt->data.error_code : 0U;
    /* SAM | 2026-10-25 +08:00 | HAL can complete RX before its error callback.
     * Read its software error field before receive_async clears it; never read
     * the hardware line-status register here because that has side effects. */
    if (!driver_event && handle && handle->error_code) {
        driver_event = true;
        driver_error = handle->error_code;
    }
    if (g_cat_uart_recovery.phase) return;
    if (driver_event) {
        (void)yp_uart_fault_capture(&g_cat_uart_first_fault, true,
            driver_error, UINT32_MAX, fault_time, rx_before, rx_before,
            s_cat_diag_read, s_cat_diag_write, s_cat_diag_dropped, s_cat_uart_rx_bytes);
        s_cat_uart_error = driver_error ? driver_error : 1U;
        s_uart4_ready = false;
        g_cat_uart_recovery.abort_done = 0U;
        g_cat_uart_recovery.abort_result = UINT32_MAX;
        g_cat_uart_recovery.rearm_result = UINT32_MAX;
        g_cat_uart_recovery.started_ms = fault_time;
        __DMB();
        g_cat_uart_recovery.phase = 1U;
        return;
    }
    /* SAM | 2026-10-10 16:52 +08:00 | Expose lost bytes and restart RX after
     * driver errors because truncated telemetry must never look valid. */
    if (p_evt->type == APP_UART_EVT_RX_DATA) {
        s_cat_uart_rx_bytes += p_evt->data.size;
        for (uint16_t i = 0; i < p_evt->data.size && i < UART4_BUFFER_SIZE; ++i) {
            uint16_t next = (s_cat_diag_write + 1U) % sizeof(s_cat_diag_rx);
            if (s_cat_diag_overflow || next == s_cat_diag_read) {
                ++s_cat_diag_dropped;
                s_cat_diag_overflow = true;
                continue;
            }
            s_cat_diag_rx[s_cat_diag_write] = s_uart4_rx_buffer[i];
            __DMB();
            s_cat_diag_write = next;
        }
    } else if (p_evt->type == APP_UART_EVT_ERROR) {
        s_cat_uart_error = p_evt->data.error_code ? p_evt->data.error_code : 1U;
    } else {
        return;
    }
    uint16_t ret = app_uart_receive_async(APP_UART_ID_4, s_uart4_rx_buffer, UART4_BUFFER_SIZE);
    (void)yp_uart_fault_capture(&g_cat_uart_first_fault, driver_event,
        driver_error, ret, fault_time, rx_before,
        handle ? (uint32_t)handle->rx_state : UINT32_MAX,
        s_cat_diag_read, s_cat_diag_write, s_cat_diag_dropped, s_cat_uart_rx_bytes);
    if (ret != APP_DRV_SUCCESS) {
        s_cat_uart_error = 0x80000000UL | ret;
        s_uart4_ready = false;
        /* SAM | 2026-10-25 +08:00 | A failed normal completion rearm follows
         * the same bounded recovery instead of inviting lazy full init. */
        g_cat_uart_recovery.abort_done = 0U;
        g_cat_uart_recovery.abort_result = UINT32_MAX;
        g_cat_uart_recovery.rearm_result = UINT32_MAX;
        g_cat_uart_recovery.started_ms = fault_time;
        __DMB();
        g_cat_uart_recovery.phase = 1U;
    }
}

/* SAM | 2026-10-25 +08:00 | A single foreground owner handles FE/PE continuing
 * RX and OE aborted RX alike: abort, await completion, flush/rearm once.
 * Damaged data stays quarantined and a missing completion fails closed. */
static void cat_uart_recovery_poll(void) {
    uint32_t phase = g_cat_uart_recovery.phase;
    if (phase == 1U) {
        /* SAM | 2026-10-25 +08:00 | A queued fault is not an outstanding
         * abort. Start its deadline only when the foreground actually issues it. */
        g_cat_uart_recovery.abort_started_ms = yp001_uart_clock_ms();
        g_cat_uart_recovery.abort_completed_ms = 0U;
        g_cat_uart_recovery.phase = 2U;
        ++g_cat_uart_recovery.count;
        uint16_t ret = app_uart_abort_receive(APP_UART_ID_4);
        g_cat_uart_recovery.abort_result = ret;
        if (ret != APP_DRV_SUCCESS) g_cat_uart_recovery.phase = 3U;
        return;
    }
    if (phase != 2U) return;
    /* SAM | 2026-10-25 +08:00 | Serialize completion/deadline observation.
     * Timely completion stays valid even if foreground consumes it late;
     * genuinely late or missing completion still fails closed at 100ms. */
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    if (!g_cat_uart_recovery.abort_done) {
        if ((uint32_t)(yp001_uart_clock_ms() - g_cat_uart_recovery.abort_started_ms) > 100U)
            g_cat_uart_recovery.phase = 3U;
        __set_PRIMASK(mask);
        return;
    }
    if ((uint32_t)(g_cat_uart_recovery.abort_completed_ms - g_cat_uart_recovery.abort_started_ms) > 100U) {
        g_cat_uart_recovery.phase = 3U;
        __set_PRIMASK(mask);
        return;
    }
    /* No receive callback can run between rearm and publishing normal state. */
    uint16_t ret = app_uart_receive_async(APP_UART_ID_4, s_uart4_rx_buffer, UART4_BUFFER_SIZE);
    g_cat_uart_recovery.rearm_result = ret;
    g_cat_uart_recovery.completed_ms = yp001_uart_clock_ms();
    s_uart4_ready = ret == APP_DRV_SUCCESS;
    __DMB();
    g_cat_uart_recovery.phase = ret == APP_DRV_SUCCESS ? 0U : 3U;
    __set_PRIMASK(mask);
    /* SAM | 2026-10-25 +08:00 | A hello attempted during abort may have
     * consumed hello_due. Request it again only after RX is actually armed;
     * transport/network remain unknown until the peer replies normally. */
    if (ret == APP_DRV_SUCCESS) yp_business_transport_lost_from(YP_PEER_UART_RX_LOST);
}

/* SAM | 2026-10-14 14:20 +08:00 | Retain only fixed AT bytes in RAM because
 * local TX success cannot distinguish an input-buffer change from a bad pin bit.
 * Packed words use wire order (AT CR LF = 0x41540D0A); phase 2 means complete.
 * This records HAL input before/after, not the actual FIFO bus writes. */
typedef struct {
    uint32_t seq, phase, length, before, after, status;
} cat1_at_trace_t;
volatile cat1_at_trace_t g_cat1_at_trace;

static uint32_t cat1_at_pack(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

/* Separate UART diagnostic, without starting MQTT/SIP or Cat1Svr AO. */
static int cmd_cat_diag(int argc, char *argv[])
{
    /* SAM | 2026-10-20 20:47 +08:00 | Accept any CAT1 AT command for diagnostics;
     * retain a bounded line buffer so arbitrary parameters cannot overflow it. */
    uint8_t probe[480];
    size_t used = 0U;
    if (argc < 1) {
        cli_printf("Usage: cat_diag [AT command]\r\n");
        return -1;
    }
    if (argc == 1) {
        memcpy(probe, "AT", 2U);
        used = 2U;
    }
    for (int i = 1; i < argc; ++i) {
        size_t n = strlen(argv[i]);
        if (used + n + (i > 1 ? 1U : 0U) + 2U > sizeof(probe)) {
            cli_printf("[CAT1 ERROR] command_too_long max=478\r\n");
            return -1;
        }
        if (i > 1) probe[used++] = ' ';
        memcpy(probe + used, argv[i], n);
        used += n;
    }
    /* SAM | 2026-10-20 20:47 +08:00 | Prevent manual AT traffic during peer OTA;
     * arbitrary commands remain available outside the protected install window. */
    if (!yp001_ota_power_change_allowed()) {
        cli_printf("[OTA] CAT1 diagnostic command denied during protected update\r\n");
        return -1;
    }
    if (!s_uart4_ready) uart4_init();
    if (!s_uart4_ready) { cli_printf("[CAT1] UART4 init failed\r\n"); return -1; }
    probe[used++] = '\r';
    probe[used++] = '\n';
    int length = (int)used;
    /* SAM | 2026-10-14 14:20 +08:00 | Trace only fixed AT because business
     * frames and other diagnostic commands must keep their current behavior. */
    bool trace = length == 4 && !memcmp(probe, "AT\r\n", 4U);
    uint32_t seq = 0U, before = 0U, after = 0U;
    if (trace) {
        seq = g_cat1_at_trace.seq + 1U;
        before = cat1_at_pack(probe);
        g_cat1_at_trace.phase = 1U;
        g_cat1_at_trace.seq = seq;
        g_cat1_at_trace.length = 4U;
        g_cat1_at_trace.before = before;
        g_cat1_at_trace.after = 0U;
        g_cat1_at_trace.status = 0xFFFFU;
        __DMB();
    }
    uint16_t ret = app_uart_transmit_sync(APP_UART_ID_4, probe, (uint16_t)length, 1000U);
    if (trace) {
        after = cat1_at_pack(probe);
        g_cat1_at_trace.after = after;
        g_cat1_at_trace.status = ret;
        __DMB();
        g_cat1_at_trace.phase = 2U;
    }
    cli_printf("[CAT1] UART4 AT TX=0x%04X dropped=%lu\r\n", ret, (unsigned long)s_cat_diag_dropped);
    if (trace) cli_printf("[CAT1 TXRAW] seq=%lu len=4 pre=%08lX post=%08lX tx=0x%04X\r\n",
                         (unsigned long)seq, (unsigned long)before,
                         (unsigned long)after, ret);
    return ret == APP_DRV_SUCCESS ? 0 : -1;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("cat_diag", "CAT1 AT; reply on UART0", cmd_cat_diag);

/* SAM | 2026-10-10 16:52 +08:00 | Add explicit baud and text bridge commands
 * because the validated LuatOS app uses UART1 460800 and custom AT commands.
 * TX success acknowledges only the MCU UART, never module execution. */
static int cmd_cat_baud(int argc, char *argv[])
{
    /* SAM | 2026-10-12 19:23 +08:00 | Block manual UART disruption because it can reset an installing peer. */
    if (!yp001_ota_power_change_allowed()) { cli_printf("[OTA] UART change denied\r\n"); return -1; }
    if (argc != 2 || (strcmp(argv[1], "115200") && strcmp(argv[1], "460800"))) {
        cli_printf("Usage: cat_baud 115200|460800\r\n");
        return -1;
    }
    uart_handle_t *owner = app_uart_get_handle(APP_UART_ID_4);
    if (owner != NULL && owner != &s_uart4_param.uart_dev.handle) {
        cli_printf("[CAT1 ERROR] UART4_owned_by_other_service\r\n");
        return -1;
    }
    uint32_t baud = !strcmp(argv[1], "460800") ? 460800U : 115200U;
    if (baud != s_cat_uart_baud || !s_uart4_ready) {
        if (owner != NULL) {
            uint16_t ret = app_uart_deinit(APP_UART_ID_4);
            if (ret != APP_DRV_SUCCESS) {
                cli_printf("[CAT1 ERROR] deinit=0x%04X\r\n", ret);
                return -1;
            }
        }
        s_uart4_ready = false;
        s_cat_diag_read = s_cat_diag_write = 0U;
        s_cat_line_used = 0U;
        s_cat_line_discard = false;
        /* SAM | 2026-10-23 +08:00 | A baud change invalidates every partial OTA frame. */
        yp001_ota_mux_lost(&s_cat_mux);
        s_cat_diag_overflow = false;
        s_cat_uart_error = 0U;
        s_cat_uart_baud = baud;
        uart4_init();
    }
    cli_printf("[CAT1 BAUD] ok=%u baud=%lu\r\n", s_uart4_ready ? 1U : 0U,
               (unsigned long)s_cat_uart_baud);
    return s_uart4_ready ? 0 : -1;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("cat_baud", "UART4 115200|460800", cmd_cat_baud);

static int cmd_cat_at(int argc, char *argv[])
{
    /* SAM | 2026-10-12 19:23 +08:00 | Block manual UART disruption because it can reset an installing peer. */
    /* SAM | 2026-10-27 +08:00 | A PREPARED GR recovery needs status/exact R6 control, not unrestricted AT/reset. Keep argument count and command grammar closed. */
    if (!yp001_ota_power_change_allowed()&&!(argc==2&&yp001_ota_recovery_control_allowed()&&
        yp001_ota_recovery_command_allowed(argv[1]))) { cli_printf("[OTA] UART change denied\r\n"); return -1; }
    uint8_t text[480];
    size_t used = 0U;
    if (argc < 2) {
        cli_printf("Usage: cat_at <module command>\r\n");
        return -1;
    }
    for (int i = 1; i < argc; ++i) {
        size_t n = strlen(argv[i]);
        if (used + n + (i > 1 ? 1U : 0U) + 2U > sizeof(text)) {
            cli_printf("[CAT1 ERROR] command_too_long max=478\r\n");
            return -1;
        }
        if (i > 1) text[used++] = ' ';
        memcpy(text + used, argv[i], n);
        used += n;
    }
    if (!s_uart4_ready) uart4_init();
    if (!s_uart4_ready) {
        cli_printf("[CAT1 TX] ok=0 error=uart_unavailable\r\n");
        return -1;
    }
    text[used++] = '\r';
    text[used++] = '\n';
    uint16_t ret = app_uart_transmit_sync(APP_UART_ID_4, text, (uint16_t)used, 1000U);
    cli_printf("[CAT1 TX] ok=%u code=0x%04X bytes=%u dropped=%lu\r\n",
               ret == APP_DRV_SUCCESS ? 1U : 0U, ret, (unsigned)used,
               (unsigned long)s_cat_diag_dropped);
    return ret == APP_DRV_SUCCESS ? 0 : -1;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("cat_at", "LuatOS command; ACK separate", cmd_cat_at);

/* SAM | 2026-10-20 19:50 +08:00 | Read actual driver geometry and runtime NVDS start because linker/algorithm limits do not prove Flash capacity; never initialize, erase or write storage here. */
static int cmd_ota_storage(int argc, char *argv[])
{
    (void)argv;
    if (argc != 1) { cli_printf("Usage: ota_storage (read only)\r\n"); return -1; }
    uint32_t id=0, size=0;
    hal_flash_get_info(&id,&size);
    uint32_t sector=hal_flash_sector_size();
    uint32_t nvds=nvds_get_start_addr();
    const uint32_t base=0x00200000U;
    uint32_t sectors=(uint32_t)NVDS_NUM_SECTOR+1U; /* Include the SDK GC sector. */
    if (!size || size>0xFFFFFFFFU-base || !sector || size%sector ||
        !sectors || sectors>size/sector || nvds<base || nvds%sector ||
        nvds-base>size-sectors*sector) {
        cli_printf("[OTA_STORAGE] INVALID id=0x%08lX flash_bytes=%lu sector=%lu nvds_start=0x%08lX; no layout approved\r\n",
            (unsigned long)id,(unsigned long)size,(unsigned long)sector,(unsigned long)nvds);
        return -1;
    }
    cli_printf("[OTA_STORAGE] id=0x%08lX flash_start=0x%08lX flash_bytes=%lu sector=%lu nvds_start=0x%08lX nvds_end=0x%08lX nvds_sectors_with_gc=%lu; read_only=1 layout_approved=0\r\n",
        (unsigned long)id,(unsigned long)base,(unsigned long)size,(unsigned long)sector,
        (unsigned long)nvds,(unsigned long)(nvds+sectors*sector),(unsigned long)sectors);
    return 0;
}
/* SAM | 2026-10-23 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("ota_storage", "Read Flash/NVDS geometry", cmd_ota_storage);

/* SAM | 2026-10-21 +08:00 | Report compiled APP_INFO version because SDK version and backend labels cannot establish installed application identity. */
static int cmd_fw_version(int argc, char *argv[])
{
    /* SAM | 2026-10-24 +08:00 | Optional read-only verification uses the real
     * application context, without injected registers, Flash writes or install. */
    if (argc != 1 && (argc != 2 || strcmp(argv[1], "verify"))) {
        cli_printf("Usage: fw_version [verify]\r\n"); return -1;
    }
    /* SAM | 2026-10-22 +08:00 | Retain an identifiable version record inside HEX/BIN and report the exact compiled release. */
    /* SAM | 2026-10-24 +08:00 | Identify the user-approved USB bench policy explicitly so test firmware cannot be mistaken for production charging acceptance. */
    cli_printf("[FW_VERSION] %s product=%s app_numeric=%lu ota_provisioned=%u usb_bench_test=%u\r\n",
        YP001_FW_IDENTITY, YP001_PRODUCT_VERSION, (unsigned long)VERSION,
        yp001_ota_port_provisioned() ? 1U : 0U, (unsigned)YP001_OTA_USB_BENCH_TEST);
    if (argc == 2) {
        yp_boot_image image = {0};
        unsigned major=0, minor=0, patch=0;
        if (sscanf(YP001_PRODUCT_VERSION, "%u.%u.%u", &major, &minor, &patch) != 3 ||
            major > 999U || minor > 999U || patch > 999U) return -1;
        unsigned running = ll_aon_wdt_is_active_flag_running();
        uint16_t wdt = app_aon_wdt_refresh();
        int result = wdt == APP_DRV_SUCCESS ?
            yp001_ota_running_image(major*1000000U+minor*1000U+patch, &image) : -1;
        cli_printf("[OTA_VERIFY] wdt_running=%u refresh=0x%04X result=%d signature_ok=%u bytes=%lu version=%lu read_only=1\r\n",
            running, wdt, result, result == 0 ? 1U : 0U,
            (unsigned long)image.size, (unsigned long)image.version);
        return result;
    }
    return 0;
}
/* SAM | 2026-10-23 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("fw_version", "Read GR firmware version", cmd_fw_version);


/* SAM | 2026-10-10 18:06 +08:00 | Power only for USB flashing; never send AT or press PWRKEY automatically. */
/* SAM | 2026-10-13 08:36 +08:00 | Use the validated bridge owner because the old AO is disabled. */
bool yp_business_port_send(const char *line, size_t length)
{
    if (!line || length == 0 || length > 512U) return false;
    if (!s_uart4_ready) uart4_init();
    if (!s_uart4_ready) return false;
    return app_uart_transmit_sync(APP_UART_ID_4, (uint8_t *)line,
        (uint16_t)length, 100U) == APP_DRV_SUCCESS;
}
void yp001_ota_uart_reply(const char *line, size_t length)
{
    if (s_uart4_ready && length <= YP001_OTA_FRAME_MAX)
        (void)app_uart_transmit_sync(APP_UART_ID_4, (uint8_t *)line, (uint16_t)length, 100U);
}

/* SAM | 2026-10-28 19:00 +08:00 | Bench builds restart a silent CAT1 once per GR boot while a GR OTA owner is active, because the install reset (and any GR reset) drops CAT1 and the protected-install gate refuses the manual key. Rail on + one non-blocking 1600ms PWRKEY; skipped if CAT1 was heard, rail isolated or the owner is not a GR transaction. Production builds keep manual PWRKEY. */
/* SAM | 2026-11-11 +08:00 | Production fix (user decision): bench switches YP001_OTA_USB_BENCH_TEST/EPAPER_UI_FACTORY_TEST are 0 in the Keil project, but this OTA-only CAT1 restart stays in every build: after the GR install reset nothing else pulses PWRKEY, so a field OTA would wait in TRIAL without CAT1. Same guards as before (GR OTA owner active, CAT1 silent, rail not isolated, once per boot). */
#ifndef YP001_CAT1_OTA_AUTOSTART
#define YP001_CAT1_OTA_AUTOSTART 1
#endif
void yp001_cat1_ota_autostart_poll(uint32_t now_ms)
{
#if YP001_CAT1_OTA_AUTOSTART
    static yp001_cat1_autostart_t autostart;
    uint32_t peer[12];
    yp_business_peer_evidence(peer);
    int action = yp001_cat1_autostart_step(&autostart, now_ms,
        yp001_ota_cat1_autostart_allowed() && !s_cat1_isolated, peer[0] != 0U || peer[2] != 0U);
    if (action == YP001_CAT1_AS_ASSERT) {
        app_io_init_t pin = APP_IO_DEFAULT_CONFIG;
        pin.mode = APP_IO_MODE_OUTPUT; pin.pull = APP_IO_NOPULL;
        uint16_t ret = APP_DRV_SUCCESS;
        if (app_io_read_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN) != YP001_CAT1_POWER_ON) {
            pin.pin = YP001_CAT1_POWER_PIN; pin.mux = YP001_GPIO_GPIO_MUX;
            ret = app_io_init(YP001_CAT1_POWER_TYPE, &pin);
            if (!ret) ret = app_io_write_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN, YP001_CAT1_POWER_ON);
        }
        pin.pin = YP001_CAT1_KEY_PIN; pin.mux = YP001_AON_GPIO_MUX;
        if (!ret) ret = app_io_init(YP001_CAT1_KEY_TYPE, &pin);
        if (!ret) ret = app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_ASSERT);
        cli_printf("[CAT1 POWER] OTA autostart: rail on, PWRKEY asserted code=0x%04X (silent %lums after boot)\r\n",
                   ret, (unsigned long)now_ms);
    } else if (action == YP001_CAT1_AS_RELEASE) {
        uint16_t ret = app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_RELEASE);
        cli_printf("[CAT1 POWER] OTA autostart: PWRKEY released code=0x%04X; awaiting CAT1 hello\r\n", ret);
    }
#else
    (void)now_ms;
#endif
}

/* SAM | 2026-10-12 19:23 +08:00 | Guard manual rail/key changes because pending installs cannot tolerate reset. */
/* SAM | 2026-11-01 +08:00 | Set only by the locked-reset path below so its own single PWRKEY pulse passes the OTA power gate. */
static bool s_cat1_key_owner_ota;
/* SAM | 2026-11-06 +08:00 | Factory hold is not the OTA lock; release or reboot restores the ordinary power policy. */
static bool s_factory_power_hold;
bool yp001_cat1_factory_hold_active(void) { return s_factory_power_hold; }
int cat1_debug_power(int argc, char *argv[])
{
    /* SAM | 2026-10-19 16:30 +08:00 | Add an awake isolation measurement state because rail-off alone leaves UART4 driving the unpowered peer. */
    if (argc != 2 || (strcmp(argv[1], "on") && strcmp(argv[1], "off") && strcmp(argv[1], "isolate") &&
                      strcmp(argv[1], "key") && strcmp(argv[1], "status") && strcmp(argv[1], "reset") && strcmp(argv[1], "hold_on") && strcmp(argv[1], "hold_off"))) {
        cli_printf("Usage: cat1_power on|off|isolate|key|reset|status|hold_on|hold_off\r\n"); return -1;
    }
    if (!strcmp(argv[1], "status")) {
        cli_printf("[CAT1 POWER] rail_request=%u factory_hold=%u; VBAT and boot unverified\r\n", (GPIO0->DATAOUT & YP001_CAT1_POWER_PIN)!=0U, s_factory_power_hold);
        return 0;
    }
    if (!strcmp(argv[1],"hold_off")) {
        s_factory_power_hold=false;
        cli_printf("[CAT1 POWER] factory_hold=0; normal policy restored, rail unchanged\r\n");return 0;
    }
    if (!strcmp(argv[1],"hold_on")) {
        if (yp001_charger_ship_locked() || !yp001_ota_power_change_allowed()) return -1;
        char name[]="cat1_power",on[]="on";char *args[]={name,on};
        int result=cat1_debug_power(2,args);
        if (!result) s_factory_power_hold=true;
        cli_printf("[CAT1 POWER] factory_hold=%u result=%d; ends on release or reboot\r\n",s_factory_power_hold,result);return result;
    }
    if (s_factory_power_hold && strcmp(argv[1],"on")) {
        cli_printf("[CAT1 POWER] denied: release factory hold first\r\n");return -1;
    }
    /* SAM | 2026-10-27 +08:00 | Rail-on alone is non-destructive recovery; off/isolate/PWRKEY remain under the original protected-install gate. */
    /* SAM | 2026-10-30 22:52 +08:00 | Rail-on never reduces power, so it is allowed at any time (also during an OTA); off/isolate/PWRKEY stay under the OTA power rule. */
    if (!yp001_ota_power_change_allowed()&&strcmp(argv[1],"on")&&!(s_cat1_key_owner_ota&&!strcmp(argv[1],"key"))) {
        /* SAM | 2026-11-01 +08:00 | Under the OTA lock a reset only ensures the rail is on; everything else that could cut CAT1 is refused and logged. */
        cli_printf("[PWR] deny %s owner=OTA\r\n", argv[1]);
        if (strcmp(argv[1], "reset")) return -1;
        /* SAM | 2026-11-01 +08:00 | Locked reset never cuts power: a running CAT1 is left alone; a CAT1 whose rail is off (e.g. after a GR
         * reboot) is powered and started with one PWRKEY pulse, so the OTA can resume. */
        if (app_io_read_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN) == YP001_CAT1_POWER_ON) return 0;
        char a0[] = "cat1_power", a1[] = "on", a2[] = "key";
        char *on_argv[] = { a0, a1 }, *key_argv[] = { a0, a2 };
        if (cat1_debug_power(2, on_argv)) return -1;
        delay_ms(200);
        s_cat1_key_owner_ota = true;
        int key_ret = cat1_debug_power(2, key_argv);
        s_cat1_key_owner_ota = false;
        return key_ret;
    }
    /* SAM | 2026-11-01 +08:00 | Restore the colleague's "reset" (used by Cat1Svr_power_on entry): rail off, 200 ms, rail on, one PWRKEY pulse.
     * Without it the low-power AO could cut CAT1 but never power it back on. */
    if (!strcmp(argv[1], "reset")) {
        char a0[] = "cat1_power", a_off[] = "off", a_on[] = "on", a_key[] = "key";
        char *v_off[] = { a0, a_off }, *v_on[] = { a0, a_on }, *v_key[] = { a0, a_key };
        (void)cat1_debug_power(2, v_off);
        delay_ms(200);
        if (cat1_debug_power(2, v_on)) return -1;
        return cat1_debug_power(2, v_key);
    }
    /* Do not let app_io_init briefly clear an already-on rail during repeated on requests. Pin level is not a VBAT measurement or boot proof. */
    if(!strcmp(argv[1],"on")&&app_io_read_pin(YP001_CAT1_POWER_TYPE,YP001_CAT1_POWER_PIN)==YP001_CAT1_POWER_ON){
        s_cat1_isolated=false;
        /* SAM | 2026-10-27 16:00 +08:00 | Preserve the established rail ACK for existing tools while reporting the idempotent path separately. */
        cli_printf("[CAT1 POWER] rail_request=on code=0x0000; USB may supply VBAT; no AT sent\r\n");
        cli_printf("[CAT1 POWER] rail unchanged\r\n");return 0;
    }
    /* SAM | 2026-10-19 16:30 +08:00 | Explicit isolate keeps UART0 alive and refuses a foreign UART4 owner; normal on/off behavior stays unchanged. */
    if (!strcmp(argv[1], "isolate")) {
        uart_handle_t *owner = app_uart_get_handle(APP_UART_ID_4);
        if (owner != NULL && owner != &s_uart4_param.uart_dev.handle) {
            cli_printf("[CAT1 POWER] isolate refused: UART4 owned by another service\r\n");
            return -1;
        }
        if (owner != NULL) {
            if (s_uart4_ready && app_uart_abort_receive(APP_UART_ID_4) != APP_DRV_SUCCESS) return -1;
            if (app_uart_deinit(APP_UART_ID_4) != APP_DRV_SUCCESS) return -1;
            s_uart4_ready = false;
        }
        app_io_init_t pads = {.pull = APP_IO_NOPULL, .mode = APP_IO_MODE_INPUT,
            .pin = YP001_CAT1_UART_TX_PIN | YP001_CAT1_UART_RX_PIN, .mux = YP001_AON_GPIO_MUX};
        if (app_io_init(YP001_CAT1_UART_TYPE, &pads) != APP_DRV_SUCCESS) return -1;
        /* SAM | 2026-10-19 17:00 +08:00 | Hold successful pad isolation across transport_lost/background polling. */
        s_cat1_isolated = true;
        s_cat_diag_read = s_cat_diag_write;
        s_cat_line_used = 0U;
        /* SAM | 2026-10-23 +08:00 | No partial binary state survives rail isolation. */
        s_cat_line_discard = false;
        yp001_ota_mux_lost(&s_cat_mux);
        /* SAM | 2026-10-25 +08:00 | Explicit rail isolation is not a spontaneous network loss. */
        yp_business_transport_lost_from(YP_PEER_POWER_OFF);
        cli_printf("[CAT1 POWER] UART4 isolated: TX/RX inputs no pull; rail-off follows; USB VBUS still present\r\n");
    }
    app_io_init_t pin = APP_IO_DEFAULT_CONFIG;
    pin.mode = APP_IO_MODE_OUTPUT;
    pin.pull = APP_IO_NOPULL;
    bool key = !strcmp(argv[1], "key");
    pin.pin = key ? YP001_CAT1_KEY_PIN : YP001_CAT1_POWER_PIN;
    pin.mux = key ? YP001_AON_GPIO_MUX : YP001_GPIO_GPIO_MUX;
    uint16_t ret = app_io_init(key ? YP001_CAT1_KEY_TYPE : YP001_CAT1_POWER_TYPE, &pin);
    if (ret) { cli_printf("[CAT1 POWER] gpio_init_error=0x%04X\r\n", ret); return -1; }
    if (key) {
        ret = app_io_write_pin(YP001_CAT1_KEY_TYPE, pin.pin, YP001_CAT1_KEY_ASSERT);
        if (!ret) delay_ms(1600);
        uint16_t release = app_io_write_pin(YP001_CAT1_KEY_TYPE, pin.pin, YP001_CAT1_KEY_RELEASE);
        if (!ret) ret = release;
        cli_printf("[CAT1 POWER] manual_key code=0x%04X; no AT sent\r\n", ret);
    } else {
        bool on = !strcmp(argv[1], "on");
        ret = app_io_write_pin(YP001_CAT1_POWER_TYPE, pin.pin,
                               on ? YP001_CAT1_POWER_ON : YP001_CAT1_POWER_OFF);
        /* SAM | 2026-10-19 17:00 +08:00 | Release isolation only after the explicit rail-on request succeeds. */
        if (on && ret == APP_DRV_SUCCESS) s_cat1_isolated = false;
        cli_printf("[CAT1 POWER] rail_request=%s code=0x%04X; USB may supply VBAT; no AT sent\r\n", on ? "on" : "off", ret);
    }
    return ret == APP_DRV_SUCCESS ? 0 : -1;
}

static void log_flush(void)
{
    app_uart_flush(YP001_DEBUG_UART_ID);
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
        /* YP001 UART0 is dedicated to debug logs and CLI. */

        /* CLI 处理：逐字符喂给 CLI 解析器 */
        for (uint16_t i = 0; i < p_evt->data.size && i < UART_RX_BUFFER_SIZE; i++) {
            uint16_t next = (s_cli_write + 1U) % CLI_RX_RING_SIZE;
            if (s_cli_overflow || next == s_cli_read) {
                s_cli_overflow = true;
                break;
            }
            s_cli_rx_ring[s_cli_write] = s_uart_rx_buffer[i];
            __DMB();
            s_cli_write = next;
        }

        /* 重新启动 DMA 接收 */
        app_uart_receive_async(YP001_DEBUG_UART_ID, s_uart_rx_buffer, UART_RX_BUFFER_SIZE);
    }
}

void uart_tx_data_send(uint8_t *p_data, uint16_t length)
{
    if (g_log_output_enabled) yp_factory_ble_capture(p_data,length);
    if (g_log_output_enabled && s_debug_uart_ready) {
        g_debug_uart_tx_status = app_uart_transmit_sync(YP001_DEBUG_UART_ID, p_data, length, 1000U);
    }
    /* 开关关闭时，数据被丢弃 */
}

/**
 * @brief 强制发送数据，不受日志开关影响（供 CLI 使用）
 */
void uart_tx_data_send_force(uint8_t *p_data, uint16_t length)
{
    /* SAM | 2026-11-06 +08:00 | Mirror bounded bytes; never send BLE or call QP from logging contexts. */
    yp_factory_ble_capture(p_data,length);
    if (s_debug_uart_ready)
    {
        g_debug_uart_tx_status = app_uart_transmit_sync(YP001_DEBUG_UART_ID, p_data, length, 1000U);
    }
}

void uart4_send_data(uint8_t *p_data, uint16_t length)
{
    if (!s_uart4_ready || !p_data || !length) return;
    app_uart_transmit_async(s_uart4_param.id, p_data, length);
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

/* SAM | 2026-10-13 08:46 +08:00 | Use accepted CAT1 NTP for the shared GR RTC because separate UI time would diverge from location timestamps. */
bool yp_business_port_time(uint32_t epoch)
{
    app_rtc_time_t rtc;
    unix_to_rtc_time(epoch, &rtc);
    rtc.week = (uint8_t)((epoch / 86400U + 4U) % 7U);
    return app_rtc_init_time(&rtc) == APP_DRV_SUCCESS;
}


#if APP_LOG_STORE_ENABLE
static void get_timestamp(app_log_store_time_t *p_time)
{
    app_rtc_time_t time;
    app_rtc_get_time(&time);
    p_time->year=time.year;
    p_time->month=time.mon;
    p_time->day=time.date;
    p_time->hour=time.hour;
    p_time->min=time.min;
    p_time->sec=time.sec;
    p_time->msec=time.ms;
}

static void app_rtc(void)
{
    app_rtc_time_t time;
    app_rtc_init(NULL);
    time.year = 23;
    time.mon  = 2;
    time.date = 13;
    time.hour = 8;
    time.min  = 0;
    time.sec  = 0;
    time.week = 0;
    time.ms   = 0;
    app_rtc_init_time(&time);
}

static void log_store_init(void)
{
    app_log_store_info_t store_info;
    app_log_store_op_t   op_func;

    store_info.nv_tag   = 0x40ff;
    store_info.db_addr  = FLASH_START_ADDR + 0x60000;
    store_info.db_size  = 0x10000;
    store_info.blk_size = 0x1000;

    op_func.flash_init  = hal_flash_init;
    op_func.flash_erase = hal_flash_erase;
    op_func.flash_write = hal_flash_write;
    op_func.flash_read  = hal_flash_read;
    op_func.time_get    = get_timestamp;
    op_func.sem_give    = NULL;
    op_func.sem_take    = NULL;

    app_rtc();
    app_log_store_init(&store_info, &op_func);
}
#endif

void app_periph_init(void)
{
    //SYS_SET_BD_ADDR(s_bd_addr);
    if (!s_debug_uart_ready)
    {
        uart_init();
    }
    app_log_assert_init();
#if APP_LOG_STORE_ENABLE
    log_store_init();
#endif
    APP_LOG_INFO("BOOT stage 1: UART init=0x%04X TX=0x%04X baud=%u", g_debug_uart_init_status, g_debug_uart_tx_status, s_uart_param.init.baud_rate);
    pwr_mgmt_mode_set(PMR_MGMT_ACTIVE_MODE);
    APP_LOG_INFO("BOOT stage 2: power mode ready; RTC init");
    app_log_flush();
    app_rtc_init(NULL);
    APP_LOG_INFO("BOOT stage 3: RTC returned; CLI init");
    app_log_flush();
    cli_init();
    /* Enable RX only after CLI state exists. */
    if (s_debug_uart_ready)
    {
        uint16_t status = app_uart_receive_async(YP001_DEBUG_UART_ID, s_uart_rx_buffer, UART_RX_BUFFER_SIZE);
        APP_LOG_INFO("BOOT stage 4: CLI ready; UART RX=0x%04X", status);
    }
}
