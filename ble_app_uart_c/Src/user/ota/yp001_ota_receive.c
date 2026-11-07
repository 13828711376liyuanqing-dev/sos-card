/* SAM | 2026-10-23 +08:00 | Buffer one sector, read back Flash, then checkpoint; uncertain writes never receive durable credit. */
#include "yp001_ota_receive.h"
#include "yp001_ota_wire.h"
#include <string.h>
static int permit(yp_receive *r)
{
    return r && r->ready && !r->io.allowed(r->io.ctx,r->session,r->hash,r->total);
}
int yp_receive_open(yp_receive *r,const yp_receive_io *io,uint32_t session,
                    const uint8_t hash[32],uint32_t total,uint32_t resume)
{
    uint8_t present=0;unsigned i;
    if(!r)return -1;
    memset(r,0,sizeof(*r));
    if(!io||!hash||!session||!io->allowed||!io->read||!io->erase||!io->write||
       !io->checkpoint||!io->verify||total<8u+YP_OTA_SIGNATURE_BYTES||
       total>YP_OTA_SLOT_BYTES||resume>total||(resume!=total&&resume%4096u))return -1;
    for(i=0;i<32;i++)present|=hash[i];
    if(!present||io->allowed(io->ctx,session,hash,total))return -1;
    r->io=*io;r->session=session;r->total=total;r->accepted=r->durable=resume;
    memcpy(r->hash,hash,32);memset(r->sector,255,sizeof(r->sector));r->ready=1;
    return 0;
}
static int flush(yp_receive *r)
{
    uint8_t check[64];uint32_t i,address=YP_OTA_B+r->durable;
    /* durable is sector-aligned until the last partial sector completes. */
    if(!permit(r)||r->durable%4096u||r->durable>YP_OTA_SLOT_BYTES-4096u)goto fail;
    if(r->io.erase(r->io.ctx,address)||r->io.write(r->io.ctx,address,r->sector,4096u))goto fail;
    for(i=0;i<4096u;i+=sizeof(check)){
        if(r->io.read(r->io.ctx,address+i,check,sizeof(check))||
           memcmp(check,r->sector+i,sizeof(check)))goto fail;
    }
    if(r->io.checkpoint(r->io.ctx,r->session,r->hash,r->total,r->accepted))goto fail;
    r->durable=r->accepted;memset(r->sector,255,sizeof(r->sector));return 0;
fail:
    r->ready=0;return -1;
}
/* SAM | 2026-11-01 +08:00 | Copy the fully staged image into B one sector at a time through the unchanged flush (erase, write, readback,
 * checkpoint). A failure closes the receiver with durable at the last good sector, so a reopen resumes on the classic path. */
static int commit(yp_receive *r)
{
    uint32_t n;
    while(r->durable<r->total){
        n=r->total-r->durable;if(n>4096u)n=4096u;
        memset(r->sector,255,sizeof(r->sector));memcpy(r->sector,r->stage+r->durable,n);
        r->accepted=r->durable+n;
        if(flush(r)){r->accepted=r->total;return -1;}
    }
    return 0;
}
int yp_receive_stage(yp_receive *r,uint8_t *buf,uint32_t size)
{
    if(!r||!r->ready||!buf||r->stage||r->accepted||r->durable||size<r->total)return -1;
    r->stage=buf;return 0;
}
int yp_receive_data(yp_receive *r,uint32_t session,uint32_t offset,const uint8_t *data,uint32_t n)
{
    uint8_t check[512];uint32_t expected;
    if(!permit(r)||session!=r->session||!data||offset>=r->total||offset%512u)return -1;
    expected=r->total-offset;if(expected>512u)expected=512u;
    if(n!=expected||offset>r->accepted)return -1;
    if(r->stage){
        /* SAM | 2026-11-01 +08:00 | Staged path: no Flash access until the last byte; a replay must match the staged bytes. */
        if(offset<r->accepted)return n>r->accepted-offset||memcmp(r->stage+offset,data,n)?-1:0;
        if(r->verified)return -1;
        memcpy(r->stage+offset,data,n);r->accepted+=n;
        return r->accepted==r->total?commit(r):0;
    }
    if(offset<r->accepted){
        if(n>r->accepted-offset)return -1;
        if(offset<r->durable){
            if(n>r->durable-offset||r->io.read(r->io.ctx,YP_OTA_B+offset,check,n))return -1;
            return memcmp(check,data,n)?-1:0;
        }
        return memcmp(r->sector+offset-r->durable,data,n)?-1:0;
    }
    if(r->verified||n>4096u-(r->accepted-r->durable))return -1;
    memcpy(r->sector+r->accepted-r->durable,data,n);r->accepted+=n;
    if(r->accepted-r->durable==4096u||r->accepted==r->total)return flush(r);
    return 0;
}
int yp_receive_verify(yp_receive *r)
{
    if(!permit(r)||r->durable!=r->total||r->accepted!=r->total)return -1;
    if(r->io.verify(r->io.ctx,r->hash,r->total)){r->ready=0;return -1;}
    r->verified=1;return 0;
}
/* SAM | 2026-10-23 +08:00 | Bounded production UART endpoint; installation remains the coordinator/Boot's separate responsibility. */
static uint32_t word(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void putword(uint8_t *p,uint32_t v)
{
    unsigned i;for(i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));
}
uint32_t yp_receive_frame(yp_receive *r,const uint8_t *frame,uint32_t n,uint8_t *out,uint32_t capacity)
{
    uint8_t body[16]={0};uint8_t type,reason=0,reply=YP_RX_ACK;
    uint32_t session,sequence,offset,length;
    /* Reserve the response BEFORE any state change: no unacknowledgeable write. */
    if(!r||!out||capacity<44u||!yp001_ota_wire_valid(frame,n))return 0;
    type=frame[5];session=word(frame+8);sequence=word(frame+12);offset=word(frame+16);
    length=(uint32_t)frame[20]|((uint32_t)frame[21]<<8);
    if(type==YP_RX_HELLO && !length){
        body[0]=0;body[1]=2;body[2]=0;body[3]=16;
        putword(body+4,YP_OTA_SLOT_BYTES);
        /* No advertised activation support; local binding is reported separately. */
        putword(body+12,r->ready?1u:0u);
        return (uint32_t)yp001_ota_wire_encode(out,capacity,YP_RX_CAPS,session,sequence,offset,body,sizeof(body));
    }
    body[0]=type;
    if(!r->ready)reason=5;
    else if(session!=r->session)reason=3;
    else if(!permit(r))reason=7;
    else if(type==YP_RX_BEGIN){
        if(length!=36u || word(frame+24)!=r->total || memcmp(frame+28,r->hash,32))reason=2;
    }else if(type==YP_RX_DATA){
        if(yp_receive_data(r,session,offset,frame+24,length))reason=r->ready?2:4;
    }else if(type==YP_RX_QUERY){
        if(length)reason=2;
    }else if(type==YP_RX_VERIFY){
        if(length)reason=2;
        else if(yp_receive_verify(r))reason=r->ready?6:4;
    }else if(type==YP_RX_ABORT){
        if(length)reason=2;
        else r->ready=0;
    }else reason=6;
    if(reason)reply=YP_RX_NACK;
    body[1]=reason;
    if(session==r->session){
        body[2]=(uint8_t)((r->ready?1u:0u)|(r->verified?2u:0u));
        putword(body+4,r->accepted);putword(body+8,r->durable);putword(body+12,r->total);
    }
    return (uint32_t)yp001_ota_wire_encode(out,capacity,reply,session,sequence,offset,body,sizeof(body));
}
