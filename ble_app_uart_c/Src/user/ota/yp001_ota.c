/* SAM | 2026-10-12 19:23 +08:00 | Foreground durable single-owner arbitration
 * because volatile grants cannot survive reset safely. */
#include "yp001_ota_port.h"
#include "cJSON.h"
#include "yp001_ota_wire.h"
#include "yp001_ota_app_crypto.h"
#include "yp001_ota_retirement.h"
#include <string.h>
#include "platform_sdk.h"
#include "../yp001_psram_mem.h"

static yp001_ota_record state;
static bool known;
/* SAM | 2026-10-27 +08:00 | Nested EPD business service may advance a pending quiet handshake, but must never re-enter a running Flash operation. */
static bool quiet_servicing;
/* SAM | 2026-10-27 +08:00 | RAM-only full-handshake evidence: [seq,token,kind,flags,request,grant,op_begin,op_end,release,release_ack,retry,retry_phase,type,wire_seq,offset,service_level]. Times use the served scheduler clock, NOT physical Flash duration. */
volatile uint32_t g_ota_quiet_trace[16],g_ota_quiet_first_timeout[16];
static uint32_t quiet_service_level;
/* SAM | 2026-10-25 +08:00 | Defer all OTA operations until peer TX is physically quiet; never recurse through the parser while Flash is busy. */
static struct {
    uint8_t phase, kind, nonce[16], bytes[YP001_OTA_FRAME_MAX+1];
    uint32_t token, at, health_at, validation_at;
    /* SAM | 2026-11-06 +08:00 | Safety waiting must not consume the read-only verifier execution budget. */
    uint32_t validation_work_ms, validation_wait_ms;
    bool validation_waiting, validation_wait_recorded;
    size_t length;
    bool granted, allowed;
} quiet;
/* SAM | 2026-11-06 +08:00 | RAM-only transition evidence distinguishes unrun validation from actual image rejection; no Flash writes. */
volatile uint32_t g_ota_activation_trace[24];
extern uint32_t yp001_uart_clock_ms(void);
extern void yp001_ota_measure_begin(uint32_t kind,uint32_t token);
extern void yp001_ota_measure_end(void);
static bool process_line(const char *line,size_t length);
static bool safe(bool commit);
static bool activation_read_check(const char *line,size_t length);
static bool read_only_query(const char *line,size_t length);
static void send(const char *op,const char *reason,const yp001_ota_record *record,uint32_t ticket,const char *nonce);
/* SAM | 2026-10-26 +08:00 | Retain first outer refusal without changing safety rules, persistent state or retry authority. */
volatile yp001_ota_quiet_denial_t yp001_ota_quiet_denial;
static uint32_t transfer_denial_mask(const yp001_ota_gates *g)
{
    return (!g->known?1u:0u)|(g->alarm?2u:0u)|(g->call?4u:0u)|
           (g->activity?8u:0u)|(!g->peer_stable?16u:0u);
}
static bool quiet_safe(void)
{
    yp001_ota_gates g;uint32_t mask;
    yp001_ota_port_gates(&g);mask=transfer_denial_mask(&g);
    if(mask){
        if(yp001_ota_quiet_denial.count!=UINT32_MAX)++yp001_ota_quiet_denial.count;
        if(!yp001_ota_quiet_denial.sequence){
            yp001_ota_quiet_denial.token=quiet.token;
            yp001_ota_quiet_denial.kind=quiet.kind;
            yp001_ota_quiet_denial.epoch=state.epoch;
            yp001_ota_quiet_denial.owner_phase=state.phase;
            yp001_ota_quiet_denial.mask=mask;
            yp001_ota_quiet_denial.gate_bits=(g.known?1u:0u)|(g.alarm?2u:0u)|
                (g.call?4u:0u)|(g.activity?8u:0u)|(g.peer_stable?16u:0u)|
                (g.stable?32u:0u)|(g.charging?64u:0u);
            yp001_ota_quiet_denial.battery=g.battery;
            yp001_ota_quiet_denial.observed_ms=yp001_uart_clock_ms();
            /* Volatile fields follow the existing RX snapshot's sequence-last publication. */
            yp001_ota_quiet_denial.sequence=1;
        }
    }
    return mask==0;
}
bool yp001_ota_flash_allowed(void){return quiet.allowed;}
static uint32_t quiet_u32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void quiet_trace_set(unsigned index,uint32_t value,uint32_t flag){
    ++g_ota_quiet_trace[0];g_ota_quiet_trace[index]=value;
    g_ota_quiet_trace[3]|=flag;++g_ota_quiet_trace[0];
}
static void quiet_trace_start(void){
    unsigned i;++g_ota_quiet_trace[0];
    for(i=1;i<16;i++)g_ota_quiet_trace[i]=0;
    g_ota_quiet_trace[1]=quiet.token;g_ota_quiet_trace[2]=quiet.kind;g_ota_quiet_trace[3]=1;
    g_ota_quiet_trace[4]=quiet.at;
    if(quiet.kind==2&&quiet.length>=24){
        g_ota_quiet_trace[12]=quiet.bytes[5];g_ota_quiet_trace[13]=quiet_u32(quiet.bytes+12);
        g_ota_quiet_trace[14]=quiet_u32(quiet.bytes+16);
    }
    ++g_ota_quiet_trace[0];
}
static void quiet_trace_timeout(uint32_t now,uint32_t phase){
    unsigned i;++g_ota_quiet_trace[0];g_ota_quiet_trace[10]=now;
    g_ota_quiet_trace[11]=phase;g_ota_quiet_trace[3]|=64;++g_ota_quiet_trace[0];
    if(!g_ota_quiet_first_timeout[0]){
        for(i=1;i<16;i++)g_ota_quiet_first_timeout[i]=g_ota_quiet_trace[i];
        /* First snapshot publishes its commit word last and is never cleared by later transactions. */
        g_ota_quiet_first_timeout[0]=1;
    }
}
static void quiet_send(uint8_t type){
    uint8_t frame[44];size_t n=yp001_ota_wire_encode(frame,sizeof(frame),type,1,quiet.token,(type==242&&!quiet.granted)?1u:0u,quiet.nonce,16);
    if(type==242&&!(g_ota_quiet_trace[3]&16))quiet_trace_set(8,yp001_uart_clock_ms(),16);
    if(n)yp001_ota_port_reply((const char*)frame,n);
}
/* SAM | 2026-11-06 +08:00 | Retain admission evidence so later gates cannot hide why validation was skipped.
 * Trace 0..13: sequence/event/owner/gates/time/budgets/checks/first wait/stage/ready;
 * 14..20 retain ingress gates,battery,sample time and sample ages/flags; 21..23 are receipt acquisition/revocation counts and last failure stage. */
