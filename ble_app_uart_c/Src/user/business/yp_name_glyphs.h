/* SAM | 2026-11-02 +08:00 | Platform-pushed resident-name glyphs (RAM banks; kept in Flash long term, see yp_ng_save).
 * Glyphs arrive staged per transaction and replace the active set only when the whole set validated. */
#ifndef YP_NAME_GLYPHS_H
#define YP_NAME_GLYPHS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* SAM | 2026-11-03 +08:00 | Campus (16px) is pushed with the name because it changes per site (燕园, 鹏园, ...). */
#define YP_NG_MAX        28U    /* 8 name characters x 2 sizes + 11 campus characters x 16px (+1 spare) */
#define YP_NG_POOL       3584U  /* SAM | 2026-11-04 +08:00 | up to the 4000-byte record: 4000 - 20 - 28 x 16 = 3532, rounded */
#define YP_NG_MAX_BYTES  200U   /* one glyph, 1bpp rows padded to bytes */
/* SAM | 2026-11-04 +08:00 | User rule: Name / Room / Campus come only from the platform, the device keeps nothing at the
 * factory, only storage space, 4 KB (approved). NVDS has a single 4 KB sector here (BLE bonds etc.), so the record moved to
 * two dedicated Flash pages A/B in the unallocated 0x2FB000-0x2FCFFF (J-Link read: all FF on 10-29, 11-03, 11-04).
 * A set whose record (20 B header + 16 B per glyph + bitmaps) is larger than YP_NG_STORE_MAX is refused at commit. */
#define YP_NG_STORE_MAX  4000U
#define YP_NG_PAGE_A     0x002FB000UL
#define YP_NG_PAGE_B     0x002FC000UL
#define YP_NG_PAGE_BYTES 4096U

typedef struct {
    uint32_t u;
    uint16_t adv_w, off;
    uint8_t size, w, h, len;
    int8_t x, y;
} yp_ng_t;

typedef enum { YP_NG_OK = 0, YP_NG_BAD, YP_NG_CRC, YP_NG_FULL, YP_NG_TXN, YP_NG_INCOMPLETE } yp_ng_err_t;

void yp_ng_begin(uint32_t id, unsigned count);
/* b64: base64 of exactly ((w+7)/8)*h bytes; crc: CRC-16/CCITT-FALSE over the 10-byte header + data. */
yp_ng_err_t yp_ng_add(uint32_t id, unsigned index, const yp_ng_t *g, const char *b64, uint16_t crc);
yp_ng_err_t yp_ng_commit(uint32_t id, unsigned count);
const yp_ng_t *yp_ng_find(uint32_t u, uint8_t size, const uint8_t **bitmap);
unsigned yp_ng_active_count(void);
uint32_t yp_ng_generation(void);
/* SAM | 2026-11-03 +08:00 | Long-term copy of the active set: save after a commit, load at boot, clear only on an explicit
 * platform clear or factory clear (name_store clear). Load/save return false on any validation or storage error.
 * SAM | 2026-11-04 +08:00 | Flash pages A/B: the new record goes to the other page, is read back, then the old page is erased;
 * load takes the valid page with the higher write generation. A record left in NVDS by an older build is moved once. */
bool yp_ng_save(uint32_t seq);
bool yp_ng_load(uint32_t *seq);
void yp_ng_clear(void);
/* Bytes of the stored record (0 = none) and its Flash page (0 = none). */
uint16_t yp_ng_stored_bytes(void);
uint32_t yp_ng_stored_page(void);
/* Last storage error of yp_ng_save / yp_ng_clear: 0 ok, 1 erase, 2 write, 3 read-back mismatch. */
uint8_t yp_ng_last_nvds_err(void);
uint16_t yp_ng_crc16(const uint8_t *data, size_t len, uint16_t crc);
#endif
