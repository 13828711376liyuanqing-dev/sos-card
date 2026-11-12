/* SAM | 2026-11-08 +08:00 | Exercise the real automatic coordinator before enabling any hardware path. */
#include "yp001_shipping.h"
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static bool allowed=true,input=true,prepared=true,confirmed=true;
static unsigned prepares,confirms,cancels;
static yp_ship_t low;
static const char *guard(void) { return allowed ? NULL : "OTA_or_business_guard"; }
static int usb(void) { return input ? 1 : 0; }
static bool prepare(void) { ++prepares; low.phase=prepared?YP_SHIP_CHECKING:YP_SHIP_IDLE; return prepared; }
static bool confirm(uint32_t token) {
    ++confirms; low.disconnect_attempted=true;
    low.phase=confirmed?YP_SHIP_SENT:YP_SHIP_FAILED;
    return confirmed && token==123;
}
static void cancel(void) { ++cancels; low.phase=YP_SHIP_IDLE; }
static const yp_ship_auto_port_t port={guard,usb,prepare,confirm,cancel};
int main(void) {
    yp_ship_auto_t job={0};
    CHECK(yp_ship_auto_start(&job,100,&port));
    CHECK(job.phase==YP_SHIP_AUTO_WAIT_USB && prepares==0);
    CHECK(yp_ship_auto_start(&job,200,&port) && job.since==100);
    yp_ship_auto_poll(&job,&low,60099,&port); CHECK(job.phase==YP_SHIP_AUTO_WAIT_USB);
    yp_ship_auto_poll(&job,&low,60100,&port); CHECK(job.phase==YP_SHIP_AUTO_FAILED && prepares==0);
    CHECK(!yp_ship_auto_start(&job,60101,&port));
    job=(yp_ship_auto_t){0};input=false;
    CHECK(yp_ship_auto_start(&job,100,&port));
    yp_ship_auto_poll(&job,&low,100,&port); CHECK(prepares==1 && job.phase==YP_SHIP_AUTO_CHECKING);
    CHECK(yp_ship_auto_start(&job,200,&port) && prepares==1);
    low.phase=YP_SHIP_READY; low.token=123;
    yp_ship_auto_poll(&job,&low,2100,&port); CHECK(job.phase==YP_SHIP_AUTO_SENT && confirms==1);
    CHECK(yp_ship_auto_start(&job,2200,&port) && confirms==1);
    job=(yp_ship_auto_t){0};low=(yp_ship_t){0};
    CHECK(yp_ship_auto_start(&job,100,&port));allowed=false;
    yp_ship_auto_poll(&job,&low,101,&port);CHECK(job.phase==YP_SHIP_AUTO_FAILED && prepares==1);
    allowed=true;job=(yp_ship_auto_t){0};prepared=false;
    CHECK(yp_ship_auto_start(&job,100,&port));yp_ship_auto_poll(&job,&low,101,&port);
    CHECK(job.phase==YP_SHIP_AUTO_FAILED && confirms==1);
    prepared=true;job=(yp_ship_auto_t){0};low=(yp_ship_t){0};
    CHECK(yp_ship_auto_start(&job,100,&port));yp_ship_auto_poll(&job,&low,101,&port);
    low.phase=YP_SHIP_READY;low.token=123;confirmed=false;
    yp_ship_auto_poll(&job,&low,2101,&port);CHECK(job.phase==YP_SHIP_AUTO_UNKNOWN && confirms==2);
    yp_ship_auto_poll(&job,&low,2201,&port);CHECK(confirms==2);
    CHECK(!yp_ship_auto_start(&job,2301,&port));
    job=(yp_ship_auto_t){0};low=(yp_ship_t){0};input=true;
    CHECK(yp_ship_auto_start(&job,0xfffffff0U,&port));
    yp_ship_auto_poll(&job,&low,59984U,&port);CHECK(job.phase==YP_SHIP_AUTO_FAILED);
    job=(yp_ship_auto_t){0};low=(yp_ship_t){0};input=false;
    CHECK(yp_ship_auto_start(&job,100,&port));yp_ship_auto_poll(&job,&low,101,&port);
    allowed=false;yp_ship_auto_poll(&job,&low,102,&port);
    CHECK(job.phase==YP_SHIP_AUTO_FAILED && low.phase==YP_SHIP_IDLE && cancels>0);
    puts("PASS automatic shipping: wait, timeout, duplicate, cutoff, OTA preemption, failure, uncertainty, wrap");
    return 0;
}
