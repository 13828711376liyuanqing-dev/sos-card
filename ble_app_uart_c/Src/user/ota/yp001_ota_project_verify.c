/* SAM | 2026-10-23 +08:00 | Authenticate YP001 fields and complete native span;
 * reject short reads before using any trailer bytes. No SDK/ROM header claim. */
#include "yp001_ota_project_verify.h"
#include <string.h>
#include "yp001_ota_layout.h"
static uint32_t u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
int yp_boot_project_verify(void*context,uint32_t address,const yp_boot_image*i){
 yp_project_verify*p=context;
 uint32_t aligned[226];uint8_t*tail=(uint8_t*)aligned;uint8_t hash[32];uint32_t build;
 if(!p||!i||!p->read||!p->hash_flash||!p->hash_ram||!p->pss||
    (address!=YP_OTA_A&&address!=YP_OTA_B)||i->size<8u||i->size>YP_OTA_SLOT_BYTES-YP_OTA_SIGNATURE_BYTES)return -1;
 if(p->read(p->ctx,address+i->size,tail,904u))return -1;
 build=u32(tail+24);
 if(memcmp(tail,"YPGR",4)||u32(tail+4)!=i->size||u32(tail+8)!=1||
    u32(tail+12)!=0x00202000u||u32(tail+16)!=5526u||u32(tail+20)!=i->version||
    i->version>999999999u||!build||build>65535u||u32(tail+28)!=1||
    memcmp(tail+32,p->layout_hash,32)||memcmp(tail+64,i->identity,32)||
    memcmp(tail+96,p->data_hash,32))return -1;
 /* A trusted full key-block digest also binds RR/c. Reject obvious incompatible
  * RSA profiles before the hardware accelerator ever consumes them. */
 if(!(tail[128]&1u)||!(tail[383]&128u)||u32(tail+384)!=65537u||
    u32(tail+128)*u32(tail+644)!=0xffffffffu)return -1;
 if(p->hash_ram(p->ctx,tail+128,520u,hash)||memcmp(hash,p->public_hash,32))return -1;
 if(p->hash_flash(p->ctx,address,i->size+648u,hash)||p->pss(p->ctx,tail+128,tail+648,hash))return -1;
 if(p->hash_flash(p->ctx,address,i->size,hash)||memcmp(hash,i->identity,32))return -1;
 return 0;
}
