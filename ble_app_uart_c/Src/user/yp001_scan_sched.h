#ifndef YP001_SCAN_SCHED_H
#define YP001_SCAN_SCHED_H

#include <stdbool.h>
#include <stdint.h>
#include "AOs.h"

#define YP_SCAN_INTERVAL_BASE_MIN  1U    /* BleScanInterval: 运动时扫描间隔(分钟) */
#define YP_SCAN_INTERVAL_MAX_MIN   5U    /* 连续失锁间隔上限(分钟) */
#define YP_SCAN_WINDOW_SEC         10U    /* BleScanPeriod: 单次扫描窗口时长(秒) */
#define YP_SCAN_REPORT_EVERY       60U   /* 主触发: 未发送扫描累计 60 条开始逐条上报 */
#define YP_SCAN_HISTORY_CAP        10U //64U   /* 环形队列容量: 扫描到立即发送，容量降低 */
#define YP_SCAN_PERIODIC_FALLBACK_MIN 1U//60U /* PeriodicPara: 时间周期兜底上限(分钟) */
#define YP_SCAN_BATTERY_STOP_PCT   10U   /* PowerThreshold: 电量 < 该百分比停止周期上报 */
#define YP_SCAN_BATTERY_HYST_PCT   2U   /* 电量滞回：回升到 stop+2% 才恢复周期，防临界抖动反复启停 */
#define YP_SCAN_MSG_BUDGET         2000U /* 单包字节兜底 */
#define YP_SCAN_POLL_INTERVAL_MS   30U  /* 调度/逐条发送：30ms/条，60 条约 1.8s 发完 */
#define YP_TX_SEND_RETRY_COUNT     3U  /* 发送失败重试次数 */

/* SAM | 2026-11-07 12:17 +08:00 | Foreground leases for shared SOS/find-device and manual scan requests. */
#define YP_SCAN_HOLD_LOCATION 1U
#define YP_SCAN_HOLD_MANUAL   2U
void yp_scan_sched_radio_hold(uint8_t owner, bool hold);
void yp_scan_sched_on_radio_stop(bool stopped);
void yp_scan_sched_init(void);
void yp_scan_sched_set_enabled(bool on);
bool yp_scan_sched_enabled(void);
void yp_scan_sched_poll(uint32_t now_ms);
void yp_scan_sched_on_adv_report(void const *p_adv);
bool yp_scan_sched_report_pending(bool bForce);

extern char *get_topic(locasvc_locate_type locate_type, char *imei);
extern char *get_msg_type(locasvc_locate_type locate_type);
extern bool ble_phone_connected(void);

#endif /* YP001_SCAN_SCHED_H */
