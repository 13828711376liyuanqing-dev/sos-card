#ifndef YP001_OTA_BOOT_H
#define YP001_OTA_BOOT_H
#include <stdint.h>
/* SAM | 2026-10-12 19:28 +08:00 | Injected, fail-closed Boot core because live layout is not provisioned.
 * Offsets are backend-relative. All callbacks return 0 only on completed durable success.
 * verify_image MUST authenticate signed identity, board/layout, data compatibility and full digest;
 * a transport CRC is NOT signature verification. Caller must validate its protected-region inventory.
 * This core is not an independently bootable target; no production backend is supplied. */
typedef struct  {
    uint32_t size,version,identity[8];
}
yp_boot_image;
typedef struct  {
    uint32_t capacity,sector,a,b,slot_size,scratch,journal[2],user,user_size;
}
yp_boot_layout;
typedef struct  {
    void *ctx;
    int (*read)(void*,uint32_t,void*,uint32_t);
    int (*write)(void*,uint32_t,const void*,uint32_t);
    int (*erase)(void*,uint32_t,uint32_t);
    int (*verify_image)(void*,uint32_t,const yp_boot_image*);
}
yp_boot_backend;
enum  {
    YP_BOOT_EMPTY,YP_BOOT_PREPARED,YP_BOOT_INSTALL,YP_BOOT_TRIAL,YP_BOOT_ROLLBACK,YP_BOOT_CONFIRMED,YP_BOOT_REVERTED
}
;
typedef struct  {
    yp_boot_layout layout;
    yp_boot_backend io;
    unsigned char *work;
    uint32_t state,index,stage,attempts,generation;
    int active,ready;
    yp_boot_image old_image,new_image;
}
yp_boot;
/* On any error reopen from durable journal before retry. No writes occur in open. */
int yp_boot_open(yp_boot*,const yp_boot_layout*,const yp_boot_backend*,void*,uint32_t);
int yp_boot_prepare(yp_boot*,const yp_boot_image*,const yp_boot_image*);
/* Caller must grant fresh one-shot safety-window authorization before invoking activate. */
int yp_boot_activate(yp_boot*);
int yp_boot_resume(yp_boot*);
/* Call once before each trial jump. Once limit exhausted this persists rollback; do not jump
 * until resume returns success and state is TRIAL/CONFIRMED/REVERTED as appropriate. */
int yp_boot_trial(yp_boot*,uint32_t);
/* Caller must establish actual version, business health and latest user-data preservation. */
int yp_boot_confirm(yp_boot*);
#endif

