/* SAM | 2026-10-23 +08:00 | Application-side native image validation using SDK104 SHA/PKC and pinned public trust. */
#ifndef YP001_OTA_APP_CRYPTO_H
#define YP001_OTA_APP_CRYPTO_H
#include "yp001_ota_boot.h"
int yp001_ota_native_verify(uint32_t address,uint32_t total,const uint8_t expected_hash[32],uint32_t version,yp_boot_image *image);
/* SAM | 2026-10-23 19:26 +08:00 | Boot journal validation authenticates signed identities again; running extent comes from the linker, never the OTA request. */
int yp001_ota_image_auth(void *ctx,uint32_t address,const yp_boot_image *image);
int yp001_ota_running_image(uint32_t version,yp_boot_image *image);
/* SAM | 2026-10-23 22:30 +08:00 | Input is exactly 904 aligned bytes, checked by the bounded UART proof receiver. */
int yp001_ota_cat_proof_verify(const uint8_t *proof,const uint8_t expected_hash[32],uint32_t version);
/* SAM | 2026-10-23 +08:00 | Fresh hardware challenge; never fall back to a timestamp/counter across reset. */
int yp001_ota_random(uint8_t out[16]);
#endif
