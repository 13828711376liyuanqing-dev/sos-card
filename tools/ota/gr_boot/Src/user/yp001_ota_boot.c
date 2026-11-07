#include "yp001_ota_boot.h"
#include <string.h>
/* SAM | 2026-10-12 19:28 +08:00 | Durable sector swap because interrupted erase/write must retain a recoverable source. */
#define WORDS 31u
#define RECORD (WORDS*4u)
#define MAGIC 0x59504231u
static uint32_t crc(const void *v,uint32_t n) {
    const unsigned char *p=v;
    uint32_t c=~0u,i;
    while(n--) {
        c^=*p++;
        for(i=0;i<8;i++)c=(c>>1)^((0u-(c&1u))&0xedb88320u);
    }
    return ~c;
}
static int inside(uint32_t a,uint32_t n,uint32_t start,uint32_t len) {
    return a>=start&&a-start<=len&&n<=len-(a-start);
}
static int overlap(uint32_t a,uint32_t n,uint32_t b,uint32_t m) {
    return a<b+m&&b<a+n;
}
static int valid_layout(const yp_boot_layout *l) {
    uint32_t p[6],n[6],i,j;
    if(!l||!l->sector||l->sector<RECORD||!l->slot_size||l->slot_size%l->sector||!l->user_size)return 0;
    p[0]=l->a;
    p[1]=l->b;
    p[2]=l->scratch;
    p[3]=l->journal[0];
    p[4]=l->journal[1];
    p[5]=l->user;
    n[0]=n[1]=l->slot_size;
    n[2]=n[3]=n[4]=l->sector;
    n[5]=l->user_size;
    for(i=0;i<6;i++) {
        if(p[i]%l->sector||n[i]%l->sector||!inside(p[i],n[i],0,l->capacity))return 0;
        for(j=0;j<i;j++)if(overlap(p[i],n[i],p[j],n[j]))return 0;
    }
    return 1;
}
static int allowed(yp_boot*b,uint32_t a,uint32_t n) {
    yp_boot_layout*l=&b->layout;
    return inside(a,n,l->a,l->slot_size)||inside(a,n,l->b,l->slot_size)||inside(a,n,l->scratch,l->sector)||inside(a,n,l->journal[0],l->sector)||inside(a,n,l->journal[1],l->sector);
}
static int write_at(yp_boot*b,uint32_t a,const void*p,uint32_t n) {
    if(!b->ready||!allowed(b,a,n))return -1;
    return b->io.write(b->io.ctx,a,p,n);
}
static int erase_at(yp_boot*b,uint32_t a) {
    if(!b->ready||a%b->layout.sector||!allowed(b,a,b->layout.sector))return -1;
    return b->io.erase(b->io.ctx,a,b->layout.sector);
}
static uint32_t layout_crc(yp_boot*b) {
    return crc(&b->layout,sizeof b->layout);
}
static void encode(yp_boot*b,uint32_t*r) {
    memset(r,0,RECORD);
    r[0]=MAGIC;
    r[1]=b->generation;
    r[2]=layout_crc(b);
    r[3]=b->state;
    r[4]=b->index;
    r[5]=b->stage;
    r[6]=b->attempts;
    memcpy(r+7,&b->old_image,sizeof b->old_image);
    memcpy(r+17,&b->new_image,sizeof b->new_image);
    r[27]=1;
    r[28]=0;
    r[29]=crc(r,29*4);
    r[30]=0;
}
static int record_valid(yp_boot*b,uint32_t*r) {
    return r[0]==MAGIC&&r[2]==layout_crc(b)&&r[3]>=YP_BOOT_PREPARED&&r[3]<=YP_BOOT_REVERTED&&r[4]<=b->layout.slot_size/b->layout.sector&&r[5]<=2&&r[7]&&r[7]<=b->layout.slot_size&&r[17]&&r[17]<=b->layout.slot_size&&r[27]==1&&r[28]==0&&r[29]==crc(r,29*4)&&r[30]==0;
}
/* Keep previous generation until payload readback and final commit word are durable. */
static int save(yp_boot*b) {
    uint32_t r[WORDS],check[WORDS],a;
    int target;
    if(!b->ready||b->generation==0xffffffffu)return -1;
    target=b->active==0?1:0;
    a=b->layout.journal[target];
    b->generation++;
    encode(b,r);
    if(erase_at(b,a)||write_at(b,a,r,RECORD-4)||b->io.read(b->io.ctx,a,check,RECORD-4)||memcmp(r,check,RECORD-4)||write_at(b,a+RECORD-4,r+30,4)||b->io.read(b->io.ctx,a,check,RECORD)||memcmp(r,check,RECORD)) {
        b->ready=0;
        return -1;
    }
    b->active=target;
    return 0;
}
int yp_boot_open(yp_boot*b,const yp_boot_layout*l,const yp_boot_backend*io,void*w,uint32_t n) {
    uint32_t r[2][WORDS],i,j;
    int v[2],blank[2]= {
        1,1
    }
    ,sel;
    if(!b)return -1;
    memset(b,0,sizeof *b);
    if(!valid_layout(l)||!io||!io->read||!io->write||!io->erase||!io->verify_image||!w||n<l->sector)return -1;
    b->layout=*l;
    b->io=*io;
    b->work=w;
    b->active=-1;
    for(i=0;i<2;i++) {
        if(io->read(io->ctx,l->journal[i],r[i],RECORD))return -1;
        v[i]=record_valid(b,r[i]);
        for(j=0;j<WORDS;j++)if(r[i][j]!=0xffffffffu)blank[i]=0;
    }
    if(!v[0]&&!v[1]) {
        if(!blank[0]||!blank[1])return -1;
        b->ready=1;
        return 0;
    }
    if(v[0]&&v[1]&&r[0][1]==r[1][1])return -1;
    sel=!v[0]?1:!v[1]?0:r[1][1]>r[0][1]?1:0;
    b->active=sel;
    b->generation=r[sel][1];
    b->state=r[sel][3];
    b->index=r[sel][4];
    b->stage=r[sel][5];
    b->attempts=r[sel][6];
    memcpy(&b->old_image,r[sel]+7,sizeof b->old_image);
    memcpy(&b->new_image,r[sel]+17,sizeof b->new_image);
    b->ready=1;
    return 0;
}
static int auth(yp_boot*b,uint32_t a,const yp_boot_image*i) {
    return !i->size||i->size>b->layout.slot_size?-1:b->io.verify_image(b->io.ctx,a,i);
}
int yp_boot_prepare(yp_boot*b,const yp_boot_image*old,const yp_boot_image*next) {
    if(!b||!b->ready||!old||!next||(b->state!=YP_BOOT_EMPTY&&b->state!=YP_BOOT_CONFIRMED&&b->state!=YP_BOOT_REVERTED)||next->version<=old->version||auth(b,b->layout.a,old)||auth(b,b->layout.b,next))return -1;
    b->old_image=*old;
    b->new_image=*next;
    b->state=YP_BOOT_PREPARED;
    b->index=b->stage=b->attempts=0;
    return save(b);
}
int yp_boot_activate(yp_boot*b) {
    if(!b||!b->ready||b->state!=YP_BOOT_PREPARED||auth(b,b->layout.a,&b->old_image)||auth(b,b->layout.b,&b->new_image))return -1;
    b->state=YP_BOOT_INSTALL;
    return save(b);
}
static int copy_sector(yp_boot*b,uint32_t from,uint32_t to) {
    unsigned char check[64];
    uint32_t i,n=b->layout.sector,k;
    if(b->io.read(b->io.ctx,from,b->work,n)||erase_at(b,to)||write_at(b,to,b->work,n))return -1;
    for(i=0;i<n;i+=k) {
        k=n-i;
        if(k>sizeof check)k=sizeof check;
        if(b->io.read(b->io.ctx,to+i,check,k)||memcmp(check,b->work+i,k))return -1;
    }
    return 0;
}
/* Journal stages describe the NEXT operation. Repeating any stage cannot destroy its source.
 * Swap the entire slot, not candidate length: a smaller candidate must preserve the whole old image.
 * A damaged rejected candidate in B must not prevent booting authenticated restored A. */
