#ifndef YP001_OTA_PREPARED_REPAIR_H
#define YP001_OTA_PREPARED_REPAIR_H
/* SAM | 2026-10-27 +08:00 | Immutable Boot-only maintenance scope, never populated by an OTA/UART request. */
#include "yp001_ota_boot.h"
#include "yp001_ota_project_verify.h"
typedef struct {
    uint32_t generation;
    uint8_t owner_pages_sha256[32];
    uint8_t candidate_native_sha256[32];
    yp_boot_image old_image,candidate;
} yp_boot_prepared_repair_scope;
/* 0 ordinary startup/no change, 1 new PREPARED generation durable, -1 refuse startup.
 * Never changes INSTALL/TRIAL/ROLLBACK, grants installation or writes A/B/owner/user regions. */
int yp_boot_repair_prepared_baseline(yp_boot*,const yp_boot_image*,int,
    const yp_boot_prepared_repair_scope*,yp_project_verify*);
#endif
