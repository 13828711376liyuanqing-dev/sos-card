#ifndef YP001_OTA_PROJECT_VERIFY_H
#define YP001_OTA_PROJECT_VERIFY_H
#include "yp001_ota_boot.h"
/* SAM | 2026-10-23 +08:00 | Project-owned signed header contract. All pins must
 * come from immutable Boot provisioning, never from the image being verified.
 * Callbacks return zero only on complete success, must be bounded and service
 * the watchdog during long hashing/PKC operations. No writes or cached hashes.
 * read/hash_flash use physical addresses; identity is 32 raw SHA256 bytes.
 * Hardware adapters and layout approval remain separate deployment gates. */
typedef struct {
 void *ctx;
 uint8_t layout_hash[32],data_hash[32],public_hash[32];
 int (*read)(void*,uint32_t,void*,uint32_t);
 int (*hash_flash)(void*,uint32_t,uint32_t,uint8_t*);
 int (*hash_ram)(void*,const void*,uint32_t,uint8_t*);
 int (*pss)(void*,const uint8_t*,const uint8_t*,const uint8_t*);
} yp_project_verify;
int yp_boot_project_verify(void*,uint32_t,const yp_boot_image*);
#endif
