#include "yp001_scan_sched.h"
#include "tk_beacon_parser.h"
#include "ble_scanner.h"
#include "business/yp001_business.h"
#include "yp001_board_config.h"
#include "app_uart.h"
#include "cJSON.h"
#include "gr55xx.h"
#include "cli.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>

#define BLE_SCAN_TEST
#define CAT1_CONFIG_TEST
//#define CAT1_LOG_DEBUG

#ifdef CAT1_LOG_DEBUG
void cat1_printf(const char *fmt, ...);
#define cli_printf cat1_printf
#endif

static bool s_enabled = true;
static bool s_active;                      /* 周期扫描循环运行中(运动触发) */
static bool s_scanning;                    /* 当前扫描窗口进行中 */
/* SAM | 2026-11-07 12:17 +08:00 | Preserve explicit radio users across scheduler reinit; a deferred stop waits for their release. */
static volatile uint8_t s_radio_holds;
static bool s_stop_deferred;
static volatile bool s_radio_stop_pending;
static volatile bool s_radio_restart_due;
static uint8_t s_fail_streak;              /* 连续失锁次数 */
static uint8_t s_interval_min;             /* 当前扫描间隔(分钟)，退避 1..5 */
static uint32_t s_scan_start_ms;           /* 当前扫描窗口起始(单调时钟) */
static uint32_t s_next_attempt_ms;         /* 下次扫描尝试最早时刻 */
static uint32_t s_last_report_ms;          /* 上次 periodic 上报时刻(PeriodicPara 兜底) */
static uint32_t s_scan_total;              /* 累计已写入窗口计数(环形索引 = %YP_SCAN_HISTORY_CAP) */
static uint32_t s_last_reported;           /* 已发送到的写入计数(未发送条数 = s_scan_total - 该值) */
static uint32_t s_start_reported;          /* 开始发送的窗口计数 */
static BeaconScanResult s_cur;             /* 当前窗口缓存(ISR 写、前台读) */
static BeaconScanResult s_history[YP_SCAN_HISTORY_CAP];

static char s_tx_line[YP_SCAN_MSG_BUDGET];
static uint32_t s_tx_count;             /* 本轮报告锁定目标点(累计写入计数快照，游标发到该点即完成) */
static bool s_tx_reporting;             /* 一轮上报进行中(防重入) */
static uint8_t s_tx_failed;                /* 任一条入队失败(仅打印；游标不推进，下轮自动重试该条) */
static uint32_t s_tx_last_push_ms;      /* 上次入队时刻(节流 YP_SCAN_POLL_INTERVAL_MS) */
static bool s_battery_stopped;          /* 电量停止状态(带滞回)：true=周期停止，回升到 stop+2% 才恢复 */

extern uint64_t get_current_unix_timestamp(void);

/* 服务器下发参数(带设备默认兜底)：未下发或 <=0 时用设备默认 */
static uint32_t cfg_interval_min(void)
{
#ifdef CAT1_CONFIG_TEST
	g_config.BleScanInterval = YP_SCAN_INTERVAL_BASE_MIN;
#endif
    return (g_config.BleScanInterval > 0)
               ? (uint32_t)g_config.BleScanInterval : YP_SCAN_INTERVAL_BASE_MIN;

}
static uint32_t cfg_window_sec(void)
{
#ifdef CAT1_CONFIG_TEST
	g_config.BleScanPeriod = YP_SCAN_WINDOW_SEC;
#endif
    return (g_config.BleScanPeriod > 0)
               ? (uint32_t)g_config.BleScanPeriod : YP_SCAN_WINDOW_SEC;

}
static uint32_t cfg_fallback_min(void)
{
#ifdef CAT1_CONFIG_TEST
	g_config.PeriodicPara = 5;
#endif
    return (g_config.PeriodicPara > 0)
               ? (uint32_t)g_config.PeriodicPara : YP_SCAN_PERIODIC_FALLBACK_MIN;

}
static uint32_t cfg_battery_stop_pct(void)
{
#ifdef CAT1_CONFIG_TEST
	g_config.PowerThreshold = YP_SCAN_BATTERY_STOP_PCT;
#endif
    return (g_config.PowerThreshold > 0)
               ? (uint32_t)g_config.PowerThreshold : YP_SCAN_BATTERY_STOP_PCT;

}

