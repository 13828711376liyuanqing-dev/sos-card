/* SAM | 2026-10-23 +08:00 | Entry gating and dispatch integration with explicit mocked hardware/core boundaries. */
#include "yp001_ota_entry.h"
#include "yp001_ota_project_sdk.h"
#include "yp001_ota_sdk_handoff.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static int calls,fail_sdk,fail_flash,fail_open,state,baseline_calls,start_calls;
int bootloader_wdt_service(void*c){(void)c;return 0;}
int yp_boot_project_sdk_init(yp_project_verify*p,const uint8_t*l,const uint8_t*d,const uint8_t*k){(void)p;(void)l;(void)d;(void)k;calls++;return fail_sdk;}
int yp_boot_project_verify(void*c,uint32_t a,const yp_boot_image*i){(void)c;(void)a;(void)i;return 0;}
/* SAM | 2026-10-27 +08:00 | Entry dispatch regression never authorizes maintenance repair; the actual repair/core path is tested independently. */
int yp_boot_prepare(yp_boot*b,const yp_boot_image*o,const yp_boot_image*n){(void)b;(void)o;(void)n;assert(0);return -1;}
int yp_boot_flash_init(yp_boot_flash*f,const yp_boot_layout*l,uint32_t b,uint32_t n,const yp_flash_range*r,uint32_t count,int approved,int(*v)(void*,uint32_t,const yp_boot_image*),void*c,int(*s)(void*),void*sc){
 (void)f;(void)r;(void)count;(void)v;(void)c;(void)s;(void)sc;calls++;
 assert(approved==1&&b==0xec000&&n==0xa000&&l->a==0x2000&&l->b==0x80000&&l->slot_size==0x6c000&&l->scratch==0xf6000&&l->journal[0]==0xf7000&&l->journal[1]==0xf8000&&l->user==0xfe000&&l->user_size==0x2000);
 return fail_flash;
}
yp_boot_backend yp_boot_flash_backend(yp_boot_flash*f){yp_boot_backend b;(void)f;memset(&b,0,sizeof b);return b;}
int yp_boot_open(yp_boot*b,const yp_boot_layout*l,const yp_boot_backend*i,void*w,uint32_t n){(void)l;(void)i;(void)w;assert(n==4096);calls++;b->state=state;return fail_open;}
yp_boot_handoff yp_boot_minimal_sdk_handoff(void){yp_boot_handoff h;memset(&h,0,sizeof h);return h;}
int yp_boot_start_baseline(yp_boot*b,const yp_boot_image*i,int approved,const yp_boot_exec_policy*p,const yp_boot_handoff*h){(void)b;(void)i;(void)h;baseline_calls++;assert(approved==1&&p->ram_low==0x20006000&&p->ram_high==0x20040000);return -12;}
int yp_boot_start(yp_boot*b,uint32_t limit,const yp_boot_exec_policy*p,const yp_boot_handoff*h){(void)b;(void)p;(void)h;assert(limit==3);start_calls++;return -13;}
int main(void){
 yp_boot_provision p;memset(&p,0,sizeof p);
 assert(yp_boot_project_entry(&p));assert(!calls);
 p.layout_approved=1;assert(yp_boot_project_entry(&p));assert(!calls);
 p.inventory_complete=1;p.baseline_approved=1;memset(p.layout_hash,1,32);memset(p.data_hash,2,32);memset(p.public_hash,3,32);
 fail_sdk=1;assert(yp_boot_project_entry(&p));assert(calls==1);fail_sdk=0;
 fail_flash=1;assert(yp_boot_project_entry(&p));assert(!baseline_calls&&!start_calls);fail_flash=0;
 fail_open=1;assert(yp_boot_project_entry(&p));assert(!baseline_calls&&!start_calls);fail_open=0;
 state=YP_BOOT_EMPTY;assert(yp_boot_project_entry(&p)==-12);assert(baseline_calls==1&&!start_calls);
 p.baseline_approved=0;assert(yp_boot_project_entry(&p));assert(baseline_calls==1&&!start_calls);
 state=YP_BOOT_INSTALL;assert(yp_boot_project_entry(&p)==-13);assert(start_calls==1);
 puts("PASS entry refuses unapproved/incomplete inventory, propagates init/read failure, separates first boot and durable recovery");return 0;
}
