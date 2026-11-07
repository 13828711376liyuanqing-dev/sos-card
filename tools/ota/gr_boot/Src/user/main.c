/* SAM | 2026-10-23 +08:00 | Production Boot root invokes authenticated baseline/recovery; no vendor copy task or capacity probes. */
#include "gr_includes.h"
#include "user_periph_setup.h"
#include "yp001_ota_entry.h"
extern const yp_boot_provision yp001_boot_provision;
extern int bootloader_wdt_service(void *);
int main(void)
{
    app_periph_init();
    if(!bootloader_wdt_service(0))
        (void)yp_boot_project_entry(&yp001_boot_provision);
    /* Returning means no authenticated handoff. Reset, never fall back to an unchecked jump. */
    hal_nvic_system_reset();
    for(;;){}
}