static void activation_trace(uint32_t event){
    yp001_ota_gates g;uint32_t bits,evidence[6],ready;
    yp001_ota_port_gates(&g);yp001_ota_port_activation_evidence(evidence);
    ready=yp001_ota_port_install_check_ready(&state)?1u:0u;
    bits=(g.known?1u:0u)|(g.stable?2u:0u)|(g.charging?4u:0u)|(g.alarm?8u:0u)|
        (g.call?16u:0u)|(g.activity?32u:0u)|(g.peer_stable?64u:0u);
    ++g_ota_activation_trace[0];g_ota_activation_trace[1]=event;
    g_ota_activation_trace[2]=state.epoch;g_ota_activation_trace[3]=state.phase;
    g_ota_activation_trace[4]=bits;g_ota_activation_trace[5]=g.battery;
    g_ota_activation_trace[6]=yp001_uart_clock_ms();
    g_ota_activation_trace[7]=quiet.validation_work_ms;g_ota_activation_trace[8]=quiet.validation_wait_ms;
    if(event==2&&!quiet.validation_wait_recorded){quiet.validation_wait_recorded=true;g_ota_activation_trace[10]=bits;g_ota_activation_trace[11]=g_ota_activation_trace[6];}
    g_ota_activation_trace[12]=evidence[5];
    if(ready&&!g_ota_activation_trace[13])++g_ota_activation_trace[21];
    if(!ready&&g_ota_activation_trace[13]&&(event==5||event==6||event==8||event==9))++g_ota_activation_trace[22];
    g_ota_activation_trace[13]=ready;
    if(event==5)g_ota_activation_trace[23]=evidence[5];
    if(event==1){
        g_ota_activation_trace[14]=bits;g_ota_activation_trace[15]=g.battery;
        memcpy((void *)&g_ota_activation_trace[16],evidence,5*sizeof(uint32_t));
    }
}
/* SAM | 2026-11-06 +08:00 | Reflect every local receipt retirement in RAM evidence without altering port authorization. */
static void activation_receipt_reset(void){
    yp001_ota_port_install_check_reset();
    if(g_ota_activation_trace[13]){g_ota_activation_trace[13]=0;++g_ota_activation_trace[22];}
}
static void quiet_start(uint8_t kind){
    quiet.kind=kind;quiet.allowed=false;quiet.granted=false;
    if(quiet.token==UINT32_MAX||yp001_ota_random(quiet.nonce)){quiet.phase=4;return;}
    ++quiet.token;quiet.phase=1;quiet.at=yp001_uart_clock_ms();quiet_trace_start();quiet_send(240);
}
bool yp001_ota_handle_line(const char *line,size_t n){
    if(!line||n<8||memcmp(line,"OTA_CTL=",8))return false;
    if(quiet.phase||n>YP001_OTA_FRAME_MAX||memchr(line,0,n))return true;
    /* SAM | 2026-10-27 +08:00 | A validated QUERY cannot write Flash; reply without a silence lease so 1Hz recovery reconciliation cannot starve CLI recovery. Never respond inside an active lease. */
    if(read_only_query(line,n))return process_line(line,n);
    memcpy(quiet.bytes,line,n);quiet.bytes[n]=0;quiet.length=n;
    /* SAM | 2026-10-27 +08:00 | Validate signed A/B read-only across foreground passes before requesting the short Flash lease. Other commands retain their existing authorization path. */
    if(activation_read_check(line,n)){
        activation_receipt_reset();quiet.kind=1;quiet.allowed=false;
        /* SAM | 2026-11-06 +08:00 | A matching ACTIVATE always enters validation; unsafe admission waits instead of falling through without a receipt. */
        quiet.validation_at=yp001_uart_clock_ms();quiet.phase=5;
        quiet.validation_work_ms=quiet.validation_wait_ms=0;quiet.validation_waiting=!safe(false);quiet.validation_wait_recorded=false;
        memset((void *)g_ota_activation_trace,0,sizeof g_ota_activation_trace);activation_trace(1);
        if(quiet.validation_waiting)activation_trace(2);
    }else quiet_start(1);
    return true;
}
void yp001_ota_dispatch_wire(const uint8_t *p,size_t n){
    if(!yp001_ota_wire_valid(p,n))return;
    if(p[5]>=240){
        if(n!=44||quiet_u32(p+8)!=1||quiet_u32(p+12)!=quiet.token||memcmp(p+24,quiet.nonce,16))return;
        if(p[5]==241&&quiet.phase==1){quiet_trace_set(5,yp001_uart_clock_ms(),2);quiet.granted=quiet_u32(p+16)==0;quiet.phase=2;}
        else if(p[5]==243&&(quiet.phase==3||quiet.phase==4)&&quiet_u32(p+16)==0){quiet_trace_set(9,yp001_uart_clock_ms(),32);quiet.phase=0;quiet.kind=0;}
        return;
    }
    if(quiet.phase||n>sizeof(quiet.bytes))return;
    memcpy(quiet.bytes,p,n);quiet.length=n;quiet_start(2);
}

static const char *phases[] = {
    "IDLE", "DOWNLOADING", "PREPARED", "INSTALL_PENDING", "COMPLETE"
};