/* 失锁：第 1 次失锁保持基础间隔(默认 1 分钟)，第 2 次起 2/3/4/5 分钟，上限 5 分钟 */
static uint8_t interval_min_next(uint8_t fail_streak)
{
    uint32_t base = cfg_interval_min();
    uint32_t m = (fail_streak <= 1U) ? base : (uint32_t)fail_streak;
    if (m > YP_SCAN_INTERVAL_MAX_MIN) m = YP_SCAN_INTERVAL_MAX_MIN;
#ifdef BLE_SCAN_TEST
    if (m > 2)
        m = 2;
#endif
    return (uint8_t)m;
}

static void clear_history(void)
{
    s_scan_total = 0U;
    s_last_reported = 0U;
    s_start_reported = 0U;
}

/* 启动扫描窗口(BleScanPeriod) */
static void start_scan(uint32_t now_ms)
{
    sdk_err_t rc;
    /* SAM | 2026-11-07 12:18 +08:00 | A stop return only accepts the request; wait for the actual BLE event before restarting. */
    if (s_radio_stop_pending) { s_next_attempt_ms = now_ms + 1000U; return; }
    rc = ble_scanner_start();
    cli_printf("[SCAN_SCHED] ble_scanner_start 0x%04X\r\n",
               (unsigned)rc);
    if (rc != BLE_SUCCESS && rc != 0x0F) {
        cli_printf("[SCAN_SCHED] ble_scanner_start failed 0x%04X\r\n",
                   (unsigned)rc);
        s_next_attempt_ms = now_ms + 1000U; /* 1s 后重试 */
        return;
    }
    s_scanning = true;
    s_scan_start_ms = now_ms;
    __disable_irq();
    s_cur.count = 0;
    s_cur.timestamp = 0;
    __enable_irq();
}

/* SAM | 2026-11-07 12:17 +08:00 | Shared location/manual leases prevent a periodic stop from interrupting another radio user. */
void yp_scan_sched_radio_hold(uint8_t owner, bool hold)
{
    if (hold) s_radio_holds |= owner;
    else s_radio_holds &= (uint8_t)~owner;
}

/* SAM | 2026-11-07 12:18 +08:00 | Only a successful controller stop event releases the asynchronous stop barrier. */
void yp_scan_sched_on_radio_stop(bool stopped)
{
    if (stopped) {
        if (s_radio_stop_pending && s_radio_holds) s_radio_restart_due = true;
        s_radio_stop_pending = false;
    }
}

/* SAM | 2026-11-07 12:19 +08:00 | A user arriving during an accepted stop resumes scanning in foreground after its completion event. */
static void radio_restart_poll(void)
{
    if (s_radio_restart_due) {
        s_radio_restart_due = false;
        if (s_radio_holds) {
            sdk_err_t rc = ble_scanner_start();
            cli_printf("[SCAN_SCHED] shared restart request 0x%04X\r\n", (unsigned)rc);
        }
    }
}

static void stop_scan(void)
{
    sdk_err_t rc;
    if (s_scanning) {
        s_scanning = false;
        s_stop_deferred = true;
    }
    if (!s_stop_deferred || s_radio_stop_pending || s_radio_holds ||
        yp_business_status()->alarm_active || ble_phone_connected()) return;
    /* SAM | 2026-11-07 12:17 +08:00 | End the logical window separately from the asynchronous radio stop request. */
    s_stop_deferred = false;
    s_radio_stop_pending = true;
    rc = ble_scanner_stop();
    if (rc != BLE_SUCCESS) {
        s_radio_stop_pending = false;
        cli_printf("[SCAN_SCHED] ble_scanner_stop failed 0x%04X\r\n", (unsigned)rc);
    } else {
        cli_printf("[SCAN_SCHED] stop requested; await BLE scan-stop event\r\n");
    }
}

void yp_scan_sched_init(void)
{
    s_enabled = true;
    s_active = false;
    s_scanning = false;
    s_fail_streak = 0U;
    s_interval_min = YP_SCAN_INTERVAL_BASE_MIN;
    s_scan_start_ms = 0U;
    s_next_attempt_ms = 0U;
    s_last_report_ms = 0U;
    s_tx_reporting = false;
    s_tx_failed = 0;
    s_tx_count = 0U;
    s_tx_last_push_ms = 0U;
    s_battery_stopped = false;
    cli_printf("[SCAN_SCHED] yp_scan_sched_init\r\n");

}

BeaconScanResult *yp_get_cur_bt_list(void)
{
	return &s_cur;
}

void yp_scan_sched_set_enabled(bool on)
{
    s_enabled = on;
    if (!on) {        
        stop_scan();
        s_active = false; /* off 同时停止周期循环 */
    }
}

