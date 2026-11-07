/* SAM | 2026-10-20 20:19 +08:00 | Exercise actual HAL backend boundaries and failed durability before any board integration. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
/* SAM | 2026-10-23 +08:00 | Fail automated tests without a Windows modal assertion dialog. */
#undef assert
#define assert(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
#include <string.h>
#include <stdbool.h>
#include "yp001_ota_flash.h"
#include "yp001_ota_start.h"
static unsigned char mem[0x100000];
static unsigned calls;static int mode;static uint32_t bytes=sizeof mem,nvds=0x2fe000;
static uint32_t verify_a=0x210000,verify_b=0x220000;
uint32_t nvds_get_start_addr(void){return nvds;}
void hal_flash_get_info(uint32_t *id,uint32_t *size){*id=0x856014;*size=bytes;}
uint32_t hal_flash_sector_size(void){return 4096;}
uint32_t hal_flash_read(uint32_t a,uint8_t*p,uint32_t n){calls++;if(mode==1)return 0;memcpy(p,mem+a-0x200000,n);return n;}
uint32_t hal_flash_write(uint32_t a,const uint8_t*p,uint32_t n){uint32_t k;calls++;if(mode==2)return n-1;for(k=0;k<n;k++)mem[a-0x200000+k]&=p[k];if(mode==3)mem[a-0x200000]^=1;return n;}
bool hal_flash_erase(uint32_t a,uint32_t n){calls++;if(mode==4)return false;memset(mem+a-0x200000,mode==5?0:255,n);return true;}
static int verify(void*c,uint32_t a,const yp_boot_image*i){(void)c;assert(a==verify_a||a==verify_b);assert(i->size==64);return mode==6||(mode==7&&i->version==2)?-1:0;}
/* SAM | 2026-10-21 +08:00 | Observe handoff ordering and inject a returning jump without executing device code. */
static unsigned handoff_steps;static int quiesce_fail;
static int quiesce(void*c){assert(c==&handoff_steps);assert(handoff_steps==0);handoff_steps=1;return quiesce_fail?-1:0;}
static void jump(void*c,uint32_t address,uint32_t size){assert(c==&handoff_steps);assert(handoff_steps==1);assert(address==0x202000&&size==64);handoff_steps=2;}
static unsigned services,fail_service;
static int service(void*c){(void)c;return ++services==fail_service?-1:0;}
int main(void){
 yp_boot_flash f;yp_boot_backend io;uint8_t data[64]={1},got[64];yp_boot_image img={64,2,{0}};
 yp_boot b;uint8_t work[4096];yp_boot_image old={64,1,{0}},selected;
 yp_boot_layout l={0x100000,4096,0x10000,0x20000,0x10000,0x30000,{0x31000,0x32000},0xfe000,0x2000};
 yp_flash_range deny={0x40000,0x1000};unsigned before;
 memset(&f,0,sizeof f);io=yp_boot_flash_backend(&f);assert(io.erase(io.ctx,0x10000,4096)<0&&calls==0);
 assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,0,verify,0,service,0)<0);
 assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)==0);
 io=yp_boot_flash_backend(&f);assert(calls==0);
 assert(io.erase(io.ctx,l.a,4096)==0);assert(io.write(io.ctx,l.a,data,sizeof data)==0);assert(io.read(io.ctx,l.a,got,sizeof got)==0&&!memcmp(got,data,sizeof got));
 before=calls;
 assert(io.erase(io.ctx,0,4096)<0);assert(io.erase(io.ctx,0xfe000,4096)<0);assert(io.write(io.ctx,0x40000,data,64)<0);
 assert(io.erase(io.ctx,l.a+1,4096)<0);assert(io.erase(io.ctx,l.a,8192)<0);assert(io.write(io.ctx,l.a+l.slot_size-32,data,64)<0);
 assert(io.read(io.ctx,0xfffffff0,got,64)<0);assert(io.write(io.ctx,l.a,0,64)<0);assert(io.write(io.ctx,l.a,data,0)<0);assert(calls==before);
 for(mode=1;mode<=3;mode++)assert(io.write(io.ctx,l.a,data,64)<0);
 for(mode=4;mode<=5;mode++)assert(io.erase(io.ctx,l.a,4096)<0);
 mode=6;assert(io.verify_image(io.ctx,l.a,&img)<0);mode=0;
 /* SAM | 2026-10-21 +08:00 | SDK verifier reads a 904-byte trailer after payload; reject before callback can cross slot. */
 img.size=l.slot_size-903;assert(io.verify_image(io.ctx,l.a,&img)<0);img.size=64;
 assert(io.verify_image(io.ctx,l.a,&img)==0);assert(io.verify_image(io.ctx,l.scratch,&img)<0);
 l.b=l.a;assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)<0);before=calls;assert(io.erase(io.ctx,0x10000,4096)<0&&calls==before);l.b=0x20000;
 l.a=0;assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)<0);l.a=0x10000;
 deny.start=l.a;assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)<0);deny.start=0x40000;
 bytes=0x200000;assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)<0);bytes=sizeof mem;
 /* SAM | 2026-10-20 +08:00 | Reject stale NVDS geometry without any Flash writes. */
 nvds=0x2fd000;before=calls;assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)<0);assert(calls==before);
 nvds=0;assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)<0);nvds=0x2fe000;
 /* SAM | 2026-10-23 +08:00 | An obsolete caller layout cannot authorize erase of the preserved tail. */
 { yp_boot_layout obsolete=l; obsolete.a=0x2000;obsolete.b=0x77000;obsolete.slot_size=0x75000;
   before=calls;assert(yp_boot_flash_init(&f,&obsolete,0xec000,0xa000,&deny,1,1,verify,0,service,0)<0);
   assert(io.erase(io.ctx,0x77000,4096)<0&&calls==before);
 }
 /* Real core over actual adapter: install, trial limit, reverse swap; preserve latest user data. */
 memset(mem,255,sizeof mem);memset(mem+l.a,0x11,l.slot_size);memset(mem+l.b,0x22,l.slot_size);mem[0xfe000]=0x55;
 assert(yp_boot_flash_init(&f,&l,0x4000,0x9000,&deny,1,1,verify,0,service,0)==0);io=yp_boot_flash_backend(&f);
 assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0);
 before=calls;assert(yp_boot_select_start(&b,1,&selected)<0&&selected.size==0);assert(calls==before);
 assert(yp_boot_prepare(&b,&old,&img)==0);
 mode=7;assert(yp_boot_select_start(&b,1,&selected)==0&&selected.version==1);mode=0;
 assert(yp_boot_select_start(&b,1,&selected)==0&&selected.version==1&&b.state==YP_BOOT_PREPARED);
 assert(yp_boot_activate(&b)==0);assert(yp_boot_select_start(&b,1,&selected)==0&&selected.version==2);
 assert(b.state==YP_BOOT_TRIAL&&mem[l.a]==0x22&&mem[l.b]==0x11);
 mem[0xfe000]=0x33;
 assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0);
 assert(yp_boot_select_start(&b,1,&selected)==0&&selected.version==1);
 assert(b.state==YP_BOOT_REVERTED&&mem[l.a]==0x11&&mem[l.b]==0x22&&mem[0xfe000]==0x33);
 assert(mem[0]==255&&mem[0x4000]==255&&mem[deny.start]==255);
 mode=6;assert(yp_boot_select_start(&b,1,&selected)<0&&selected.size==0);mode=0;
 assert(yp_boot_prepare(&b,&old,&img)==0);assert(yp_boot_activate(&b)==0);
 assert(yp_boot_select_start(&b,2,&selected)==0&&selected.version==2);assert(yp_boot_confirm(&b)==0);
 assert(yp_boot_select_start(&b,2,&selected)==0&&selected.version==2);
 assert(yp_boot_select_start(&b,0,&selected)<0&&selected.size==0);
 b.state=999;assert(yp_boot_select_start(&b,2,&selected)<0&&selected.size==0);
 /* SAM | 2026-10-21 +08:00 | Selected 432KiB candidate slots preserve current A entry and isolate high Boot. Test addresses are not deployment approval. */
 l.a=0x2000;l.b=0x80000;l.slot_size=0x6c000;l.scratch=0xf6000;l.journal[0]=0xf7000;l.journal[1]=0xf8000;
 deny.start=0xf9000;deny.size=0x2000;verify_a=0x202000;verify_b=0x280000;
 memset(mem,255,sizeof mem);memset(mem+l.a,0x11,l.slot_size);memset(mem+l.b,0x22,l.slot_size);mem[0xfe000]=0x55;
 assert(yp_boot_flash_init(&f,&l,0xec000,0x9000,&deny,1,1,verify,0,service,0)==0);io=yp_boot_flash_backend(&f);
 /* SAM | 2026-10-23 +08:00 | Every preserved sector rejects writes and erase before calling HAL. */
 before=calls;
 { unsigned addr; for(addr=0x6e000;addr<0x80000;addr+=4096){
   assert(io.erase(io.ctx,addr,4096)<0);assert(io.write(io.ctx,addr,data,64)<0);
 } assert(calls==before); }
 before=calls;assert(io.erase(io.ctx,0xec000,4096)<0);assert(io.erase(io.ctx,0xf9000,4096)<0);assert(io.erase(io.ctx,0xfa000,4096)<0);assert(calls==before);
 assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0);assert(yp_boot_prepare(&b,&old,&img)==0);assert(yp_boot_activate(&b)==0);
 assert(yp_boot_select_start(&b,1,&selected)==0&&selected.version==2);mem[0xfe000]=0x33;
 assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0);assert(yp_boot_select_start(&b,1,&selected)==0&&selected.version==1);
 assert(mem[l.a]==0x11&&mem[l.a+l.slot_size-1]==0x11&&mem[l.b]==0x22&&mem[l.b+l.slot_size-1]==0x22);
 assert(mem[0xfe000]==0x33&&mem[0xec000]==255&&mem[0xf4fff]==255&&mem[0xf9000]==255&&mem[0xfa000]==255);
 /* SAM | 2026-10-21 +08:00 | Authenticated identity alone must not permit a bad reset vector or out-of-policy stack. */
 {
  yp_boot_exec_policy policy={0x20006000,0x20040000};uint32_t v[2]={0x20040000,0x202021};
  memcpy(mem+l.a,v,sizeof v);
  assert(yp_boot_select_checked(&b,2,&policy,&selected)==0&&selected.version==1);
  v[0]=0x20040008;memcpy(mem+l.a,v,sizeof v);assert(yp_boot_select_checked(&b,2,&policy,&selected)<0&&selected.size==0);
  v[0]=0x20006000;memcpy(mem+l.a,v,sizeof v);assert(yp_boot_select_checked(&b,2,&policy,&selected)<0);
  v[0]=0x20040000;v[1]=0x277021;memcpy(mem+l.a,v,sizeof v);assert(yp_boot_select_checked(&b,2,&policy,&selected)<0);
  v[1]=0x202020;memcpy(mem+l.a,v,sizeof v);assert(yp_boot_select_checked(&b,2,&policy,&selected)<0);
  v[1]=0x202041;memcpy(mem+l.a,v,sizeof v);assert(yp_boot_select_checked(&b,2,&policy,&selected)<0);
  v[1]=0x202021;memcpy(mem+l.a,v,sizeof v);mode=1;assert(yp_boot_select_checked(&b,2,&policy,&selected)<0);mode=0;
  assert(yp_boot_select_checked(&b,2,0,&selected)<0&&selected.size==0);
  {
   yp_boot_handoff ops={&handoff_steps,quiesce,jump};
   before=calls;assert(yp_boot_start(&b,2,&policy,0)==YP_BOOT_START_INVALID);assert(calls==before);
   ops.jump=0;assert(yp_boot_start(&b,2,&policy,&ops)==YP_BOOT_START_INVALID);assert(calls==before);ops.jump=jump;
   ops.quiesce=0;assert(yp_boot_start(&b,2,&policy,&ops)==YP_BOOT_START_INVALID);assert(calls==before);ops.quiesce=quiesce;
   mode=6;assert(yp_boot_start(&b,2,&policy,&ops)==YP_BOOT_START_REJECTED&&handoff_steps==0);mode=0;
   v[1]=0x277021;memcpy(mem+l.a,v,sizeof v);
   assert(yp_boot_start(&b,2,&policy,&ops)==YP_BOOT_START_REJECTED&&handoff_steps==0);
   v[1]=0x202021;memcpy(mem+l.a,v,sizeof v);
   quiesce_fail=1;assert(yp_boot_start(&b,2,&policy,&ops)==YP_BOOT_START_QUIESCE_FAILED&&handoff_steps==1);
   quiesce_fail=0;handoff_steps=0;
   assert(yp_boot_start(&b,2,&policy,&ops)==YP_BOOT_START_JUMP_RETURNED&&handoff_steps==2);
  }
 }
 /* SAM | 2026-10-23 +08:00 | Initial signed baseline may boot without modifying any Flash; never bypass a transaction or dirty journal tail. */
 {
  static unsigned char snapshot[sizeof mem];
  yp_boot_exec_policy policy={0x20006000,0x20040000};
  yp_boot_handoff ops={&handoff_steps,quiesce,jump};
  uint32_t v[2]={0x20040000,0x202021};
  memset(mem+l.journal[0],255,l.sector);memset(mem+l.journal[1],255,l.sector);
  memcpy(mem+l.a,v,sizeof v);assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0);
  memcpy(snapshot,mem,sizeof mem);handoff_steps=0;
  assert(yp_boot_start_baseline(&b,&old,0,&policy,&ops)==YP_BOOT_START_REJECTED&&handoff_steps==0);
  mode=6;assert(yp_boot_start_baseline(&b,&old,1,&policy,&ops)==YP_BOOT_START_REJECTED&&handoff_steps==0);mode=0;
  mem[l.journal[1]+l.sector-1]=0;
  assert(yp_boot_start_baseline(&b,&old,1,&policy,&ops)==YP_BOOT_START_REJECTED&&handoff_steps==0);
  mem[l.journal[1]+l.sector-1]=255;
  b.state=YP_BOOT_PREPARED;assert(yp_boot_start_baseline(&b,&old,1,&policy,&ops)==YP_BOOT_START_REJECTED);b.state=YP_BOOT_EMPTY;
  v[1]=0x277021;memcpy(mem+l.a,v,sizeof v);
  assert(yp_boot_start_baseline(&b,&old,1,&policy,&ops)==YP_BOOT_START_REJECTED&&handoff_steps==0);
  v[1]=0x202021;memcpy(mem+l.a,v,sizeof v);
  assert(yp_boot_start_baseline(&b,&old,1,&policy,&ops)==YP_BOOT_START_JUMP_RETURNED&&handoff_steps==2);
  assert(!memcmp(snapshot,mem,sizeof mem)&&b.state==YP_BOOT_EMPTY&&b.active==-1&&b.generation==0);
 }
 /* SAM | 2026-10-21 +08:00 | Service failure must latch off IO, including after an erase has already changed Flash. */
 assert(yp_boot_flash_init(&f,&l,0xec000,0x9000,&deny,1,1,verify,0,0,0)<0);
 assert(yp_boot_flash_init(&f,&l,0xec000,0x9000,&deny,1,1,verify,0,service,0)==0);
 before=services;assert(io.erase(io.ctx,0xfe000,4096)<0&&services==before);
 fail_service=services+1;before=calls;assert(io.erase(io.ctx,l.a,4096)<0&&calls==before);
 fail_service=0;assert(io.read(io.ctx,l.a,got,64)<0&&calls==before);
 assert(yp_boot_flash_init(&f,&l,0xec000,0x9000,&deny,1,1,verify,0,service,0)==0);
 mem[l.a]=0;fail_service=services+2;assert(io.erase(io.ctx,l.a,4096)<0&&mem[l.a]==255);
 fail_service=0;before=calls;assert(io.write(io.ctx,l.a,data,64)<0&&calls==before);
 /* Reopen persistent INSTALL after service failure; latest user bytes survive. */
 memset(mem,255,sizeof mem);memset(mem+l.a,0x11,l.slot_size);memset(mem+l.b,0x22,l.slot_size);mem[0xfe000]=0x39;
 assert(yp_boot_flash_init(&f,&l,0xec000,0x9000,&deny,1,1,verify,0,service,0)==0);
 assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0);
 assert(yp_boot_prepare(&b,&old,&img)==0&&yp_boot_activate(&b)==0);
 fail_service=services+4;assert(yp_boot_resume(&b)<0);assert(!f.ready);
 fail_service=0;
 assert(yp_boot_flash_init(&f,&l,0xec000,0x9000,&deny,1,1,verify,0,service,0)==0);
 assert(yp_boot_open(&b,&l,&io,work,sizeof work)==0&&yp_boot_resume(&b)==0);
 assert(b.state==YP_BOOT_TRIAL&&mem[l.a]==0x22&&mem[l.b]==0x11&&mem[0xfe000]==0x39);
 puts("PASS HAL whitelist, geometry, protection, short IO, corrupt write/erase and verifier failure");return 0;
}
