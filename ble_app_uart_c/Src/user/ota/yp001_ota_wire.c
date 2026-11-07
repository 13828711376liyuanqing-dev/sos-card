/* SAM | 2026-10-23 +08:00 | Implement the approved OTA2 envelope; CRC is not signature or write permission. */
#include "yp001_ota_wire.h"
#include <string.h>
static uint32_t get(const uint8_t *p, unsigned n)
{
    uint32_t v = 0; unsigned i;
    for (i = 0; i < n; ++i) v |= (uint32_t)p[i] << (8U*i);
    return v;
}
static void put(uint8_t *p, uint32_t v, unsigned n)
{
    unsigned i; for (i = 0; i < n; ++i) p[i] = (uint8_t)(v >> (8U*i));
}
static uint16_t crc16(const uint8_t *p, size_t n)
{
    uint16_t c = 0xffffU; unsigned i;
    while (n--) { c ^= (uint16_t)*p++ << 8; for (i=0;i<8;++i) c = (uint16_t)((c<<1)^((c&0x8000U)?0x1021U:0U)); }
    return c;
}
static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t c = 0xffffffffU; unsigned i;
    while (n--) { c ^= *p++; for (i=0;i<8;++i) c = (c>>1)^((c&1U)?0xedb88320U:0U); }
    return ~c;
}
static int header(const uint8_t *p)
{
    return !memcmp(p,"OTA2",4) && p[4]==2 && !p[6] && !p[7] &&
        get(p+20,2)<=512 && crc16(p,22)==get(p+22,2);
}
int yp001_ota_wire_valid(const uint8_t *p, size_t n)
{
    return p && n>=28 && n<=YP001_OTA_WIRE_MAX && header(p) &&
        n==28U+get(p+20,2) && crc32(p,n-4)==get(p+n-4,4);
}
size_t yp001_ota_wire_encode(uint8_t *p, size_t cap, uint8_t type,
    uint32_t session, uint32_t seq, uint32_t offset, const uint8_t *data, size_t n)
{
    if (!p || n>512 || cap<n+28 || (n && !data)) return 0;
    memcpy(p,"OTA2",4); p[4]=2; p[5]=type; p[6]=p[7]=0;
    put(p+8,session,4); put(p+12,seq,4); put(p+16,offset,4); put(p+20,(uint32_t)n,2);
    put(p+22,crc16(p,22),2);
    if (n) memcpy(p+24,data,n);
    put(p+24+n,crc32(p,24+n),4); return n+28;
}
unsigned yp001_ota_wire_feed(yp001_ota_wire_rx *r, uint8_t b, yp001_ota_wire_sink sink, void *ctx)
{
    size_t n;
    unsigned delivered=0;
    if (!r || !sink) return 0;
    if (r->used>=YP001_OTA_WIRE_MAX) r->used=r->expected=0;
    r->bytes[r->used++]=b;
    while (r->used) {
        if (memcmp(r->bytes,"OTA2",r->used<4?r->used:4)) goto discard;
        if (r->used<24) return delivered;
        if (!r->expected) {
            if (!header(r->bytes)) goto discard;
            r->expected=(uint16_t)(28U+get(r->bytes+20,2));
        }
        n=r->expected;
        if (r->used<n) return delivered;
        /* SAM | 2026-10-23 +08:00 | Header/length already checked before payload;
         * verify frame CRC here without repeating header validation in flash-limited builds. */
        if (crc32(r->bytes,n-4)!=get(r->bytes+n-4,4)) goto discard;
        sink(r->bytes,n,ctx);
        ++delivered;
        r->expected=0;
        r->used=(uint16_t)(r->used-n);
        memmove(r->bytes,r->bytes+n,r->used);
        continue;
discard:
        r->expected=0;
        --r->used; memmove(r->bytes,r->bytes+1,r->used);
    }
    return delivered;
}
/* SAM | 2026-10-23 +08:00 | Quarantine uncertain bytes after loss; embedded binary newlines are never text. */
void yp001_ota_mux_lost(yp001_ota_mux *m)
{
    m->wire.used=m->wire.expected=0; m->mode=3;
}
/* SAM | 2026-10-26 +08:00 | Recover only CRC-validated release ACKs while text remains quarantined after OE; the coordinator still checks token/nonce and pending phase. Never dispatch DATA or grants here. */
typedef struct {yp001_ota_wire_sink sink;void *context;} release_sink;
static void release_only(const uint8_t *p,size_t n,void *context)
{
    release_sink *s=context;
    if(n==44&&p[5]==243&&get(p+8,4)==1&&get(p+16,4)==0)s->sink(p,n,s->context);
}
void yp001_ota_mux_feed(yp001_ota_mux *m,uint8_t b,uint32_t now,
    yp001_ota_wire_sink text,yp001_ota_wire_sink frame,void *ctx)
{
    if ((m->mode==2 || (m->mode==0 && m->wire.used)) &&
        (uint32_t)(now-m->last_ms)>2000U) yp001_ota_mux_lost(m);
    m->last_ms=now;
    if (m->mode==3) {
        release_sink recovery={frame,ctx};
        yp001_ota_wire_feed(&m->wire,b,release_only,&recovery);
        if(b=='\n'&&!m->wire.used)m->mode=0;
        return;
    }
    if (m->mode==2) {
        if (yp001_ota_wire_feed(&m->wire,b,frame,ctx) && !m->wire.used) m->mode=0;
        return;
    }
    if (m->mode==0) {
        if (b==(uint8_t)"OTA2"[m->wire.used]) {
            m->wire.bytes[m->wire.used++]=b;
            if (m->wire.used==4) m->mode=2;
            return;
        }
        if (m->wire.used) text(m->wire.bytes,m->wire.used,ctx);
        m->wire.used=0; m->mode=1;
    }
    text(&b,1,ctx);
    if (b=='\n') m->mode=0;
}