static bool hex64(const char *s)
{
    unsigned i;
    if (!s || strlen(s) != 64) return false;
    for (i = 0; i < 64; ++i) {
        if (!((s[i] >= '0' && s[i] <= '9') ||
              (s[i] >= 'a' && s[i] <= 'f') ||
              (s[i] >= 'A' && s[i] <= 'F'))) return false;
    }
    return true;
}

static const char *str(cJSON *j, const char *key)
{
    cJSON *value = cJSON_GetObjectItemCaseSensitive(j, key);
    return cJSON_IsString(value) ? value->valuestring : NULL;
}

/* SAM | 2026-10-12 19:37 +08:00 | Validate record combinations because a
 * valid CRC alone cannot establish a safe owner or a completed result. */
static bool valid(const yp001_ota_record *r)
{
    if (r->phase < OTA_IDLE || r->phase > OTA_COMPLETE ||
        !memchr(r->job, 0, sizeof(r->job)) ||
        !memchr(r->hash, 0, sizeof(r->hash)) ||
        !memchr(r->target, 0, sizeof(r->target)) ||
        !memchr(r->version, 0, sizeof(r->version)) ||
        !memchr(r->source_version, 0, sizeof(r->source_version)) ||
        !memchr(r->actual_version, 0, sizeof(r->actual_version)) ||
        !memchr(r->outcome, 0, sizeof(r->outcome))) return false;
    if (r->phase == OTA_IDLE) {
        return !r->epoch && !r->job[0] && !r->hash[0] && !r->target[0] &&
               !r->version[0] && !r->source_version[0] &&
               !r->actual_version[0] && !r->outcome[0];
    }
    if (!r->epoch || !hex64(r->job) || !hex64(r->hash) ||
        (strcmp(r->target, "CAT1") && strcmp(r->target, "GR5526")) ||
        !r->version[0] || !r->source_version[0]) return false;
    if (r->phase != OTA_COMPLETE) return !r->actual_version[0] && !r->outcome[0];
    if (strcmp(r->actual_version, r->source_version) &&
        strcmp(r->actual_version, r->version)) return false;
    /* SAM | 2026-10-24 +08:00 | Retain a distinct cancellation receipt without changing the persisted record layout. */
    return ((!strcmp(r->outcome,"cancel")||!strcmp(r->outcome,"retired")) && !strcmp(r->actual_version,r->source_version)) || !strcmp(r->outcome, "fail") ||
           (!strcmp(r->outcome, "success") && !strcmp(r->actual_version, r->version));
}

void yp001_ota_init(void)
{
    int result;
    memset(&quiet,0,sizeof(quiet));
    activation_receipt_reset();
    /* SAM | 2026-10-23 22:30 +08:00 | Boot never inherits a volatile CAT signature decision. */
    yp001_ota_port_cat_proof_reset();
    memset(&state, 0, sizeof(state));
    result = yp001_ota_port_load(&state);
    known = result == 0 || (result == 1 && valid(&state));
    /* Never send potentially unterminated corrupt journal strings. */
    if (result == 0 || !known) memset(&state, 0, sizeof(state));
}

/* SAM | 2026-10-31 15:08 +08:00 | CAT1 asks for this hold as soon as it receives an OTA command and repeats it every 10 s until the OTA ends,
 * then releases it. While held, nothing may cut or reconfigure CAT1 power. A hold not refreshed for 45 min lapses so a dead CAT1
 * cannot keep the rail on forever. Rail-on is re-asserted when the hold starts. */
extern uint32_t yp001_uart_clock_ms(void);
extern int cat1_debug_power(int argc, char *argv[]);
static bool s_cat1_hold;
static uint32_t s_cat1_hold_ms;
static bool cat1_hold_active(void)
{
    return s_cat1_hold && (uint32_t)(yp001_uart_clock_ms() - s_cat1_hold_ms) < 45U * 60U * 1000U;
}
bool yp001_ota_cat1_hold(bool on)
{
    bool was = cat1_hold_active();
    s_cat1_hold = on;
    s_cat1_hold_ms = yp001_uart_clock_ms();
    if (on && !was) {
        /* SAM | 2026-11-01 +08:00 | OTA power lock, the first thing done on an OTA command: CAT1 rail on (and kept: off/isolate/key/reset
         * and the low-power AO are refused while held), GR sleep refused (sleep_test checks power_change_allowed), memory and
         * PSRAM kept at full power so the OTA staging region is not lost. */
        char a0[] = "cat1_power", a1[] = "on";
        char *argv[] = { a0, a1 };
        (void)cat1_debug_power(2, argv);
        mem_pwr_mgmt_mode_set(MEM_POWER_FULL_MODE);
        (void)yp_psram_mem_init();
    }
    return was != on;
}

bool yp001_ota_power_change_allowed(void)
{
    if (cat1_hold_active()) return false;
    /* SAM | 2026-11-01 +08:00 | The live lock is RAM-only and is lost when GR reboots (activation). For the first 10 min after boot an OTA
     * still in flight per the journal also keeps CAT1 powered, until CAT1 refreshes the live lock. A stale record cannot block
     * low power for longer than this window. */
    if (yp001_ota_port_provisioned() && known &&
        (state.phase == OTA_DOWNLOADING || state.phase == OTA_PREPARED || state.phase == OTA_INSTALL_PENDING) &&
        yp001_uart_clock_ms() < 10U * 60U * 1000U) return false;
    /* SAM | 2026-10-27 +08:00 | An accepted activation is still coordinating with the live peer while validation/stability runs; do not cut or reconfigure its power mid-command. The bounded command timeout releases this volatile hold. */
    if(quiet.phase==5)return false;
    /* An unprovisioned product can never grant OTA. A provisioned journal
     * read/write error must instead protect the potentially pending install. */
    /* SAM | 2026-10-30 22:52 +08:00 | OTA in flight (download, prepared or install pending, any component) keeps CAT1 powered: the peer needs power to download,
     * transfer and install. Outside an OTA the business logic may power CAT1 off as before. Once the OTA completes, fails or is cancelled the journal leaves these phases. */
    /* SAM | 2026-11-01 +08:00 | Removed: the journal-phase rule kept CAT1 powered forever after a failed OTA left a stale DOWNLOADING record
     * (colleague's low-power never ran, cat_at refused). The live OTA power lock (yp001_ota_cat1_hold, refreshed by CAT1 while its OTA runs) replaces it. */
    return !yp001_ota_port_provisioned() ||
           (known && (state.phase != OTA_INSTALL_PENDING ||
            (!strcmp(state.target,"GR5526") && yp001_ota_port_power_safe(&state))));
}

