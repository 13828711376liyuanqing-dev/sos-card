/* SAM | 2026-11-06 +08:00 | Caller-locked bounded copies keep SDK/IRQ log producers away from QP and BLE sends. */
#ifndef YP001_FACTORY_STREAM_H
#define YP001_FACTORY_STREAM_H
#include <stdint.h>
#include <stddef.h>
#define FT_STREAM_CAPACITY 4096U
typedef struct { uint8_t data[FT_STREAM_CAPACITY]; uint16_t read,write; uint32_t dropped; } ft_stream_t;
static inline void ft_stream_reset(ft_stream_t *s) { s->read=s->write=0;s->dropped=0; }
static inline unsigned ft_stream_push(ft_stream_t *s,const uint8_t *data,unsigned size) {
    unsigned copied=0;
    if (!data) return 0;
    while (copied<size && copied<256U) {
        uint16_t next=(uint16_t)((s->write+1U)%FT_STREAM_CAPACITY);
        if (next==s->read) break;
        s->data[s->write]=data[copied++];s->write=next;
    }
    uint32_t lost=(uint32_t)(size-copied);
    s->dropped=UINT32_MAX-s->dropped<lost?UINT32_MAX:s->dropped+lost;
    return copied;
}
static inline unsigned ft_stream_pop(ft_stream_t *s,uint8_t *out,unsigned limit) {
    unsigned n=0;
    while (n<limit && s->read!=s->write) { out[n++]=s->data[s->read];s->read=(uint16_t)((s->read+1U)%FT_STREAM_CAPACITY); }
    return n;
}
#endif
