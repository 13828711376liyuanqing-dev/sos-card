/* SAM | 2026-10-13 08:40 +08:00 | F-001/F-002/F-013/F-022/F-023: own application state on GR because network/call/UI acknowledgements are different evidence. */
#include "yp001_business.h"
#include "yp001_key_call.h"
#include "cJSON.h"
#include "gr55xx_nvds.h"
#include "gr55xx.h"
#include <stdio.h>
#include <string.h>
#include "AOs.h"
#include "yp_name_glyphs.h"
#include <stdlib.h>

#define TEST_DATA  1
#define YP_NVDS_TAG_IMEI NV_TAG_APP(0x0001)
#define YP_NVDS_TAG_RESIDENT NV_TAG_APP(0x0002)
#define KEY_IDLE_MS 0xFFFFFFFFU

typedef struct { char name[64]; char room[64]; char campus[96]; } yp_resident_nv_t;

static yp_business_status_t s;
/* SAM | 2026-11-03 +08:00 | Resident name push transaction; last_seq is restored from NVDS at init. */
static struct { uint32_t id, seq, last_seq; char name[64], room[64], campus[96]; bool open; } name_txn;
static bool alarm_pending, cancel_pending, battery_pending, hello_due;
/* SAM | 2026-11-04 +08:00 | Retry queue admission, never a successfully queued QP dial. */
static bool sos_start_due, sos_started, sos_stop_due, sos_stop_waiting;
/* SAM | 2026-11-03 +08:00 | Set once yp_business_init() has restored NVDS; battery samples can arrive earlier during BSP_start. */
static bool s_inited;
static uint32_t last_hello, last_rx, last_alarm, last_cancel, clock_ms;
/* SAM | 2026-10-25 +08:00 | Volatile transition history survives partial hello resync, without touching readiness or user data. */
static struct {
    uint32_t change_ms, source, previous_transport, previous_network, last_loss_ms, last_loss_source;
    bool transport;
    yp_network_t network;
} peer_history;
static void peer_changed(uint32_t source)
{
    if(peer_history.transport==s.transport_ready&&peer_history.network==s.network)return;
    peer_history.previous_transport=peer_history.transport;
    peer_history.previous_network=peer_history.network;
    peer_history.transport=s.transport_ready;peer_history.network=s.network;
    peer_history.change_ms=s.now_ms;peer_history.source=source;
}
/* SAM | 2026-10-23 20:18 +08:00 | Keep measured CAT source identity separate from GR and expire it even when other UART traffic continues. */
static char cat_product_version[12];
static uint32_t cat_version_ms;
static bool version_text(const char *v)
{
    unsigned fields=0,digits=0,value=0;
    if(!v||strlen(v)>11)return false;
    while(*v){
        if(*v>='0'&&*v<='9'){value=value*10u+(unsigned)(*v-'0');if(++digits>3u||value>999u)return false;}
        else if(*v=='.'&&digits&&fields<2u){++fields;digits=0;value=0;}
        else return false;
        ++v;
    }
    return fields==2u&&digits>0;
}
bool yp_business_cat_version(char *version,size_t capacity)
{
    size_t n=strlen(cat_product_version)+1u;
    if(!version||!s.transport_ready||!cat_product_version[0]||
       (uint32_t)(s.now_ms-cat_version_ms)>20000u||capacity<n)return false;
    memcpy(version,cat_product_version,n);return true;
}
static bool alarm_sent, cancel_sent;
/* Written only by the 10ms sampler, consumed in foreground; aligned 32-bit
 * sequence avoids losing an edge when the foreground consumes a request. */
static volatile uint32_t key_requests;
static uint32_t consumed_keys;
static char s_key_buf[YP_KEY_BUF_SIZE + 1];
static uint32_t s_last_release_ms = KEY_IDLE_MS; /* last tap release time */
static volatile bool s_key_settle_req;           /* chord ready for the UI */

static uint32_t s_left_ms = KEY_IDLE_MS, s_right_ms = KEY_IDLE_MS;
static uint32_t sos_ms = KEY_IDLE_MS;
/* SAM | 2026-11-07 11:39 +08:00 | Latch a held SOS chord until release because cancellation must not rearm the same press. */
static bool sos_segment_latched;
/* SAM | 2026-11-06 +08:00 | One press of the left or right key answers an incoming call / hangs up a dialing or connected one. */
static yp_keycall_t s_keycall;
static bool s_left_raw, s_right_raw;       /* previous 10ms sample */
static bool s_left_stable, s_right_stable; /* last confirmed level */
static bool s_motion_saw_activity;
/* SAM | 2026-10-13 08:55 +08:00 | Sequence mailbox avoids losing ISR writes during foreground read/clear. */
static volatile uint32_t call_request;
static uint32_t consumed_call;
/* SAM | 2026-10-23 +08:00 | Conservative local OTA qualification: fresh measurements and 60s continuous quiet; no platform-configurable bypass. */
static volatile bool ota_keys_seen,ota_key_down;
static volatile uint32_t ota_keys_ms;
static bool ota_battery_seen,ota_motion_seen,ota_moving;
static uint32_t ota_battery_ms,ota_motion_ms;
static volatile uint32_t ota_quiet_ms;
/* SAM | 2026-10-28 17:10 +08:00 | Default the USB bench switch to production (0) because this module must not depend on OTA headers; only explicitly marked bench builds set it. */
#ifndef YP001_OTA_USB_BENCH_TEST
#define YP001_OTA_USB_BENCH_TEST 0
#endif

