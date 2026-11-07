/* SAM | 2026-10-21 +08:00 | Test SDK adapter ordering and reset fallback without executing device instructions. */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include "yp001_ota_sdk_handoff.h"
static unsigned step;static int fail_refresh;
static jmp_buf reset_return;
int bootloader_wdt_service(void *ctx){(void)ctx;assert(step==0||step==2);++step;return fail_refresh?-1:0;}
void app_periph_deinit(void){assert(step==1);++step;}
void sys_firmware_jump(uint32_t a,uint32_t n){assert(step==3);assert(a==0x202000&&n==64);++step;}
void hal_nvic_system_reset(void){assert(step==4||step==3);++step;longjmp(reset_return,1);}
int main(void){
 yp_boot_handoff h=yp_boot_minimal_sdk_handoff();
 assert(step==0&&h.ctx==0&&h.quiesce&&h.jump);
 assert(h.quiesce(h.ctx)==0&&step==2);
 if(!setjmp(reset_return)){h.jump(h.ctx,0x202000,64);assert(!"jump returned without reset");}
 assert(step==5);
 step=0;fail_refresh=1;assert(h.quiesce(h.ctx)<0&&step==1);
 step=2;if(!setjmp(reset_return)){h.jump(h.ctx,0x202000,64);assert(!"failed refresh returned");}assert(step==4);
 puts("PASS SDK handoff refresh/deinit/refresh/jump/reset order");return 0;
}
