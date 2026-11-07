#ifndef YP001_OTA_PROJECT_SDK_H
#define YP001_OTA_PROJECT_SDK_H
#include "yp001_ota_project_verify.h"
/* SAM | 2026-10-23 +08:00 | SDK104 non-encrypted hardware bindings. This does not
 * approve a layout or install; callers must supply fixed, audited trust pins. */
int yp_boot_project_sdk_init(yp_project_verify*,const uint8_t*,const uint8_t*,const uint8_t*);
#endif
