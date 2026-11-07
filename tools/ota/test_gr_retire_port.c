/* SAM | 2026-10-25 +08:00 | Exercise retirement against the real Boot journal states; no hardware. */
#define main existing_port_suite
#include "test_gr_port.c"
#undef main
static int unchanged_retire(yp001_ota_record *r,bool expected){
 static unsigned char before_b[442368],before_j[8192],before_o[8192];
 memcpy(before_b,bflash,sizeof bflash);memcpy(before_j,journalflash,sizeof journalflash);memcpy(before_o,flash,sizeof flash);
 CHECK(yp001_ota_port_retire(r)==expected);
 CHECK(!memcmp(before_b,bflash,sizeof bflash)&&!memcmp(before_j,journalflash,sizeof journalflash)&&!memcmp(before_o,flash,sizeof flash));
 return 0;
}
int main(void){
 yp001_ota_record r,loaded;yp_boot boot;yp_boot_image old={4096,1000002,{0x11}},next={4096,1005000,{0x78}};
 static uint32_t work[1024];static unsigned char trial[8192],owner_before[8192];uint32_t at,total,durable,provision[27];
 yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};
 yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};
 memset(flash,255,sizeof flash);memset(journalflash,255,sizeof journalflash);memset(bootflash,255,sizeof bootflash);
 memset(aflash,0x11,sizeof aflash);memset(bflash,255,sizeof bflash);memset(provision,0,sizeof provision);
 provision[0]=provision[1]=provision[2]=1;memcpy(provision+3,yp_ota_layout_pin,32);memcpy(provision+11,yp_ota_data_pin,32);memcpy(provision+19,yp_ota_public_pin,32);
 memcpy(bootflash+256,provision,sizeof provision);sca[0]=sizeof bootflash;sca[2]=sca[3]=0x2ec000;
 memset(&r,0,sizeof r);r.epoch=2;r.phase=OTA_DOWNLOADING;strcpy(r.target,"GR5526");strcpy(r.source_version,"1.0.2");strcpy(r.version,"1.5.0");
 strcpy(r.job,"2bdfc1ca8e696f2f77218982fa61b80939f6e95852aa3336bf64264feaeace8d");
 strcpy(r.hash,"96bc08c57633b4a820fa2ed0b2df57860eefefa85596aff338b407454c1a5139");CHECK(yp001_ota_port_store(&r));CHECK(yp001_ota_port_progress_store(&r,429256,0));
 for(at=4096;at<=299008;at+=4096)CHECK(yp001_ota_port_progress_store(&r,429256,at));
 CHECK(!unchanged_retire(&r,true));strcpy(r.source_version,"1.0.1");CHECK(!unchanged_retire(&r,false));strcpy(r.source_version,"1.0.2");
 memset(bflash,0x78,sizeof bflash);CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work));
 CHECK(!yp_boot_prepare(&boot,&old,&next));CHECK(!unchanged_retire(&r,false));
 CHECK(!yp_boot_activate(&boot));CHECK(!unchanged_retire(&r,false));
 CHECK(!yp_boot_resume(&boot)&&boot.state==YP_BOOT_TRIAL);CHECK(!unchanged_retire(&r,false));memcpy(trial,journalflash,sizeof trial);
 CHECK(!yp_boot_confirm(&boot));CHECK(!unchanged_retire(&r,true));
 memcpy(journalflash,trial,sizeof trial);CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work));
 CHECK(!yp_boot_trial(&boot,1));CHECK(!yp_boot_trial(&boot,1)&&boot.state==YP_BOOT_ROLLBACK);CHECK(!unchanged_retire(&r,false));
 CHECK(!yp_boot_resume(&boot)&&boot.state==YP_BOOT_REVERTED);CHECK(!unchanged_retire(&r,true));
 memcpy(owner_before,flash,sizeof flash);
 for(at=1;at<=2;at++){
  memcpy(flash,owner_before,sizeof flash);loaded=r;loaded.phase=OTA_COMPLETE;strcpy(loaded.outcome,"retired");strcpy(loaded.actual_version,"1.0.2");
  fail_write=(int)at;writes=0;CHECK(!yp001_ota_port_store(&loaded));fail_write=0;
  CHECK(yp001_ota_port_load(&loaded)==1&&loaded.phase==OTA_DOWNLOADING);
  CHECK(yp001_ota_port_progress_load(&r,&total,&durable)&&total==429256&&durable==299008);
 }
 memcpy(flash,owner_before,sizeof flash);loaded=r;loaded.phase=OTA_COMPLETE;strcpy(loaded.outcome,"retired");CHECK(yp001_ota_port_store(&loaded));
 CHECK(yp001_ota_port_progress_load(&loaded,&total,&durable)&&durable==299008);
 loaded.epoch=3;memset(loaded.hash,'c',64);loaded.phase=OTA_DOWNLOADING;CHECK(yp001_ota_port_store(&loaded));
 CHECK(yp001_ota_port_progress_load(&loaded,&total,&durable)&&total==0&&durable==0);
 /* SAM | 2026-10-26 +08:00 | Reproduce the real R5 zero-checkpoint/dirty-R4-B condition: empty cancellation must reject, precise retirement must preserve B and all journals. */
 strcpy(loaded.job,"5fbfa8fba57e15654dab0c62023f245c681227dd3ef481078fa681bf894edc5f");
 strcpy(loaded.hash,"eaf020f7a88d368d3017cd2c093535beb20b35f6001a71a505cf54662ad659f4");
 CHECK(yp001_ota_port_store(&loaded));CHECK(yp001_ota_port_progress_store(&loaded,432328,0));
 memset(bflash,0x78,sizeof bflash);
 CHECK(!yp001_ota_port_cancel_empty(&loaded));CHECK(!unchanged_retire(&loaded,true));
 loaded.epoch=4;CHECK(!unchanged_retire(&loaded,false));loaded.epoch=3;
 CHECK(yp001_ota_port_progress_store(&loaded,432328,4096));CHECK(!unchanged_retire(&loaded,false));
 puts("PASS real Boot retirement matrix, no-write predicates, interrupted commits, retained old progress and zero new-owner progress");return 0;
}
