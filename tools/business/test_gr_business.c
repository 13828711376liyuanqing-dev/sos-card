/* SAM | 2026-10-13 08:35 +08:00 | Exercise business boundaries because UI must reflect real independent states. */
#include "yp001_business.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)
/* SAM | 2026-10-13 12:05 +08:00 | Observe battery frames because unchanged hello must restore the peer RAM snapshot. */
static unsigned alarms, sends, cancels, batteries;
static char last_battery[160];
static bool send_ok = true;
bool yp_business_port_time(uint32_t epoch) { return epoch > 1577836800U; }
bool yp_business_port_send(const char *line, size_t n) {
    ++sends;
    if (strstr(line,"\"op\":\"alarm\"")) ++alarms;
    if (strstr(line,"\"op\":\"cancel\"")) ++cancels;
    if (strstr(line,"\"op\":\"battery\"")) {
        ++batteries; snprintf(last_battery,sizeof(last_battery),"%s",line);
    }
    return send_ok && n > 0;
}
static bool event(const char *json) {
    char line[1024]; snprintf(line,sizeof(line),"BUS_EVT=%s",json);
    return yp_business_handle_line(line,strlen(line));
}
int main(void) {
    yp_business_init();
    CHECK(!yp_business_status()->imei_known && !yp_business_status()->time_known);
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(yp_business_status()->transport_ready && yp_business_status()->imei_known);
    /* Both held three seconds measured from the second press; 500ms inclusive. */
    yp_business_keys(true,false,100); yp_business_keys(true,true,600);
    yp_business_keys(true,true,3599); yp_business_poll(3599);
    CHECK(!yp_business_status()->alarm_active);
    yp_business_keys(true,true,3600); yp_business_poll(3600);
    CHECK(yp_business_status()->alarm_active && alarms == 1);
    event("{\"op\":\"alarm_state\",\"active\":true,\"id\":78}");
    yp_business_keys(true,true,10000); yp_business_poll(10000);
    CHECK(alarms == 1 && yp_business_status()->alarm_id == 78);
    event("{\"op\":\"call\",\"state\":\"connected\"}");
    event("{\"op\":\"call\",\"state\":\"ended\"}");
    CHECK(yp_business_status()->alarm_active && yp_business_status()->call == YP_CALL_ENDED);
    event("{\"op\":\"alarm_ack\",\"id\":78}");
    CHECK(yp_business_status()->alarm_active);
    yp_business_init();
    yp_business_keys(true,false,100); yp_business_keys(true,true,601);
    yp_business_keys(true,true,5000); yp_business_poll(5000);
    CHECK(!yp_business_status()->alarm_active);
    yp_business_keys(false,false,5010);
    yp_business_keys(true,true,5020); yp_business_keys(false,true,7000);
    yp_business_keys(true,true,7010); yp_business_keys(true,true,11000);
    yp_business_poll(11000); CHECK(!yp_business_status()->alarm_active);
    yp_business_init();
    yp_business_keys(true,true,0xffffff00U); yp_business_keys(true,true,2744U);
    yp_business_poll(2744U); CHECK(yp_business_status()->alarm_active);
    yp_business_init();
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":true,\"alarm_id\":91}");
    unsigned before = alarms; yp_business_poll(5000);
    CHECK(yp_business_status()->alarm_active && alarms == before);
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(yp_business_status()->alarm_active);
    event("{\"op\":\"alarm_state\",\"active\":true,\"id\":91}");
    uint32_t unchanged=yp_business_status()->revision;
    event("{\"op\":\"alarm_state\",\"active\":true,\"id\":91}");
    CHECK(unchanged==yp_business_status()->revision);
    event("{\"op\":\"call\",\"state\":\"unknown\"}");
    CHECK(yp_business_status()->call==YP_CALL_UNKNOWN);
    event("{\"op\":\"time\",\"epoch\":1791849600}");
    CHECK(yp_business_status()->time_known);
    CHECK(strcmp(yp_business_status()->date,"2026-10-13") == 0);
    CHECK(strcmp(yp_business_status()->clock,"08:00") == 0);
    yp_business_poll(65000); CHECK(strcmp(yp_business_status()->clock,"08:01") == 0);
    event("{\"op\":\"time\",\"epoch\":-1}"); CHECK(strcmp(yp_business_status()->date,"2026-10-13") == 0);
    event("{\"op\":\"network\",\"state\":\"mqtt\"}");
    event("{\"op\":\"signal\",\"csq\":22}"); CHECK(yp_business_status()->signal_known);
    event("{\"op\":\"signal\",\"csq\":99}"); CHECK(!yp_business_status()->signal_known);
    yp_business_transport_lost(); CHECK(!yp_business_status()->transport_ready);
    CHECK(yp_business_status()->alarm_active && yp_business_status()->network == YP_NET_UNKNOWN);
    yp_business_battery(true,24,false); CHECK(yp_business_status()->battery_known);
    yp_business_battery(true,101,false); CHECK(!yp_business_status()->battery_known);
    CHECK(yp_business_set_resident("张秀芳","1-102","燕园"));
    CHECK(yp_business_status()->resident_known);
    char long_name[80]; memset(long_name,'x',79); long_name[79]=0;
    CHECK(!yp_business_set_resident(long_name,"1","园"));
    CHECK(strcmp(yp_business_status()->name,"张秀芳")==0);
    yp_business_show_time(false); CHECK(!yp_business_status()->show_time);
    uint32_t revision = yp_business_status()->revision;
    CHECK(!yp_business_handle_line("other",5));
    event("{\"op\":\"hello\",\"imei\":\"bad\"}");
    event("{\"op\":\"call\",\"state\":42}");
    event("{\"op\":\"call\",\"op\":\"hello\",\"state\":\"connected\"}");
    CHECK(yp_business_status()->revision == revision);
    yp_business_init();
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":true,\"alarm_id\":91}");
    event("{\"op\":\"alarm_state\",\"active\":true,\"id\":90}");
    CHECK(yp_business_status()->alarm_id==91);
    yp_business_cancel_alarm(); yp_business_poll(1);
    CHECK(cancels==1 && yp_business_status()->alarm_active);
    yp_business_poll(2000); CHECK(cancels==1);
    yp_business_poll(2001); CHECK(cancels==2);
    event("{\"op\":\"alarm_state\",\"active\":false,\"id\":91}");
    yp_business_poll(4001); CHECK(cancels==2 && !yp_business_status()->alarm_active);
    /* SAM | 2026-10-13 12:05 +08:00 | Repeat the identical hello because a quick CAT reset does not change the GR display snapshot. */
    yp_business_init(); yp_business_battery(true,24,false);
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    yp_business_poll(1); unsigned battery_before=batteries;
    uint32_t battery_revision=yp_business_status()->revision;
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(yp_business_status()->revision==battery_revision);
    yp_business_poll(2); CHECK(batteries==battery_before+1);
    CHECK(strstr(last_battery,"\"known\":true") && strstr(last_battery,"\"battery\":24"));
    send_ok=false; event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    yp_business_poll(3); send_ok=true; battery_before=batteries;
    yp_business_poll(4); CHECK(batteries==battery_before+1);
    battery_before=batteries;
    event("{\"op\":\"hello\",\"imei\":\"bad\",\"alarm_active\":false,\"alarm_id\":0}");
    yp_business_poll(5); CHECK(batteries==battery_before);
    yp_business_battery(false,0,false);yp_business_poll(6);battery_before=batteries;
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    yp_business_poll(7);CHECK(batteries==battery_before+1 && strstr(last_battery,"\"known\":false"));
    /* SAM | 2026-10-20 16:36 +08:00 | A validated hello clears only obsolete link notices, never alarm or other business notices. */
    yp_business_init(); yp_business_transport_lost();
    CHECK(!strcmp(yp_business_status()->notice,"CAT1 LINK UNKNOWN"));
    event("{\"op\":\"hello\",\"imei\":\"bad\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(!strcmp(yp_business_status()->notice,"CAT1 LINK UNKNOWN"));
    event("{\"op\":\"network\",\"state\":\"mqtt\"}");
    CHECK(!strcmp(yp_business_status()->notice,"CAT1 LINK UNKNOWN"));
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(yp_business_status()->transport_ready && !yp_business_status()->notice[0]);
    CHECK(yp_business_start_alarm());
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(!strcmp(yp_business_status()->notice,"ALARM PENDING"));
    yp_business_init(); send_ok=false; yp_business_poll(1); send_ok=true;
    CHECK(!strcmp(yp_business_status()->notice,"CAT1 UART UNAVAILABLE"));
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    CHECK(!yp_business_status()->notice[0]);
    /* SAM | 2026-10-23 +08:00 | Quiet requires continuous fresh evidence, including across uint32 wrap. */
    {
        yp_business_ota_inputs_t guard;int32_t xyz[3]={0,0,1000};uint32_t now;unsigned i;
        yp_business_init();yp_business_ota_inputs(&guard);CHECK(!guard.known&&!guard.stable);
        yp_business_poll(0);yp_business_battery(true,90,true);yp_business_keys(false,false,0);yp_business_acceleration(true,xyz,0);
        for(i=1;i<=300;i++){
            now=i*200;yp_business_poll(now);yp_business_battery(true,90,true);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);
            yp_business_ota_inputs(&guard);CHECK(guard.known&&!guard.activity);CHECK(guard.stable==(i==300));
        }
        xyz[0]=100;yp_business_poll(60200);yp_business_keys(false,false,60200);yp_business_acceleration(true,xyz,60200);
        /* SAM | 2026-10-28 17:10 +08:00 | Bench builds ignore ordinary per-sample deltas because authorized bench OTA must not restart on handling/noise; production still counts them. */
#if YP001_OTA_USB_BENCH_TEST
        yp_business_ota_inputs(&guard);CHECK(!guard.activity&&guard.stable);
#else
        yp_business_ota_inputs(&guard);CHECK(guard.activity&&!guard.stable);
#endif
        yp_business_acceleration(false,xyz,60200);yp_business_ota_inputs(&guard);CHECK(!guard.known&&!guard.stable);
        yp_business_init();xyz[0]=0;
        for(i=0;i<=300;i++){
            now=0xffff8acfu+i*200u;yp_business_poll(now);yp_business_battery(true,90,true);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);yp_business_ota_inputs(&guard);
        }
        CHECK(guard.known&&guard.stable);
        yp_business_poll(now+2000);yp_business_ota_inputs(&guard);CHECK(!guard.known&&!guard.stable);
    }
    /* SAM | 2026-10-23 20:18 +08:00 | Peer source identity must expire and never be substituted by GR's own version. */
    {
        char version[12];yp_business_init();yp_business_poll(100);
        CHECK(!yp_business_cat_version(version,sizeof version));
        event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0,\"component_version\":\"001.000.002\",\"product_build_version\":\"1.0.2\",\"build\":3}");
        CHECK(yp_business_cat_version(version,sizeof version)&&!strcmp(version,"1.0.2"));
        CHECK(!yp_business_cat_version(version,3));
        yp_business_poll(20101);CHECK(!yp_business_cat_version(version,sizeof version));
        event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0,\"component_version\":\"001.000.002\",\"product_build_version\":\"1.0.2\",\"build\":3}");
        CHECK(yp_business_cat_version(version,sizeof version));
        event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
        CHECK(!yp_business_cat_version(version,sizeof version));
        event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0,\"component_version\":\"001.000.002\",\"product_build_version\":\"1.0.1000\",\"build\":3}");
        CHECK(!yp_business_cat_version(version,sizeof version));
    }
    /* SAM | 2026-10-24 22:58 +08:00 | A fresh ISR key timestamp may lead the foreground clock; it must neither invalidate fresh motion nor hide genuinely expired motion. */
    {
        yp_business_ota_inputs_t guard;int32_t xyz[3]={0,0,1000};
        yp_business_init();yp_business_poll(1000);yp_business_battery(true,90,true);
        yp_business_acceleration(true,xyz,1000);yp_business_keys(false,false,1200);
        yp_business_ota_inputs(&guard);CHECK(guard.known);
        yp_business_keys(false,false,2501);yp_business_ota_inputs(&guard);CHECK(!guard.known);
        yp_business_acceleration(true,xyz,2501);yp_business_ota_inputs(&guard);CHECK(guard.known);
        yp_business_poll(2702);yp_business_ota_inputs(&guard);CHECK(!guard.known);
    }
