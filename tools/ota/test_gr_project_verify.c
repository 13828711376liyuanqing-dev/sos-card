/* SAM | 2026-10-23 +08:00 | Fault-inject native project verification; crypto callbacks are mocks, not hardware acceptance. */
#include "yp001_ota_project_verify.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char flash[1024],payload_hash[32],span_hash[32];
static int bad_read,bad_hash,bad_pss,reads,hashes,pss_calls;
static void word(unsigned off,uint32_t v){memcpy(flash+off,&v,4);}
static int read_flash(void*c,uint32_t a,void*p,uint32_t n){(void)c;reads++;if(bad_read||a<0x202000u||a-0x202000u+n>sizeof flash)return -1;memcpy(p,flash+a-0x202000u,n);return 0;}
static int hash_flash(void*c,uint32_t a,uint32_t n,unsigned char*out){(void)c;hashes++;assert(a==0x202000u);if(bad_hash)return -1;assert(n==120||n==768);memcpy(out,n==120?payload_hash:span_hash,32);return 0;}
static int hash_ram(void*c,const void*p,uint32_t n,unsigned char*out){(void)c;(void)p;assert(n==520);memset(out,3,32);return bad_hash?-1:0;}
static int pss(void*c,const unsigned char*k,const unsigned char*s,const unsigned char*h){(void)c;(void)k;(void)s;pss_calls++;assert(!memcmp(h,span_hash,32));return bad_pss?-1:0;}
static void reset(yp_project_verify*p,yp_boot_image*i){
 memset(flash,0,sizeof flash);memset(p,0,sizeof *p);memset(i,0,sizeof *i);
 memset(payload_hash,4,32);memset(span_hash,5,32);i->size=120;i->version=1005000;memcpy(i->identity,payload_hash,32);
 memcpy(flash+120,"YPGR",4);word(124,120);word(128,1);word(132,0x202000);word(136,5526);word(140,i->version);word(144,5);word(148,1);
 memset(flash+152,1,32);memcpy(flash+184,payload_hash,32);memset(flash+216,2,32);
 flash[248]=1;flash[503]=128;word(504,65537);word(764,0xffffffffu);
 memset(p->layout_hash,1,32);memset(p->data_hash,2,32);memset(p->public_hash,3,32);
 p->read=read_flash;p->hash_flash=hash_flash;p->hash_ram=hash_ram;p->pss=pss;
 bad_read=bad_hash=bad_pss=reads=hashes=pss_calls=0;
}
int main(void){
 yp_project_verify p;yp_boot_image i;unsigned k;
 reset(&p,&i);assert(!yp_boot_project_verify(&p,0x202000,&i));assert(reads==1&&hashes==2&&pss_calls==1);
 for(k=0;k<128;k++){
  reset(&p,&i);flash[120+k]^=1;
  /* Build is any signed 1..65535 value; tampering is caught by real PSS, not this mock. */
  if(k>=24&&k<28)continue;
  assert(yp_boot_project_verify(&p,0x202000,&i));
 }
 reset(&p,&i);bad_read=1;assert(yp_boot_project_verify(&p,0x202000,&i));assert(!hashes&&!pss_calls);
 reset(&p,&i);bad_hash=1;assert(yp_boot_project_verify(&p,0x202000,&i));assert(!pss_calls);
 reset(&p,&i);bad_pss=1;assert(yp_boot_project_verify(&p,0x202000,&i));
 reset(&p,&i);payload_hash[0]^=1;assert(yp_boot_project_verify(&p,0x202000,&i));
 reset(&p,&i);i.size=441465;assert(yp_boot_project_verify(&p,0x202000,&i));assert(!reads);
 reset(&p,&i);assert(yp_boot_project_verify(&p,0x2fe000,&i));assert(!reads);
 reset(&p,&i);assert(yp_boot_project_verify(&p,0x277000,&i));assert(!reads);
 reset(&p,&i);p.pss=0;assert(yp_boot_project_verify(&p,0x202000,&i));assert(!reads);
 reset(&p,&i);p.public_hash[0]^=1;assert(yp_boot_project_verify(&p,0x202000,&i));assert(!pss_calls);
 reset(&p,&i);word(144,0);assert(yp_boot_project_verify(&p,0x202000,&i));
 puts("PASS project header, identity, contract pins, bounds, failed reads/hash/signature; no writes");return 0;
}
