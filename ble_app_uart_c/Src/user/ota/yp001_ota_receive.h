/* SAM | 2026-10-23 +08:00 | B-slot reception separates accepted bytes from durable checkpoints. */
#ifndef YP001_OTA_RECEIVE_H
#define YP001_OTA_RECEIVE_H
#include <stdint.h>
#include "yp001_ota_layout.h"
typedef struct {
    void *ctx;
    /* Revalidate trusted owner and transfer safety before EVERY operation. */
    int (*allowed)(void *, uint32_t, const uint8_t *, uint32_t);
    int (*read)(void *, uint32_t, void *, uint32_t);
    int (*erase)(void *, uint32_t);
    int (*write)(void *, uint32_t, const void *, uint32_t);
    /* Atomically persist owner/hash/total/offset after readback. */
    int (*checkpoint)(void *, uint32_t, const uint8_t *, uint32_t, uint32_t);
    /* Whole native hash + signature/model/layout/data/version, never CRC alone. */
    int (*verify)(void *, const uint8_t *, uint32_t);
} yp_receive_io;
typedef struct {
    yp_receive_io io;
    uint32_t session, total, accepted, durable;
    uint8_t hash[32], sector[4096];
    int ready, verified;
    /* SAM | 2026-11-01 +08:00 | Optional volatile staging buffer (PSRAM OTA region): data lands here first and B is written only once the
     * whole image has arrived. NULL keeps the original sector-by-sector path. */
    uint8_t *stage;
} yp_receive;
/* resume comes only from a validated persistent record, never from a UART claim.
 * IO addresses are absolute; only selected B is ever passed to callbacks.
 * Nonzero callback result means failure. No concurrent/reentrant calls. */
int yp_receive_open(yp_receive *, const yp_receive_io *, uint32_t,
                    const uint8_t[32], uint32_t, uint32_t);
int yp_receive_data(yp_receive *, uint32_t, uint32_t, const uint8_t *, uint32_t);
int yp_receive_verify(yp_receive *);
/* SAM | 2026-11-01 +08:00 | Attach a staging buffer right after open; only for a fresh transfer (nothing accepted or durable) and size >= total. */
int yp_receive_stage(yp_receive *, uint8_t *, uint32_t);
/* SAM | 2026-10-23 +08:00 | Actual UART dispatch contract; BEGIN never creates write authority from untrusted bytes. */
enum { YP_RX_HELLO=1, YP_RX_CAPS=2, YP_RX_BEGIN=3, YP_RX_DATA=4,
       YP_RX_QUERY=5, YP_RX_VERIFY=6, YP_RX_ACTIVATE=7, YP_RX_ABORT=8,
       YP_RX_RESULT=9, YP_RX_ACK=128, YP_RX_NACK=129 };
/* Response payload: request u8, reason u8, flags u16, accepted/durable/total u32.
 * flags: 1=receiver open, 2=verified. Echo session/sequence/offset in header.
 * HELLO returns CAPS: max payload u16, sector u16, slot u32, features u32, flags u32.
 * No activation opcode is authorized by this staging endpoint. */
uint32_t yp_receive_frame(yp_receive *, const uint8_t *, uint32_t, uint8_t *, uint32_t);
#endif