#if YP001_OTA_USB_BENCH_TEST
    /* SAM | 2026-10-28 17:10 +08:00 | Bench motion relaxation is limited to per-sample deltas (field 69/77 mg); sample gaps, out-of-range samples, sensor loss and keys must still block. */
    {
        yp_business_ota_inputs_t guard;int32_t xyz[3]={0,0,1000};uint32_t now=0;unsigned i;
        yp_business_init();
        for(i=0;i<=300;i++){
            now=i*200;yp_business_poll(now);yp_business_battery(true,90,true);yp_business_keys(false,false,now);
            xyz[2]=(i&1)?1077:1008;yp_business_acceleration(true,xyz,now);yp_business_ota_inputs(&guard);
            CHECK(guard.known);if(i)CHECK(!guard.activity);
        }
        CHECK(guard.stable);
        /* SAM | 2026-10-28 22:06 +08:00 | Bench: a late sample (busy foreground, 1.6 s gap) must not restart the 60 s quiet window; staleness is still enforced by `known` at evaluation time. */
        now+=1600;yp_business_poll(now);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);
        yp_business_ota_inputs(&guard);CHECK(guard.known&&!guard.activity&&guard.stable);
        now+=1600;yp_business_poll(now);yp_business_battery(true,90,true);yp_business_keys(false,false,now);
        yp_business_ota_inputs(&guard);CHECK(!guard.known&&!guard.stable);
        yp_business_acceleration(true,xyz,now);yp_business_ota_inputs(&guard);CHECK(guard.known&&guard.stable);
        /* An out-of-range magnitude still counts as motion and restarts quiet. */
        xyz[2]=1600;now+=200;yp_business_poll(now);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);
        yp_business_ota_inputs(&guard);CHECK(guard.activity&&!guard.stable);
        xyz[2]=1000;now+=200;yp_business_poll(now);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);
        yp_business_ota_inputs(&guard);CHECK(!guard.activity&&!guard.stable);
        xyz[2]=1600;now+=200;yp_business_poll(now);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);
        yp_business_ota_inputs(&guard);CHECK(guard.activity&&!guard.stable);
        /* SAM | 2026-10-28 19:47 +08:00 | Bench keys no longer count as OTA activity (user decision); alarm/call still block through the separate gates. */
        xyz[2]=1000;now+=200;yp_business_poll(now);yp_business_keys(true,false,now);yp_business_acceleration(true,xyz,now);
        yp_business_ota_inputs(&guard);CHECK(!guard.activity&&!guard.stable);
        xyz[2]=5000;now+=200;yp_business_poll(now);yp_business_keys(false,false,now);yp_business_acceleration(true,xyz,now);
        yp_business_ota_inputs(&guard);CHECK(!guard.known&&!guard.stable);
    }
