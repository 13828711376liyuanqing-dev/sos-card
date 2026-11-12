/* SAM | 2026-11-06 +08:00 | Host test: one press of the left or right key answers an incoming call / hangs up a dialing or
 * connected one (user requirement 2026-11-06). Builds the real yp001_business.c; drives yp_business_keys with key levels
 * and yp_business_handle_line with BUS_EVT call states; reads back the BUS_CMD lines the code sends to CAT1. */
#include "yp001_business.h"
#include "yp001_key_call.h"
#include "AOs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

/* ---- stubs (same idea as tools/name_push) ---- */
uint8_t nvds_get(uint16_t tag, uint16_t *len, uint8_t *buf) { (void)tag; (void)len; (void)buf; return 1; }
uint8_t nvds_put(uint16_t tag, uint16_t len, const uint8_t *buf) { (void)tag; (void)len; (void)buf; return 0; }
uint8_t nvds_del(uint16_t tag) { (void)tag; return 1; }
uint16_t nvds_tag_length(uint16_t tag) { (void)tag; return 0; }
uint32_t hal_flash_read(const uint32_t a, uint8_t *b, const uint32_t n) { (void)a; memset(b, 0xFF, n); return n; }
uint32_t hal_flash_write(const uint32_t a, const uint8_t *b, const uint32_t n) { (void)a; (void)b; return n; }
bool hal_flash_erase(const uint32_t a, const uint32_t n) { (void)a; (void)n; return true; }
bool yp_business_port_time(uint32_t epoch) { return epoch > 0; }
static int n_sos_start;
void start_sos_process(bool bStart) { if (bStart) ++n_sos_start; }
bool yp001_ota_power_change_allowed(void) { return true; }
int cli_printf(const char *fmt, ...) { (void)fmt; return 0; }
ParaConfig_t g_config;
ParaBindMsg_t g_bind_msg;
bool yp_business_port_sos(bool start) { (void)start; return true; }
static unsigned n_accept, n_hangup, n_alarm;
bool yp_business_port_send(const char *line, size_t n) {
    (void)n;
    if (strstr(line, "\"op\":\"accept\"")) ++n_accept;
    if (strstr(line, "\"op\":\"hangup\"")) ++n_hangup;
    if (strstr(line, "\"op\":\"alarm\"")) ++n_alarm;
    return true;
}

/* ---- helpers ---- */
static uint32_t T = 100000;
/* One key sample needs two identical calls to pass the 1-sample debounce in yp_business_keys. */
static void level(bool l, bool r) { yp_business_keys(l, r, T); T += 10; yp_business_keys(l, r, T); T += 10; }
static void tap(bool l, bool r) { level(l, r); T += 60; level(false, false); T += 600; }
static void poll(void) { T += 10; yp_business_poll(T); }
static void call(const char *state) {
    char line[160];
    int n = snprintf(line, sizeof line, "BUS_EVT={\"op\":\"call\",\"state\":\"%s\"}\r\n", state);
    (void)yp_business_handle_line(line, (size_t)n);
}
static void hello(void) {
    const char *h = "BUS_EVT={\"op\":\"hello\",\"imei\":\"864317088496529\",\"alarm_active\":false,\"alarm_id\":0}\r\n";
    (void)yp_business_handle_line(h, strlen(h));
}
static void reset_counts(void) { n_accept = n_hangup = n_alarm = 0; }
static int seq_is(const char *want) {
    char buf[32];
    T += 800;                                     /* let the chord settle */
    yp_business_keys(false, false, T); T += 10; yp_business_keys(false, false, T);
    memset(buf, 0, sizeof buf);
    (void)yp_business_take_sequence(buf, sizeof buf);
    return strcmp(buf, want) == 0;
}
static void fresh(const char *state) {
    /* poll() first: the 20 s "CAT1 silent" check uses the clock that poll() sets, so hello/call must follow it. */
    yp_business_init(); T += 5000; poll(); hello(); call(state); poll(); reset_counts();
}