static void changed(void) { ++s.revision; }
static void notice(const char *text) {
    if (strcmp(s.notice, text)) {
        (void)snprintf(s.notice, sizeof(s.notice), "%s", text);
        changed();
    }
}
static const char *str(cJSON *j, const char *key) {
    cJSON *p = cJSON_GetObjectItemCaseSensitive(j,key);
    return cJSON_IsString(p) ? p->valuestring : NULL;
}
static bool number(cJSON *j, const char *key, uint32_t max, uint32_t *v) {
    cJSON *p = cJSON_GetObjectItemCaseSensitive(j,key);
    if (!cJSON_IsNumber(p) || !(p->valuedouble >= 0.0) ||
        !(p->valuedouble <= (double)max)) return false;
    *v = (uint32_t)p->valuedouble;
    return p->valuedouble == (double)*v;
}
static bool integer(cJSON *j, const char *key, int32_t min, int32_t max, int32_t *v) {
    cJSON *p = cJSON_GetObjectItemCaseSensitive(j,key);
    if (!cJSON_IsNumber(p) || !(p->valuedouble >= (double)min) || !(p->valuedouble <= (double)max)) return false;
    *v = (int32_t)p->valuedouble;
    return p->valuedouble == (double)*v;
}
static bool valid_imei(const char *p) {
    if (!p || strlen(p) != IMEI_BUF_LEN) return false;
    for (unsigned i=0; i<IMEI_BUF_LEN; ++i) if (p[i] < '0' || p[i] > '9') return false;
    return true;
}

void imei_persist(void)
{
    uint16_t len = IMEI_BUF_LEN;
    uint8_t old[16] = {0};
	uint8_t err = 0;
    if (!valid_imei(s.imei)) return;
    if (nvds_get(YP_NVDS_TAG_IMEI, &len, old) == NVDS_SUCCESS &&
        len == IMEI_BUF_LEN && memcmp(old, s.imei, sizeof(old)) == 0) return;
    err = nvds_put(YP_NVDS_TAG_IMEI, strlen(s.imei), (const uint8_t *)s.imei);
	printf("imei_persist IMEI = %s,err = %d",s.imei,err);
}

static void imei_restore(void)
{
    uint16_t len = IMEI_BUF_LEN;
    uint8_t buf[16] = {0};
	uint8_t err = 0;
	err = nvds_get(YP_NVDS_TAG_IMEI, &len, buf);
	printf("imei_restore err = %d",err);
    if (err != NVDS_SUCCESS)
	{
		return;
	}
	printf("imei_restore IMEI = %s",buf);
    if (len != IMEI_BUF_LEN || !valid_imei((const char *)buf)) return;
    if (!s.imei_known || strcmp(s.imei, (const char *)buf)) {
        memcpy(s.imei, buf, sizeof(buf));
        s.imei_known = true;
        changed();
    }
}

static void resident_persist(void)
{
    /* SAM | 2026-11-03 +08:00 | Name alone is enough to keep: room/campus may legitimately be empty. */
    if (!s.resident_known || !s.name[0]) return;
    yp_resident_nv_t rec;
    memcpy(rec.name, s.name, sizeof(rec.name));
    memcpy(rec.room, s.room, sizeof(rec.room));
    memcpy(rec.campus, s.campus, sizeof(rec.campus));
    /* SAM | 2026-11-03 +08:00 | nvds_get() p_len is in/out: it must carry the buffer size (0 always failed on the board). */
    uint16_t len = sizeof(rec);
    uint8_t old[sizeof(rec)] = {0};
    if (nvds_get(YP_NVDS_TAG_RESIDENT, &len, old) == NVDS_SUCCESS &&
        len == sizeof(rec) && memcmp(old, &rec, sizeof(rec)) == 0) return;
    (void)nvds_put(YP_NVDS_TAG_RESIDENT, sizeof(rec), (const uint8_t *)&rec);
}

static void resident_restore(void)
{
    /* SAM | 2026-11-03 +08:00 | Bench 11-03: len 0 made every restore fail, so the name was lost on each reboot. */
    uint16_t len = sizeof(yp_resident_nv_t);
    uint8_t buf[sizeof(yp_resident_nv_t)] = {0};
    if (nvds_get(YP_NVDS_TAG_RESIDENT, &len, buf) != NVDS_SUCCESS) return;
    if (len != sizeof(buf)) return;
    const yp_resident_nv_t *rec = (const yp_resident_nv_t *)buf;
    if (!rec->name[0]) return;
    memcpy(s.name, rec->name, sizeof(s.name));
    memcpy(s.room, rec->room, sizeof(s.room));
    memcpy(s.campus, rec->campus, sizeof(s.campus));
    s.resident_known = true;
    changed();
}
/* SAM | 2026-11-04 +08:00 | Keep alarm ID/ACK synchronization while suppressing the legacy CAT1 dial. */
static bool send(const char *op, uint32_t id) {
    char line[160];

    int n = snprintf(line, sizeof(line),
        "BUS_CMD={\"op\":\"%s\",\"id\":%lu,\"known\":%s,\"battery\":%u%s}\r\n",
        op, (unsigned long)id, s.battery_known ? "true":"false", s.battery_percent,
        !strcmp(op,"alarm") ? ",\"dial\":false" : "");
    return n > 0 && (size_t)n < sizeof(line) && yp_business_port_send(line,(size_t)n);
}
/* No libc timezone dependency: customer local screen time is UTC+08:00;
 * event epoch remains UTC seconds. Clock validity only comes from NTP. */
