/* SAM | 2026-10-20 +08:00 | Recover persisted installs/rollbacks before choosing executable code; PREPARED never grants install permission. Isolated, not a production entrypoint. */
#include "yp001_ota_start.h"
#include <string.h>
int yp_boot_select_start(yp_boot*b,uint32_t limit,yp_boot_image*out){
 const yp_boot_image*image;
 if(!out)return -1;
 memset(out,0,sizeof *out);
 if(!b||!b->ready||!limit||!b->io.verify_image)return -1;
 if(b->state==YP_BOOT_INSTALL||b->state==YP_BOOT_ROLLBACK){if(yp_boot_resume(b))return -1;}
 if(b->state==YP_BOOT_TRIAL){
  if(yp_boot_trial(b,limit))return -1;
  if(b->state==YP_BOOT_ROLLBACK&&yp_boot_resume(b))return -1;
 }
 switch(b->state){
 case YP_BOOT_PREPARED:case YP_BOOT_REVERTED:image=&b->old_image;break;
 case YP_BOOT_TRIAL:case YP_BOOT_CONFIRMED:image=&b->new_image;break;
 default:return -1;
 }
 if(!image->size||image->size>b->layout.slot_size||b->io.verify_image(b->io.ctx,b->layout.a,image))return -1;
 *out=*image;return 0;
}
/* SAM | 2026-10-21 +08:00 | Reject vectors outside the authenticated payload and current application RAM before a future jump adapter. */
int yp_boot_select_checked(yp_boot*b,uint32_t limit,const yp_boot_exec_policy*p,yp_boot_image*out){
 yp_boot_image image;uint32_t vectors[2],run,entry;
 if(!out)return -1;
 memset(out,0,sizeof *out);
 if(!b||!b->ready||!b->io.read||!p||p->ram_low<0x20006000u||p->ram_high>0x20040000u||
    p->ram_low>=p->ram_high||(p->ram_low&7u)||(p->ram_high&7u)||b->layout.a!=0x2000u)return -1;
 if(yp_boot_select_start(b,limit,&image)||image.size<8u||b->io.read(b->io.ctx,b->layout.a,vectors,sizeof vectors))return -1;
 run=0x00200000u+b->layout.a;entry=vectors[1]&~1u;
 if((vectors[0]&7u)||vectors[0]<=p->ram_low||vectors[0]>p->ram_high||!(vectors[1]&1u)||
    entry<run+8u||entry-run>=image.size)return -1;
 *out=image;return 0;
}
/* SAM | 2026-10-21 +08:00 | Gate all handoff callbacks behind authenticated vector selection; returned jump is always failure. */
int yp_boot_start(yp_boot*b,uint32_t limit,const yp_boot_exec_policy*p,const yp_boot_handoff*h){
 yp_boot_image image;yp_boot_handoff handoff;uint32_t run;
 if(!h||!h->quiesce||!h->jump)return YP_BOOT_START_INVALID;
 handoff=*h;
 if(yp_boot_select_checked(b,limit,p,&image))return YP_BOOT_START_REJECTED;
 run=0x00200000u+b->layout.a;
 if(handoff.quiesce(handoff.ctx))return YP_BOOT_START_QUIESCE_FAILED;
 handoff.jump(handoff.ctx,run,image.size);
 return YP_BOOT_START_JUMP_RETURNED;
}
/* SAM | 2026-10-23 +08:00 | Authenticate a provisioned first baseline without erasing B/user data or inventing a durable confirmation. */
int yp_boot_start_baseline(yp_boot*b,const yp_boot_image*baseline,int approved,const yp_boot_exec_policy*p,const yp_boot_handoff*h){
 yp_boot view;unsigned char block[64];uint32_t slot,off,k,n;
 if(!b||!b->ready||!baseline||approved!=1||b->state!=YP_BOOT_EMPTY||
    b->active!=-1||b->generation!=0||!b->io.read||!b->layout.sector)return YP_BOOT_START_REJECTED;
 if(!h||!h->quiesce||!h->jump)return YP_BOOT_START_INVALID;
 /* open validates record headers; first deployment additionally requires erased
  * tails, so residual unknown data never becomes permission to boot a baseline. */
 for(slot=0;slot<2;slot++){
  for(off=0;off<b->layout.sector;off+=n){
   n=b->layout.sector-off;if(n>sizeof block)n=sizeof block;
   if(b->io.read(b->io.ctx,b->layout.journal[slot]+off,block,n))return YP_BOOT_START_REJECTED;
   for(k=0;k<n;k++)if(block[k]!=255)return YP_BOOT_START_REJECTED;
  }
 }
 /* Local selection view only; CONFIRMED here is not persisted or reported as an
  * upgrade result. Reuse the identical signature/vector/handoff checks. */
 view=*b;view.state=YP_BOOT_CONFIRMED;view.new_image=*baseline;
 return yp_boot_start(&view,1,p,h);
}
