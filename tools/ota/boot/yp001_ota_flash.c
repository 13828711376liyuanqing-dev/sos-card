/* SAM | 2026-10-20 20:21 +08:00 | Fail-closed SDK104 Flash adapter because vendor copy ignores errors and lacks user-region protection. Isolated only; DO NOT FLASH. */
#include "yp001_ota_flash.h"
#include "hal_flash.h"
#include "gr_soc.h"
#include <string.h>
#define BASE 0x00200000u
#define CAPACITY 0x00100000u
#define SECTOR 4096u
static int inside(uint32_t a,uint32_t n,uint32_t s,uint32_t len){return n&&a>=s&&a-s<len&&n<=len-(a-s);}
static int intersects(uint32_t a,uint32_t n,uint32_t b,uint32_t m){return a<b+m&&b<a+n;}
static int permit(yp_boot_flash*f,uint32_t a,uint32_t n){
 uint32_t i;yp_boot_layout*l;
 if(!f||!f->ready||!inside(a,n,0,CAPACITY))return 0;
 l=&f->layout;
 for(i=0;i<f->blocked_count;i++)if(intersects(a,n,f->blocked[i].start,f->blocked[i].size))return 0;
 return inside(a,n,l->a,l->slot_size)||inside(a,n,l->b,l->slot_size)||inside(a,n,l->scratch,SECTOR)||inside(a,n,l->journal[0],SECTOR)||inside(a,n,l->journal[1],SECTOR);
}
/* SAM | 2026-10-21 +08:00 | Service only validated operations; never keep feeding after a service failure. HAL calls themselves must have bounded duration. */
static int service(yp_boot_flash*f){
 if(!f->ready||!f->service||f->service(f->service_ctx)){f->ready=0;return -1;}
 return 0;
}
static int flash_read(void*c,uint32_t a,void*p,uint32_t n){
 yp_boot_flash*f=c;if(!p||!permit(f,a,n))return -1;
 if(service(f)||hal_flash_read(BASE+a,p,n)!=n)return -1;
 return service(f);
}
static int check(yp_boot_flash*f,uint32_t a,const uint8_t*p,uint32_t n,int erased){
 uint8_t got[64];uint32_t k,i;
 while(n){k=n>sizeof got?sizeof got:n;if(service(f)||hal_flash_read(BASE+a,got,k)!=k||service(f))return -1;
 if(erased){for(i=0;i<k;i++)if(got[i]!=255)return -1;}
 else if(memcmp(p,got,k))return -1;
 a+=k;n-=k;if(!erased)p+=k;
 }(void)f;return 0;
}
static int flash_write(void*c,uint32_t a,const void*p,uint32_t n){
 yp_boot_flash*f=c;if(!p||!permit(f,a,n))return -1;
 if(service(f)||hal_flash_write(BASE+a,p,n)!=n||service(f))return -1;
 return check(f,a,p,n,0);
}
static int flash_erase(void*c,uint32_t a,uint32_t n){
 yp_boot_flash*f=c;if(n!=SECTOR||a%SECTOR||!permit(f,a,n))return -1;
 if(service(f)||!hal_flash_erase(BASE+a,n)||service(f))return -1;
 return check(f,a,0,n,1);
}
static int flash_verify(void*c,uint32_t a,const yp_boot_image*i){
 yp_boot_flash*f=c;
 if(!i||!permit(f,a,i->size)||(a!=f->layout.a&&a!=f->layout.b)||i->size>f->layout.slot_size||!f->verify)return -1;
 /* SAM | 2026-10-21 +08:00 | Validate full signed extent before SDK can read its trailer; subtraction prevents overflow. */
 if(f->layout.slot_size-i->size<YP_BOOT_SIGNATURE_TRAILER_BYTES||
    !permit(f,a,i->size+YP_BOOT_SIGNATURE_TRAILER_BYTES))return -1;
 /* Verifier receives physical address; must authenticate full identity/layout/data compatibility. */
 if(service(f)||f->verify(f->verify_ctx,BASE+a,i))return -1;
 return service(f);
}
yp_boot_backend yp_boot_flash_backend(yp_boot_flash*f){
 yp_boot_backend b;b.ctx=f;b.read=flash_read;b.write=flash_write;b.erase=flash_erase;b.verify_image=flash_verify;return b;
}
int yp_boot_flash_init(yp_boot_flash*f,const yp_boot_layout*l,uint32_t boot,uint32_t boot_size,const yp_flash_range*extra,uint32_t count,int approved,int (*verify)(void*,uint32_t,const yp_boot_image*),void*ctx,int (*svc)(void*),void*svc_ctx){
 uint32_t id,size,i,j,p[5],n[5];yp_flash_range mandatory[5];
 if(!f)return -1;
 memset(f,0,sizeof *f);
 if(!l||!approved||!verify||!svc||count>8||(count&&!extra)||l->capacity!=CAPACITY||l->sector!=SECTOR||!l->slot_size||l->slot_size%SECTOR)return -1;
 if(!inside(boot,boot_size,0,CAPACITY)||boot%SECTOR||boot_size%SECTOR||!inside(l->user,l->user_size,0,CAPACITY)||l->user%SECTOR||l->user_size%SECTOR)return -1;
 hal_flash_get_info(&id,&size);if(!id||size!=CAPACITY||hal_flash_sector_size()!=SECTOR)return -1;
 /* SAM | 2026-10-20 +08:00 | Reject a moved/uninitialized NVDS before enabling IO; fixed protection must match live geometry. */
 if(nvds_get_start_addr()!=BASE+0xfe000u)return -1;
 mandatory[0].start=0;mandatory[0].size=0x2000;
 mandatory[1].start=boot;mandatory[1].size=boot_size;
 mandatory[2].start=0xfe000;mandatory[2].size=0x2000;
 mandatory[3].start=l->user;mandatory[3].size=l->user_size;
 /* SAM | 2026-10-23 +08:00 | Unknown legacy bytes are unconditionally protected, even if caller supplies an obsolete slot. */
 mandatory[4].start=YP_OTA_PRESERVE_START-BASE;mandatory[4].size=YP_OTA_PRESERVE_BYTES;
 memcpy(f->blocked,mandatory,sizeof mandatory);f->blocked_count=5;
 for(i=0;i<count;i++){
 if(!inside(extra[i].start,extra[i].size,0,CAPACITY))return -1;
 f->blocked[f->blocked_count++]=extra[i];
 }
 p[0]=l->a;p[1]=l->b;p[2]=l->scratch;p[3]=l->journal[0];p[4]=l->journal[1];
 n[0]=n[1]=l->slot_size;n[2]=n[3]=n[4]=SECTOR;
 for(i=0;i<5;i++){
 if(p[i]%SECTOR||!inside(p[i],n[i],0,CAPACITY))return -1;
 for(j=0;j<i;j++)if(intersects(p[i],n[i],p[j],n[j]))return -1;
 for(j=0;j<f->blocked_count;j++)if(intersects(p[i],n[i],f->blocked[j].start,f->blocked[j].size))return -1;
 }
 f->layout=*l;f->verify=verify;f->verify_ctx=ctx;f->service=svc;f->service_ctx=svc_ctx;f->ready=1;return 0;
}