static void format_clock(void) {
    static const unsigned month_days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    static const char *week[] = {"SUN","MON","TUE","WED","THU","FRI","SAT"};
    uint32_t local = s.epoch + 8U*3600U;
    uint32_t days = local / 86400U, day = days;
    unsigned year=1970, month=0;
    for (;;) {
        unsigned count = (year%4==0 && (year%100!=0 || year%400==0)) ? 366U:365U;
        if (day<count) break;
        day-=count; ++year;
    }
    for (;;) {
        unsigned count=month_days[month];
        if (month==1 && year%4==0 && (year%100!=0 || year%400==0)) ++count;
        if (day<count) break;
        day-=count; ++month;
    }
    char date[11], clock[6];
    (void)snprintf(date,sizeof(date),"%04u-%02u-%02u",year,month+1,(unsigned)day+1);
    (void)snprintf(clock,sizeof(clock),"%02u:%02u",(unsigned)(local%86400U/3600U),(unsigned)(local%3600U/60U));
    if (strcmp(date,s.date) || strcmp(clock,s.clock)) {
        memcpy(s.date,date,sizeof(date)); memcpy(s.clock,clock,sizeof(clock));
        (void)snprintf(s.weekday,sizeof(s.weekday),"%s",week[(days+4)%7]);
        changed();
    }
}
void yp_business_init(void) {
    memset(&s,0,sizeof(s)); s.show_time=true; s.revision=1; s.call=YP_CALL_UNKNOWN;
    /* SAM | 2026-10-25 +08:00 | A new runtime cannot inherit peer provenance from an earlier session. */
    memset(&peer_history,0,sizeof peer_history);
    /* SAM | 2026-10-23 20:18 +08:00 | Reinitialization cannot retain a previous CAT session's identity. */
    cat_product_version[0]=0;cat_version_ms=0;
    alarm_pending=cancel_pending=battery_pending=alarm_sent=cancel_sent=false;
    /* SAM | 2026-11-04 +08:00 | Reinitialize the QP admission/cancellation mailbox with business state. */
    sos_start_due=sos_started=sos_stop_due=sos_stop_waiting=false;
    hello_due=true; last_hello=last_rx=last_alarm=clock_ms=0;
    key_requests=consumed_keys=0; call_request=consumed_call=0; last_cancel=0;
    s_left_ms=s_right_ms=sos_ms=KEY_IDLE_MS;
    /* SAM | 2026-11-07 11:39 +08:00 | Clear the chord latch with the key sampler at initialization. */
    sos_segment_latched=false;
    yp_keycall_init(&s_keycall);
    s_key_buf[0]='\0'; s_last_release_ms=KEY_IDLE_MS; s_key_settle_req=false;
    s_left_raw=s_right_raw=false; s_left_stable=s_right_stable=false;
    ota_keys_seen=ota_key_down=ota_battery_seen=ota_motion_seen=false;ota_moving=true;
    imei_restore();
    resident_restore();
    /* SAM | 2026-11-03 +08:00 | Restore the stored name glyphs; their Seq is the floor for later pushes. */
    { uint32_t seq=0; if (yp_ng_load(&seq)) name_txn.last_seq=seq; }
    s_inited=true;
}
const yp_business_status_t *yp_business_status(void) { return &s; }
void yp_business_keys(bool left, bool right, uint32_t now) {
    size_t len;
    ota_keys_ms=now;ota_key_down=left||right;ota_keys_seen=true;
    /* SAM | 2026-10-28 19:47 +08:00 | Bench builds stop keys from restarting OTA quiet time because a touch during an authorized bench OTA restarted the 60s commit and 120s TRIAL windows (user decision); alarm/call still block via their own gates. Production unchanged. */
    if((left||right)&&!YP001_OTA_USB_BENCH_TEST)ota_quiet_ms=now;
    if (left != s_left_raw) {
        s_left_raw = left;
        left = s_left_stable;
    } else {
        s_left_stable = left;
    }
    if (right != s_right_raw) {
        s_right_raw = right;
        right = s_right_stable;
    } else {
        s_right_stable = right;
    }

    /* SAM | 2026-11-06 +08:00 | Call keys (user requirement): incoming + one press (left or right) = answer; dialing or connected +
     * one press = hang up. Uses the existing UART call path (call_request -> BUS_CMD accept/hangup -> CAT1 SIP). */
    {
        yp_keycall_action_t act=yp_keycall_step(&s_keycall,left,right,now,
            s.call==YP_CALL_INCOMING,s.call==YP_CALL_DIALING||s.call==YP_CALL_CONNECTED);
        if (act==YP_KEYCALL_ACCEPT) yp_business_call_action(true);
        else if (act==YP_KEYCALL_HANGUP) yp_business_call_action(false);
    }

    /* Consume a finished chord after a burst of inactivity. */
    if (s_key_buf[0] != '\0' && s_last_release_ms != KEY_IDLE_MS &&
        (uint32_t)(now - s_last_release_ms) >= UI_CLICK_BURST_MS) {
        s_key_settle_req = true;
        s_last_release_ms = KEY_IDLE_MS; /* latch once until the UI takes it */
    }

    /* SAM | 2026-11-07 11:39 +08:00 | Adapt the donor latch to our sequence mailbox and debounced key levels. */
    if (left && right) {
        if (s_left_ms != KEY_IDLE_MS && s_right_ms != KEY_IDLE_MS) {
            uint32_t press_lag = (s_left_ms > s_right_ms) ?
                                 (s_left_ms - s_right_ms) : (s_right_ms - s_left_ms);
            if (press_lag <= UI_SOS_LAG_MS) {
                if (sos_ms == KEY_IDLE_MS) sos_ms = now;
                else if (!sos_segment_latched && (uint32_t)(now - sos_ms) >= 2800U) {
                    sos_segment_latched = true; ++key_requests;
                }
            } else {
                sos_ms = KEY_IDLE_MS;
            }
        }
    } else {
        sos_ms = KEY_IDLE_MS;
        sos_segment_latched = false;
    }

    /* Left release: one tap appended as 'L'. */
    if (!left && s_left_ms != KEY_IDLE_MS) {
        if (yp_keycall_swallow(&s_keycall, true)) {
            /* answered or hung up with this key: not a tap */
        } else if ((uint32_t)(now - s_left_ms) < UI_CLICK_SILENCE_MS) {
            if (s_key_settle_req) { s_key_settle_req = false; s_key_buf[0] = '\0'; }
            len = strlen(s_key_buf);
            if (len >= YP_KEY_BUF_SIZE) s_key_buf[0] = '\0'; /* full: restart */
            len = strlen(s_key_buf);
            s_key_buf[len] = 'L'; s_key_buf[len + 1U] = '\0';
            s_last_release_ms = now;
        } else {
            s_key_buf[0] = '\0';
        }
        s_left_ms = KEY_IDLE_MS;
    }
    /* Right release: one tap appended as 'R'. */
    if (!right && s_right_ms != KEY_IDLE_MS) {
        if (yp_keycall_swallow(&s_keycall, false)) {
            /* answered or hung up with this key: not a tap */
        } else if ((uint32_t)(now - s_right_ms) < UI_CLICK_SILENCE_MS) {
            if (s_key_settle_req) { s_key_settle_req = false; s_key_buf[0] = '\0'; }
            len = strlen(s_key_buf);
            if (len >= YP_KEY_BUF_SIZE) s_key_buf[0] = '\0'; /* full: restart */
            len = strlen(s_key_buf);
            s_key_buf[len] = 'R'; s_key_buf[len + 1U] = '\0';
            s_last_release_ms = now;
        } else {
            s_key_buf[0] = '\0';
        }
        s_right_ms = KEY_IDLE_MS;
    }

    if (left && s_left_ms == KEY_IDLE_MS) s_left_ms = now;
    if (right && s_right_ms == KEY_IDLE_MS) s_right_ms = now;
}