int main(void)
{
    /* ---- pure logic ---- */
    yp_keycall_t k; yp_keycall_init(&k);
    CHECK(yp_keycall_step(&k, true, false, 0, true, false) == YP_KEYCALL_ACCEPT);    /* left while ringing */
    CHECK(yp_keycall_step(&k, true, true, 100, true, false) == YP_KEYCALL_NONE);     /* second key of the same gesture */
    yp_keycall_init(&k);
    CHECK(yp_keycall_step(&k, false, true, 0, false, true) == YP_KEYCALL_HANGUP);    /* right while connected */
    CHECK(yp_keycall_step(&k, true, true, 200, false, true) == YP_KEYCALL_NONE);     /* both keys: still one action */
    CHECK(yp_keycall_step(&k, false, false, 300, false, true) == YP_KEYCALL_NONE);
    CHECK(yp_keycall_step(&k, false, false, 900, false, true) == YP_KEYCALL_NONE);
    CHECK(yp_keycall_step(&k, true, false, 1000, false, true) == YP_KEYCALL_HANGUP); /* a new press later is a new gesture */
    yp_keycall_init(&k);
    CHECK(yp_keycall_step(&k, true, false, 0, false, false) == YP_KEYCALL_NONE);     /* no call: nothing */

    /* ---- real business code ---- */
    /* incoming: one tap on either key answers, once, and is not an IMEI tap */
    fresh("incoming"); tap(true, false); poll();
    CHECK(n_accept == 1 && n_hangup == 0); CHECK(seq_is(""));
    fresh("incoming"); tap(false, true); poll();
    CHECK(n_accept == 1 && n_hangup == 0); CHECK(seq_is(""));

    /* dialing: one tap on either key hangs up */
    fresh("dialing"); tap(true, false); poll();
    CHECK(n_hangup == 1 && n_accept == 0); CHECK(seq_is(""));
    fresh("dialing"); tap(false, true); poll();
    CHECK(n_hangup == 1 && n_accept == 0); CHECK(seq_is(""));

    /* connected: either key hangs up */
    fresh("connected"); tap(true, false); poll();
    CHECK(n_hangup == 1 && n_accept == 0);
    fresh("connected"); tap(false, true); poll();
    CHECK(n_hangup == 1 && n_accept == 0);

    /* a long hold (2 s) still hangs up, exactly once */
    fresh("connected"); level(true, false); T += 2000; level(true, false); level(false, false); poll(); poll();
    CHECK(n_hangup == 1);

    /* both keys together while connected: one hang-up, no accept */
    fresh("connected"); level(true, false); level(true, true); T += 60; level(false, false); poll();
    CHECK(n_hangup == 1 && n_accept == 0);

    /* answer, then (once connected) the next press hangs up */
    fresh("incoming"); tap(true, false); poll();
    CHECK(n_accept == 1); call("connected"); poll(); tap(false, true); poll();
    CHECK(n_hangup == 1);

    /* no call, or the call is over: the press does nothing to the call and stays a normal tap */
    fresh("idle"); tap(true, false); poll();
    CHECK(n_accept == 0 && n_hangup == 0); CHECK(seq_is("L"));
    fresh("ended"); tap(false, true); poll();
    CHECK(n_accept == 0 && n_hangup == 0);
    fresh("failed"); tap(true, false); poll();
    CHECK(n_accept == 0 && n_hangup == 0);
    fresh("unknown"); tap(false, true); poll();
    CHECK(n_accept == 0 && n_hangup == 0);

    /* IMEI sequence when there is no call: unchanged (left, right, left) */
    fresh("idle"); tap(true, false); tap(false, true); tap(true, false); poll();
    CHECK(n_accept == 0 && n_hangup == 0); CHECK(seq_is("LRL"));

    /* SOS chord held 3 s with no call still starts the alarm (unchanged) */
    /* the 2.8 s timer starts at the first sample where both keys are confirmed down, so hold first, then wait */
    fresh("idle"); level(true, true); level(true, true); T += 3000; level(true, true); level(false, false); poll(); poll();
    /* SAM | 2026-11-08 +08:00 | Colleague architecture: GR starts the SOS itself (start_sos_process), no BUS alarm frame. */
    CHECK(n_sos_start >= 1 && n_hangup == 0);

    printf("ALL PASS key_call\n");
    return 0;
}
