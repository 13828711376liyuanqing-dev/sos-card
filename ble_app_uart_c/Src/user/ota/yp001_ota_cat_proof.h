/* SAM | 2026-10-23 22:30 +08:00 | Distinct CAT proof authenticates package identity without writing or borrowing a GR image slot. */
#ifndef YP001_OTA_CAT_PROOF_H
#define YP001_OTA_CAT_PROOF_H
#include "yp001_ota_project_verify.h"
#include <string.h>
#define YP_CAT_PROOF_BYTES 904u
static uint32_t yp_cat_word(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static int yp_cat_proof_verify(yp_project_verify*p,const uint8_t*t,const uint8_t expected[32],uint32_t version){
 uint8_t digest[32];uint32_t size;
 if(!p||!t||!expected||!p->hash_ram||!p->pss||!version||version>999999999u)return -1;
 size=yp_cat_word(t+4);
 if(memcmp(t,"YPCT",4)||size<138u||size>974848u||yp_cat_word(t+8)!=1u||
    yp_cat_word(t+12)!=2052u||yp_cat_word(t+16)!=780u||yp_cat_word(t+20)!=version||
    yp_cat_word(t+24)!=113u||yp_cat_word(t+28)!=1u||memcmp(t+32,p->layout_hash,32)||
    memcmp(t+64,expected,32)||memcmp(t+96,p->data_hash,32))return -1;
 if(!(t[128]&1u)||!(t[383]&128u)||yp_cat_word(t+384)!=65537u||
    yp_cat_word(t+128)*yp_cat_word(t+644)!=0xffffffffu)return -1;
 if(p->hash_ram(p->ctx,t+128,520u,digest)||memcmp(digest,p->public_hash,32)||
    p->hash_ram(p->ctx,t,648u,digest)||p->pss(p->ctx,t+128,t+648,digest))return -1;
 return 0;
}
#endif