bool yp_scan_sched_enabled(void) { return s_enabled; }


void yp_scan_sched_on_adv_report(void const *p_adv)
{
    uint8_t addr[6];
    int8_t rssi;
    tk_beacon_data_t data;
    BeaconScanResult *p;
    uint32_t saved_primask;

    if (!s_enabled || !s_scanning) return;
    if (!tk_beacon_process(p_adv, addr, &rssi, &data)) return;

    /* SAM | 2026-11-05 +08:00 | Preserve the caller's IRQ state and keep serial output out of the scan cache critical section. */
    saved_primask = __get_PRIMASK();
    __disable_irq();
    p = &s_cur;
    {
        int idx = -1;
        uint8_t i;
        for (i = 0; i < p->count; i++) {
            if (memcmp(p->list[i].addr, addr, 6U) == 0) { idx = i; break; }
        }
        if (idx >= 0) {
            p->list[idx].rssi = rssi;
            p->list[idx].major = data.major;
            p->list[idx].minor = data.minor;
        } else if (p->count < MAX_BEACON_PER_SCAN) {
            p->list[p->count].rssi = rssi;
            memcpy(p->list[p->count].addr, addr, 6U);
            p->list[p->count].major = data.major;
            p->list[p->count].minor = data.minor;
            p->count++;
        } else {
            uint8_t min_pos = 0;
            int8_t min_rssi = p->list[0].rssi;
            for (i = 1; i < p->count; i++) {
                if (p->list[i].rssi < min_rssi) {
                    min_rssi = p->list[i].rssi;
                    min_pos = i;
                }
            }
            if (rssi > min_rssi) {
                p->list[min_pos].rssi = rssi;
                memcpy(p->list[min_pos].addr, addr, 6U);
                p->list[min_pos].major = data.major;
                p->list[min_pos].minor = data.minor;
            }
        }
    }
    __set_PRIMASK(saved_primask);
}

static uint16_t report_build_next(void)
{
    const yp_business_status_t *b = yp_business_status();
    cJSON *root, *arr, *bi;
    char *json, *topic;
    int n;

    root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "MsgType", get_msg_type(LOCATE_TYPE_PERIOD));
    cJSON_AddNumberToObject(root, "Battery", b->battery_known ? b->battery_percent : 80);
    cJSON_AddNumberToObject(root, "Time", get_current_unix_timestamp());
    cJSON_AddNumberToObject(root, "PeriodicPara", cfg_fallback_min());
	
    arr = cJSON_CreateArray();
    {
        BeaconScanResult *r = &s_history[s_last_reported % YP_SCAN_HISTORY_CAP];
        uint8_t j;

        for (j = 0U; j < r->count; j++) {
            bi = cJSON_CreateObject();
            cJSON_AddNumberToObject(bi, "Major", r->list[j].major);
            cJSON_AddNumberToObject(bi, "Minor", r->list[j].minor);
            cJSON_AddNumberToObject(bi, "Rssi", r->list[j].rssi);
            cJSON_AddItemToArray(arr, bi);
        }
        cJSON_AddItemToObject(root, "Beacon", arr);
    }


    json = cJSON_PrintUnformatted(root);
    if (json == NULL) { cJSON_Delete(root); return 0; }
	if(s_last_reported == s_start_reported)
	{
	    topic = get_topic(LOCATE_TYPE_PERIOD, AO_Cat1Svr.IMEI);
	    n = snprintf(s_tx_line, sizeof(s_tx_line), "MQTT_SEND=%s,%s\r\n",
	                 topic ? topic : "", json);
	    if (topic != NULL) free(topic);
	}
	else
	{
        n = snprintf(s_tx_line, sizeof(s_tx_line), "BEACON_DATA=%d,%s\r\n", s_last_reported - s_start_reported, json);
	}
    cJSON_free(json);
    cJSON_Delete(root);
    if (n <= 0 || (size_t)n >= sizeof(s_tx_line)) return 0; /* 行超长，丢弃该包 */
    return (uint16_t)n;
}

