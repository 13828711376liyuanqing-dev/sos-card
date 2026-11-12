/* SAM | 2026-10-25 +08:00 | Real business-state transitions must retain read-only diagnostic provenance. */
#include "yp001_business.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); return 1; } } while(0)
bool yp_business_port_time(uint32_t epoch) { return epoch>1577836800U; }
bool yp_business_port_send(const char *line,size_t n) { return line&&n; }
static void event(const char *json) {
    char line[512];snprintf(line,sizeof line,"BUS_EVT=%s",json);
    (void)yp_business_handle_line(line,strlen(line));
}
static void hello(void) {
    event("{\"op\":\"hello\",\"imei\":\"123456789012345\",\"alarm_active\":false,\"alarm_id\":0}");
}
int main(void) {
    uint32_t e[12],again[12];
    yp_business_init();yp_business_observation_clock(100);hello();
    event("{\"op\":\"network\",\"state\":\"mqtt\"}");
    event("{\"op\":\"call\",\"state\":\"idle\"}");
    yp_business_observation_clock(200);yp_business_peer_evidence(e);
    CHECK(e[0]==1&&e[1]==YP_NET_MQTT&&e[2]==100&&e[3]==100);
    CHECK(e[4]==100&&e[5]==YP_PEER_NETWORK+YP_NET_MQTT&&e[7]==YP_NET_UNKNOWN);
    yp_business_peer_evidence(again);CHECK(!memcmp(e,again,sizeof e));
    /* Replay the bad CAT event order; known idle call survives, only peer network drops. */
    event("{\"op\":\"network\",\"state\":\"ip\"}");yp_business_peer_evidence(e);
    CHECK(e[0]==1&&e[1]==YP_NET_IP&&e[8]==YP_CALL_IDLE);
    CHECK(e[4]==200&&e[5]==YP_PEER_NETWORK+YP_NET_IP&&e[6]==1&&e[7]==YP_NET_MQTT);
    yp_business_observation_clock(300);hello();yp_business_peer_evidence(again);
    CHECK(again[2]==300&&again[4]==200&&again[5]==e[5]);
    /* A real timeout records its cause, retained even after a partial hello resynchronization. */
    yp_business_poll(20301);yp_business_peer_evidence(e);
    CHECK(!e[0]&&e[1]==YP_NET_UNKNOWN&&e[8]==YP_CALL_UNKNOWN);
    CHECK(e[5]==YP_PEER_RX_TIMEOUT&&e[10]==20301&&e[11]==YP_PEER_RX_TIMEOUT);
    yp_business_observation_clock(20302);hello();event("{\"op\":\"call\",\"state\":\"idle\"}");
    yp_business_peer_evidence(e);
    CHECK(e[0]==1&&e[1]==YP_NET_UNKNOWN&&e[8]==YP_CALL_IDLE&&e[5]==YP_PEER_HELLO);
    CHECK(e[10]==20301&&e[11]==YP_PEER_RX_TIMEOUT);
    event("{\"op\":\"network\",\"state\":\"mqtt\"}");
    yp_business_observation_clock(20400);yp_business_transport_lost_from(YP_PEER_UART_RX_LOST);
    yp_business_peer_evidence(e);CHECK(!e[0]&&e[11]==YP_PEER_UART_RX_LOST);
    /* Unknown/malformed traffic never repairs or replaces evidence. */
    event("{\"op\":\"network\",\"state\":\"garbage\"}");yp_business_peer_evidence(again);
    CHECK(!memcmp(e,again,sizeof e));
    yp_business_init();yp_business_observation_clock(0xfffffff0U);hello();
    yp_business_observation_clock(0x10U);yp_business_peer_evidence(e);CHECK(e[3]==32);
    CHECK(e[10]==0&&e[11]==YP_PEER_INIT);
    puts("PASS peer evidence: network downgrade, timeout, partial resync, UART loss, wrap, read-only");
    return 0;
}