/* SAM | 2026-10-28 19:00 +08:00 | The running application implies Boot has finished any swap, and a GR target means no CAT1 vendor install can be interrupted; restarting CAT1 then only restores the transport the transaction needs. Excludes quiet/validation windows and unknown journals. */
bool yp001_ota_cat1_autostart_allowed(void)
{
    return yp001_ota_port_provisioned()&&known&&!quiet.phase&&!strcmp(state.target,"GR5526")&&
        (state.phase==OTA_DOWNLOADING||state.phase==OTA_PREPARED||state.phase==OTA_INSTALL_PENDING);
}

static bool save(const yp001_ota_record *next)
{
    if (!yp001_ota_port_store(next)) {
        known = false; /* A failed write can have an uncertain durable outcome. */
        return false;
    }
    state = *next;
    return true;
}
/* SAM | 2026-10-27 +08:00 | Recovery transport is distinct from disruptive power/UART reconfiguration; never admit it during any quiet/validation operation or CAT native install. */
bool yp001_ota_recovery_control_allowed(void)
{
    return known&&!quiet.phase&&state.phase==OTA_INSTALL_PENDING&&!strcmp(state.target,"GR5526")&&
        yp001_ota_port_recovery_prepared(&state);
}

/* SAM | 2026-10-23 +08:00 | Export live commit gates only on matching owner replies; this hint never replaces ACTIVATE's fresh GR check. */
static bool safe(bool commit);
/* SAM | 2026-10-29 21:51 +08:00 | Round-1 defect 2: commit_safe was evaluated in send(), after the handler's Flash writes had stalled the motion sampler, so
 * CAT1 rejected a valid GRANT. A mutating handler records the safe(true) result it checked before writing; send() uses it once, then clears. */
static int commit_hint=-1;
static void send(const char *op, const char *reason, const yp001_ota_record *record, uint32_t ticket,const char *nonce)
{
    char output[YP001_OTA_FRAME_MAX + 1];
    cJSON *j = cJSON_CreateObject();
    if (!j) return;
    cJSON_AddStringToObject(j, "op", op);
    cJSON_AddStringToObject(j, "reason", reason);
    cJSON_AddStringToObject(j, "job", record->job);
    cJSON_AddStringToObject(j, "hash", record->hash);
    cJSON_AddStringToObject(j, "target", record->target);
    cJSON_AddStringToObject(j, "version",
        record->phase == OTA_COMPLETE ? record->actual_version : record->version);
    cJSON_AddStringToObject(j, "outcome", (!strcmp(record->outcome,"cancel")||!strcmp(record->outcome,"retired")) ? "fail" : record->outcome);
    /* SAM | 2026-10-24 +08:00 | Distinguish the durable pre-install cancellation receipt from any ordinary failed installation. */
    if(!strcmp(record->outcome,"cancel"))cJSON_AddBoolToObject(j,"cancelled_before_install",true);
    if(!strcmp(record->outcome,"retired"))cJSON_AddBoolToObject(j,"retired_before_install",true);
    /* SAM | 2026-10-23 +08:00 | Completion challenges are scoped to this reply, never ambient retained JSON state. */
    if(nonce&&nonce[0])cJSON_AddStringToObject(j,"nonce",nonce);
    cJSON_AddNumberToObject(j, "epoch", record->epoch);
    /* SAM | 2026-10-23 +08:00 | A native reset reply belongs to one outstanding CAT request, not a replayable ordinary reboot command. */
    if(ticket)cJSON_AddNumberToObject(j,!strcmp(op,"PROOF_ACK")?"offset":"ticket",ticket);
    cJSON_AddStringToObject(j, "phase", known ? phases[state.phase] : "UNKNOWN");
    /* SAM | 2026-10-23 22:30 +08:00 | CAT can re-send volatile proof after GR reset without re-downloading or re-activating. */
    if(known&&!strcmp(record->target,"CAT1"))cJSON_AddBoolToObject(j,"cat_proof_ready",yp001_ota_port_cat_proof_present(record));
    cJSON_AddBoolToObject(j, "commit_safe", known && !strcmp(reason,"ok") &&
        (!strcmp(op,"STATUS") || !strcmp(op,"GRANT") || !strcmp(op,"REBOOT_GRANT")) &&
        (state.phase==OTA_PREPARED || state.phase==OTA_INSTALL_PENDING) &&
        record->epoch==state.epoch && !strcmp(record->job,state.job) &&
        !strcmp(record->hash,state.hash) && !strcmp(record->target,state.target) &&
        !strcmp(record->version,state.version) && (commit_hint>=0?commit_hint==1:safe(true)));
    commit_hint=-1;
    memcpy(output, "OTA_GR=", 7);
    if (cJSON_PrintPreallocated(j, output + 7, sizeof(output) - 10, false)) {
        size_t length = strlen(output);
        output[length++] = '\r';
        output[length++] = '\n';
        yp001_ota_port_reply(output, length);
    }
    cJSON_Delete(j);
}