static bool report_push_next(void)
{
    uint16_t n, rc;
    uint32_t remaining = s_tx_count - s_last_reported; /* 本轮剩余待发条数 */

    if (remaining == 0U) return true;

    if ((uint32_t)(s_scan_total - s_tx_count) >=
        (uint32_t)(YP_SCAN_HISTORY_CAP - remaining)) {
        s_last_reported = s_scan_total;
        s_tx_reporting = false;
        cli_printf("[SCAN_SCHED] report aborted: ring advanced %lu during tx; %lu remaining\r\n",
                   (unsigned long)(s_scan_total - s_tx_count),
                   (unsigned long)remaining);
        return false;
    }

    n = report_build_next();
    if (n == 0U) {
        s_tx_failed = 0;
        s_last_reported++;
        return false; 
    }
    //rc = Cat1Svr_send_async(&AO_Cat1Svr, (uint8_t *)s_tx_line, n);
    rc = app_uart_transmit_sync(APP_UART_ID_4, (uint8_t *)s_tx_line, n, 1000);
    if (rc != APP_DRV_SUCCESS && rc != APP_DRV_ERR_BUSY) {
        s_tx_failed++;
        if (s_tx_failed >= YP_TX_SEND_RETRY_COUNT) {
            s_tx_failed = 0;
            s_last_reported++;
        }
        cli_printf("[SCAN_SCHED] item %lu async enqueue failed 0x%04X\r\n",
                   (unsigned long)(s_last_reported + 1U), (unsigned)rc);
        return false;
    }
    cli_printf("[SCAN_SCHED] item %lu queued: %u bytes\r\n",
               (unsigned long)(s_last_reported + 1U), (unsigned)n);
    s_tx_failed = 0;
    s_last_reported++;
    return true;
}

static bool report_start(uint32_t pending)
{
    size_t imei_len = strlen(AO_Cat1Svr.IMEI);

    if (imei_len == 0U) {
        cli_printf("[SCAN_SCHED] report skipped: IMEI unknown\r\n");
        return false;
    }
#if 0
    /* CAT1 断电时不上报*/
    if (app_io_read_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN) !=
        YP001_CAT1_POWER_ON) {
        cli_printf("[SCAN_SCHED] report skipped: CAT1 rail off\r\n");
        return false;
    }
#endif
    if (pending == 0U) 
        return false;
    if (s_tx_reporting) 
        return false;
    s_tx_count = s_scan_total;
    s_tx_failed = 0;
    s_tx_reporting = true;
    s_tx_last_push_ms = 0U;
    report_push_next();
    return true;
}

bool yp_scan_sched_report_pending(bool bForce)
{
    if (bForce) {
        uint16_t n, rc;
        
        cli_printf("[SCAN_SCHED] report force when %d/%d\r\n", s_start_reported, s_last_reported);
        s_start_reported = s_last_reported;
        n = snprintf(s_tx_line, sizeof(s_tx_line), "BEACON_DATA_FORCE=%d\r\n", s_last_reported);
        rc = Cat1Svr_send_async(&AO_Cat1Svr, (uint8_t *)s_tx_line, n);
    } else {
        uint32_t pending = s_scan_total - s_last_reported;
        return report_start(pending);
    }
}

