/* SAM | 2026-10-12 19:28 +08:00 | NOR power-cut test because swap must recover. */
#include "yp001_ota_boot.h"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
#include <string.h>
#ifndef SEC
#define SEC 256u
#endif
#define CAP (SEC*12u)
static unsigned char flash[CAP], baseline[CAP], work[SEC];
static int cut=-1, count, torn;
static int rd(void *u,uint32_t a,void *p,uint32_t n) {
    (void)u;
    if(a>CAP||n>CAP-a)return -1;
    memcpy(p,flash+a,n);
    return 0;
}
static int mutation(uint32_t *n) {
    if(count++==cut) {
        *n=torn?( *n/2u):0;
        return -1;
    }
    return 0;
}
static int wr(void *u,uint32_t a,const void *p,uint32_t n) {
    uint32_t i,k=n;
    int r;
    (void)u;
    CHECK(a<=CAP&&n<=CAP-a);
    r=mutation(&k);
    for(i=0;i<k;i++) {
        CHECK((flash[a+i]&((const unsigned char*)p)[i])==((const unsigned char*)p)[i]);
        flash[a+i]&=((const unsigned char*)p)[i];
    }
    return r;
}
static int er(void *u,uint32_t a,uint32_t n) {
    uint32_t k=n;
    int r;
    (void)u;
    CHECK(a%SEC==0&&n==SEC);
    r=mutation(&k);
    memset(flash+a,255,k);
    return r;
}
/* Test signature oracle only: production must inject independent signed-image verification. */
static int verify(void *u,uint32_t a,const yp_boot_image *im) {
    uint32_t i;
    (void)u;
    if(im->size==0||im->size>SEC*3)return -1;
    for(i=0;i<im->size;i++)if(flash[a+i]!=(unsigned char)im->version)return -1;
    return im->identity[0]==im->version?0:-1;
}
static yp_boot_layout layout= {
    CAP,SEC,0,SEC*3,SEC*3,SEC*6, {
        SEC*7,SEC*8
    }
    ,SEC*9,SEC*3
}
;
static yp_boot_backend io= {
    0,rd,wr,er,verify
}
;
static yp_boot_image oldimg= {
    SEC*3,1, {
        1
    }
}
,newimg= {
    SEC+19,2, {
        2
    }
}
;
static void init(void) {
    memset(flash,255,sizeof flash);
    memset(flash,1,oldimg.size);
    memset(flash+SEC*3,2,newimg.size);
    memset(flash+SEC*9,0x5a,SEC*3);
    cut=-1;
    count=0;
}
static void openok(yp_boot *b) {
    CHECK(yp_boot_open(b,&layout,&io,work,sizeof work)==0);
}
static void users(void) {
    uint32_t i;
    for(i=SEC*9;i<CAP;i++)CHECK(flash[i]==0x5a);
}
static void prepared(yp_boot *b) {
    init();
    openok(b);
    CHECK(yp_boot_prepare(b,&oldimg,&newimg)==0);
}
int main(void) {
    yp_boot b;
    int i,j,total,r;
    prepared(&b);
    memcpy(baseline,flash,CAP);
    count=0;
    CHECK(yp_boot_resume(&b)==0);
    CHECK(count==0);
    CHECK(verify(0,0,&oldimg)==0);
    CHECK(yp_boot_activate(&b)==0);
    count=0;
    CHECK(yp_boot_resume(&b)==0);
    total=count;
    CHECK(verify(0,0,&newimg)==0);
    CHECK(verify(0,SEC*3,&oldimg)==0);
    users();
    for(j=0;j<2;j++)for(i=0;i<total+5;i++) {
        memcpy(flash,baseline,CAP);
        cut=-1;
        openok(&b);
        CHECK(yp_boot_activate(&b)==0);
        count=0;
        cut=i;
        torn=j;
        r=yp_boot_resume(&b);
        (void)r;
        cut=-1;
        openok(&b);
        CHECK(yp_boot_resume(&b)==0);
        CHECK(verify(0,0,&newimg)==0);
        CHECK(verify(0,SEC*3,&oldimg)==0);
        users();
    }
    printf("install power cuts: %d points x 2 modes PASS\n",total+5);
    CHECK(yp_boot_trial(&b,1)==0);
    memcpy(baseline,flash,CAP);
    count=0;
    CHECK(yp_boot_trial(&b,1)==0);
    CHECK(yp_boot_resume(&b)==0);
    total=count;
    CHECK(verify(0,0,&oldimg)==0);
    for(j=0;j<2;j++)for(i=0;i<total+5;i++) {
        memcpy(flash,baseline,CAP);
        cut=-1;
        openok(&b);
        count=0;
        cut=i;
        torn=j;
        r=yp_boot_trial(&b,1);
        if(r==0)r=yp_boot_resume(&b);
        cut=-1;
        openok(&b);
        if(b.state==YP_BOOT_TRIAL)CHECK(yp_boot_trial(&b,1)==0);
        CHECK(yp_boot_resume(&b)==0);
        CHECK(verify(0,0,&oldimg)==0);
        users();
    }
    printf("rollback power cuts: %d points x 2 modes PASS\n",total+5);
    prepared(&b);
    CHECK(yp_boot_activate(&b)==0);
    CHECK(yp_boot_resume(&b)==0);
    CHECK(yp_boot_confirm(&b)==0);
    openok(&b);
    CHECK(b.state==YP_BOOT_CONFIRMED);
    prepared(&b);
    CHECK(yp_boot_activate(&b)==0);
    CHECK(yp_boot_resume(&b)==0);
    flash[0]=0;
    CHECK(yp_boot_trial(&b,1)==0);
    CHECK(yp_boot_resume(&b)==0);
    CHECK(verify(0,0,&oldimg)==0);
    users();
    init();
    openok(&b);
    newimg.identity[0]=9;
    count=0;
    CHECK(yp_boot_prepare(&b,&oldimg,&newimg)!=0&&count==0);
    newimg.identity[0]=2;
    init();
    flash[SEC*7]=0;
    count=0;
    CHECK(yp_boot_open(&b,&layout,&io,work,sizeof work)!=0&&count==0);
    layout.b=SEC*2;
    count=0;
    CHECK(yp_boot_open(&b,&layout,&io,work,sizeof work)!=0&&count==0);
    layout.b=SEC*3;
    io.verify_image=0;
    CHECK(yp_boot_open(&b,&layout,&io,work,sizeof work)!=0);
    io.verify_image=verify;
    /* Every mutation point may be interrupted on ten consecutive boots. */
    prepared(&b);
    CHECK(yp_boot_activate(&b)==0);
    memcpy(baseline,flash,CAP);
    for(i=0;i<60;i++) {
        memcpy(flash,baseline,CAP);
        for(j=0;j<10;j++) {
            cut=-1;
            openok(&b);
            count=0;
            cut=i;
            torn=j%2;
            r=yp_boot_resume(&b);
            (void)r;
            users();
        }
        cut=-1;
        openok(&b);
        CHECK(yp_boot_resume(&b)==0);
        CHECK(verify(0,0,&newimg)==0);
        users();
    }
    /* A new legitimate user write after upgrade must survive rollback. */
    flash[SEC*9]=0x18;
    CHECK(yp_boot_trial(&b,1)==0);
    CHECK(yp_boot_trial(&b,1)==0);
    memcpy(baseline,flash,CAP);
    for(i=0;i<60;i++) {
        memcpy(flash,baseline,CAP);
        for(j=0;j<10;j++) {
            cut=-1;
            openok(&b);
            count=0;
            cut=i;
            torn=j%2;
            r=yp_boot_resume(&b);
            (void)r;
            CHECK(flash[SEC*9]==0x18);
        }
        cut=-1;
        openok(&b);
        CHECK(yp_boot_resume(&b)==0);
        CHECK(verify(0,0,&oldimg)==0);
        CHECK(flash[SEC*9]==0x18);
    }
    printf("repeated install/rollback cuts: 120 cases x 10 resets PASS\n");
    layout.a=0xffffff00u;
    count=0;
    CHECK(yp_boot_open(&b,&layout,&io,work,sizeof work)!=0&&count==0);
    layout.a=0;
    layout.user=SEC*8;
    CHECK(yp_boot_open(&b,&layout,&io,work,sizeof work)!=0);
    layout.user=SEC*9;
    prepared(&b);
    flash[layout.journal[b.active]+12]^=1;
    count=0;
    CHECK(yp_boot_open(&b,&layout,&io,work,sizeof work)!=0&&count==0);
    puts("bounds, missing backend, invalid signature, corrupt journal, PREPARED isolation, confirmation PASS");
    return 0;
}