/* SAM | 2026-10-23 19:26 +08:00 | Persist the real GR result before releasing the owner; QUERY can replay it after a lost UART response. */
static void advance_quiet(void)
{
    yp001_ota_record result;uint32_t now=yp001_uart_clock_ms();
    /* SAM | 2026-11-06 +08:00 | Read-only work and bounded safety waiting have separate clocks; neither holds a Flash lease. */
    if(quiet.phase==5){
        int checked=0;uint32_t delta=now-quiet.validation_at;
        uint32_t *elapsed=quiet.validation_waiting?&quiet.validation_wait_ms:&quiet.validation_work_ms;
        *elapsed=delta>120001u-*elapsed?120001u:*elapsed+delta;quiet.validation_at=now;
        if(quiet.validation_work_ms>120000u||quiet.validation_wait_ms>120000u){
            const char *reason=quiet.validation_wait_ms>120000u?"activation_safe_wait":"activation_validation_timeout";
            activation_trace(6);activation_receipt_reset();quiet.phase=0;quiet.kind=0;
            send("DENY",reason,&state,0,NULL);return;
        }
        if(!safe(false)){
            if(!quiet.validation_waiting)activation_trace(2);
            quiet.validation_waiting=true;return;
        }
        checked=yp001_ota_port_install_check_step(&state);++g_ota_activation_trace[9];
        delta=yp001_uart_clock_ms()-now;quiet.validation_at=yp001_uart_clock_ms();
        quiet.validation_work_ms=delta>120001u-quiet.validation_work_ms?120001u:quiet.validation_work_ms+delta;
        if(checked<0||quiet.validation_work_ms>120000u){
            activation_trace(5);activation_receipt_reset();quiet.phase=0;quiet.kind=0;
            send("DENY",checked<0?"activation_validation_failed":"activation_validation_timeout",&state,0,NULL);return;
        }
        if(checked==1&&safe(true)){activation_trace(4);quiet_start(1);}
        else{
            bool waiting=checked==1;
            if(waiting&&!quiet.validation_waiting)activation_trace(2);
            quiet.validation_waiting=waiting;
        }
        return;
    }
    if((quiet.phase==1||quiet.phase==3)&&(uint32_t)(now-quiet.at)>2000u){
        quiet_trace_timeout(now,quiet.phase);
        activation_receipt_reset();activation_trace(9);
        quiet.allowed=false;
        if(quiet.phase==1){quiet.granted=false;quiet.phase=3;quiet.at=now;quiet_send(242);}
        else{quiet.phase=4;quiet.at=now;quiet_send(242);} /* One replay of release, never another Flash transaction. */
    }
    /* SAM | 2026-10-29 06:21 +08:00 | Bound phase 4: when CAT1 missed the whole handshake (e.g. it was restarting) it never sends 243, and GR waited forever while dropping every OTA_CTL, deadlocking the post-rollback result. No Flash is permitted here; after 10 s return to idle so QUERY is answered and the lease is retried on the normal 1 s cadence. */
    if(quiet.phase==4&&(uint32_t)(now-quiet.at)>10000u){
        quiet_trace_timeout(now,4);quiet.allowed=false;quiet.granted=false;quiet.phase=0;quiet.kind=0;
    }
    if(quiet.phase==2){
        quiet.granted=quiet.granted&&quiet_safe();
        if(quiet.granted){
            ++g_ota_quiet_trace[0];g_ota_quiet_trace[15]=quiet_service_level;++g_ota_quiet_trace[0];
            quiet_trace_set(6,yp001_uart_clock_ms(),4);
            yp001_ota_measure_begin(quiet.kind,quiet.token);
            quiet.allowed=true;
            if(quiet.kind==1)process_line((const char*)quiet.bytes,quiet.length);
            else if(quiet.kind==2)yp001_ota_port_wire(quiet.bytes,quiet.length);
            else if(known&&state.phase==OTA_INSTALL_PENDING&&!strcmp(state.target,"GR5526")&&
                    yp001_ota_port_result(&state,&result)&&valid(&result)&&save(&result))
                send("RELEASED","ok",&state,0,NULL);
            quiet.allowed=false;
            /* SAM | 2026-10-27 +08:00 | A read receipt never survives completion of its single control transaction. */
            if(quiet.kind==1){activation_receipt_reset();activation_trace(8);}
            yp001_ota_measure_end();
            quiet_trace_set(7,yp001_uart_clock_ms(),8);
        } else if(quiet.kind==1){process_line((const char*)quiet.bytes,quiet.length);activation_receipt_reset();activation_trace(9);}
        quiet.phase=3;quiet.at=yp001_uart_clock_ms();quiet_send(242);
    }
    if(!quiet.phase&&known&&state.phase==OTA_INSTALL_PENDING&&!strcmp(state.target,"GR5526")&&
       /* SAM | 2026-10-27 +08:00 | Observe health once per second without a silence lease; request a short lease only when confirmation/result persistence is actually ready. */
       (uint32_t)(now-quiet.health_at)>=1000u&&safe(false)){
        quiet.health_at=now;
        if(yp001_ota_port_result_pending(&state))quiet_start(3);
    }
}
/* SAM | 2026-10-27 +08:00 | EPD BUSY waits already dispatch UART; service the accepted handshake at the same foreground level rather than leave a granted peer waiting up to 30s. Reset polling stays in outer QV idle. */
void yp001_ota_service_pending(void)
{
    if(quiet_servicing||!quiet.phase)return;
    quiet_servicing=true;quiet_service_level=1;
    advance_quiet();
    quiet_servicing=false;
}
void yp001_ota_poll(void)
{
    if(quiet_servicing)return;
    quiet_servicing=true;quiet_service_level=2;
    yp001_ota_port_poll();
    advance_quiet();
    quiet_servicing=false;
}

