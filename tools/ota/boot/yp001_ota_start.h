#ifndef YP001_OTA_START_H
#define YP001_OTA_START_H
#include "yp001_ota_boot.h"
/* SAM | 2026-10-20 +08:00 | Select only an authenticated, recovered A-slot image. No activation, SCA write, direct jump, or health confirmation here.
 * Caller opens the durable journal first and calls once per startup, not in a polling loop.
 * Empty journals require a separately authenticated provisioning/migration path; they never imply a factory image is trusted.
 * Output must not alias the Boot context. Failure clears output; caller must not jump. */
int yp_boot_select_start(yp_boot*,uint32_t,yp_boot_image*);
/* SAM | 2026-10-21 +08:00 | Trusted application RAM policy, not supplied by package/UART. Bounds refer to the current main application's linked RAM. */
typedef struct {uint32_t ram_low,ram_high;} yp_boot_exec_policy;
/* Select/authenticate first, then read MSP and Thumb reset vector from recovered A.
 * No deinit or jump. Caller must not mutate image/Flash between success and execution. */
int yp_boot_select_checked(yp_boot*,uint32_t,const yp_boot_exec_policy*,yp_boot_image*);
/* SAM | 2026-10-21 +08:00 | Trusted board callbacks isolate handoff sequencing from SDK/board implementation.
 * quiesce must stop all image writers/DMA and prepare peripheral, interrupt and
 * watchdog handoff without changing authenticated Flash. Zero means ready.
 * jump receives physical A address and executable payload size (no trailer),
 * for a board adapter to sys_firmware_jump. It must not return on success.
 * Call once after journal open. Any return requires the caller's controlled
 * recovery/reset path; never resume application services after quiesce or retry
 * in a loop. No board implementation or production activation is supplied here. */
typedef struct {
 void *ctx;
 int (*quiesce)(void *ctx);
 void (*jump)(void *ctx,uint32_t run_address,uint32_t payload_size);
} yp_boot_handoff;
enum {
 YP_BOOT_START_INVALID=-1,
 YP_BOOT_START_REJECTED=-2,
 YP_BOOT_START_QUIESCE_FAILED=-3,
 YP_BOOT_START_JUMP_RETURNED=-4
};
int yp_boot_start(yp_boot*,uint32_t,const yp_boot_exec_policy*,const yp_boot_handoff*);
/* SAM | 2026-10-23 +08:00 | First deployment only: baseline identity and approval must come from trusted provisioning, never the candidate/UART.
 * Requires EMPTY opened journal, both entire journal sectors erased, authenticated
 * A image and checked vectors. Writes no Flash/state and never adopts a transaction.
 * Existing transactions must use yp_boot_start. No production provisioning supplied. */
int yp_boot_start_baseline(yp_boot*,const yp_boot_image*,int,const yp_boot_exec_policy*,const yp_boot_handoff*);
#endif
