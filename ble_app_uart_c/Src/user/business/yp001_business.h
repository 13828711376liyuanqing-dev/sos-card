/* SAM | 2026-10-13 08:30 +08:00 | Central business state because template pages must follow real services. */
#ifndef YP001_BUSINESS_H
#define YP001_BUSINESS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define UI_CLICK_SILENCE_MS 1000U  /* max single-key hold counted as one tap */
#define UI_CLICK_BURST_MS   800U  /* inactivity after last tap settles chord */
#define UI_SOS_LAG_MS       500U
/* Max taps per settled L/R chord (e.g. "L", "R", "LLL", "RRR", "LRLR"). */
#define YP_KEY_BUF_SIZE     10U


typedef enum { YP_CALL_IDLE, YP_CALL_DIALING, YP_CALL_INCOMING,
               YP_CALL_CONNECTED, YP_CALL_ENDED, YP_CALL_FAILED, YP_CALL_UNKNOWN } yp_call_t;
typedef enum { YP_NET_UNKNOWN, YP_NET_NO_SIM, YP_NET_REGISTERING,
               YP_NET_IP, YP_NET_MQTT, YP_NET_OFFLINE } yp_network_t;
typedef struct {
    bool alarm_active, battery_known, charging, time_known, show_time;
    bool resident_known, imei_known, signal_known, arrears_known, arrears;
    bool searching, sleeping, transport_ready;
    uint8_t battery_percent, signal;
    yp_call_t call;
    yp_network_t network;
    uint32_t now_ms, epoch, revision, alarm_id;
    char imei[16], name[64], room[64], campus[96];
    char date[11], clock[6], weekday[16];
    char notice[64];
} yp_business_status_t;
void yp_business_init(void);
const yp_business_status_t *yp_business_status(void);
/* SAM | 2026-10-23 20:18 +08:00 | Copy only a fresh measured CAT product identity; this is not whole-release confirmation. */
bool yp_business_cat_version(char *version,size_t capacity);
/* SAM | 2026-10-23 +08:00 | OTA consumes fresh measured inputs, never a silent sensor or stale released key as proof of safety. */
typedef struct { bool known,stable,activity; } yp_business_ota_inputs_t;
void yp_business_motion(bool known, bool moving, uint32_t now);
void yp_business_ota_inputs(yp_business_ota_inputs_t *inputs);
/* SAM | 2026-11-07 07:14 +08:00 | Only the physical OTA port supplies live USB proof; sensor ages and activity remain mandatory. */
void yp_business_ota_inputs_with_usb(yp_business_ota_inputs_t *inputs, bool usb_power);
/* SAM | 2026-10-25 +08:00 | Pure clock and evidence APIs cannot send UART or alter samples. */
void yp_business_observation_clock(uint32_t now_ms);
void yp_business_ota_evidence(uint32_t out[5]);
/* SAM | 2026-10-25 +08:00 | Read-only peer provenance distinguishes actual UART loss, timeout and received network changes. */
typedef enum { YP_PEER_INIT=0, YP_PEER_HELLO=1, YP_PEER_LINK_INVALIDATED=2,
               YP_PEER_UART_RX_LOST=3, YP_PEER_RX_TIMEOUT=4,
               YP_PEER_SLEEP_RESTORE=5, YP_PEER_POWER_OFF=6, YP_PEER_NETWORK=16 } yp_peer_source_t;
/* transport,network,last_rx,rx_age,change_ms,source,previous_transport,previous_network,
 * call,last_hello,last_loss_ms,last_loss_source; all fixed-width words, no side effects. */
void yp_business_peer_evidence(uint32_t out[12]);
void yp_business_transport_lost_from(yp_peer_source_t source);
void yp_business_poll(uint32_t now_ms);
/* Sample both physical levels at 10ms cadence; no UART/LVGL work in ISR.
 * Single-key releases append 'L'/'R'; the chord settles after
 * UI_CLICK_BURST_MS with no new key. SOS uses both-key timing. */
void yp_business_keys(bool left, bool right, uint32_t now_ms);
/* Take one settled chord (e.g. "L", "RRR", "LLL", "LRLR"); false when idle. */
bool yp_business_take_sequence(char *buf, size_t cap);
void yp_business_battery(bool known, uint8_t percent, bool charging);
bool yp_business_handle_line(const char *line, size_t length);
void yp_business_transport_lost(void);
bool yp_business_start_alarm(void);
/* SAM | 2026-11-04 +08:00 | QP queue acceptance is separate from CAT1 durable state confirmation. */
bool yp_business_port_sos(bool start);
bool yp_business_sos_start_allowed(void);
void yp_business_sos_stopped(void);
void yp_business_cancel_alarm(void); /* Internal entry only: gesture/platform field unconfirmed. */
/* SAM | 2026-11-07 11:57 +08:00 | Foreground call state update for QP and validated CAT1 events. */
void yp_business_call_set(yp_call_t state);
void yp_business_call_action(bool accept);
void yp_business_show_time(bool enabled);
bool yp_business_set_resident(const char *name, const char *room, const char *campus);
/* SAM | 2026-11-02 +08:00 | Ask CAT1 for glyphs (Unicode code points) the name still cannot draw; false when not sent. */
bool yp_business_request_glyphs(const uint32_t *cps, unsigned count);
/* SAM | 2026-11-03 +08:00 | Remove the resident name (text + glyphs, RAM and NVDS): platform clear and factory reset only. */
void yp_business_clear_resident(void);
void yp_business_factory_reset_name(void);
/* UART port returns queue/driver acceptance, never cloud delivery. */
bool yp_business_port_send(const char *line, size_t length);
/* SAM | 2026-10-13 08:46 +08:00 | Align shared GR RTC with NTP because screen and event timestamps must agree. */
bool yp_business_port_time(uint32_t epoch);
#endif
