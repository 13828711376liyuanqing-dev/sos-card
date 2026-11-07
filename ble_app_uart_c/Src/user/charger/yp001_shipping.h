/* SAM | 2026-10-13 14:03 +08:00 | Keep ship transitions independent of SDK
 * because the actual register controller needs host bus-failure tests.
 * ETA69631 Rev1.9 pp17-18,26-27,29; factory adapter-wake mode only. */
#ifndef YP001_SHIPPING_H
#define YP001_SHIPPING_H
#include <stdbool.h>
#include <stdint.h>
typedef enum { YP_SHIP_IDLE, YP_SHIP_CHECKING, YP_SHIP_READY,
               YP_SHIP_SENT, YP_SHIP_FAILED } yp_ship_phase_t;
typedef struct {
    volatile yp_ship_phase_t phase; /* Read by key ISR; only foreground writes. */
    uint32_t since, token, sequence;
    bool disconnect_attempted;
    const char *reason;
} yp_ship_t;
typedef bool (*yp_ship_read_t)(uint8_t reg, uint8_t *value);
typedef bool (*yp_ship_write_t)(uint8_t reg, uint8_t mask, uint8_t bits);
typedef bool (*yp_ship_guard_t)(void);
static inline bool yp_ship_locked(const yp_ship_t *s) { return s->phase!=YP_SHIP_IDLE; }
static inline bool yp_ship_check(yp_ship_t *s, yp_ship_read_t read, yp_ship_guard_t guard) {
    uint8_t id, status, dpm, power, timer, ship;
    if (!guard()) { s->reason="business/key/CAT1/OTA guard"; return false; }
    if (!read(0x0B,&id)||!read(8,&status)||!read(0x0A,&dpm)||
        !read(1,&power)||!read(5,&timer)||!read(7,&ship)) {
        s->reason="I2C read failed"; return false;
    }
    if (ship&0x20U) { s->disconnect_attempted=true; s->reason="BATFET already armed"; return false; }
    if ((id&0x7FU)!=0x3FU || (status&0xFCU)!=0U || (dpm&0x80U)!=0U ||
        (power&0x30U)!=0U || (timer&0x30U)!=0U) {
        s->reason="input/charge/OTG/watchdog/ID guard"; return false;
    }
    /* Recheck after synchronous reads; ISR may have latched a short press. */
    if (!guard()) { s->reason="guard changed during I2C"; return false; }
    return true;
}
static inline bool yp_ship_prepare(yp_ship_t *s,uint32_t now,yp_ship_read_t read,yp_ship_guard_t guard) {
    if (yp_ship_locked(s)) return false;
    s->reason="qualification"; s->disconnect_attempted=false;
    if (!yp_ship_check(s,read,guard)) {
        if (s->disconnect_attempted) s->phase=YP_SHIP_FAILED;
        return false;
    }
    s->phase=YP_SHIP_CHECKING; s->since=now; s->token=0;
    return true;
}
static inline void yp_ship_poll(yp_ship_t *s,uint32_t now,yp_ship_read_t read,yp_ship_guard_t guard) {
    if (s->phase!=YP_SHIP_CHECKING && s->phase!=YP_SHIP_READY) return;
    if (!yp_ship_check(s,read,guard)) { s->phase=YP_SHIP_FAILED; s->token=0; return; }
    if (s->phase==YP_SHIP_CHECKING && (uint32_t)(now-s->since)>=2000U) {
        s->phase=YP_SHIP_READY; s->since=now;
        s->token=(++s->sequence)^now^0x53484950U;
        if (!s->token) s->token=1;
        s->reason="ready; confirm within 30 seconds";
    } else if (s->phase==YP_SHIP_READY && (uint32_t)(now-s->since)>=30000U) {
        s->phase=YP_SHIP_FAILED; s->token=0; s->reason="confirmation expired";
    }
}
static inline bool yp_ship_confirm(yp_ship_t *s,uint32_t token,uint32_t now,
    yp_ship_read_t read,yp_ship_write_t write,yp_ship_guard_t guard) {
    if (s->phase!=YP_SHIP_READY || !token || token!=s->token) return false;
    if ((uint32_t)(now-s->since)>=30000U || !yp_ship_check(s,read,guard)) {
        s->phase=YP_SHIP_FAILED; s->token=0; return false;
    }
    s->token=0; /* Consume before any write; retries require fresh preparation. */
    if (!write(7,0x08U,0x08U) || !write(0x0D,0x40U,0U) ||
        !yp_ship_check(s,read,guard)) {
        s->phase=YP_SHIP_FAILED; s->reason="delay setup/final guard failed"; return false;
    }
    /* The write may reach hardware even when its ACK/readback fails. */
    s->disconnect_attempted=true;
    if (!write(7,0x20U,0x20U)) {
        s->phase=YP_SHIP_FAILED; s->reason="BATFET write/readback uncertain; restore with 5V"; return false;
    }
    s->phase=YP_SHIP_SENT; s->since=now;
    s->reason="command accepted; SYS/current require measurement";
    return true;
}
static inline bool yp_ship_cancel(yp_ship_t *s) {
    if (s->disconnect_attempted) return false;
    s->phase=YP_SHIP_IDLE; s->token=0; s->reason="cancelled before BATFET write";
    return true;
}
#endif
