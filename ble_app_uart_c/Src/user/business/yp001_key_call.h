/* SAM | 2026-11-06 +08:00 | Single key press during a call (user requirement 2026-11-06):
 *   - call INCOMING                     : one press of the left OR the right key answers it;
 *   - call DIALING or CONNECTED         : one press of the left OR the right key hangs it up
 *     (no chord, no long press, no 3 s hold; previously only the two-key 3 s gesture could end anything);
 *   - no call (idle / ended / failed / unknown): the press does nothing here (taps still feed the IMEI sequence).
 * Pure logic, no hardware or business state, so tools/key_call/test_key_call.c can drive it with key sequences.
 * A gesture is one action: if the second key goes down within YP_KEYCALL_GESTURE_MS of the first (an SOS chord, or both thumbs),
 * the second press is part of the same gesture and does nothing. The key that triggered an action is "swallowed": its release is
 * not a tap, so answering or hanging up never enters the "press left/right repeatedly to show the IMEI" sequence. */
#ifndef YP001_KEY_CALL_H
#define YP001_KEY_CALL_H
#include <stdbool.h>
#include <stdint.h>

#define YP_KEYCALL_GESTURE_MS 500U

typedef enum { YP_KEYCALL_NONE, YP_KEYCALL_ACCEPT, YP_KEYCALL_HANGUP } yp_keycall_action_t;

typedef struct {
    bool left, right;                 /* stable key levels at the previous step */
    bool active;                      /* a press gesture is in progress */
    uint32_t start_ms;                /* first key-down of the gesture */
    bool swallow_left, swallow_right; /* the next release of this key is not a tap */
} yp_keycall_t;

static inline void yp_keycall_init(yp_keycall_t *k)
{
    k->left = k->right = k->active = k->swallow_left = k->swallow_right = false;
    k->start_ms = 0U;
}

/* Call once per stable key sample. incoming / in_progress come from the CAT1 call state:
 * incoming = INCOMING; in_progress = DIALING or CONNECTED. */
static inline yp_keycall_action_t yp_keycall_step(yp_keycall_t *k, bool left, bool right, uint32_t now,
                                                  bool incoming, bool in_progress)
{
    bool edge_left = left && !k->left, edge_right = right && !k->right;
    yp_keycall_action_t action = YP_KEYCALL_NONE;

    if (k->active && !left && !right && (uint32_t)(now - k->start_ms) > YP_KEYCALL_GESTURE_MS) k->active = false;
    if (edge_left || edge_right) {
        if (!k->active || (uint32_t)(now - k->start_ms) > YP_KEYCALL_GESTURE_MS) {
            k->active = true;
            k->start_ms = now;
            action = incoming ? YP_KEYCALL_ACCEPT : (in_progress ? YP_KEYCALL_HANGUP : YP_KEYCALL_NONE);
            if (action != YP_KEYCALL_NONE) {
                k->swallow_left = edge_left;
                k->swallow_right = edge_right;
            }
        } else if (k->swallow_left || k->swallow_right) {
            /* second key of the same gesture: also not a tap */
            if (edge_left) k->swallow_left = true;
            if (edge_right) k->swallow_right = true;
        }
    }
    k->left = left;
    k->right = right;
    return action;
}

/* True once if the release of this key belongs to an answer / hang-up press and must not count as a tap. */
static inline bool yp_keycall_swallow(yp_keycall_t *k, bool is_left)
{
    bool *flag = is_left ? &k->swallow_left : &k->swallow_right;
    bool v = *flag;
    *flag = false;
    return v;
}
#endif