bool yp_business_take_sequence(char *buf, size_t cap)
{
    bool got = false;
    if (buf == NULL || cap == 0U) return false;
    buf[0] = '\0';
    /* Snapshot one settled chord under interrupt lock; only a real chord is
     * taken, so the UI interaction timer stays accurate. */
    __disable_irq();
    if (s_key_settle_req && s_key_buf[0] != '\0') {
        s_key_settle_req = false;
        (void)snprintf(buf, cap, "%s", s_key_buf);
        s_key_buf[0] = '\0';
        got = true;
    } else {
        s_key_settle_req = false; /* clear a stale latch defensively */
    }
    __enable_irq();
    return got;
}
/* SAM | 2026-11-04 +08:00 | QP owns the call; CAT1 alarm frames only persist state and publish SOS. */
bool yp_business_start_alarm(void) {
    if (s.alarm_active || sos_stop_due || sos_stop_waiting) return false;
    s.alarm_active=true; s.alarm_id=0; s.sleeping=false;
    alarm_pending=true; alarm_sent=false;
    sos_start_due=true; sos_started=false;
    notice("ALARM PENDING"); changed();
    return true;
}
bool yp_business_sos_start_allowed(void) {
    return s.alarm_active && !cancel_pending;
}
/* SAM | 2026-11-04 +08:00 | Drain the previous QP stop before a new alarm can reuse queued start events. */
void yp_business_sos_stopped(void) {
    sos_stop_waiting=false;
}
void yp_business_cancel_alarm(void) {
    if (s.alarm_active && !cancel_pending) {
        cancel_pending=true; cancel_sent=false;
        sos_start_due=false; sos_stop_due=sos_started;
        /* SAM | 2026-11-04 +08:00 | Keep alarm active until the matching durable CAT1 cancellation arrives. */
        notice("ALARM CANCELLING"); changed();
    }
}
/* SAM | 2026-11-07 11:57 +08:00 | Share QP and CAT1 display state updates because call completion must preserve the alarm. */
void yp_business_call_set(yp_call_t state) {
    if (s.call != state) { s.call=state; changed(); }
}
void yp_business_call_action(bool accept) { call_request=((call_request+4U)&~3U)|(accept ? 1U:2U); }
void yp_business_show_time(bool enabled) {
    if (s.show_time != enabled) { s.show_time=enabled; changed(); }
}
bool yp_business_set_resident(const char *name,const char *room,const char *campus) {
    if (!name || !room || !campus || !name[0] || strlen(name)>=sizeof(s.name) ||
        strlen(room)>=sizeof(s.room) || strlen(campus)>=sizeof(s.campus)) return false;
    /* Atomic RAM view only; persistence/authorized platform fields are separate. */
    strcpy(s.name,name); strcpy(s.room,room); strcpy(s.campus,campus);
    s.resident_known=true; changed();
    resident_persist();
    return true;
}
void yp_business_battery(bool known,uint8_t percent,bool charging) {
    ota_battery_seen=true;ota_battery_ms=s.now_ms;
    known=known && percent<=100U;
    /* SAM | 2026-11-07 07:08 +08:00 | Keep measured battery validity/percent because OTA gates share this state, including TEST_DATA builds. */
#ifdef TEST_DATA
    strcpy(s.imei, "860123456789024");
    strcpy(s.date, "2026-10-18");
    strcpy(s.clock, "10:28");
    strcpy(s.weekday, "SUN");
    s.imei_known = true;
    s.time_known = true;
    s.show_time = true;
    //imei_persist();
	/* SAM | 2026-11-02 +08:00 | Test name only fills an empty slot because it re-ran on every battery sample and overwrote platform-pushed names. */
	/* SAM | 2026-11-03 +08:00 | Bench 11-03: a battery sample before yp_business_init() saw no name and persisted the test name over
	 * the pushed one (NVDS order: pushed record, glyphs, then the test record). Wait for init, and keep the test name in RAM only. */
	if (s_inited && !s.resident_known) {
	    strcpy(s.name, "\xE5\xBC\xA0\xE7\xA7\x80\xE8\x8A\xB3"); strcpy(s.room, "1#1-102");
	    strcpy(s.campus, "\xE6\xB3\xB0\xE5\xBA\xB7\xE4\xB9\x8B\xE5\xAE\xB6\xC2\xB7\xE7\x87\x95\xE5\x9B\xAD");
	    s.resident_known = true; changed();
	}
#endif
    if (s.battery_known!=known || (known && s.battery_percent!=percent) || s.charging!=charging) {
        s.battery_known=known; s.battery_percent=known ? percent:0;
        s.charging=charging; battery_pending=true; changed();
    }
}
/* SAM | 2026-10-30 19:56 +08:00 | OTA motion input comes from the colleague's own judgement (yp_motion_*: motion-interrupt pin with the configured still time),
 * so there is one motion source. Bench builds (YP001_OTA_USB_BENCH_TEST=1) do not let motion block an authorized OTA. */
