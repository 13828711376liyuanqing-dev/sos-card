/* SAM | 2026-11-04 +08:00 | Run the real GR business state machine against queue and UART failures. */
#define main name_fixture_main
#define yp_business_port_send fixture_port_send
#define yp_business_port_sos fixture_port_sos
#include "../name_push/test_name_push.c"
#undef main
#undef yp_business_port_send
#undef yp_business_port_sos

static unsigned starts, stops, syncs, cancels;
static bool queue_ok=true, uart_ok=true;
bool yp_business_port_sos(bool start) {
    if (!queue_ok) return false;
    if (start) ++starts; else ++stops;
    return true;
}
bool yp_business_port_send(const char *line, size_t n) {
    if (strstr(line,"\"op\":\"alarm\"")) {
        if (!strstr(line,"\"dial\":false")) abort();
        ++syncs;
    }
    if (strstr(line,"\"op\":\"cancel\"")) ++cancels;
    return uart_ok && n>0;
}
static void deliver(const char *json) {
    char frame[300]; snprintf(frame,sizeof(frame),"BUS_EVT=%s",json);
    if (!yp_business_handle_line(frame,strlen(frame))) abort();
}
static void ready(void) {
    yp_business_init(); queue_ok=uart_ok=true;
    starts=stops=syncs=cancels=0;
    deliver("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
}
/* SAM | 2026-11-07 11:38 +08:00 | Sample the real key entry every 10ms so a held chord cannot rearm after cancellation. */
static void hold_keys(bool left, bool right, uint32_t first, uint32_t last) {
    for (uint32_t now=first; now<=last; now+=10U) {
        yp_business_keys(left,right,now);
        yp_business_poll(now);
    }
}
int main(void) {
    ready();
    CHECK(yp_business_start_alarm()); yp_business_poll(1);
    CHECK(starts==1 && syncs==1 && yp_business_sos_start_allowed());
    yp_business_poll(2001); CHECK(starts==1 && syncs==2);
    CHECK(!yp_business_start_alarm());
    deliver("{\"op\":\"alarm_state\",\"active\":true,\"id\":78}");
    yp_business_keys(true,true,2010); yp_business_keys(true,true,5010); yp_business_poll(5010);
    CHECK(yp_business_status()->alarm_active && starts==1 && cancels==0);
    deliver("{\"op\":\"call\",\"state\":\"ended\"}");
    deliver("{\"op\":\"alarm_ack\",\"id\":78}");
    CHECK(yp_business_status()->alarm_active);
    yp_business_cancel_alarm(); CHECK(yp_business_status()->alarm_active && !yp_business_sos_start_allowed());
    queue_ok=false; yp_business_poll(5020); CHECK(stops==0 && cancels==0);
    queue_ok=true; yp_business_poll(5030); CHECK(stops==1 && cancels==1);
    yp_business_poll(7030); CHECK(stops==1 && cancels==2);
    deliver("{\"op\":\"alarm_state\",\"active\":false,\"id\":77}");
    CHECK(yp_business_status()->alarm_active);
    deliver("{\"op\":\"alarm_state\",\"active\":false,\"id\":78}");
    CHECK(!yp_business_status()->alarm_active);
    CHECK(!yp_business_start_alarm()); /* Prior QP stop is queued but not yet executed. */
    yp_business_sos_stopped();
    CHECK(yp_business_start_alarm()); yp_business_poll(7040); CHECK(starts==2);

    ready(); CHECK(yp_business_start_alarm()); yp_business_cancel_alarm(); yp_business_poll(1);
    CHECK(starts==0 && syncs==1 && yp_business_status()->alarm_active);
    deliver("{\"op\":\"alarm_state\",\"active\":true,\"id\":79}");
    yp_business_poll(2); CHECK(starts==0 && cancels==1);
    deliver("{\"op\":\"alarm_state\",\"active\":false,\"id\":79}");
    CHECK(!yp_business_status()->alarm_active);

    ready(); CHECK(yp_business_start_alarm()); queue_ok=false; yp_business_poll(1);
    CHECK(starts==0); queue_ok=true; yp_business_poll(2); CHECK(starts==1);
    deliver("{\"op\":\"alarm_state\",\"active\":true,\"id\":80}");
    yp_business_transport_lost(); yp_business_cancel_alarm(); yp_business_poll(3);
    CHECK(stops==1 && yp_business_status()->alarm_active && cancels==0);
    deliver("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":true,\"alarm_id\":80}");
    yp_business_poll(4); CHECK(cancels==1 && starts==1);
    deliver("{\"op\":\"alarm_state\",\"active\":false,\"id\":80}");
    CHECK(!yp_business_status()->alarm_active);
    yp_business_init(); starts=stops=syncs=cancels=0;
    CHECK(yp_business_start_alarm()); yp_business_poll(1);
    CHECK(starts==1 && syncs==0 && !yp_business_status()->transport_ready);
    deliver("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
    yp_business_poll(2); CHECK(starts==1 && syncs==1);
    /* SAM | 2026-11-07 11:38 +08:00 | Cancellation during one held chord must require a new release/press before another SOS. */
    ready(); hold_keys(true,true,0,10000);
    CHECK(starts==1 && yp_business_status()->alarm_active && cancels==0);
    deliver("{\"op\":\"alarm_state\",\"active\":true,\"id\":81}");
    yp_business_cancel_alarm(); yp_business_poll(10010);
    deliver("{\"op\":\"alarm_state\",\"active\":false,\"id\":81}");
    yp_business_sos_stopped();
    CHECK(!yp_business_status()->alarm_active && stops==1);
    hold_keys(true,true,10020,20020);
    CHECK(starts==1 && !yp_business_status()->alarm_active);
    /* One raw release sample is bounce, not a new gesture. */
    yp_business_keys(false,false,20030);
    hold_keys(true,true,20040,24040);
    CHECK(starts==1 && !yp_business_status()->alarm_active);
    hold_keys(false,false,24050,24070);
    hold_keys(true,true,24080,27200);
    CHECK(starts==2 && yp_business_status()->alarm_active);

    /* Initialization clears the latch; the existing 500ms chord boundary still applies. */
    ready(); hold_keys(true,false,0,490); hold_keys(true,true,500,3700);
    CHECK(starts==1);
    ready(); hold_keys(true,false,0,500); hold_keys(true,true,510,3710);
    CHECK(starts==0 && !yp_business_status()->alarm_active);
    ready(); hold_keys(true,true,0,3200);
    CHECK(starts==1);
    puts("SOS QP host checks passed: single dial admission, queue retry, held-chord latch, rearm after release, debounce, 500ms boundary, early cancel, matching ID, UART recovery, start before UART readiness.");
    return 0;
}