/* Bound parser recursion before invoking cJSON on untrusted UART input. */
static bool shallow_json(const char *s)
{
    unsigned depth = 0;
    bool quoted = false, escaped = false;
    for (; *s; ++s) {
        if (quoted) {
            if (escaped) escaped = false;
            else if (*s == '\\') escaped = true;
            else if (*s == '"') quoted = false;
        } else if (*s == '"') quoted = true;
        else if (*s == '{' || *s == '[') { if (++depth > 8) return false; }
        else if (*s == '}' || *s == ']') { if (!depth) return false; --depth; }
    }
    return !quoted && depth == 0;
}
/* SAM | 2026-11-06 +08:00 | Identify the exact ACTIVATE independently of transient safety; validation waits read-only and the full parser rechecks identity/gates before mutation. */
static bool activation_read_check(const char *line,size_t length)
{
    char text[YP001_OTA_FRAME_MAX+1];cJSON *j,*a,*b,*epoch;bool match=false;
    const char *op,*job,*hash,*target,*version;
    if(!known||strcmp(state.target,"GR5526")||(state.phase!=OTA_PREPARED&&state.phase!=OTA_INSTALL_PENDING)||length<8||length>YP001_OTA_FRAME_MAX)return false;
    memcpy(text,line+8,length-8);text[length-8]=0;
    if(!shallow_json(text))return false;
    j=cJSON_ParseWithOpts(text,NULL,true);
    if(!cJSON_IsObject(j))goto done;
    for(a=j->child;a;a=a->next)for(b=a->next;b;b=b->next)
        if(a->string&&b->string&&!strcmp(a->string,b->string))goto done;
    op=str(j,"op");job=str(j,"job");hash=str(j,"hash");target=str(j,"target");version=str(j,"version");epoch=cJSON_GetObjectItemCaseSensitive(j,"epoch");
    match=op&&!strcmp(op,"ACTIVATE")&&job&&!strcmp(job,state.job)&&hash&&!strcmp(hash,state.hash)&&
        target&&!strcmp(target,state.target)&&version&&!strcmp(version,state.version)&&
        cJSON_IsNumber(epoch)&&epoch->valuedouble==(double)state.epoch;
done:
    cJSON_Delete(j);return match;
}

static bool safe(bool commit)
{
    yp001_ota_gates gates;
    yp001_ota_port_gates(&gates);
    return transfer_denial_mask(&gates)==0 &&
           /* SAM | 2026-11-07 07:14 +08:00 | User policy: >=50-percent measured battery OR healthy live USB; other commit gates remain. */
           (!commit || (gates.stable && yp001_ota_commit_power(gates.battery)));
}

/* SAM | 2026-10-27 +08:00 | Classify with the same depth, full-consumption and duplicate-key restrictions as dispatch; substring matches must never admit a mutating request. */
static bool read_only_query(const char *line,size_t length)
{
    char text[YP001_OTA_FRAME_MAX+1];cJSON *j,*item,*other;const char *op;bool query=false;
    if(length<8||length>YP001_OTA_FRAME_MAX||memchr(line,0,length))return false;
    memcpy(text,line+8,length-8);text[length-8]=0;
    if(!shallow_json(text))return false;
    j=cJSON_ParseWithOpts(text,NULL,true);
    if(!cJSON_IsObject(j))goto done;
    for(item=j->child;item;item=item->next)for(other=item->next;other;other=other->next)
        if(item->string&&other->string&&!strcmp(item->string,other->string))goto done;
    op=str(j,"op");query=op&&!strcmp(op,"QUERY");
done:
    cJSON_Delete(j);return query;
}

