/* SAM | 2026-11-02 +08:00 | Two RAM banks (staging/active) so a broken or partial push never alters the shown name.
 * Layout matches font_cn_*.c: 1bpp, each row padded to whole bytes, MSB first.
 * SAM | 2026-11-03 +08:00 | The committed set is also kept long term so the name never loses glyphs across
 * reboot, power loss or OTA; it is removed only by an explicit clear (platform clear / factory clear).
 * SAM | 2026-11-04 +08:00 | Storage moved from NVDS (one ~1 KB tag in a single 4 KB sector shared with BLE bonds) to two
 * dedicated Flash pages A/B (YP_NG_PAGE_A/B, 4 KB each): Name / Room / Campus glyphs all come from the platform now. */
#include "yp_name_glyphs.h"
#include "gr55xx_nvds.h"
#include "hal_flash.h"
#include <string.h>

/* SAM | 2026-11-04 +08:00 | Legacy NVDS records (YNG1, tags 3/4) of 1.5.8-1.5.10 builds: read once, moved to Flash, removed. */
#define YP_NG_TAG_A     NV_TAG_APP(0x0003)
#define YP_NG_TAG_B     NV_TAG_APP(0x0004)
#define YP_NG_MAGIC     0x31474E59UL     /* "YNG1" legacy NVDS record */
#define YP_NG_MAGIC2    0x32474E59UL     /* "YNG2" Flash page record */

typedef struct {
    yp_ng_t g[YP_NG_MAX];
    uint8_t pool[YP_NG_POOL];
    uint16_t used;
    uint8_t count;
} bank_t;

static bank_t s_bank[2];
static uint8_t s_active;            /* index of the active bank; the other one stages */
static uint32_t s_txn, s_seen;      /* staging transaction id and received-index bitmask */
static unsigned s_expect;
static bool s_open;
static uint32_t s_generation;      /* bumps on every commit so the UI redraws even when the name text is unchanged */
static uint32_t s_store_page;      /* Flash page holding the valid stored record, 0 = none */
static uint32_t s_store_gen;       /* write generation of that record */
static uint16_t s_store_len;       /* its length in bytes */
static uint8_t s_nvds_err;         /* last storage error (0 ok, 1 erase, 2 write, 3 read-back) */

/* Legacy NVDS record: header, then count entries, then `used` pool bytes. CRC-16 covers everything after the header. */
typedef struct { uint32_t magic, seq; uint16_t used, crc; uint8_t count, rsv[3]; } store_hdr_t;
/* Flash record: same layout plus a write generation (newer page wins; Seq can repeat when the same set is saved again). */
typedef struct { uint32_t magic, seq, gen; uint16_t used, crc; uint8_t count, rsv[3]; } page_hdr_t;
static size_t store_bytes(const bank_t *b) { return sizeof(page_hdr_t) + b->count * sizeof(yp_ng_t) + b->used; }

uint16_t yp_ng_crc16(const uint8_t *data, size_t len, uint16_t crc)
{
    while (len--) {
        crc ^= (uint16_t)(*data++ << 8);
        for (unsigned i = 0; i < 8U; ++i) crc = (crc & 0x8000U) ? (uint16_t)((crc << 1) ^ 0x1021U) : (uint16_t)(crc << 1);
    }
    return crc;
}