void yp_business_motion(bool known,bool moving,uint32_t now)
{
    if(!known){ota_motion_seen=false;ota_moving=true;ota_quiet_ms=now;return;}
    if(YP001_OTA_USB_BENCH_TEST)moving=false;
    if(moving)ota_quiet_ms=now;
    ota_motion_seen=true;ota_moving=moving;ota_motion_ms=now;
}
static bool ota_fresh(uint32_t now,uint32_t sample,uint32_t limit)
{
    int32_t age=(int32_t)(now-sample);
    /* IRQ sampling may be slightly newer than this foreground snapshot. */
    return age>= -100 && (age<0 || (uint32_t)age<=limit);
}
/* SAM | 2026-11-07 07:14 +08:00 | Healthy measured USB can replace unknown battery, never missing/stale observations or activity checks. */
void yp_business_ota_inputs_with_usb(yp_business_ota_inputs_t *v,bool usb_power)
{
    /* SAM | 2026-10-24 22:58 +08:00 | Use the newer real ISR/foreground observation clock because UART processing can precede the next foreground poll; never refresh a sensor timestamp or relax its age limit. */
    uint32_t now=s.now_ms;
    if(!v)return;
    if(ota_keys_seen&&(int32_t)(ota_keys_ms-now)>0)now=ota_keys_ms;
    v->known=ota_battery_seen&&(s.battery_known||usb_power)&&ota_fresh(now,ota_battery_ms,3000u)&&
        ota_keys_seen&&ota_fresh(now,ota_keys_ms,100u)&&ota_motion_seen&&ota_fresh(now,ota_motion_ms,1500u);
    /* SAM | 2026-10-28 19:47 +08:00 | Bench builds exclude held keys and queued key/call-action requests from OTA activity (see yp_business_keys); a dual-key SOS still raises alarm_active, which the OTA gates reject. */
    v->activity=(!YP001_OTA_USB_BENCH_TEST&&(ota_key_down||key_requests!=consumed_keys||call_request!=consumed_call))||
        ota_moving||s.searching||s.sleeping;
    if(v->activity)ota_quiet_ms=now;
    v->stable=v->known&&!v->activity&&(int32_t)(now-ota_quiet_ms)>=60000;
}
/* SAM | 2026-11-07 07:14 +08:00 | Existing callers without physical USB evidence keep the battery-known contract. */
void yp_business_ota_inputs(yp_business_ota_inputs_t *v) { yp_business_ota_inputs_with_usb(v,false); }
/* SAM | 2026-10-25 +08:00 | Preserve the specific invalidation source; the existing fail-closed behavior is unchanged. */
void yp_business_transport_lost_from(yp_peer_source_t source) {
    /* SAM | 2026-10-23 20:18 +08:00 | A new CAT session must prove its own source version again. */
    cat_product_version[0]=0;
    s.transport_ready=false; s.network=YP_NET_UNKNOWN; s.signal_known=false; s.call=YP_CALL_UNKNOWN;
    peer_history.last_loss_ms=s.now_ms;peer_history.last_loss_source=source;
    peer_changed(source);
    notice("CAT1 LINK UNKNOWN"); hello_due=true; changed();
    /* Do not equate a lost link with a terminated call or cancelled alarm. */
}
void yp_business_transport_lost(void) { yp_business_transport_lost_from(YP_PEER_LINK_INVALIDATED); }
/* SAM | 2026-10-25 +08:00 | Observation clock updates do not dispatch business or refresh sensor timestamps. */
void yp_business_observation_clock(uint32_t now) { s.now_ms=now; }
void yp_business_ota_evidence(uint32_t out[5])
{
    uint32_t now=s.now_ms,keys=ota_keys_ms;
    if(ota_keys_seen&&(int32_t)(keys-now)>0)now=keys;
    out[0]=now;out[1]=now-ota_battery_ms;out[2]=now-keys;out[3]=now-ota_motion_ms;
    out[4]=(ota_battery_seen?1u:0u)|(s.battery_known?2u:0u)|(ota_keys_seen?4u:0u)|
        (ota_motion_seen?8u:0u)|(ota_key_down?16u:0u)|(ota_moving?32u:0u);
}
/* SAM | 2026-10-25 +08:00 | Snapshot only; getters must never refresh last_rx or manufacture network readiness. */
void yp_business_peer_evidence(uint32_t out[12])
{
    out[0]=s.transport_ready;out[1]=s.network;out[2]=last_rx;out[3]=s.now_ms-last_rx;
    out[4]=peer_history.change_ms;out[5]=peer_history.source;
    out[6]=peer_history.previous_transport;out[7]=peer_history.previous_network;
    out[8]=s.call;out[9]=last_hello;
    out[10]=peer_history.last_loss_ms;out[11]=peer_history.last_loss_source;
}
void yp_business_poll(uint32_t now) {
    s.now_ms=now;
    if (key_requests!=consumed_keys) {
        consumed_keys=key_requests;
        /* SAM | 2026-11-04 +08:00 | A repeated SOS gesture cannot cancel or redial an active alarm (F-001). */
        if (!s.alarm_active) (void)yp_business_start_alarm();
    }
    if (s.time_known) {
        uint32_t elapsed=(uint32_t)(now-clock_ms)/1000U;
        if (elapsed) { s.epoch+=elapsed; clock_ms+=elapsed*1000U; format_clock(); }
    }
    /* SAM | 2026-10-25 +08:00 | Identify the existing 20s timeout separately from physical UART loss. */
    if (s.transport_ready && (uint32_t)(now-last_rx)>20000U) yp_business_transport_lost_from(YP_PEER_RX_TIMEOUT);
    if (hello_due || (uint32_t)(now-last_hello)>=5000U) {
        last_hello=now; hello_due=false;
        if (!send("hello",0)) notice("CAT1 UART UNAVAILABLE");
    }
    /* SAM | 2026-11-04 +08:00 | Stop QP locally even during UART loss; a full queue keeps cancellation pending. */
    if (sos_stop_due) {
        sos_stop_waiting=true;
        if (yp_business_port_sos(false)) {
            sos_stop_due=false; sos_started=false;
        } else sos_stop_waiting=false;
    }
    /* SAM | 2026-11-04 +08:00 | Admit QP SOS before UART readiness so the existing sleep/wake path can start. */
    if (sos_start_due && !cancel_pending && yp_business_port_sos(true)) {
        sos_start_due=false; sos_started=true;
    }
    if (!s.transport_ready) { consumed_call=call_request; return; }
    if (alarm_pending && (!alarm_sent || (uint32_t)(now-last_alarm)>=2000U)) {
        last_alarm=now; alarm_sent=true;
        if (!send("alarm",s.alarm_id)) notice("ALARM UART RETRY");
    }
    /* SAM | 2026-10-13 08:55 +08:00 | UART acceptance is not durable cancellation; retry the same identity until peer confirms. */
    if (cancel_pending && !sos_stop_due && s.alarm_id && (!cancel_sent || (uint32_t)(now-last_cancel)>=2000U)) {
        last_cancel=now; cancel_sent=true;
        if (!send("cancel",s.alarm_id)) notice("CANCEL UART RETRY");
    }
    uint32_t request=call_request;
    uint8_t action=request!=consumed_call ? (uint8_t)(request&3U):0;
    consumed_call=request;
    if (action && ((action==1 && s.call==YP_CALL_INCOMING) ||
        (action==2 && (s.call==YP_CALL_DIALING || s.call==YP_CALL_INCOMING || s.call==YP_CALL_CONNECTED)))) {
        if (!send(action==1 ? "accept":"hangup",s.alarm_id)) notice("CALL UART FAILED");
    }
    if (battery_pending && send("battery",0)) battery_pending=false;
}
/* SAM | 2026-11-02 +08:00 | Resident name push (name_begin / glyph x g / name_end). The name text keeps the existing
 * NVDS persistence; glyphs stay RAM-only, so after reboot the UI asks CAT1 to re-fetch them (NAME_RES need). */
