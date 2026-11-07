/* SAM | 2026-10-23 +08:00 | Connect approved provisioning, checked SDK verifier,
 * protected Flash, durable recovery and authenticated handoff. Candidate only. */
#include "yp001_ota_entry.h"
#include "yp001_ota_layout.h"
#include "yp001_ota_project_sdk.h"
#include "yp001_ota_sdk_handoff.h"
#include "yp001_ota_prepared_repair.h"
#include "yp001_ota_r6_repair_scope.h"
#include <string.h>
extern int bootloader_wdt_service(void*);
static int nonzero(const uint8_t*p){uint32_t i;uint8_t v=0;for(i=0;i<32;i++)v|=p[i];return v!=0;}
/* SAM | 2026-10-27 +08:00 | A maintenance A replacement invalidates an existing PREPARED old-image identity. Rebind only the pinned original journal/candidate and exact coordinator snapshot, using full native A/B authentication and the existing atomic prepare transaction. */
int yp_boot_repair_prepared_baseline(yp_boot *core,const yp_boot_image *baseline,int approved,
    const yp_boot_prepared_repair_scope *scope,yp_project_verify *verifier)
{
    yp_boot view;uint8_t owner_hash[32],candidate_hash[32];
    if(!core||!baseline||!scope||!verifier)return -1;
    if(core->state!=YP_BOOT_PREPARED||core->generation!=scope->generation||
       memcmp(&core->old_image,&scope->old_image,sizeof(core->old_image))||
       memcmp(&core->new_image,&scope->candidate,sizeof(core->new_image)))return 0;
    if(!core->ready||!core->io.verify_image||core->index||core->stage||core->attempts)return -1;
    /* Updating Boot first must leave the intact authenticated old baseline bootable. */
    if(!core->io.verify_image(core->io.ctx,core->layout.a,&core->old_image))return 0;
    if(approved!=1||!scope->generation||scope->generation==UINT32_MAX||
       baseline->version!=core->old_image.version||!verifier->hash_flash||
       verifier->hash_flash(verifier->ctx,0x002f9000u,8192u,owner_hash)||
       memcmp(owner_hash,scope->owner_pages_sha256,sizeof owner_hash))return -1;
    /* The signed payload identity alone must not substitute for the task's full native-component hash, including its 904-byte trailer. */
    if(core->layout.slot_size<904u||scope->candidate.size>core->layout.slot_size-904u||
       verifier->hash_flash(verifier->ctx,0x00200000u+core->layout.b,scope->candidate.size+904u,candidate_hash)||
       memcmp(candidate_hash,scope->candidate_native_sha256,sizeof candidate_hash))return -1;
    /* RAM-only adapter to the existing prepare primitive. No REVERTED/CONFIRMED/INSTALL record is written: prepare authenticates new A and the unchanged B, then atomically saves only PREPARED. */
    view=*core;view.state=YP_BOOT_REVERTED;
    if(yp_boot_prepare(&view,baseline,&scope->candidate)||view.state!=YP_BOOT_PREPARED||
       view.generation!=scope->generation+1u||memcmp(&view.old_image,baseline,sizeof(*baseline))||
       memcmp(&view.new_image,&scope->candidate,sizeof(scope->candidate)))return -1;
    *core=view;return 1;
}
int yp_boot_project_entry(const yp_boot_provision*p){
 /* Relative addresses match undeployed layout_candidate.json revision 40KiB.
  * Coordinator pages and unallocated space are outside all backend write ranges. */
 static const yp_boot_layout layout={0x100000u,4096u,YP_OTA_A-0x200000u,YP_OTA_B-0x200000u,YP_OTA_SLOT_BYTES,0xf6000u,{0xf7000u,0xf8000u},0xfe000u,0x2000u};
 static const yp_boot_exec_policy policy={0x20006000u,0x20040000u};
 yp_project_verify verifier;yp_boot_flash flash;yp_boot core;yp_boot_backend backend;
 yp_boot_handoff handoff;uint32_t work[1024];
 if(!p||p->layout_approved!=1||p->inventory_complete!=1||
    !nonzero(p->layout_hash)||!nonzero(p->data_hash)||!nonzero(p->public_hash))return -1;
 if(yp_boot_project_sdk_init(&verifier,p->layout_hash,p->data_hash,p->public_hash))return -1;
 if(yp_boot_flash_init(&flash,&layout,0xec000u,0xa000u,p->additional_user_regions,
    p->additional_user_region_count,1,yp_boot_project_verify,&verifier,bootloader_wdt_service,0))return -1;
 backend=yp_boot_flash_backend(&flash);
 if(yp_boot_open(&core,&layout,&backend,work,sizeof work))return -1;
 handoff=yp_boot_minimal_sdk_handoff();
 if(core.state==YP_BOOT_EMPTY){
  if(p->baseline_approved!=1)return -1;
  return yp_boot_start_baseline(&core,&p->baseline,1,&policy,&handoff);
 }
 /* SAM | 2026-10-27 +08:00 | The fixed R6 maintenance scope can repair PREPARED metadata only; actual installation still requires the application's separately authorized activation. */
 if(yp_boot_repair_prepared_baseline(&core,&p->baseline,p->baseline_approved,&r6_baseline_repair_scope,&verifier)<0)return -1;
 /* Never turn PREPARED into INSTALL here: only an already durable commit may
  * resume. Trial budget and rollback are enforced by the existing startup core. */
 return yp_boot_start(&core,3,&policy,&handoff);
}
