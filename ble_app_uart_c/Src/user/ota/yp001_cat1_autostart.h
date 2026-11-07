/* SAM | 2026-10-28 19:00 +08:00 | Bench CAT1 autostart during an active GR OTA because every GR reset (including the install reset) leaves CAT1 unpowered, boot never presses PWRKEY and the protected-install gate refuses the manual key, so download/TRIAL health over MQTT could never resume. Header-only so the host test runs the exact decision and the Keil project needs no new file. */
#ifndef YP001_CAT1_AUTOSTART_H
#define YP001_CAT1_AUTOSTART_H
#include <stdbool.h>
#include <stdint.h>

#define YP001_CAT1_AUTOSTART_GRACE_MS 15000u /* CAT1 that is already running reports well within this; pressing it would power it off. */
#define YP001_CAT1_AUTOSTART_PULSE_MS 1600u  /* Same pulse width as the verified manual `cat1_power key`. */

enum { YP001_CAT1_AS_NONE, YP001_CAT1_AS_ASSERT, YP001_CAT1_AS_RELEASE };
typedef struct { uint8_t state; uint32_t at; } yp001_cat1_autostart_t; /* state: 0 waiting, 1 asserted, 2 finished for this boot */

/* now_ms counts from GR boot. At most one press per boot; never when CAT1 has been heard; release is always delivered once asserted. */
static inline int yp001_cat1_autostart_step(yp001_cat1_autostart_t *s, uint32_t now_ms, bool gr_owner_active, bool peer_seen)
{
    if (s->state == 1u) {
        if ((uint32_t)(now_ms - s->at) < YP001_CAT1_AUTOSTART_PULSE_MS) return YP001_CAT1_AS_NONE;
        s->state = 2u; return YP001_CAT1_AS_RELEASE;
    }
    if (s->state == 2u) return YP001_CAT1_AS_NONE;
    if (peer_seen) { s->state = 2u; return YP001_CAT1_AS_NONE; }
    if (!gr_owner_active || now_ms < YP001_CAT1_AUTOSTART_GRACE_MS) return YP001_CAT1_AS_NONE;
    s->state = 1u; s->at = now_ms; return YP001_CAT1_AS_ASSERT;
}
#endif
