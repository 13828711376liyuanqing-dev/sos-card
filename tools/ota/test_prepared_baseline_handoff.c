/* SAM | 2026-10-27 +08:00 | Preserve a prepared signed candidate while replacing a maintenance baseline; host NOR/signature oracle only. */
#define main prior_boot_suite
#define SEC 1024u
#include "test_gr_boot.c"
#undef main
#include "boot/yp001_ota_start.h"
#ifndef BEFORE_REPAIR
#include "boot/yp001_ota_prepared_repair.h"
#include "boot/yp001_ota_entry.h"
#include "boot/yp001_ota_project_sdk.h"
#include "boot/yp001_ota_sdk_handoff.h"
/* Uncalled board-entry wiring must fail if accidentally reached. The test executes the actual repair function and actual Boot core below. */
int bootloader_wdt_service(void*c){(void)c;CHECK(0);return -1;}
int yp_boot_project_sdk_init(yp_project_verify*p,const uint8_t*l,const uint8_t*d,const uint8_t*k){(void)p;(void)l;(void)d;(void)k;CHECK(0);return -1;}
int yp_boot_project_verify(void*c,uint32_t a,const yp_boot_image*i){(void)c;(void)a;(void)i;CHECK(0);return -1;}
int yp_boot_flash_init(yp_boot_flash*f,const yp_boot_layout*l,uint32_t b,uint32_t n,const yp_flash_range*r,uint32_t count,int approved,int(*v)(void*,uint32_t,const yp_boot_image*),void*c,int(*s)(void*),void*sc){
 (void)f;(void)l;(void)b;(void)n;(void)r;(void)count;(void)approved;(void)v;(void)c;(void)s;(void)sc;CHECK(0);return -1;
}
yp_boot_backend yp_boot_flash_backend(yp_boot_flash*f){yp_boot_backend b={0};(void)f;CHECK(0);return b;}
yp_boot_handoff yp_boot_minimal_sdk_handoff(void){yp_boot_handoff h={0};CHECK(0);return h;}
#endif
static yp_boot_image replacement={SEC*2,1,{3}};
static int repair_verify(void*c,uint32_t a,const yp_boot_image*i){
 (void)c;if(!i||!i->size||i->size>SEC*3)return -1;
 for(uint32_t k=0;k<i->size;k++)if(flash[a+k]!=(unsigned char)i->identity[0])return -1;
 return 0;
}
#ifndef BEFORE_REPAIR
static uint8_t owner_digest_value=0xa5;
static uint8_t candidate_digest_value=0xb6;
static int owner_hash(void*c,uint32_t a,uint32_t n,uint8_t*out){(void)c;
 if(a==0x2f9000&&n==8192){memset(out,owner_digest_value,32);return 0;}
 CHECK(a==0x200000u+layout.b&&n==newimg.size+904u);memset(out,candidate_digest_value,32);return 0;}
static yp_boot_prepared_repair_scope scope;
static yp_project_verify verifier;
static int repair(yp_boot*b){return yp_boot_repair_prepared_baseline(b,&replacement,1,&scope,&verifier);}
#endif
int main(void){
 yp_boot b;yp_boot_image selected;
 io.verify_image=repair_verify;prepared(&b);memset(flash+layout.a,3,replacement.size);
#ifndef BEFORE_REPAIR
 memset(&scope,0,sizeof scope);scope.generation=1;scope.old_image=oldimg;scope.candidate=newimg;memset(scope.owner_pages_sha256,0xa5,32);memset(scope.candidate_native_sha256,0xb6,32);memset(&verifier,0,sizeof verifier);verifier.hash_flash=owner_hash;
 CHECK(yp_boot_select_start(&b,3,&selected)!=0);
 CHECK(repair(&b)==1);
#endif
 /* The old Boot's ordinary PREPARED selection rejects the replacement before repair. */
 CHECK(yp_boot_select_start(&b,3,&selected)==0&&!memcmp(&selected,&replacement,sizeof selected));
#ifndef BEFORE_REPAIR
 CHECK(b.state==YP_BOOT_PREPARED&&b.generation==2);count=0;CHECK(repair(&b)==0&&count==0);users();
 /* SAM | 2026-10-27 +08:00 | A second scoped maintenance rebind uses generation 2 and its exact old descriptor, never broadens to arbitrary journals or activates the candidate. */
 scope.generation=2;scope.old_image=replacement;replacement.identity[0]=4;memset(flash+layout.a,4,replacement.size);
 count=0;CHECK(repair(&b)==1&&b.state==YP_BOOT_PREPARED&&b.generation==3);users();
 CHECK(yp_boot_select_start(&b,3,&selected)==0&&!memcmp(&selected,&replacement,sizeof selected));
 count=0;CHECK(repair(&b)==0&&count==0);
 scope.generation=1;scope.old_image=oldimg;replacement.identity[0]=3;

 prepared(&b);count=0;CHECK(repair(&b)==0&&count==0); /* New Boot can be deployed first while old A is still intact. */
 memset(flash+layout.a,3,replacement.size);owner_digest_value=0xa4;count=0;CHECK(repair(&b)<0&&count==0);owner_digest_value=0xa5;
 candidate_digest_value=0xb7;count=0;CHECK(repair(&b)<0&&count==0);candidate_digest_value=0xb6;
 flash[layout.b]^=1;count=0;CHECK(repair(&b)<0&&count==0);flash[layout.b]^=1;
 {yp_boot_image wrong=replacement;wrong.version=9;count=0;CHECK(yp_boot_repair_prepared_baseline(&b,&wrong,1,&scope,&verifier)<0&&count==0);}
 count=0;CHECK(yp_boot_repair_prepared_baseline(&b,&replacement,0,&scope,&verifier)<0&&count==0);
 memcpy(baseline,flash,CAP);
 for(int mode=0;mode<2;mode++)for(int point=0;point<4;point++){
  memcpy(flash,baseline,CAP);cut=-1;openok(&b);count=0;cut=point;torn=mode;(void)repair(&b);cut=-1;openok(&b);
  CHECK(b.state==YP_BOOT_PREPARED);CHECK(repair(&b)>=0);
  CHECK(yp_boot_select_start(&b,3,&selected)==0&&!memcmp(&selected,&replacement,sizeof selected));users();
  for(uint32_t k=0;k<newimg.size;k++)CHECK(flash[layout.b+k]==2);
 }
 prepared(&b);CHECK(!yp_boot_activate(&b));count=0;CHECK(repair(&b)==0&&count==0&&b.state==YP_BOOT_INSTALL);
 puts("PASS scoped PREPARED baseline handoff: old/new boot order, exact owner/image/version, no activation, idempotence and 4 cut points x 2 modes");
#endif
 return 0;
}