static bool process_line(const char *line, size_t length)
{
    char text[YP001_OTA_FRAME_MAX + 1];
    cJSON *j, *item, *other;
    const char *op = NULL, *job, *hash, *target, *version, *outcome;
    const char *reason = "invalid_request", *response = "DENY";
    yp001_ota_record request, next;
    bool identity;
    uint32_t component_size=0,reply_ticket=0;
    char result_nonce[33]={0}; /* SAM | 2026-10-23 +08:00 | Per-request completion challenge. */

    if (length < 8 || memcmp(line, "OTA_CTL=", 8)) return false;
    memset(&request, 0, sizeof(request));
    if (length > YP001_OTA_FRAME_MAX || memchr(line, 0, length)) {
        send("DENY", "invalid_frame", &request,0,NULL);
        return true;
    }
    memcpy(text, line + 8, length - 8);
    text[length - 8] = 0;
    if (!shallow_json(text)) {
        send("DENY", "invalid_json_depth", &request,0,NULL);
        return true;
    }
    j = cJSON_ParseWithOpts(text, NULL, true);
    if (!cJSON_IsObject(j)) {
        cJSON_Delete(j);
        send("DENY", "invalid_json", &request,0,NULL);
        return true;
    }
    for (item = j->child; item; item = item->next) {
        for (other = item->next; other; other = other->next) {
            if (item->string && other->string && !strcmp(item->string, other->string)) {
                reason = "duplicate_key";
                goto done;
            }
        }
    }
    op = str(j, "op");
    if (op && !strcmp(op, "QUERY")) {
        send("STATUS", known ? "ok" : "storage_unavailable", &state,0,NULL);
        cJSON_Delete(j);
        return true;
    }
    job = str(j, "job");
    hash = str(j, "hash");
    target = str(j, "target");
    version = str(j, "version");
    item = cJSON_GetObjectItemCaseSensitive(j, "epoch");
    if (!op || !hex64(job) || !hex64(hash) || !target ||
        (strcmp(target, "CAT1") && strcmp(target, "GR5526")) ||
        !version || !version[0] || strlen(version) >= sizeof(request.version) ||
        !cJSON_IsNumber(item) || item->valuedouble < 0 ||
        item->valuedouble > 4294967295.0 ||
        item->valuedouble != (double)(uint32_t)item->valuedouble) goto done;
    strcpy(request.job, job);
    strcpy(request.hash, hash);
    strcpy(request.target, target);
    strcpy(request.version, version);
    request.epoch = (uint32_t)item->valuedouble;
    if (!quiet.allowed) { reason="quiet_denied";goto done; }
    if (!known) { reason = "storage_unavailable"; goto done; }
    identity = !strcmp(request.job, state.job) && !strcmp(request.hash, state.hash) &&
               !strcmp(request.target, state.target);
    next = state;

    if (!strcmp(op, "REQUEST")) {
        if (request.epoch != 0) { reason = "epoch_invalid"; goto done; }
        /* SAM | 2026-10-23 +08:00 | GR authorizes the exact native extent before binary traffic; remote BEGIN cannot choose a Flash destination. */
        if (!strcmp(request.target,"GR5526")) {
            item=cJSON_GetObjectItemCaseSensitive(j,"size");
            if(!cJSON_IsNumber(item)||item->valuedouble<912||item->valuedouble>442368||
               item->valuedouble!=(double)(uint32_t)item->valuedouble){reason="component_size_invalid";goto done;}
            component_size=(uint32_t)item->valuedouble;
        }
        /* Lost responses never create another epoch for the same transaction. */
        if (identity && !strcmp(request.version, state.version)) {
            if(component_size && state.phase==OTA_DOWNLOADING &&
               !yp001_ota_port_receive_prepare(&state,component_size)){reason="receiver_unavailable";goto done;}
            request = state;
            response = "STATUS";
            reason = "ok";
            goto done;
        }
        if (state.phase != OTA_IDLE && state.phase != OTA_COMPLETE) {
            reason = "busy";
            goto done;
        }
        if (state.epoch == UINT32_MAX) { reason = "epoch_invalid"; goto done; }
        if (!safe(false)) { reason = "business_gate"; goto done; }
        next = request;
        next.epoch = state.epoch + 1;
        next.phase = OTA_DOWNLOADING;
        if (!yp001_ota_port_source_version(&next, next.source_version,
                                          sizeof(next.source_version)) ||
            !memchr(next.source_version, 0, sizeof(next.source_version)) ||
            !next.source_version[0]) {
            reason = "source_version_unavailable";
            goto done;
        }
        if (!save(&next)) { reason = "storage_error"; goto done; }
        request = state;
        if(component_size && !yp001_ota_port_receive_prepare(&state,component_size)){
            reason="receiver_unavailable";goto done;
        }
        response = "GRANT";
        reason = "ok";
        goto done;
    }
    if (!identity || request.epoch != state.epoch ||
        (strcmp(op, "COMPLETE") && strcmp(request.version, state.version))) {
        reason = "stale_owner";
        goto done;
    }
    /* SAM | 2026-10-24 +08:00 | Cancel only an exact empty GR owner before installation; persist failure before releasing and replay the receipt after reset. */
    /* SAM | 2026-10-25 +08:00 | Retire only the exact spent R4 owner; preserve B bytes and durable progress in its receipt. */
    if (!strcmp(op,"RETIRE")) {
        /* SAM | 2026-10-26 +08:00 | R5 retirement is separately approved; keep the original exact R4 scope and never generalize RETIRE to arbitrary owners. */
        if(!yp001_ota_retirement_size(&state)){
            reason="retire_scope";goto done;
        }
        if(state.phase==OTA_COMPLETE&&!strcmp(state.outcome,"retired")){
            request=state;response="RETIRED";reason="retired_before_install";goto done;
        }
        if(!safe(false)||state.phase!=OTA_DOWNLOADING||!yp001_ota_port_retire(&state)){
            reason="retire_not_safe";goto done;
        }
        next.phase=OTA_COMPLETE;strcpy(next.actual_version,state.source_version);strcpy(next.outcome,"retired");
        if(!save(&next)){reason="storage_error";goto done;}
        request=state;response="RETIRED";reason="retired_before_install";
    } else if (!strcmp(op,"CANCEL_EMPTY")) {
        if(strcmp(state.target,"GR5526")){reason="cancel_target_invalid";goto done;}
        if(state.phase==OTA_COMPLETE&&!strcmp(state.outcome,"cancel")){
            request=state;response="CANCELLED";reason="cancelled_before_install";goto done;
        }
        if(state.phase!=OTA_DOWNLOADING||!safe(false)||!yp001_ota_port_cancel_empty(&state)){
            reason="cancel_not_empty_or_safe";goto done;
        }
        next.phase=OTA_COMPLETE;strcpy(next.actual_version,state.source_version);strcpy(next.outcome,"cancel");
        if(!save(&next)){reason="storage_error";goto done;}
        request=state;response="CANCELLED";reason="cancelled_before_install";
    } else if (!strcmp(op,"CAT_PROOF")) {
        /* SAM | 2026-10-23 22:30 +08:00 | Bounded hex chunks carry signed metadata only; current durable identity and ordinary business gate remain mandatory. */
        const char*data=str(j,"data");uint8_t bytes[256];uint32_t offset,n,k;
        item=cJSON_GetObjectItemCaseSensitive(j,"offset");
        if(strcmp(state.target,"CAT1")||!safe(false)||!data||!strlen(data)||strlen(data)>512||strlen(data)%2||
           !cJSON_IsNumber(item)||item->valuedouble<0||item->valuedouble>904||
           item->valuedouble!=(double)(uint32_t)item->valuedouble){reason="proof_invalid";goto done;}
        offset=(uint32_t)item->valuedouble;n=(uint32_t)strlen(data)/2;
        for(k=0;k<n;k++){
            unsigned a=(unsigned char)data[k*2],b=(unsigned char)data[k*2+1];
            a=(a>='0'&&a<='9')?a-'0':(a>='a'&&a<='f')?a-'a'+10u:16u;
            b=(b>='0'&&b<='9')?b-'0':(b>='a'&&b<='f')?b-'a'+10u:16u;
            if(a>15||b>15){reason="proof_invalid";goto done;}bytes[k]=(uint8_t)(a*16+b);
        }
        if(!yp001_ota_port_cat_proof(&state,offset,bytes,n,&reply_ticket)){reason="proof_unverified";goto done;}
        response="PROOF_ACK";reason="ok";
    } else if (!strcmp(op,"RESULT_QUERY")) {
        /* SAM | 2026-10-23 +08:00 | CAT must answer a fresh challenge after its own confirmed journal; this is never activation authority. */
        if(!yp001_ota_port_cat_challenge(&state,result_nonce)){reason="result_challenge_unavailable";goto done;}
        response="RESULT_CHALLENGE";reason="ok";
    } else if (!strcmp(op,"CAT_RESULT")) {
        const char *nonce=str(j,"nonce"),*actual=str(j,"actual_version"),*native_phase=str(j,"native_phase");
        bool confirmed;
        item=cJSON_GetObjectItemCaseSensitive(j,"health_ms");
        confirmed=native_phase&&!strcmp(native_phase,"CONFIRMED")&&
            cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"code_identity"))&&
            /* SAM | 2026-10-24 +08:00 | Require explicit postboot installation evidence; legacy pending_clear frames do not qualify. */
            cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"installation_verified"))&&
            cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"data_ok"))&&
            cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"durable_result"))&&
            cJSON_IsNumber(item)&&item->valuedouble>=120000.0&&item->valuedouble<=4294967295.0&&
            item->valuedouble==(double)(uint32_t)item->valuedouble;
        if(!nonce||strlen(nonce)!=32||!actual||!yp001_ota_port_cat_result(&state,nonce,actual,confirmed)){
            reason="cat_result_unverified";goto done;
        }
        response="RESULT_ACK";reason="ok";
    } else if (!strcmp(op, "PREPARED")) {
        if (state.phase == OTA_PREPARED) {
            response = "STATUS";
            reason = "ok";
            goto done;
        }
        if (state.phase != OTA_DOWNLOADING) { reason = "phase_invalid"; goto done; }
        if (!yp001_ota_port_package_ready(&state)) { reason = "package_unverified"; goto done; }
        next.phase = OTA_PREPARED;
        if (!save(&next)) { reason = "storage_error"; goto done; }
        response = "STATUS";
        reason = "ok";
    } else if (!strcmp(op, "ACTIVATE")) {
        /* SAM | 2026-10-27 +08:00 | A legitimate GR activation cannot fall back to long crypto inside its short lease. Missing/revoked receipt is a terminal refusal for this command. */
        if(!strcmp(state.target,"GR5526")&&!yp001_ota_port_install_check_ready(&state)){
            reason="activation_validation_failed";goto done;
        }
        /* SAM | 2026-10-23 19:26 +08:00 | Resume only GR's durable uncommitted intent; CAT1 grants remain one-shot. Fresh gates are mandatory on every retry. */
        if (state.phase == OTA_INSTALL_PENDING && !strcmp(state.target,"GR5526")) {
            if (!safe(true)) { reason="safe_commit_gate"; goto done; }
            commit_hint=1;
            if (!yp001_ota_port_install_commit(&state)) { reason="boot_commit_failed"; goto done; }
            response="GRANT";reason="ok";goto done;
        }
        /* Do not re-issue a consumed activation grant after a lost response. */
        if (state.phase != OTA_PREPARED) { reason = "phase_invalid"; goto done; }
        if (!safe(true)) { reason = "safe_commit_gate"; goto done; }
        commit_hint=1;
        if (!yp001_ota_port_package_ready(&state)) { reason = "package_unverified"; goto done; }
        if (!strcmp(state.target,"GR5526") && !yp001_ota_port_install_prepare(&state)) {
            reason="boot_prepare_failed";goto done;
        }
        next.phase = OTA_INSTALL_PENDING;
        if (!save(&next)) { reason = "storage_error"; goto done; }
        if (!strcmp(state.target,"GR5526") && !yp001_ota_port_install_commit_prechecked(&state)) {
            reason="boot_commit_failed";goto done;
        }
        response = "GRANT";
        reason = "ok";
    } else if (!strcmp(op, "REBOOT")) {
        /* SAM | 2026-10-23 +08:00 | CAT native reset is separately authorized in the existing pending transaction; ordinary ATREBOOT remains forbidden. */
        if(state.phase!=OTA_INSTALL_PENDING || strcmp(state.target,"CAT1")){reason="phase_invalid";goto done;}
        item=cJSON_GetObjectItemCaseSensitive(j,"ticket");
        if(!cJSON_IsNumber(item)||item->valuedouble<1||item->valuedouble>4294967295.0||
           item->valuedouble!=(double)(uint32_t)item->valuedouble){reason="ticket_invalid";goto done;}
        if(!safe(true)){reason="safe_commit_gate";goto done;}
        commit_hint=1;
        reply_ticket=(uint32_t)item->valuedouble;
        response="REBOOT_GRANT";reason="ok";
    } else if (!strcmp(op, "COMPLETE")) {
        outcome = str(j, "outcome");
        if (!outcome || (strcmp(outcome, "success") && strcmp(outcome, "fail")) ||
            (strcmp(request.version, state.version) && strcmp(request.version, state.source_version)) ||
            (!strcmp(outcome, "success") && strcmp(request.version, state.version))) {
            reason = "invalid_result";
            goto done;
        }
        if (state.phase == OTA_COMPLETE) {
            if (strcmp(outcome, state.outcome) || strcmp(request.version, state.actual_version)) {
                reason = "result_mismatch";
                goto done;
            }
        } else {
            if (state.phase != OTA_INSTALL_PENDING) { reason = "phase_invalid"; goto done; }
            strcpy(next.actual_version, request.version);
            strcpy(next.outcome, outcome);
            if (!yp001_ota_port_completed(&next)) {
                reason = "health_or_pending_unverified";
                goto done;
            }
            next.phase = OTA_COMPLETE;
            if (!save(&next)) { reason = "storage_error"; goto done; }
        }
        request = state;
        response = "RELEASED";
        reason = "ok";
    } else reason = "phase_invalid";

done:
    send(response, reason, &request,reply_ticket,result_nonce);
    cJSON_Delete(j);
    return true;
}