static void name_result(uint32_t id, unsigned err, unsigned index) {
    char line[96];
    int n = snprintf(line, sizeof(line), "NAME_RES={\"op\":\"result\",\"id\":%lu,\"ok\":%s,\"err\":%u,\"i\":%u}\r\n",
                     (unsigned long)id, err ? "false" : "true", err, index);
    if (n > 0 && (size_t)n < sizeof(line)) (void)yp_business_port_send(line, (size_t)n);
}
static bool hex_field(cJSON *j, const char *key, size_t min, size_t max, uint32_t *v) {
    const char *t = str(j,key); char *end;
    if (!t || strlen(t) < min || strlen(t) > max) return false;
    *v = (uint32_t)strtoul(t, &end, 16);
    return *end == '\0';
}
static void name_line(cJSON *j, const char *op) {
    uint32_t id, v, count;
    if (!number(j,"id",0xffffffffU,&id)) return;
    if (!strcmp(op,"name_begin")) {
        const char *name=str(j,"name"), *room=str(j,"room"), *campus=str(j,"campus");
        name_txn.open=false;
        /* SAM | 2026-11-03 +08:00 | g may be 0: an English (ASCII) name is drawn with the built-in font. */
        if (!number(j,"g",YP_NG_MAX,&count) || !number(j,"seq",0xffffffffU,&v) || !name || !room || !campus ||
            !name[0] || strlen(name)>=sizeof(name_txn.name) || strlen(room)>=sizeof(name_txn.room) ||
            strlen(campus)>=sizeof(name_txn.campus)) { name_result(id,YP_NG_BAD,0); return; }
        if (v < name_txn.last_seq) { name_result(id,YP_NG_TXN,0); return; }
        strcpy(name_txn.name,name); strcpy(name_txn.room,room); strcpy(name_txn.campus,campus);
        name_txn.id=id; name_txn.seq=v; name_txn.open=true;
        yp_ng_begin(id,count);
    } else if (!strcmp(op,"glyph")) {
        yp_ng_t g; int32_t x, y; uint32_t i, u, sz, w, h, a, c; const char *d=str(j,"d");
        if (!name_txn.open || id!=name_txn.id) { name_result(id,YP_NG_TXN,0); return; }
        if (!number(j,"i",YP_NG_MAX-1U,&i) || !number(j,"s",32U,&sz) || !number(j,"w",40U,&w) || !number(j,"h",40U,&h) ||
            !integer(j,"x",-40,40,&x) || !integer(j,"y",-40,40,&y) || !number(j,"a",640U,&a) || !d ||
            !hex_field(j,"u",2U,6U,&u) || !hex_field(j,"c",4U,4U,&c)) { name_txn.open=false; name_result(id,YP_NG_BAD,0); return; }
        g.u=u; g.size=(uint8_t)sz; g.w=(uint8_t)w; g.h=(uint8_t)h; g.x=(int8_t)x; g.y=(int8_t)y; g.adv_w=(uint16_t)a;
        yp_ng_err_t e=yp_ng_add(id,i,&g,d,(uint16_t)c);
        if (e) { name_txn.open=false; name_result(id,e,i); }
    } else {
        if (!name_txn.open || id!=name_txn.id || !number(j,"g",YP_NG_MAX,&count)) { name_result(id,YP_NG_TXN,0); return; }
        name_txn.open=false;
        yp_ng_err_t e=yp_ng_commit(id,count);
        if (!e && !yp_business_set_resident(name_txn.name,name_txn.room,name_txn.campus)) e=YP_NG_BAD;
        if (!e) { name_txn.last_seq=name_txn.seq; changed(); }
        /* SAM | 2026-11-03 +08:00 | Keep the shown set for good; a storage failure is reported (err 6) but the RAM copy stays shown. */
        if (!e && !yp_ng_save(name_txn.seq)) { name_result(id,6U,0); return; }
        name_result(id,e,0);
    }
}
/* SAM | 2026-11-03 +08:00 | The only two ways the resident name goes away: platform clear (op name_clear) and factory reset.
 * Reboot, power loss, OTA and silence keep it. */