int yp_boot_resume(yp_boot*b) {
    uint32_t a,c;
    if(!b||!b->ready)return -1;
    if(b->state!=YP_BOOT_INSTALL&&b->state!=YP_BOOT_ROLLBACK)return 0;
    while(b->index<b->layout.slot_size/b->layout.sector) {
        a=b->layout.a+b->index*b->layout.sector;
        c=b->layout.b+b->index*b->layout.sector;
        if(b->stage==0) {
            if(copy_sector(b,a,b->layout.scratch))goto fail;
            b->stage=1;
        }
        else if(b->stage==1) {
            if(copy_sector(b,c,a))goto fail;
            b->stage=2;
        }
        else {
            if(copy_sector(b,b->layout.scratch,c))goto fail;
            b->index++;
            b->stage=0;
        }
        if(save(b))return -1;
    }
    if(auth(b,b->layout.a,b->state==YP_BOOT_INSTALL?&b->new_image:&b->old_image)||(b->state==YP_BOOT_INSTALL&&auth(b,b->layout.b,&b->old_image)))goto fail;
    b->state=b->state==YP_BOOT_INSTALL?YP_BOOT_TRIAL:YP_BOOT_REVERTED;
    b->attempts=0;
    return save(b);
    fail:b->ready=0;
    return -1;
}
int yp_boot_trial(yp_boot*b,uint32_t limit) {
    if(!b||!b->ready||b->state!=YP_BOOT_TRIAL||!limit)return -1;
    if(b->attempts>=limit||auth(b,b->layout.a,&b->new_image)) {
        if(auth(b,b->layout.b,&b->old_image))return -1;
        b->state=YP_BOOT_ROLLBACK;
        b->index=b->stage=0;
    }
    else b->attempts++;
    return save(b);
}
int yp_boot_confirm(yp_boot*b) {
    if(!b||!b->ready||b->state!=YP_BOOT_TRIAL||auth(b,b->layout.a,&b->new_image))return -1;
    b->state=YP_BOOT_CONFIRMED;
    return save(b);
}