#endif
    /* SAM | 2026-10-28 19:47 +08:00 | Key handling during an established quiet window: bench keeps stillness and quiet time; production resets both. */
    {
        yp_business_ota_inputs_t guard;int32_t xyz[3]={0,0,1000};uint32_t now=0;unsigned i;
        yp_business_init();
        for(i=0;i<=300;i++){
            now=i*200;yp_business_poll(now);yp_business_battery(true,90,true);yp_business_keys(false,false,now);
            yp_business_acceleration(true,xyz,now);yp_business_ota_inputs(&guard);
        }
        CHECK(guard.known&&guard.stable);
        /* Hold one key for 2s, then a single click that queues a call action. */
        for(i=1;i<=10;i++){
            now+=200;yp_business_poll(now);yp_business_battery(true,90,true);yp_business_keys(true,false,now);
            yp_business_acceleration(true,xyz,now);yp_business_ota_inputs(&guard);
#if YP001_OTA_USB_BENCH_TEST
            CHECK(guard.known&&!guard.activity&&guard.stable);
#else
            CHECK(guard.activity&&!guard.stable);
#endif
        }
        now+=200;yp_business_keys(false,false,now);yp_business_call_action(true);
        yp_business_acceleration(true,xyz,now);yp_business_ota_inputs(&guard);
#if YP001_OTA_USB_BENCH_TEST
        CHECK(!guard.activity&&guard.stable);
#else
        CHECK(guard.activity&&!guard.stable);
#endif
    }
    puts("PASS: GR business boundaries, battery resync and recovered-link notice isolation");
    return 0;
}
