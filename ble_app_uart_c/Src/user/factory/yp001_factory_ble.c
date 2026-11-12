/* SAM | 2026-10-13 15:00 +08:00 | Sealed-product factory commands over
 * official GUS server; callbacks enqueue only, no blocking bus/UI in callback. */
#include "yp001_factory_ble.h"
#include "yp001_factory_protocol.h"
#include "yp001_factory_stream.h"
#include "user_periph_setup.h"
#include "gus.h"
#include "app_log.h"
#include "app_io.h"
#include "gr_includes.h"
#include "../yp001_board_config.h"
#include "../yp001_battery.h"
#include "../charger/yp001_charger.h"
#include "../business/yp001_business.h"
#include "../ota/yp001_ota.h"
#include "../gui/epaper_ui.h"
#include "cli.h"
#include <stdio.h>
static volatile uint32_t clock_ms;
static uint32_t lease_since;
static bool granted;
static uint8_t connection=0xFF;
static volatile bool port_open,tx_busy,request_ready;
static char rx[FT_LINE_CAPACITY],request[FT_LINE_CAPACITY],tx[384],pending_tx[384];
/* SAM | 2026-11-06 +08:00 | Byte mirroring is bounded and independent of SDK/QP callbacks. */
/* SAM | 2026-11-06 +08:00 | Command output has its own capacity and drains before background prints. */
static ft_stream_t serial_stream,serial_replies;
static volatile bool serial_enabled,serial_command;
static volatile uint32_t session_generation;
static uint32_t executing_generation;
static uint16_t rx_used,tx_size,tx_pos;
static bool rx_drop;
/* SAM | 2026-10-13 15:28 +08:00 | Bound notification failure without
 * overwriting a buffer still owned by SDK; close link on expiry. */
static uint32_t tx_since;
static bool closing;

