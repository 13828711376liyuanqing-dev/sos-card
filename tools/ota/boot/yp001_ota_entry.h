#ifndef YP001_OTA_ENTRY_H
#define YP001_OTA_ENTRY_H
#include "yp001_ota_flash.h"
/* SAM | 2026-10-23 +08:00 | Provisioning is immutable build/deployment input,
 * never accepted from UART, MQTT or an image's self-declared metadata. */
typedef struct {
 int layout_approved,inventory_complete,baseline_approved;
 uint8_t layout_hash[32],data_hash[32],public_hash[32];
 yp_boot_image baseline;
 const yp_flash_range *additional_user_regions;
 uint32_t additional_user_region_count;
} yp_boot_provision;
/* Caller initializes SDK platform/watchdog before entry. Return always means
 * no successful handoff; fail closed/reset without erasing or loading defaults. */
int yp_boot_project_entry(const yp_boot_provision*);
#endif
