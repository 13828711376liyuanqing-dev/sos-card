/* SAM | 2026-11-02 +08:00 | Host test of the real GR name-push code (yp001_business.c + yp_name_glyphs.c) fed with
 * lines produced by tools/glyph_maker (argv[1]); checks commit, glyph bytes, rejection paths, persistence across reboot and clear.
 * SAM | 2026-11-04 +08:00 | Glyph record in Flash pages A/B (0x2FB000/0x2FC000) instead of NVDS: RAM Flash image below with
 * NOR semantics (erase = FF, write only clears bits), write cut-off (power loss) and erase/write failures; legacy NVDS migration. */
#include "yp001_business.h"
#include "yp_name_glyphs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s (last NAME_RES: %s)\n", __LINE__, #x, last_res); return 1; } } while (0)

static char last_res[256];
static unsigned res_count;
/* RAM NVDS: a few tags; nv_fail = number of next puts that fail (space not enough). */
static struct { uint16_t tag, len; uint8_t data[4096]; int used; } nv[8];
static int nv_fail;
static unsigned nv_cap;   /* nonzero: total bytes the RAM NVDS holds (put fails beyond it) */
static int nv_find(uint16_t tag) { for (int i = 0; i < 8; ++i) if (nv[i].used && nv[i].tag == tag) return i; return -1; }
uint8_t nvds_get(uint16_t tag, uint16_t *len, uint8_t *buf) {
    int i = nv_find(tag);
    if (i < 0) return 1;
    if (*len < nv[i].len) return 1;   /* like the SDK: p_len in = buffer size (11-03: len 0 must fail) */
    memcpy(buf, nv[i].data, nv[i].len); *len = nv[i].len; return 0;
}
uint8_t nvds_put(uint16_t tag, uint16_t len, const uint8_t *buf) {
    if (nv_fail) { --nv_fail; return 2; }
    int i = nv_find(tag);
    /* Like the board (11-03): an item over about 1 KB fails and the tag's old data is gone too. */
    if (len > 1024) { if (i >= 0) nv[i].used = 0; return 4; }
    if (nv_cap) { unsigned sum = len; for (int k = 0; k < 8; ++k) if (nv[k].used && k != i) sum += nv[k].len; if (sum > nv_cap) return 2; }
    for (int k = 0; i < 0 && k < 8; ++k) if (!nv[k].used) i = k;
    nv[i].used = 1; nv[i].tag = tag; nv[i].len = len; memcpy(nv[i].data, buf, len); return 0;
}
uint8_t nvds_del(uint16_t tag) { int i = nv_find(tag); if (i < 0) return 1; nv[i].used = 0; return 0; }
uint16_t nvds_tag_length(uint16_t tag) { int i = nv_find(tag); return i < 0 ? 0 : nv[i].len; }
void yp_ng_test_wipe_ram(void);
void yp_business_test_cold_boot(void);
static void reboot(void) { yp_ng_test_wipe_ram(); yp_business_init(); }
/* Flash: only the two name-glyph pages exist; any other address fails (the code must never touch it). */
static uint8_t fl[2][4096];
static unsigned fl_cut;     /* nonzero: the next write stores only this many bytes, then 'power is lost' (reports success) */
static int fl_write_fail, fl_erase_fail, fl_foreign;
static uint8_t *fl_at(uint32_t a, uint32_t n) {
    for (int k = 0; k < 2; ++k) { uint32_t base = 0x2FB000UL + 0x1000UL * (uint32_t)k;
        if (a >= base && a + n <= base + 4096U) return fl[k] + (a - base); }
    ++fl_foreign; return NULL;
}
uint32_t hal_flash_read(const uint32_t a, uint8_t *b, const uint32_t n) { uint8_t *s = fl_at(a, n); if (!s) return 0; memcpy(b, s, n); return n; }
uint32_t hal_flash_write(const uint32_t a, const uint8_t *b, const uint32_t n) {
    uint8_t *d = fl_at(a, n); if (!d) return 0;
    if (fl_write_fail) { --fl_write_fail; return 0; }
    uint32_t m = fl_cut && fl_cut < n ? fl_cut : n; fl_cut = 0;
    for (uint32_t i = 0; i < m; ++i) d[i] &= b[i];
    return n;
}
bool hal_flash_erase(const uint32_t a, const uint32_t n) {
    uint8_t *d = fl_at(a, n); if (!d || (a & 0xFFFU) || n != 4096U) return false;
    if (fl_erase_fail) { --fl_erase_fail; return false; }
    memset(d, 0xFF, n); return true;
}
static int page_of(uint32_t page) { return page == 0x2FB000UL ? 0 : page == 0x2FC000UL ? 1 : -1; }
static bool page_has_record(int k) { return !memcmp(fl[k], "YNG2", 4); }
static unsigned stored_pages(void) { return page_has_record(0) + page_has_record(1); }
static bool page_blank(int k) { for (int i = 0; i < 4096; ++i) if (fl[k][i] != 0xFF) return false; return true; }
static char big[64][1024];
static unsigned nbig;