void yp_scan_sched_poll(uint32_t now_ms)
{
    static uint32_t s_last_ms;
    const yp_business_status_t *b;
    bool blocked;

    if ((uint32_t)(now_ms - s_last_ms) < YP_SCAN_POLL_INTERVAL_MS) return;
    s_last_ms = now_ms;

    if (s_tx_reporting) {
        if ((uint32_t)(now_ms - s_tx_last_push_ms) >= YP_SCAN_POLL_INTERVAL_MS) {
            s_tx_last_push_ms = now_ms;
            report_push_next();
        }
        if (s_last_reported >= s_tx_count) {
            s_tx_reporting = false;
            if (s_tx_failed == 0) {
                cli_printf("[SCAN_SCHED] async report done: sent up to scan %lu\r\n",
                           (unsigned long)s_last_reported);
            }
        }
    }

    /* SAM | 2026-11-07 12:17 +08:00 | Finish a postponed radio stop even after the periodic scheduler is disabled. */
    radio_restart_poll();
    if (s_stop_deferred) { stop_scan(); return; }
    if (!s_enabled) return;

    b = yp_business_status();
    /* 告警(SOS)与手机 BLE 连接期间暂停，避免抢占 SOS 取位扫描/GUS 透传 */
    blocked = b->alarm_active || ble_phone_connected();

    /* 电量兜底：< PowerThreshold 停止周期上报(扫描一并停止，省电)。
     * 滞回：回升到 stop+YP_SCAN_BATTERY_HYST_PCT 才恢复，防临界抖动反复启停；
     * battery_known 未知时不限制(保持原语义)。 */
    #if 0
    if (b->battery_known) {
        uint32_t pct = (uint32_t)b->battery_percent;
        uint32_t stop_pct = cfg_battery_stop_pct();
        uint32_t resume_pct = stop_pct + YP_SCAN_BATTERY_HYST_PCT;
        if (resume_pct > 100U) resume_pct = 100U;
        if (!s_battery_stopped && pct < stop_pct) {
            s_battery_stopped = true;
            if (s_active) {
                cli_printf("[SCAN_SCHED] battery %u%% < %u%%, stop periodic cycle\r\n",
                           (unsigned)b->battery_percent, (unsigned)stop_pct);
                yp_scan_sched_report_pending(true);
                stop_scan();
                s_active = false;
            }
        } else if (s_battery_stopped && pct >= resume_pct) {
            s_battery_stopped = false;
            cli_printf("[SCAN_SCHED] battery %u%% >= %u%%, periodic cycle resumed\r\n",
                       (unsigned)b->battery_percent, (unsigned)resume_pct);
        }
        if (s_battery_stopped) return;
    }
	#endif
	
    if (s_scanning) {
        if (blocked) {
            /* 环境变化：中止当前窗口，不计数 */
            stop_scan();
            __disable_irq();
            s_cur.count = 0;
            __enable_irq();
            s_next_attempt_ms = now_ms + 1000U;
            return;
        }
        if ((uint32_t)(now_ms - s_scan_start_ms) >= cfg_window_sec() * 1000U) {
            stop_scan();
#ifdef BLE_SCAN_TEST
            if (s_cur.count == 0) s_cur.count = 1;
#endif
            if (s_cur.count > 0) {
                s_fail_streak = 0U;
                __disable_irq();
                s_cur.timestamp = b->epoch;
                s_history[s_scan_total % YP_SCAN_HISTORY_CAP] = s_cur;
                s_scan_total++;
                __enable_irq();
                cli_printf("[SCAN_SCHED] count = %d, total=%d\r\n", s_cur.count, s_scan_total);
            } else {
                s_fail_streak++;
            }
            s_interval_min = interval_min_next(s_fail_streak);
            s_next_attempt_ms = s_scan_start_ms +
                                (uint32_t)s_interval_min * 60000U;
           (void)yp_scan_sched_report_pending(false);
#ifdef BLE_SCAN_TEST
            if ((s_last_reported - s_start_reported) > 5)
#else
            if ((s_last_reported - s_start_reported) > YP_SCAN_REPORT_EVERY)
#endif
            {
                (void)yp_scan_sched_report_pending(true);
            }
        }
        if (!yp_motion_moving()) {
            cli_printf("[SCAN_SCHED] motion stop: (pending %u)\r\n",
                   (unsigned)s_last_reported - s_start_reported);       
            stop_scan();
            (void)yp_scan_sched_report_pending(true);
            s_active = false;
        }

        return;
    }

    /* 间隔等待(周期已启动) */
    if (s_active) {
        if (blocked) 
            return;

        if (!yp_motion_moving()) {
            stop_scan();
            (void)yp_scan_sched_report_pending(true);
            s_active = false;
            return;
        }        
        /* PeriodicPara 兜底：距上次上报 >= N 分钟且有未发送 → 时间触发上报 */
        if ((uint32_t)(now_ms - s_last_report_ms) >=
                cfg_fallback_min() * 60000U) {
            (void)yp_scan_sched_report_pending(true);
             s_last_report_ms = now_ms;
        }
        if (now_ms >= s_next_attempt_ms) {
			cli_printf("[SCAN_SCHED] period start\r\n");
            start_scan(now_ms);
        }
        return;
    }
    /* 运动到来：启动周期扫描 */

    if (yp_motion_moving() && !blocked) {
        s_active = true;
        s_fail_streak = 0U;
        s_interval_min = (uint8_t)cfg_interval_min();
        s_last_report_ms = now_ms; /* 周期起始作为上报计时起点 */
        cli_printf("[SCAN_SCHED] motion start: (interval %u min)\r\n",
                   (unsigned)s_interval_min);
        start_scan(now_ms);
        clear_history();
        //cli_execute_string("cat1_power on");
        //cli_execute_string("cat1_power key");
    }

}

#ifdef CAT1_LOG_DEBUG
void cat1_printf(const char *fmt, ...) {
    static char buf[256];
    va_list args;
    int len;

    va_start(args, fmt);
    len = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    if (len > 0) {
        Cat1Svr_send_async(&AO_Cat1Svr, (uint8_t *)buf, len);
    }    
}
#endif