void yp_business_clear_resident(void) {
    yp_ng_clear();
    (void)nvds_del(YP_NVDS_TAG_RESIDENT);
    s.name[0]=s.room[0]=s.campus[0]=0;
    s.resident_known=false;
    name_txn.open=false; name_txn.last_seq=0;
    changed();
}
void yp_business_factory_reset_name(void) { yp_business_clear_resident(); }
/* SAM | 2026-11-02 +08:00 | Ask CAT1 to re-fetch glyphs that neither the local fonts nor the RAM cache can draw. */
bool yp_business_request_glyphs(const uint32_t *cps, unsigned count) {
    char line[200]; int n=snprintf(line,sizeof(line),"NAME_RES={\"op\":\"need\",\"u\":\"");
    if (!s.transport_ready || !count || n<=0) return false;
    for (unsigned i=0; i<count && (size_t)n+8U<sizeof(line); ++i)
        n+=snprintf(line+n,sizeof(line)-(size_t)n,"%s%04lX",i?",":"",(unsigned long)cps[i]);
    n+=snprintf(line+n,sizeof(line)-(size_t)n,"\"}\r\n");
    return n>0 && (size_t)n<sizeof(line) && yp_business_port_send(line,(size_t)n);
}
/* Flat typed event envelope: depth/duplicate keys rejected before any mutation.
 * Limits are independent from the UART ring capacity. No platform commands or
 * JSON strings may become CLI commands. */
bool yp_business_handle_line(const char *line,size_t length) {
    char text[512]; cJSON *j,*a,*b;
    if (!line || length<8 || memcmp(line,"BUS_EVT=",8)) return false;
    if (length<=8 || length-8>=sizeof(text) || memchr(line,0,length)) return true;
    memcpy(text,line+8,length-8); text[length-8]=0;
    bool quoted=false,escape=false; unsigned depth=0;
    for (const char *p=text; *p; ++p) {
        if (quoted) { if (escape) escape=false; else if (*p=='\\') escape=true; else if (*p=='"') quoted=false; }
        else if (*p=='"') quoted=true;
        else if (*p=='{' || *p=='[') { if (++depth>2) return true; }
        else if (*p=='}' || *p==']') { if (!depth) return true; --depth; }
    }
    if (quoted || depth) return true;
    j=cJSON_ParseWithOpts(text,NULL,true);
    if (!cJSON_IsObject(j)) { cJSON_Delete(j); return true; }
    for (a=j->child;a;a=a->next) for (b=a->next;b;b=b->next)
        if (a->string && b->string && !strcmp(a->string,b->string)) { cJSON_Delete(j); return true; }
    const char *op=str(j,"op"), *value=str(j,"state"); uint32_t n=0;
    if (!op) goto done;
    if (!strcmp(op,"hello")) {
        const char *imei=str(j,"imei"); cJSON *active=cJSON_GetObjectItemCaseSensitive(j,"alarm_active");
        if (!valid_imei(imei) || !cJSON_IsBool(active) || !number(j,"alarm_id",0xffffffffU,&n)) goto done;
        if (cJSON_IsTrue(active) && !n) goto done;
        if (s.alarm_active && !alarm_pending && n<s.alarm_id) goto done;
        bool differs=!s.imei_known || strcmp(s.imei,imei) || !s.transport_ready;
        strcpy(s.imei,imei); s.imei_known=true; s.transport_ready=true;
        imei_persist();
        /* SAM | 2026-10-25 +08:00 | Record only a real peer-state change; periodic hello cannot hide the preceding network transition. */
        peer_changed(YP_PEER_HELLO);
        /* SAM | 2026-10-23 20:18 +08:00 | Older/malformed hello invalidates cached version without discarding valid alarm/link synchronization. */
        {
            const char *product=str(j,"product_build_version"),*component=str(j,"component_version");uint32_t build;
            cat_product_version[0]=0;
            if(version_text(product)&&version_text(component)&&number(j,"build",65535u,&build)&&build>0u){
                strcpy(cat_product_version,product);cat_version_ms=s.now_ms;
            }
        }
        if (cJSON_IsTrue(active)) {
            differs=differs || !s.alarm_active || s.alarm_id!=n;
            s.alarm_active=true; s.alarm_id=n; alarm_pending=false;
        } else if (!alarm_pending && s.alarm_active && n==s.alarm_id) {
            /* SAM | 2026-11-04 +08:00 | Matching durable cancellation also drains the QP job before a new SOS starts. */
            s.alarm_active=false; cancel_pending=false; sos_start_due=false; sos_stop_due=sos_started; differs=true;
        }
        /* SAM | 2026-10-13 12:05 +08:00 | Resend battery after every validated
         * hello because a quick CAT reset can lose RAM data without changing
         * the displayed identity/alarm; resync alone must not refresh LVGL. */
        battery_pending=true;
        if (differs) changed();
        last_rx=s.now_ms;
    } else if (!strcmp(op,"alarm_state")) {
        cJSON *active=cJSON_GetObjectItemCaseSensitive(j,"active");
        if (!cJSON_IsBool(active) || !number(j,"id",0xffffffffU,&n) || (cJSON_IsTrue(active) && !n)) goto done;
        if (s.alarm_active && !alarm_pending && n<s.alarm_id) goto done;
        if (cJSON_IsTrue(active)) {
            if (!s.alarm_active || s.alarm_id!=n || alarm_pending) {
                s.alarm_active=true; s.alarm_id=n; alarm_pending=false;
                notice("ALARM ACTIVE"); changed();
            }
        } else if (s.alarm_active && n==s.alarm_id && !alarm_pending) {
            /* SAM | 2026-11-04 +08:00 | Keep the QP stop pending even when CAT1 has already committed cancellation. */
            s.alarm_active=false; cancel_pending=false; sos_start_due=false; sos_stop_due=sos_started; notice("ALARM CANCELLED"); changed();
        }
        last_rx=s.now_ms;
    } else if (!strcmp(op,"call") && value) {
        static const char *names[]={"idle","dialing","incoming","connected","ended","failed","unknown"};
        for (unsigned i=0;i<7;++i) if (!strcmp(value,names[i])) {
            /* SAM | 2026-11-07 11:57 +08:00 | Use the same revision update for received call states and QP dialing. */
            yp_business_call_set((yp_call_t)i);
            last_rx=s.now_ms; break;
        }
    } else if (!strcmp(op,"network") && value) {
        static const char *names[]={"unknown","no_sim","registering","ip","mqtt","offline"};
        for (unsigned i=0;i<6;++i) if (!strcmp(value,names[i])) {
            if (s.network!=(yp_network_t)i ||
                (s.signal_known && (i==YP_NET_NO_SIM || i==YP_NET_OFFLINE))) changed();
            s.network=(yp_network_t)i;
            /* SAM | 2026-10-25 +08:00 | Retain the validated received network enum as the source of a peer downgrade. */
            peer_changed(YP_PEER_NETWORK+i);
            if (i==YP_NET_NO_SIM || i==YP_NET_OFFLINE) s.signal_known=false;
            last_rx=s.now_ms; break;
        }
    } else if (!strcmp(op,"signal") && number(j,"csq",99,&n)) {
        bool known=n<=31 && s.network!=YP_NET_NO_SIM && s.network!=YP_NET_OFFLINE;
        if (known!=s.signal_known || (known && s.signal!=n)) {
            s.signal_known=known; s.signal=(uint8_t)n; changed();
        }
    } else if (!strcmp(op,"time") && number(j,"epoch",4102444799U,&n) && n>=1577836800U) {
        if (yp_business_port_time(n)) {
            s.epoch=n; clock_ms=s.now_ms; s.time_known=true; format_clock();
        } else notice("RTC UPDATE FAILED");
    } else if (!strcmp(op,"notice")) {
        value=str(j,"code");
        if (value && strlen(value)<sizeof(s.notice)) notice(value);
    } else if (!strcmp(op,"alarm_ack") && number(j,"id",0xffffffffU,&n) && n==s.alarm_id) notice("ALARM ACKNOWLEDGED");
    /* SAM | 2026-11-02 +08:00 | Platform-pushed resident name + glyphs: staged in RAM, shown only after the whole set validated. */
    else if (!strcmp(op,"name_begin") || !strcmp(op,"glyph") || !strcmp(op,"name_end")) name_line(j,op);
    /* SAM | 2026-11-03 +08:00 | Platform "clear name": drop name text and glyphs from RAM and NVDS. */
    else if (!strcmp(op,"name_clear") && number(j,"id",0xffffffffU,&n)) { yp_business_clear_resident(); name_result(n,0,0); }
done:
    cJSON_Delete(j); return true;
}

