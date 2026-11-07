/* SAM | 2026-10-20 20:18 +08:00 | Retain all transaction entry points for honest isolated size measurement; never execute Flash callbacks. DO NOT FLASH. */
#include "yp001_ota_boot.h"
static int (* volatile p_open)(yp_boot*,const yp_boot_layout*,const yp_boot_backend*,void*,uint32_t)=yp_boot_open;
static int (* volatile p_prepare)(yp_boot*,const yp_boot_image*,const yp_boot_image*)=yp_boot_prepare;
static int (* volatile p_activate)(yp_boot*)=yp_boot_activate;
static int (* volatile p_resume)(yp_boot*)=yp_boot_resume;
static int (* volatile p_trial)(yp_boot*,uint32_t)=yp_boot_trial;
static int (* volatile p_confirm)(yp_boot*)=yp_boot_confirm;
void boot_core_size_probe(void) {
    (void)p_open; (void)p_prepare; (void)p_activate;
    (void)p_resume; (void)p_trial; (void)p_confirm;
}

/* SAM | 2026-10-20 20:24 +08:00 | Retain HAL adapter for size only, never initialize or invoke it. */
#include "yp001_ota_flash.h"
static yp_boot_backend (* volatile p_flash_backend)(yp_boot_flash*)=yp_boot_flash_backend;
static int (* volatile p_flash_init)(yp_boot_flash*,const yp_boot_layout*,uint32_t,uint32_t,const yp_flash_range*,uint32_t,int,int (*)(void*,uint32_t,const yp_boot_image*),void*,int (*)(void*),void*)=yp_boot_flash_init;
void flash_backend_size_probe(void){(void)p_flash_backend;(void)p_flash_init;}

/* SAM | 2026-10-20 +08:00 | Retain startup selector for measurement only; never select or jump in reference target. */
#include "yp001_ota_start.h"
static int (* volatile p_select_start)(yp_boot*,uint32_t,yp_boot_image*)=yp_boot_select_start;
void start_selector_size_probe(void){(void)p_select_start;}

/* SAM | 2026-10-20 +08:00 | Keep real signature implementation after removing vendor startup reachability; never invoke sample key verification. */
#include <stdbool.h>
#include "sign_verify.h"
/* SAM | 2026-10-23 +08:00 | Replace obsolete unchecked vendor wrapper retention with checked project SDK bindings. */
#include "yp001_ota_project_sdk.h"
static int (* volatile p_sdk_signature)(yp_project_verify*,const uint8_t*,const uint8_t*,const uint8_t*)=yp_boot_project_sdk_init;
/* SAM | 2026-10-23 +08:00 | Retain project field verifier in capacity accounting; no callbacks executed. */
extern int yp_boot_project_verify(void*,uint32_t,const yp_boot_image*);
static int (* volatile p_project_verify)(void*,uint32_t,const yp_boot_image*)=yp_boot_project_verify;
/* SAM | 2026-10-23 +08:00 | Include actual guarded entry in size measurement; never invoke it in the NO_FLASH target. */
#include "yp001_ota_entry.h"
static int (* volatile p_project_entry)(const yp_boot_provision*)=yp_boot_project_entry;
void signature_size_probe(void){(void)p_project_entry;(void)p_sdk_signature;(void)p_project_verify;}

/* SAM | 2026-10-21 +08:00 | Retain checked selector for measurement; no device execution. */
static int (* volatile p_select_checked)(yp_boot*,uint32_t,const yp_boot_exec_policy*,yp_boot_image*)=yp_boot_select_checked;
/* SAM | 2026-10-21 +08:00 | Retain handoff code for capacity validation without invoking callbacks or jumping. */
static int (* volatile p_start)(yp_boot*,uint32_t,const yp_boot_exec_policy*,const yp_boot_handoff*)=yp_boot_start;
/* SAM | 2026-10-21 +08:00 | Keep SDK adapter linked for capacity only; do not obtain or invoke hardware callbacks. */
#include "yp001_ota_sdk_handoff.h"
static yp_boot_handoff (* volatile p_sdk_handoff)(void)=yp_boot_minimal_sdk_handoff;
/* SAM | 2026-10-23 +08:00 | Include authenticated first-baseline path in the isolated capacity measurement; never execute it. */
extern int yp_boot_start_baseline(yp_boot*,const yp_boot_image*,int,const yp_boot_exec_policy*,const yp_boot_handoff*);
static int (* volatile p_baseline)(yp_boot*,const yp_boot_image*,int,const yp_boot_exec_policy*,const yp_boot_handoff*)=yp_boot_start_baseline;
void checked_selector_size_probe(void){(void)p_select_checked;(void)p_start;(void)p_sdk_handoff;(void)p_baseline;}