void yp_factory_ble_capture(const uint8_t *data,uint16_t size) {
    if (!port_open || (!serial_enabled && !serial_command)) return;
    uint32_t mask=__get_PRIMASK();__disable_irq();
    bool reply=serial_command && !__get_IPSR();
    if (port_open && (serial_enabled || reply)) (void)ft_stream_push(reply?&serial_replies:&serial_stream,data,size);
    __set_PRIMASK(mask);
}
void yp_factory_ble_tick(uint32_t elapsed_ms) { clock_ms+=elapsed_ms; }
void yp_factory_ble_disconnected(uint8_t conn) {
    if (conn!=connection) return;
    session_generation++;
    connection=0xFF; port_open=tx_busy=request_ready=false;
    serial_enabled=serial_command=false;ft_stream_reset(&serial_stream);ft_stream_reset(&serial_replies);
    granted=false; rx_used=tx_size=tx_pos=0;rx_drop=false;closing=false;
}
static void service_event(gus_evt_t *e) {
    if (e->evt_type==GUS_EVT_TX_PORT_OPENED) {
        if (closing) return;
        session_generation++;
        connection=e->conn_idx;port_open=true;granted=false;
    } else if (e->conn_idx!=connection) return;
    else if (e->evt_type==GUS_EVT_TX_PORT_CLOSED) {
        /* SAM | 2026-10-13 15:50 +08:00 | CCCD disable is not a GAP
         * disconnect; preserve any SDK-owned notification until real close. */
        serial_enabled=false;
        granted=false;request_ready=false;rx_used=0;rx_drop=false;
        port_open=false;closing=true;
        (void)ble_gap_disconnect(e->conn_idx);
    }
    else if (e->evt_type==GUS_EVT_TX_DATA_SENT) tx_busy=false;
    else if (e->evt_type==GUS_EVT_RX_DATA_RECEIVED) {
        for (uint16_t i=0;i<e->length;++i) {
            uint8_t c=e->p_data[i];
            if (c=='\r') continue;
            if (c=='\n') {
                if (!rx_drop && rx_used && !request_ready) {
                    rx[rx_used]=0; memcpy(request,rx,rx_used+1U);__DMB();request_ready=true;
                }
                rx_used=0;rx_drop=false;
            } else if (c<32U || c>126U || rx_used>=FT_LINE_CAPACITY-1U) { rx_drop=true;rx_used=0; }
            else if (!rx_drop) rx[rx_used++]=(char)c;
        }
    }
}
void yp_factory_ble_init(void) {
    gus_init_t init={.evt_handler=service_event};
    sdk_err_t result=gus_service_init(&init);
    APP_LOG_INFO("[FACTORY BLE] GUS server init=%04X protocol=1",result);
}
static bool safe(void) {
    const yp_business_status_t *b=yp_business_status();
    return !b->alarm_active&&!b->searching&&b->call!=YP_CALL_DIALING&&
        b->call!=YP_CALL_INCOMING&&b->call!=YP_CALL_CONNECTED&&yp001_ota_power_change_allowed();
}
/* SAM | 2026-11-06 +08:00 | Format in foreground scratch RAM; publish atomically only to the still-current connection and never overwrite SDK-owned bytes. */
static void publish_frame(uint16_t size,uint32_t generation) {
    uint32_t mask=__get_PRIMASK();__disable_irq();
    if (port_open && !closing && !tx_busy && generation==session_generation) {
        memcpy(tx,pending_tx,size);tx_size=size;tx_pos=0;tx_since=clock_ms;
    }
    __set_PRIMASK(mask);
}
static void respond(const ft_request_t *r,bool ok,const char *extra) {
    if (!port_open || executing_generation!=session_generation) return;
    int n=snprintf(pending_tx,sizeof(pending_tx),"FT v=1 seq=%lu op=%s ok=%u %s\n",
        (unsigned long)r->seq,ft_name(r->op),(unsigned)ok,extra);
    if (n<0||(size_t)n>=sizeof(pending_tx)) return;
    publish_frame((uint16_t)n,executing_generation);
}
static void ship_status(const ft_request_t *r,bool ok) {
    uint8_t phase;uint32_t token;bool attempted;
    yp001_charger_ship_snapshot(&phase,&token,&attempted);
    /* SAM | 2026-11-08 20:30 +08:00 | Publish actual job progress separately from the legacy register-controller state. */
    uint8_t automatic;const char *reason;
    yp001_charger_ship_auto_snapshot(&automatic,&reason);
    char extra[192];snprintf(extra,sizeof(extra),"state=%u token=%lu attempted=%u delay_s=12 auto_phase=%u reason=%s",
        phase,(unsigned long)token,(unsigned)attempted,automatic,reason);respond(r,ok,extra);
}
/* SAM | 2026-11-06 +08:00 | Structured GPIO request evidence must not be presented as measured VBAT or module startup. */
static void power_reply(const ft_request_t *r,int code) {
    char extra[112];snprintf(extra,sizeof(extra),"rail=%u hold=%u code=%d boot=unknown",
        (GPIO0->DATAOUT&YP001_CAT1_POWER_PIN)!=0U,yp001_cat1_factory_hold_active(),code);
    respond(r,code==0,extra);
}
static void serial_frame(void) {
    uint8_t bytes[64];unsigned n;uint32_t lost;uint16_t size;
    uint32_t generation=session_generation;
    uint32_t mask=__get_PRIMASK();__disable_irq();
    ft_stream_t *queue=(serial_replies.read!=serial_replies.write || serial_replies.dropped)?&serial_replies:&serial_stream;
    lost=queue->dropped;queue->dropped=0;
    n=lost?0U:ft_stream_pop(queue,bytes,sizeof(bytes));
    __set_PRIMASK(mask);
    if (lost) {
        int written=snprintf(pending_tx,sizeof(pending_tx),"SER_DROP %lu\n",(unsigned long)lost);
        size=(uint16_t)written;
    } else if (n) {
        static const char hex[]="0123456789abcdef";
        memcpy(pending_tx,"SER ",4);
        for (unsigned i=0;i<n;++i) { pending_tx[4U+2U*i]=hex[bytes[i]>>4U];pending_tx[5U+2U*i]=hex[bytes[i]&15U]; }
        pending_tx[4U+2U*n]='\n';size=(uint16_t)(5U+2U*n);
    } else return;
    publish_frame(size,generation);
}
static void execute(const ft_request_t *r) {
    bool locked=yp001_charger_ship_locked();
    if (r->op==FT_INFO) {
        const yp_business_status_t *b=yp_business_status();
        uint16_t mv=0; bool adc=!locked && yp001_battery_read(&mv)==YP001_BATTERY_OK;
        yp001_charger_status_t ch;bool ch_ok=!locked&&yp001_charger_cached_status(&ch);
        char extra[300];snprintf(extra,sizeof(extra),
            "fw=FT1_20261013 serial=1 imei=%s adc=%u mv=%u bat=%u left=%u right=%u alarm=%u call=%u net=%u link=%u cat_request=%u chg=%u vin=%u chg_ok=%u",
            b->imei_known?b->imei:"NA",(unsigned)adc,mv,adc?yp001_battery_estimate(mv):0U,
            app_io_read_pin(YP001_KEY1_TYPE,YP001_KEY1_PIN)==APP_IO_PIN_RESET,
            app_io_read_pin(YP001_KEY2_TYPE,YP001_KEY2_PIN)==APP_IO_PIN_RESET,
            b->alarm_active,b->call,b->network,b->transport_ready,(GPIO0->DATAOUT&YP001_CAT1_POWER_PIN)!=0U,
            ch_ok?(ch.power_raw>>4U)&1U:0U,ch_ok?ch.input_present:0U,(unsigned)ch_ok);
        respond(r,true,extra);return;
    }
    if (r->op==FT_CAT_STATUS) {power_reply(r,0);return;}
    if (r->op==FT_SERIAL_OFF) {
        /* SAM | 2026-11-06 +08:00 | Manual stop discards queued wireless bytes without touching UART logging or the active SDK buffer. */
        uint32_t mask=__get_PRIMASK();__disable_irq();
        serial_enabled=false;ft_stream_reset(&serial_stream);ft_stream_reset(&serial_replies);__set_PRIMASK(mask);
        respond(r,true,"enabled=0");return;
    }
    if (r->op==FT_CAT_HOLD_OFF) {
        if (!ft_lease_valid(granted,lease_since,clock_ms)) {respond(r,false,"reason=physical_unlock_or_business_guard");return;}
        char name[]="cat1_power",off[]="hold_off";char *args[]={name,off};
        /* Releasing only this RAM flag cannot clear an OTA owner or cut power. */
        power_reply(r,cat1_debug_power(2,args));return;
    }
    if (r->op==FT_CLI) {
        if (!ft_cli_allowed(r->command)) {respond(r,false,"reason=command_not_enabled");return;}
        /* SAM | 2026-11-08 20:30 +08:00 | Only the approved single shipping entry bypasses the operator key lease. */
        /* SAM | 2026-11-12 +08:00 | Factory deep-sleep current test is forced by user decision: no key lease or business guard (sleep_test force keeps only OTA/ship/key-held checks). */
        if (strcmp(r->command,"charger ship start") && strcmp(r->command,"sleep_test enter force") && !ft_cli_read_only(r->command) &&
            (!ft_lease_valid(granted,lease_since,clock_ms)||
             (strcmp(r->command,"cat1_power hold_off") && !safe()))) {
            respond(r,false,"reason=physical_unlock_or_business_guard");return;
        }
        serial_command=true;
        int code=cli_execute_string_result(r->command);
        /* printf may be buffered by app_log until foreground flush. */
        app_log_flush();
        serial_command=false;
        char extra[40];snprintf(extra,sizeof(extra),"code=%d",code);respond(r,code==0,extra);return;
    }
    /* SAM | 2026-11-08 20:30 +08:00 | Start is self-guarded by the charger coordinator, including all existing power checks. */
    if (r->op==FT_SHIP_START) {ship_status(r,yp001_charger_ship_start());return;}
    if (r->op==FT_SHIP_STATUS) {ship_status(r,true);return;}
    if (r->op==FT_UNLOCK) {
        /* Single physical left key avoids the customer's two-key SOS gesture. */
        bool ok=safe()&&app_io_read_pin(YP001_KEY1_TYPE,YP001_KEY1_PIN)==APP_IO_PIN_RESET&&
            app_io_read_pin(YP001_KEY2_TYPE,YP001_KEY2_PIN)!=APP_IO_PIN_RESET;
        granted=ok;lease_since=clock_ms;respond(r,ok,ok?"lease_s=60":"reason=hold_left_only");return;
    }
    if (!ft_lease_valid(granted,lease_since,clock_ms)||!safe()) {
        respond(r,false,"reason=physical_unlock_or_business_guard");return;
    }
    if (locked && r->op!=FT_SHIP_CONFIRM && r->op!=FT_SHIP_CANCEL) {
        respond(r,false,"reason=ship_locked");return;
    }
    switch(r->op) {
        case FT_PAGE: respond(r,epaper_ui_select_page((epaper_ui_page_t)r->arg),"result=page_queued_visual_check_required");break;
        case FT_CAT_OFF: case FT_CAT_ON: case FT_CAT_HOLD_ON: {
            char name[]="cat1_power",off[]="off",on[]="on",hold[]="hold_on";
            char *args[]={name,r->op==FT_CAT_OFF?off:(r->op==FT_CAT_ON?on:hold)};
            power_reply(r,cat1_debug_power(2,args));break;
        }
        case FT_SERIAL_ON: serial_enabled=true;respond(r,true,"enabled=1");break;
        case FT_SHIP_PREP: ship_status(r,yp001_charger_ship_prepare());break;
        case FT_SHIP_CONFIRM: ship_status(r,yp001_charger_ship_confirm(r->arg));break;
        case FT_SHIP_CANCEL: ship_status(r,yp001_charger_ship_cancel());break;
        default: respond(r,false,"reason=unsupported");break;
    }
}
void yp_factory_ble_poll(void) {
    /* SAM | 2026-11-06 +08:00 | Never execute a command or send notifications from a masked/IRQ context. */
    if (__get_IPSR() || __get_PRIMASK() || __get_BASEPRI()) return;
    if (!port_open) return;
    if (closing) return;
    /* OTA owns timing/power: pause background wireless logs without changing UART output. */
    if (serial_enabled && !yp001_ota_power_change_allowed()) serial_enabled=false;
    if ((tx_busy||tx_pos<tx_size) && (uint32_t)(clock_ms-tx_since)>=5000U) {
        closing=true;granted=false;
        /* The disconnect event releases the SDK-owned tx buffer. */
        (void)ble_gap_disconnect(connection);
        return;
    }
    if (!tx_busy&&tx_pos<tx_size) {
        uint16_t n=(uint16_t)(tx_size-tx_pos);if(n>20U)n=20U;
        tx_busy=true;
        sdk_err_t ret=gus_tx_data_send(connection,(uint8_t *)tx+tx_pos,n);
        if (ret==SDK_SUCCESS) tx_pos+=n;else tx_busy=false;
    }
    if (tx_busy||tx_pos<tx_size) return;
    if (!request_ready) {serial_frame();return;}
    char line[FT_LINE_CAPACITY];memcpy(line,request,sizeof(line));request_ready=false;
    ft_request_t r;
    executing_generation=session_generation;
    if (ft_parse(line,&r)) execute(&r);
    else APP_LOG_WARNING("[FACTORY BLE] malformed/unsupported request dropped");
}