#ifdef YP_BUSINESS_HOST_TEST
/* SAM | 2026-11-03 +08:00 | Host test only: model a power-on (RAM statics zero, init not yet run). */
void yp_business_test_cold_boot(void) { memset(&s,0,sizeof(s)); s_inited=false; }
#endif
#ifndef YP_BUSINESS_HOST_TEST
/* SAM | 2026-10-13 08:52 +08:00 | Expose explicit local acceptance controls because customer key-cancel and platform time fields are not frozen. */
#include "cli.h"
static int cmd_business(int argc, char *argv[]) {
    if (argc==2 && !strcmp(argv[1],"status")) {
        cli_printf("[BUSINESS] link=%u net=%u alarm=%u id=%lu call=%u bat_known=%u bat=%u time=%u show_time=%u notice=%s\r\n",
            s.transport_ready,s.network,s.alarm_active,(unsigned long)s.alarm_id,s.call,
            s.battery_known,s.battery_percent,s.time_known,s.show_time,s.notice);
        return 0;
    }
    if (argc==2 && !strcmp(argv[1],"cancel")) {
        yp_business_cancel_alarm();
        cli_printf("[BUSINESS] cancel requested; wait for matching durable CAT1 state\r\n"); return 0;
    }
    if (argc==3 && !strcmp(argv[1],"time") && (!strcmp(argv[2],"on") || !strcmp(argv[2],"off"))) {
        yp_business_show_time(!strcmp(argv[2],"on"));
        cli_printf("[BUSINESS] local RAM display setting; platform persistence not provisioned\r\n"); return 0;
    }
    cli_printf("Usage: business status | cancel | time on/off\r\n"); return -1;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("business", "Live status; cancel; RAM clock", cmd_business);
/* SAM | 2026-11-02 +08:00 | Bench-only injection of one CAT1 BUS_EVT body (no spaces) to test the name/glyph path without a platform. */
static int cmd_busline(int argc, char *argv[]) {
    static char line[CLI_MAX_CMD_LEN + 8];
    int n;
    if (argc != 2 || (n = snprintf(line, sizeof(line), "BUS_EVT=%s", argv[1])) <= 0 || (size_t)n >= sizeof(line)) {
        cli_printf("Usage: busline <json>\r\n"); return -1;
    }
    (void)yp_business_handle_line(line, (size_t)n);
    cli_printf("[BUSLINE] %d B glyphs=%u name=%s\r\n", n, yp_ng_active_count(), s.resident_known ? "set" : "--");
    return 0;
}
CLI_CMD_REGISTER("busline", "Inject one BUS_EVT body", cmd_busline);
/* SAM | 2026-11-03 +08:00 | Bench view/clear of the stored resident name (clear = same path as platform clear / factory reset). */
static int cmd_name_store(int argc, char *argv[]) {
    if (argc==2 && !strcmp(argv[1],"clear")) {
        yp_business_clear_resident();
        cli_printf("[NAME] cleared (RAM + Flash pages + NVDS)\r\n"); return 0;
    }
    if (argc==2 && !strcmp(argv[1],"status")) {
        uint16_t len=yp_ng_stored_bytes();
        /* SAM | 2026-11-04 +08:00 | Glyph record now in Flash page A/B (page=0x000000: nothing stored, the factory state). */
        cli_printf("[NAME] resident=%s glyphs=%u seq=%lu stored_bytes=%u page=0x%06lX store_err=%u\r\n", s.resident_known ? "set":"--",
                   yp_ng_active_count(), (unsigned long)name_txn.last_seq, (unsigned)len, (unsigned long)yp_ng_stored_page(),
                   (unsigned)yp_ng_last_nvds_err());
        return 0;
    }
    cli_printf("Usage: name_store status | clear\r\n"); return -1;
}
CLI_CMD_REGISTER("name_store", "Stored resident name status/clear", cmd_name_store);
#endif
