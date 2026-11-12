/* SAM | 2026-10-13 14:26 +08:00 | Compile actual guard/prepare wrappers
 * against SDK stand-ins because GPIO DATA and DATAOUT are different. */
#include "yp001_shipping.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL guard line %d: %s\n",__LINE__,#x); return 1; } } while(0)
#define YP_CALL_DIALING 1
#define YP_CALL_INCOMING 2
#define YP_CALL_CONNECTED 3
#define YP001_CAT1_POWER_TYPE 0
#define YP001_CAT1_POWER_PIN 0x40U
#define YP001_CAT1_POWER_OFF 0
#define YP001_KEY1_TYPE 1
#define YP001_KEY1_PIN 2U
#define YP001_KEY2_TYPE 1
#define YP001_KEY2_PIN 16U
#define APP_IO_PIN_RESET 0
typedef struct { bool alarm_active, searching, transport_ready; int call; } yp_business_status_t;
static yp_business_status_t business;
static struct { unsigned DATAOUT; } gpio;
#define GPIO0 (&gpio)
static bool provisioned, ota_allowed=true, pressed, s_ship_key_seen;
static yp_ship_t s_ship;
static uint32_t s_test_clock_ms=100, s_ship_poll_ms;
static uint8_t regs[16];
static unsigned stops;
static const yp_business_status_t *yp_business_status(void) { return &business; }
static yp_ship_auto_t s_ship_auto;
static bool s_ship_auto_internal;
static bool factory_hold, cat1_off_fails;
static unsigned cat1_calls;
static bool yp001_cat1_factory_hold_active(void) { return factory_hold; }
/* SAM | 2026-11-08 +08:00 | Stand-in for the CLI power command used by the forced shipment: hold_off releases the hold, off drops the rail request. */
static int cat1_debug_power(int argc, char **argv) {
    (void)argc; ++cat1_calls;
    if (!strcmp(argv[1], "hold_off")) { factory_hold = false; return 0; }
    if (!strcmp(argv[1], "off")) { if (cat1_off_fails) return -1; gpio.DATAOUT = 0; return 0; }
    return -1;
}
static bool yp001_ota_port_provisioned(void) { return provisioned; }
static bool yp001_ota_power_change_allowed(void) { return ota_allowed; }
static int app_io_read_pin(int type, unsigned pin) {
    (void)pin; return type==YP001_CAT1_POWER_TYPE ? 0 : !pressed;
}
static bool yp001_charger_ship_locked(void) { return yp_ship_locked(&s_ship); }
static bool yp001_charger_probe(void) { return true; }
static bool read_reg(uint8_t reg,uint8_t *value) { *value=regs[reg]; return true; }
static bool yp001_charger_test_stop(void) { ++stops; return true; }
static void yp001_charger_ship_status(void) { }
#define cli_printf(...) ((void)0)
/* GUARD SOURCE */
/* PREPARE SOURCE */
int main(void) {
    regs[0x0B]=0x3F;
    gpio.DATAOUT=0x40U; /* Output ON while input reads LOW. */
    CHECK(!ship_business_guard()); CHECK(!yp001_charger_ship_prepare()); CHECK(stops==0);
    gpio.DATAOUT=0; CHECK(ship_business_guard()); CHECK(ship_auto_guard()==NULL);
    regs[0x0A]=0x80; CHECK(!yp001_charger_ship_prepare()); CHECK(stops==0);
    regs[0x0A]=0; regs[8]=4; CHECK(!yp001_charger_ship_prepare()); CHECK(stops==0);
    regs[8]=0; regs[1]=0x20; CHECK(!yp001_charger_ship_prepare()); CHECK(stops==0);
    regs[1]=0; provisioned=true; CHECK(!ship_business_guard()); CHECK(ship_auto_guard()==NULL); provisioned=false;   /* legacy manual path still refuses an OTA layout; the forced start does not */
    ota_allowed=false; CHECK(!ship_business_guard()); CHECK(ship_auto_guard()!=NULL); ota_allowed=true;
    business.alarm_active=true; CHECK(!ship_business_guard()); business.alarm_active=false;
    business.call=YP_CALL_CONNECTED; CHECK(!ship_business_guard()); business.call=0;
    business.transport_ready=true; CHECK(!ship_business_guard()); CHECK(ship_auto_guard()==NULL); business.transport_ready=false;
    s_ship_key_seen=true; CHECK(!ship_business_guard()); s_ship_key_seen=false;
    pressed=true; CHECK(!ship_business_guard()); pressed=false;
    CHECK(yp001_charger_ship_prepare()); CHECK(stops==1); CHECK(s_ship.phase==YP_SHIP_CHECKING);
    CHECK(!yp001_charger_ship_prepare()); CHECK(stops==1);
    s_ship_auto.phase=YP_SHIP_AUTO_WAIT_USB;CHECK(!yp001_charger_ship_prepare());
    /* SAM | 2026-11-08 +08:00 | Forced factory shipment (an automatic job exists): only a live OTA transaction and the job's own CAT1 rail remain. */
    s_ship_auto.phase=YP_SHIP_AUTO_WAIT_USB; gpio.DATAOUT=0;
    provisioned=true; business.alarm_active=true; business.call=YP_CALL_CONNECTED; business.transport_ready=true;
    pressed=true; s_ship_key_seen=true; factory_hold=true;
    CHECK(ship_business_guard()); CHECK(ship_auto_guard()==NULL);                       /* none of those conditions applies any more */
    ota_allowed=false; CHECK(!ship_business_guard()); CHECK(ship_auto_guard()!=NULL && !strcmp(ship_auto_guard(),"OTA_guard")); ota_allowed=true;
    gpio.DATAOUT=0x40U; cat1_calls=0; ship_force_cat1_off();                            /* force: release hold, drop the CAT1 rail, clear the key latch */
    CHECK(!factory_hold && gpio.DATAOUT==0 && !s_ship_key_seen && cat1_calls==2);
    CHECK(ship_business_guard() && ship_auto_guard()==NULL);
    cat1_calls=0; ship_force_cat1_off(); CHECK(cat1_calls==0);                          /* idempotent: nothing to do the second time */
    gpio.DATAOUT=0x40U; factory_hold=true; cat1_calls=0; ota_allowed=false; ship_force_cat1_off();
    CHECK(cat1_calls==0 && gpio.DATAOUT==0x40U && factory_hold); ota_allowed=true;      /* never force power during an OTA transaction */
    cat1_off_fails=true; factory_hold=false; ship_force_cat1_off();
    CHECK(gpio.DATAOUT==0x40U && !ship_business_guard() && !strcmp(ship_auto_guard(),"CAT1_power_off_failed")); cat1_off_fails=false;   /* failed force: explicit reason */
    s_ship_auto.phase=YP_SHIP_AUTO_IDLE; gpio.DATAOUT=0x40U; CHECK(ship_auto_guard()==NULL);   /* a new start is not refused for the rail; it forces it */
    puts("PASS: actual factory guard and prepare wrapper; GPIO output ON/input LOW refused; invalid input no stop; forced shipment ignores business/key/link/OTA-layout, forces CAT1 off, refuses only during OTA");
    return 0;
}
