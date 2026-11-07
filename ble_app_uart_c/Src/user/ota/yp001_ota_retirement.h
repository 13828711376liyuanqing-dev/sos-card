/* SAM | 2026-10-26 +08:00 | Exact pre-install retirement scopes preserve dirty B bytes; zero durable progress does not imply an erased slot. */
#ifndef YP001_OTA_RETIREMENT_H
#define YP001_OTA_RETIREMENT_H
#include "yp001_ota.h"
#include <string.h>
static inline uint32_t yp001_ota_retirement_size(const yp001_ota_record *r)
{
    if(!r||strcmp(r->target,"GR5526")||strcmp(r->source_version,"1.0.2")||strcmp(r->version,"1.5.0"))return 0;
    if(r->epoch==2&&!strcmp(r->job,"2bdfc1ca8e696f2f77218982fa61b80939f6e95852aa3336bf64264feaeace8d")&&
       !strcmp(r->hash,"96bc08c57633b4a820fa2ed0b2df57860eefefa85596aff338b407454c1a5139"))return 429256u;
    if(r->epoch==3&&!strcmp(r->job,"5fbfa8fba57e15654dab0c62023f245c681227dd3ef481078fa681bf894edc5f")&&
       !strcmp(r->hash,"eaf020f7a88d368d3017cd2c093535beb20b35f6001a71a505cf54662ad659f4"))return 432328u;
    return 0;
}
#endif