static int b64v(char c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

/* Strict decode: length must be a multiple of 4 and produce exactly `want` bytes. */
static bool b64_decode(const char *s, uint8_t *out, size_t want)
{
    size_t n = strlen(s), o = 0;
    if (n == 0U || n % 4U) return false;
    for (size_t i = 0; i < n; i += 4U) {
        int v[4];
        for (unsigned k = 0; k < 4U; ++k) v[k] = s[i + k] == '=' && i + 4U == n && k >= 2U ? -2 : b64v(s[i + k]);
        if (v[0] < 0 || v[1] < 0 || v[2] == -1 || v[3] == -1 || (v[2] == -2 && v[3] != -2)) return false;
        uint32_t x = (uint32_t)v[0] << 18 | (uint32_t)v[1] << 12 | (uint32_t)(v[2] < 0 ? 0 : v[2]) << 6 | (uint32_t)(v[3] < 0 ? 0 : v[3]);
        uint8_t b[3] = {(uint8_t)(x >> 16), (uint8_t)(x >> 8), (uint8_t)x};
        unsigned m = v[2] == -2 ? 1U : v[3] == -2 ? 2U : 3U;
        for (unsigned k = 0; k < m; ++k) { if (o >= want) return false; out[o++] = b[k]; }
    }
    return o == want;
}

void yp_ng_begin(uint32_t id, unsigned count)
{
    bank_t *b = &s_bank[s_active ^ 1U];
    memset(b, 0, sizeof(*b));
    s_txn = id; s_seen = 0; s_expect = count; s_open = count <= YP_NG_MAX;   /* 0 = pure ASCII name: built-in font, no glyphs */
}

yp_ng_err_t yp_ng_add(uint32_t id, unsigned index, const yp_ng_t *g, const char *b64, uint16_t crc)
{
    bank_t *b = &s_bank[s_active ^ 1U];
    uint8_t buf[YP_NG_MAX_BYTES], hdr[10];
    if (!s_open || id != s_txn) return YP_NG_TXN;
    /* Full Unicode range: rare name characters are often in CJK Ext-B and beyond (U+20000+). */
    if (!g || !b64 || index >= s_expect || (g->size != 16U && g->size != 32U) || g->u < 0x80U || g->u > 0x10FFFFU ||
        (g->u >= 0xD800U && g->u <= 0xDFFFU) || !g->w || !g->h || g->w > 40U || g->h > 40U ||
        g->x < -40 || g->x > 40 || g->y < -40 || g->y > 40 || g->adv_w > 40U * 16U) return YP_NG_BAD;
    size_t len = (size_t)(g->w + 7U) / 8U * g->h;
    if (len > YP_NG_MAX_BYTES || !b64_decode(b64, buf, len)) return YP_NG_BAD;
    hdr[0] = (uint8_t)(g->u >> 16); hdr[1] = (uint8_t)(g->u >> 8); hdr[2] = (uint8_t)g->u;
    hdr[3] = g->size; hdr[4] = g->w; hdr[5] = g->h; hdr[6] = (uint8_t)g->x; hdr[7] = (uint8_t)g->y;
    hdr[8] = (uint8_t)(g->adv_w >> 8); hdr[9] = (uint8_t)g->adv_w;
    if (yp_ng_crc16(buf, len, yp_ng_crc16(hdr, sizeof(hdr), 0xFFFFU)) != crc) return YP_NG_CRC;
    /* A resent line for the same index is accepted only if identical, so retries are idempotent. */
    if (s_seen & (1UL << index)) {
        for (unsigned i = 0; i < b->count; ++i)
            if (b->g[i].u == g->u && b->g[i].size == g->size)
                return b->g[i].len == len && !memcmp(b->pool + b->g[i].off, buf, len) ? YP_NG_OK : YP_NG_BAD;
        return YP_NG_BAD;
    }
    for (unsigned i = 0; i < b->count; ++i)
        if (b->g[i].u == g->u && b->g[i].size == g->size) return YP_NG_BAD;   /* duplicate glyph under another index */
    if (b->count >= YP_NG_MAX || b->used + len > sizeof(b->pool)) return YP_NG_FULL;
    yp_ng_t *e = &b->g[b->count++];
    *e = *g; e->off = b->used; e->len = (uint8_t)len;
    memcpy(b->pool + b->used, buf, len); b->used = (uint16_t)(b->used + len);
    s_seen |= 1UL << index;
    return YP_NG_OK;
}

yp_ng_err_t yp_ng_commit(uint32_t id, unsigned count)
{
    if (!s_open || id != s_txn) return YP_NG_TXN;
    if (count != s_expect || s_seen != (s_expect >= 32U ? 0xFFFFFFFFUL : (1UL << s_expect) - 1U)) return YP_NG_INCOMPLETE;
    if (store_bytes(&s_bank[s_active ^ 1U]) > YP_NG_STORE_MAX) { s_open = false; return YP_NG_FULL; }
    s_active ^= 1U;
    s_open = false;
    ++s_generation;
    return YP_NG_OK;
}

const yp_ng_t *yp_ng_find(uint32_t u, uint8_t size, const uint8_t **bitmap)
{
    const bank_t *b = &s_bank[s_active];
    for (unsigned i = 0; i < b->count; ++i)
        if (b->g[i].u == u && b->g[i].size == size) {
            if (bitmap) *bitmap = b->pool + b->g[i].off;
            return &b->g[i];
        }
    return NULL;
}

unsigned yp_ng_active_count(void) { return s_bank[s_active].count; }

static uint8_t s_blob[YP_NG_PAGE_BYTES];

/* Record of the active bank in s_blob (Flash layout); returns its length. */
static size_t serialize(const bank_t *b, uint32_t seq, uint32_t gen)
{
    page_hdr_t h = {YP_NG_MAGIC2, seq, gen, b->used, 0, b->count, {0}};
    size_t n = sizeof(h);
    memcpy(s_blob + n, b->g, b->count * sizeof(yp_ng_t)); n += b->count * sizeof(yp_ng_t);
    memcpy(s_blob + n, b->pool, b->used); n += b->used;
    h.crc = yp_ng_crc16(s_blob + sizeof(h), n - sizeof(h), 0xFFFFU);
    memcpy(s_blob, &h, sizeof(h));
    return n;
}

/* Flash `page` equals s_blob[0..n) (compared in small chunks, no second 4 KB buffer). */
static bool page_equals(uint32_t page, size_t n)
{
    uint8_t chunk[64];
    for (size_t at = 0; at < n; at += sizeof(chunk)) {
        uint32_t k = (uint32_t)((n - at) < sizeof(chunk) ? (n - at) : sizeof(chunk));
        if (hal_flash_read(page + (uint32_t)at, chunk, k) != k || memcmp(chunk, s_blob + at, k)) return false;
    }
    return true;
}

/* Fill the active bank from a checked record in s_blob (entries + pool after a `hdr`-byte header). */
static bool take(size_t hdr, uint8_t count, uint16_t used)
{
    bank_t *b = &s_bank[s_active];
    memset(b, 0, sizeof(*b));
    memcpy(b->g, s_blob + hdr, count * sizeof(yp_ng_t));
    memcpy(b->pool, s_blob + hdr + count * sizeof(yp_ng_t), used);
    for (unsigned i = 0; i < count; ++i)      /* every entry must point inside the stored pool */
        if ((uint32_t)b->g[i].off + b->g[i].len > used || b->g[i].len > YP_NG_MAX_BYTES) { memset(b, 0, sizeof(*b)); return false; }
    b->count = count; b->used = used;
    return true;
}

/* Read and check one Flash page into s_blob. */
static bool read_page(uint32_t page, page_hdr_t *h, uint16_t *len)
{
    if (hal_flash_read(page, (uint8_t *)h, sizeof(*h)) != sizeof(*h) || h->magic != YP_NG_MAGIC2 ||
        h->count > YP_NG_MAX || h->used > YP_NG_POOL) return false;
    size_t n = sizeof(*h) + h->count * sizeof(yp_ng_t) + h->used;
    if (n > YP_NG_STORE_MAX || hal_flash_read(page, s_blob, (uint32_t)n) != n) return false;
    *len = (uint16_t)n;
    return yp_ng_crc16(s_blob + sizeof(*h), n - sizeof(*h), 0xFFFFU) == h->crc;
}

bool yp_ng_save(uint32_t seq)
{
    const bank_t *b = &s_bank[s_active];
    if (store_bytes(b) > YP_NG_STORE_MAX) return false;
    /* Same content already stored: do not wear the Flash. */
    if (s_store_page && page_equals(s_store_page, serialize(b, seq, s_store_gen))) return true;
    uint32_t target = s_store_page == YP_NG_PAGE_A ? YP_NG_PAGE_B : YP_NG_PAGE_A, gen = s_store_gen + 1U;
    size_t n = serialize(b, seq, gen);
    /* New copy first, read back, only then remove the old one: a reset at any point leaves one valid record. */
    if (!hal_flash_erase(target, YP_NG_PAGE_BYTES)) { s_nvds_err = 1; return false; }
    if (hal_flash_write(target, s_blob, (uint32_t)n) != n) { s_nvds_err = 2; return false; }
    if (!page_equals(target, n)) { s_nvds_err = 3; return false; }
    if (s_store_page) (void)hal_flash_erase(s_store_page, YP_NG_PAGE_BYTES);
    (void)nvds_del(YP_NG_TAG_A);      /* a legacy NVDS record must not come back over a newer Flash one */
    (void)nvds_del(YP_NG_TAG_B);
    s_store_page = target; s_store_gen = gen; s_store_len = (uint16_t)n; s_nvds_err = 0;
    return true;
}

/* Legacy NVDS record (1.5.8-1.5.10): read and check one tag into s_blob. */
static bool load_tag(uint16_t tag, store_hdr_t *h, uint16_t *len)
{
    *len = (uint16_t)sizeof(s_blob);
    if (nvds_get(tag, len, s_blob) != NVDS_SUCCESS || *len < sizeof(*h)) return false;
    memcpy(h, s_blob, sizeof(*h));
    return h->magic == YP_NG_MAGIC && h->count <= YP_NG_MAX && h->used <= YP_NG_POOL &&
        *len == sizeof(*h) + h->count * sizeof(yp_ng_t) + h->used &&
        yp_ng_crc16(s_blob + sizeof(*h), *len - sizeof(*h), 0xFFFFU) == h->crc;
}

bool yp_ng_load(uint32_t *seq)
{
    page_hdr_t a, bb;
    uint16_t la = 0, lb = 0;
    bool va = read_page(YP_NG_PAGE_A, &a, &la), vb = read_page(YP_NG_PAGE_B, &bb, &lb);
    s_store_page = 0; s_store_gen = 0; s_store_len = 0;
    if (va || vb) {
        /* Both valid only if a reset hit between the new write and the old erase: the higher generation wins. */
        bool use_b = vb && (!va || bb.gen > a.gen);
        const page_hdr_t *h = use_b ? &bb : &a;
        uint32_t page = use_b ? YP_NG_PAGE_B : YP_NG_PAGE_A;
        if (!use_b || va) {               /* s_blob holds the page read last (B when it was valid): reload the winner */
            if (!read_page(page, use_b ? &bb : &a, use_b ? &lb : &la)) return false;
        }
        if (!take(sizeof(*h), h->count, h->used)) return false;
        if (va && vb) (void)hal_flash_erase(use_b ? YP_NG_PAGE_A : YP_NG_PAGE_B, YP_NG_PAGE_BYTES);
        s_store_page = page; s_store_gen = h->gen; s_store_len = use_b ? lb : la;
        if (seq) *seq = h->seq;
        ++s_generation;
        return true;
    }
    /* Older build: a record in NVDS. Show it, move it to Flash (yp_ng_save also removes the NVDS tags). */
    store_hdr_t h;
    uint16_t len;
    bool ta = load_tag(YP_NG_TAG_A, &h, &len);
    uint32_t seq_a = h.seq;
    bool tb = load_tag(YP_NG_TAG_B, &h, &len);
    if (!ta && !tb) return false;
    if (tb && ta && seq_a >= h.seq) tb = false;
    if (!tb && !load_tag(YP_NG_TAG_A, &h, &len)) return false;
    if (!take(sizeof(h), h.count, h.used)) return false;
    if (seq) *seq = h.seq;
    ++s_generation;
    (void)yp_ng_save(h.seq);
    return true;
}

void yp_ng_clear(void)
{
    memset(s_bank, 0, sizeof(s_bank));
    s_open = false;
    s_nvds_err = (hal_flash_erase(YP_NG_PAGE_A, YP_NG_PAGE_BYTES) && hal_flash_erase(YP_NG_PAGE_B, YP_NG_PAGE_BYTES)) ? 0U : 1U;
    (void)nvds_del(YP_NG_TAG_A);
    (void)nvds_del(YP_NG_TAG_B);
    s_store_page = 0; s_store_gen = 0; s_store_len = 0;
    ++s_generation;
}
uint16_t yp_ng_stored_bytes(void) { return s_store_len; }
uint32_t yp_ng_stored_page(void) { return s_store_page; }
uint8_t yp_ng_last_nvds_err(void) { return s_nvds_err; }
uint32_t yp_ng_generation(void) { return s_generation; }

#ifdef YP_BUSINESS_HOST_TEST
/* Host test only: lose RAM as a real reset would, keeping Flash and NVDS. */
void yp_ng_test_wipe_ram(void) { memset(s_bank, 0, sizeof(s_bank)); s_open = false; s_store_page = 0; s_store_gen = 0; s_store_len = 0; }
#endif