bool yp_business_port_time(uint32_t epoch) { return epoch > 0; }
void start_sos_process(void) {}
/* SAM | 2026-11-04 +08:00 | Name tests do not run QP; emulate successful queue admission. */
bool yp_business_port_sos(bool start) { (void)start; return true; }
bool yp_business_port_send(const char *line, size_t n) {
    if (!strncmp(line, "NAME_RES=", 9)) { ++res_count; snprintf(last_res, sizeof(last_res), "%.*s", (int)n, line); }
    return true;
}

static char lines[64][1024];
static unsigned nlines;
static bool feed(const char *l) { return yp_business_handle_line(l, strlen(l)); }
static void feed_all(void) { for (unsigned i = 0; i < nlines; ++i) feed(lines[i]); }

int main(int argc, char **argv) {
    FILE *f;
    static char want_name[64];
    CHECK(argc == 4);
    /* argv[2] is the expected name as UTF-8 hex: Windows argv is not UTF-8. */
    for (size_t i = 0; argv[2][2 * i] && argv[2][2 * i + 1] && i + 1 < sizeof(want_name); ++i) {
        unsigned b; sscanf(argv[2] + 2 * i, "%2x", &b); want_name[i] = (char)b;
    }
    argv[2] = want_name;
    CHECK((f = fopen(argv[1], "rb")) != NULL);
    while (nlines < 64 && fgets(lines[nlines], sizeof(lines[0]), f)) {
        lines[nlines][strcspn(lines[nlines], "\r\n")] = 0;
        if (lines[nlines][0]) ++nlines;
    }
    fclose(f);
    CHECK(nlines >= 3);
    CHECK((f = fopen(argv[3], "rb")) != NULL);
    while (nbig < 64 && fgets(big[nbig], sizeof(big[0]), f)) {
        big[nbig][strcspn(big[nbig], "\r\n")] = 0;
        if (big[nbig][0]) ++nbig;
    }
    fclose(f);
    memset(fl, 0xFF, sizeof(fl));     /* factory state: both pages erased */
    yp_business_init();

    /* 1. Happy path: whole set commits, name changes, one OK result. */
    feed_all();
    printf("fed %u lines -> %s", nlines, last_res);
    CHECK(res_count == 1 && strstr(last_res, "\"ok\":true"));
    CHECK(yp_business_status()->resident_known);
    CHECK(strcmp(yp_business_status()->name, argv[2]) == 0);
    CHECK(yp_ng_active_count() == nlines - 2);
    printf("commit ok: name=%s glyphs=%u gen=%u\n", yp_business_status()->name, yp_ng_active_count(), (unsigned)yp_ng_generation());

    /* 2. Every glyph decodes to the bytes the generator wrote (expected bytes in argv[1].hex). */
    {
        char path[512]; snprintf(path, sizeof(path), "%s.hex", argv[1]);
        FILE *h = fopen(path, "rb"); char row[600]; unsigned checked = 0;
        CHECK(h != NULL);
        while (fgets(row, sizeof(row), h)) {
            unsigned u, size; char hex[500]; const uint8_t *bm; uint8_t want[200]; size_t n = 0;
            if (sscanf(row, "%x %u %499s", &u, &size, hex) != 3) continue;
            for (char *p = hex; p[0] && p[1]; p += 2) { unsigned b; sscanf(p, "%2x", &b); want[n++] = (uint8_t)b; }
            const yp_ng_t *g = yp_ng_find(u, (uint8_t)size, &bm);
            CHECK(g != NULL && g->len == n && memcmp(bm, want, n) == 0);
            ++checked;
        }
        fclose(h);
        CHECK(checked == nlines - 2);
        printf("bitmaps identical: %u\n", checked);
    }
    uint32_t gen = yp_ng_generation();

    /* 3. Corrupted pixel data (same CRC) is rejected; the active set and name stay untouched. */
    {
        char bad[1024]; strcpy(bad, lines[1]);
        char *d = strstr(bad, "\"d\":\""); CHECK(d != NULL);
        d += 5; *d = (*d == 'A') ? 'B' : 'A';
        res_count = 0;
        feed(lines[0]); feed(bad);
        CHECK(res_count == 1 && strstr(last_res, "\"ok\":false") && strstr(last_res, "\"err\":2"));
        for (unsigned i = 2; i < nlines; ++i) feed(lines[i]);       /* rest of the txn must not commit */
        CHECK(yp_ng_generation() == gen && yp_ng_active_count() == nlines - 2);
        CHECK(strcmp(yp_business_status()->name, argv[2]) == 0);
        printf("bad crc rejected, old set kept\n");
    }

    /* 4. Missing glyph line -> name_end reports INCOMPLETE, nothing changes. */
    res_count = 0;
    feed(lines[0]);
    for (unsigned i = 2; i < nlines; ++i) feed(lines[i]);
    CHECK(strstr(last_res, "\"ok\":false") && strstr(last_res, "\"err\":5") && yp_ng_generation() == gen);
    printf("incomplete set rejected\n");

    /* 5. Resent identical glyph line inside a txn is idempotent; full resend commits again. */
    res_count = 0;
    feed(lines[0]); feed(lines[1]); feed(lines[1]);
    for (unsigned i = 2; i < nlines; ++i) feed(lines[i]);
    CHECK(res_count == 1 && strstr(last_res, "\"ok\":true") && yp_ng_generation() == gen + 1);
    printf("duplicate line idempotent\n");

    /* 6. Older seq is refused (stale platform message). */
    res_count = 0;
    feed("BUS_EVT={\"op\":\"name_begin\",\"id\":77,\"seq\":1,\"g\":1,\"name\":\"x\",\"room\":\"\",\"campus\":\"\"}");
    CHECK(res_count == 1 && strstr(last_res, "\"ok\":false") && strstr(last_res, "\"err\":4"));
    printf("stale seq refused\n");

    /* 7. Glyph without a begin, malformed JSON, oversize count: rejected, no crash. */
    yp_business_init();
    res_count = 0; feed(lines[1]);
    CHECK(strstr(last_res, "\"err\":4"));
    CHECK(feed("BUS_EVT={\"op\":\"glyph\",\"id\":1,\"i\":0}"));
    CHECK(feed("BUS_EVT={\"op\":\"name_begin\",\"id\":9,\"seq\":1,\"g\":99,\"name\":\"x\",\"room\":\"\",\"campus\":\"\"}"));
    CHECK(strstr(last_res, "\"err\":1"));

    /* 8. Long-term storage (2026-11-03): commit the set again, then a reset restores name AND glyphs byte for byte. */
    yp_business_init();
    feed_all();
    CHECK(strstr(last_res, "\"ok\":true") && yp_ng_stored_bytes() > 0 && stored_pages() == 1 && page_of(yp_ng_stored_page()) >= 0);
    reboot();
    CHECK(yp_business_status()->resident_known && strcmp(yp_business_status()->name, argv[2]) == 0);
    CHECK(yp_ng_active_count() == nlines - 2);
    {
        char path[512]; snprintf(path, sizeof(path), "%s.hex", argv[1]);
        FILE *h = fopen(path, "rb"); char row[600]; unsigned ok = 0;
        while (h && fgets(row, sizeof(row), h)) {
            unsigned u, size; char hex[500]; const uint8_t *bm; uint8_t want[200]; size_t n = 0;
            if (sscanf(row, "%x %u %499s", &u, &size, hex) != 3) continue;
            for (char *p = hex; p[0] && p[1]; p += 2) { unsigned b; sscanf(p, "%2x", &b); want[n++] = (uint8_t)b; }
            const yp_ng_t *g = yp_ng_find(u, (uint8_t)size, &bm);
            ok += g && g->len == n && !memcmp(bm, want, n);
        }
        if (h) fclose(h);
        CHECK(ok == nlines - 2);
    }
    printf("reboot: name and %u glyphs restored from NVDS, bitmaps identical\n", yp_ng_active_count());   /* text: NVDS; glyphs: Flash page */

    /* 9. After the reboot the stored Seq still blocks an older push. */
    res_count = 0;
    feed("BUS_EVT={\"op\":\"name_begin\",\"id\":78,\"seq\":2,\"g\":1,\"name\":\"x\",\"room\":\"\",\"campus\":\"\"}");
    CHECK(strstr(last_res, "\"err\":4"));
    printf("stale seq refused after reboot\n");

    /* 10. Re-sending the same set does not rewrite the Flash (no extra wear); a corrupted record is not used. */
    {
        int i = page_of(yp_ng_stored_page()); uint16_t klen = yp_ng_stored_bytes(); uint8_t keep[4096]; memcpy(keep, fl[i], 4096);
        fl[i][klen - 1] ^= 0xFF;                               /* corrupt the stored pool */
        reboot();
        CHECK(yp_ng_active_count() == 0);                     /* not shown; UI will ask CAT1 for the glyphs */
        memcpy(fl[i], keep, 4096);
        reboot();
        CHECK(yp_ng_active_count() == nlines - 2);
        printf("corrupted record ignored, good record restored\n");
    }

    /* 10b. A set whose record is over 4000 B (was 1000 B with NVDS) is refused (err 3, YP_NG_FULL) and changes nothing. */
    {
        uint16_t before = yp_ng_stored_bytes();
        /* With the 4 KB pool the 18th 200-byte glyph is refused at once (err 3); the rest of that set is then out of
         * transaction (err 4). CAT1 refuses such a file before forwarding (MAX_STORE), so GR never sees it in practice. */
        bool full = false;
        res_count = 0;
        for (unsigned i = 0; i < nbig; ++i) { feed(big[i]); full = full || (strstr(last_res, "\"id\":7") && strstr(last_res, "\"err\":3")); }
        CHECK(full);
        CHECK(yp_ng_active_count() == nlines - 2 && strcmp(yp_business_status()->name, argv[2]) == 0);
        CHECK(yp_ng_stored_bytes() == before && stored_pages() == 1);
        printf("oversize set (%u lines) refused, shown and stored set unchanged\n", nbig);
    }

    /* 11. Flash A/B: a new push goes to the other page, is read back, then the old page is erased (one record left). */
    {
        static char l0[1024]; char *p = strstr(lines[0], "\"seq\":"); CHECK(p);
        unsigned long seq0 = strtoul(p + 6, NULL, 10);
#define PUSH(k) do { snprintf(l0, sizeof(l0), "%.*s\"seq\":%lu%s", (int)(p - lines[0]), lines[0], seq0 + (k), strchr(p + 6, ',')); \
                     feed(l0); for (unsigned q = 1; q < nlines; ++q) feed(lines[q]); } while (0)
        /* 11a. Pages alternate, exactly one record after every push, nothing outside the two pages touched. */
        int first = page_of(yp_ng_stored_page());
        PUSH(1);
        CHECK(strstr(last_res, "\"ok\":true") && stored_pages() == 1 && page_of(yp_ng_stored_page()) == (first ^ 1) && page_blank(first));
        PUSH(2);
        CHECK(strstr(last_res, "\"ok\":true") && stored_pages() == 1 && page_of(yp_ng_stored_page()) == first && yp_ng_last_nvds_err() == 0);
        CHECK(fl_foreign == 0);
        printf("each push writes the other page and erases the old one (one record left)\n");
        /* 11b. Power lost half way through writing the new page: the old record is still there after the reset. */
        int at = page_of(yp_ng_stored_page());
        fl_cut = 300; PUSH(3);
        CHECK(strstr(last_res, "\"err\":6") && yp_ng_last_nvds_err() == 3 && page_has_record(at));
        reboot();
        CHECK(yp_ng_active_count() == nlines - 2 && page_of(yp_ng_stored_page()) == at);
        printf("power lost while writing -> previous record kept and restored\n");
        /* 11c. Erase or write fails: err 6, set still shown from RAM, previous record kept. */
        fl_erase_fail = 1; PUSH(4);
        CHECK(strstr(last_res, "\"err\":6") && yp_ng_last_nvds_err() == 1 && yp_ng_active_count() == nlines - 2 && page_has_record(at));
        fl_write_fail = 1; PUSH(5);
        CHECK(strstr(last_res, "\"err\":6") && yp_ng_last_nvds_err() == 2);
        reboot();
        CHECK(yp_ng_active_count() == nlines - 2 && strcmp(yp_business_status()->name, argv[2]) == 0);
        PUSH(6);
        CHECK(strstr(last_res, "\"ok\":true") && stored_pages() == 1);
        printf("erase / write failure -> err 6, RAM copy shown, previous record kept\n");
        /* 11d. Reset between the new write and the old erase: both pages valid, the higher generation wins, the other is erased. */
        int cur = page_of(yp_ng_stored_page());
        memcpy(fl[cur ^ 1], fl[cur], 4096);
        fl[cur ^ 1][8] = (uint8_t)(fl[cur ^ 1][8] - 1);          /* older generation (header bytes 8..11, LE) */
        CHECK(stored_pages() == 2);
        reboot();
        CHECK(yp_ng_active_count() == nlines - 2 && stored_pages() == 1 && page_of(yp_ng_stored_page()) == cur);
        printf("both pages valid -> newer generation kept, other erased\n");
        /* 11e. A board from 1.5.8-1.5.10 has the record in NVDS (YNG1, 16 B header): shown, moved to Flash, NVDS tag removed. */
        uint16_t n = yp_ng_stored_bytes(); uint8_t legacy[4096];
        memcpy(legacy, "YNG1", 4); memcpy(legacy + 4, fl[cur] + 4, 4);                /* magic, seq */
        memcpy(legacy + 8, fl[cur] + 12, 8);                                          /* used, crc, count, rsv */
        memcpy(legacy + 16, fl[cur] + 20, (size_t)n - 20U);                           /* entries + pool (CRC unchanged) */
        memset(fl, 0xFF, sizeof(fl));
        CHECK(nvds_put(0x4003, (uint16_t)(n - 4U), legacy) == 0);
        reboot();
        CHECK(yp_ng_active_count() == nlines - 2 && stored_pages() == 1 && nv_find(0x4003) < 0 && nv_find(0x4004) < 0);
        reboot();
        CHECK(yp_ng_active_count() == nlines - 2);
        printf("legacy NVDS record -> moved to a Flash page, NVDS tag removed\n");
#undef PUSH
    }

    /* 12. Platform clear: text + glyphs gone from RAM and NVDS, and stay gone after a reboot. */
    res_count = 0;
    feed("BUS_EVT={\"op\":\"name_clear\",\"id\":90}");
    CHECK(strstr(last_res, "\"id\":90") && strstr(last_res, "\"ok\":true"));
    CHECK(!yp_business_status()->resident_known && yp_ng_active_count() == 0);
    CHECK(stored_pages() == 0 && page_blank(0) && page_blank(1) && nvds_tag_length(0x4002) == 0);
    reboot();
    CHECK(!yp_business_status()->resident_known && yp_ng_active_count() == 0);
    printf("clear: RAM, both Flash pages and NVDS emptied, still empty after reboot\n");

    /* 13. After a clear any Seq is accepted again; an English (ASCII) name commits with 0 glyphs. */
    feed("BUS_EVT={\"op\":\"name_begin\",\"id\":91,\"seq\":1,\"g\":0,\"name\":\"Anna Smith\",\"room\":\"1#1-102\",\"campus\":\"\"}");
    feed("BUS_EVT={\"op\":\"name_end\",\"id\":91,\"g\":0}");
    CHECK(strstr(last_res, "\"id\":91") && strstr(last_res, "\"ok\":true"));
    CHECK(yp_business_status()->resident_known && !strcmp(yp_business_status()->name, "Anna Smith") && yp_ng_active_count() == 0);
    reboot();
    CHECK(!strcmp(yp_business_status()->name, "Anna Smith"));
    printf("English name with 0 glyphs committed and kept across reboot\n");

    /* 13b. Bench 11-03: on power-on a battery sample (TEST_DATA test name) can run before yp_business_init();
     * it must not overwrite the stored pushed name. */
    feed_all();                                            /* push the generated set (Seq above the English one) */
    CHECK(strstr(last_res, "\"ok\":true"));
    yp_business_test_cold_boot(); yp_ng_test_wipe_ram();
    yp_business_battery(true, 80, false);                  /* early sample: no name in RAM yet */
    yp_business_init();
    yp_business_battery(true, 80, false);
    CHECK(yp_business_status()->resident_known && strcmp(yp_business_status()->name, argv[2]) == 0);
    CHECK(yp_ng_active_count() == nlines - 2);
    printf("early battery sample before init keeps the pushed name\n");

    /* 14. Factory reset entry clears the same way. */
    yp_business_factory_reset_name();
    CHECK(!yp_business_status()->resident_known && nvds_tag_length(0x4002) == 0 && page_blank(0) && page_blank(1));
    CHECK(fl_foreign == 0);
    printf("factory reset clears the name and both Flash pages; no Flash outside the two pages touched\n");
    printf("ALL PASS\n");
    return 0;
}
