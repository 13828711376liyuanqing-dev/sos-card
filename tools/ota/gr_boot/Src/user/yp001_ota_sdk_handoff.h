#ifndef YP001_OTA_SDK_HANDOFF_H
#define YP001_OTA_SDK_HANDOFF_H
#include "yp001_ota_start.h"
/* SAM | 2026-10-21 +08:00 | SDK104 minimal Boot adapter, not an activation grant.
 * Only for the audited single-threaded no-DFU/no-log Boot after app_periph_init;
 * all synchronous Flash/crypto operations must have finished, no DMA writers.
 * Use through yp_boot_start after trusted provisioning and journal open.
 * Getter performs no hardware IO. Real interrupt/WDT continuity needs device
 * acceptance; future additional peripherals require a fresh shutdown audit. */
yp_boot_handoff yp_boot_minimal_sdk_handoff(void);
#endif
