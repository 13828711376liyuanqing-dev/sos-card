#ifndef YP001_OTA_FLASH_H
#define YP001_OTA_FLASH_H
#include "yp001_ota_boot.h"
#include "yp001_ota_layout.h"
/* SAM | 2026-10-21 +08:00 | SDK104 bl_fw_info_t is 904 bytes; image.size denotes executable payload excluding this trailer. */
#define YP_BOOT_SIGNATURE_TRAILER_BYTES YP_OTA_SIGNATURE_BYTES
/* SAM | 2026-10-20 20:21 +08:00 | Explicit approved inventory and SDK104 HAL adapter; no default production layout or verifier. Offsets relative to 0x00200000. */
typedef struct {uint32_t start,size;} yp_flash_range;
typedef struct {
 yp_boot_layout layout;
 yp_flash_range blocked[13];
 uint32_t blocked_count;
 int ready;
 int (*verify)(void*,uint32_t,const yp_boot_image*);
 void *verify_ctx;
 /* SAM | 2026-10-21 +08:00 | Mandatory trusted watchdog service; nonzero latches backend closed until reinit. */
 int (*service)(void*);
 void *service_ctx;
} yp_boot_flash;
/* Caller supplies complete immutable user inventory and Boot extent; approved=0 rejects.
 * No writes during init. Not authorization to install, not a replacement for safety gates.
 * Context and inventory must not be mutated while callbacks run. No concurrent users. */
int yp_boot_flash_init(yp_boot_flash*,const yp_boot_layout*,uint32_t,uint32_t,const yp_flash_range*,uint32_t,int,int (*)(void*,uint32_t,const yp_boot_image*),void*,int (*)(void*),void*);
yp_boot_backend yp_boot_flash_backend(yp_boot_flash*);
#endif
