/* SAM | 2026-10-27 +08:00 | Test the production read-only/short-commit boundary and revocation using the existing confined HAL model. */
#define main prior_port_suite
#include "test_gr_port.c"
#undef main
static yp001_ota_record setup(void){
 yp001_ota_record r;uint32_t provision[27];
 memset(&r,0,sizeof r);r.epoch=90;r.phase=OTA_DOWNLOADING;
 memset(r.job,'a',64);memset(r.hash,'b',64);strcpy(r.target,"GR5526");strcpy(r.source_version,"1.0.2");strcpy(r.version,"1.5.0");
 memset(flash,255,sizeof flash);memset(journalflash,255,sizeof journalflash);memset(bootflash,255,sizeof bootflash);memset(bflash,255,sizeof bflash);memset(aflash,0x11,sizeof aflash);
 memset(provision,0,sizeof provision);provision[0]=provision[1]=provision[2]=1;
 memcpy(provision+3,yp_ota_layout_pin,32);memcpy(provision+11,yp_ota_data_pin,32);memcpy(provision+19,yp_ota_public_pin,32);memcpy(bootflash+256,provision,sizeof provision);
 sca[0]=sizeof bootflash;sca[2]=sca[3]=0x2ec000;short_read=0;fail_write=0;flash_granted=true;native_ok=1;running_version=1000002;strcpy(yp_test_product_version,"1.0.2");
 journal_writes=journal_fail_write=0;journal_write_then_fail=false;
 input=(yp_business_ota_inputs_t){true,true,false};business.battery_known=true;business.battery_percent=89;business.charging=true;business.transport_ready=true;business.network=YP_NET_MQTT;business.call=YP_CALL_IDLE;
 test_usb_valid=false;yp001_ota_port_install_check_reset();
 if(!yp001_ota_port_store(&r)||!yp001_ota_port_progress_store(&r,5000,0))abort();
 memset(bflash,0x78,sizeof bflash);
 if(!yp001_ota_port_progress_store(&r,5000,4096)||!yp001_ota_port_progress_store(&r,5000,5000))abort();
 r.phase=OTA_PREPARED;if(!yp001_ota_port_store(&r))abort();return r;
}
/* SAM | 2026-11-07 09:13 +08:00 | Rejected read-only commands must release the fixture lease state just like production quiet_drop. */
static int rejects_activation(const yp001_ota_record *r){
 bool prior=flash_granted;int verdict=0;flash_granted=false;yp001_ota_port_install_check_reset();
 for(unsigned i=0;i<3&&verdict==0;i++)verdict=yp001_ota_port_install_check_step(r);
 flash_granted=prior;return verdict<0&&!yp001_ota_port_install_check_ready(r);
}
/* SAM | 2026-11-07 09:13 +08:00 | Fault-inject a CRC-valid durable owner without discarding progress, so rejection reaches the native hash/Boot identity checks. */
static void corrupt_owner(const yp001_ota_record *r){
 typedef struct {uint32_t magic,generation;yp001_ota_record record;uint32_t total,durable,crc,commit;} fixture_page;
 for(unsigned slot=0;slot<2;slot++){
  fixture_page page;memcpy(&page,flash+slot*4096,sizeof page);
  page.record=*r;page.crc=crc(&page,offsetof(fixture_page,crc));
  memcpy(flash+slot*4096,&page,sizeof page);
 }
}
/* SAM | 2026-11-07 09:13 +08:00 | Reproduce post-swap duplicate activation using real Boot journals; health must continue without writes or reset. */
static int duplicate_after_swap(void){
 yp001_ota_record r=setup(),wrong,result;yp_boot boot;static uint32_t work[1024];
 yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};
 yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};
 yp_boot_image old={4096,1000002,{0x11}},next={4096,1005000,{0x78}};
 static uint8_t owner_before[8192],boot_before[8192];unsigned resets_before=resets;
 CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&!yp_boot_prepare(&boot,&old,&next)&&!yp_boot_activate(&boot));
 r.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&r));
 CHECK(!yp_boot_resume(&boot)&&!yp_boot_trial(&boot,3));
 strcpy(yp_test_product_version,"1.5.0");running_version=1005000;
 business.now_ms=0;CHECK(prime_health(&r)==0);
 for(business.now_ms=1000;business.now_ms<=60000;business.now_ms+=1000)CHECK(!yp001_ota_port_result(&r,&result));
 memcpy(owner_before,flash,sizeof flash);memcpy(boot_before,journalflash,sizeof journalflash);
 CHECK(validate_activation(&r)==0);CHECK(yp001_ota_port_install_commit(&r));
 CHECK(!memcmp(owner_before,flash,sizeof flash)&&!memcmp(boot_before,journalflash,sizeof journalflash));
 business.now_ms=61000;yp001_ota_port_poll();CHECK(resets==resets_before);
 /* A new command must reject every nonmatching durable identity, rather than trust version text. */
 wrong=r;wrong.epoch++;CHECK(rejects_activation(&wrong));
 wrong=r;wrong.hash[63]='c';CHECK(rejects_activation(&wrong));
 corrupt_owner(&wrong);CHECK(rejects_activation(&wrong));
 {uint32_t e[6];yp001_ota_port_activation_evidence(e);CHECK(e[5]==12);}
 memcpy(flash,owner_before,sizeof flash);
 wrong=r;strcpy(wrong.source_version,"1.0.3");CHECK(rejects_activation(&wrong));
 corrupt_owner(&wrong);CHECK(rejects_activation(&wrong));memcpy(flash,owner_before,sizeof flash);
 wrong=r;strcpy(wrong.version,"1.5.1");corrupt_owner(&wrong);CHECK(rejects_activation(&wrong));memcpy(flash,owner_before,sizeof flash);
 aflash[0]^=1;CHECK(rejects_activation(&r));aflash[0]^=1;
 native_ok=0;CHECK(rejects_activation(&r));native_ok=1;
 CHECK(validate_activation(&r)==0&&yp001_ota_port_install_commit(&r));
 for(business.now_ms=61000;business.now_ms<=121000;business.now_ms+=1000)CHECK(!yp001_ota_port_result(&r,&result));
 CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&boot.state==YP_BOOT_CONFIRMED);
 /* Boot confirmation invalidates any TRIAL receipt; revalidation acknowledges CONFIRMED without changing it. */
 CHECK(!yp001_ota_port_install_commit(&r));
 memcpy(boot_before,journalflash,sizeof journalflash);CHECK(validate_activation(&r)==0&&yp001_ota_port_install_commit(&r));
 CHECK(!memcmp(boot_before,journalflash,sizeof journalflash));yp001_ota_port_poll();CHECK(resets==resets_before);
 CHECK(yp001_ota_port_result(&r,&result)&&!strcmp(result.outcome,"success"));
 puts("PASS duplicate ACTIVATE: TRIAL/CONFIRMED, identity rejection, no writes/reset, continuous health");return 0;
}
int main(void){
 CHECK(duplicate_after_swap()==0);
 yp001_ota_record r,wrong;unsigned calls;static uint8_t before_owner[8192],before_boot[8192];
 /* SAM | 2026-11-07 07:14 +08:00 | Real final commit enforces 49/50 and a fresh USB read, including unplug after validation. */
 for(unsigned pre=0;pre<2;pre++)for(unsigned mode=0;mode<4;mode++){
  r=setup();CHECK(validate_activation(&r)==0&&yp001_ota_port_install_prepare(&r));r.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&r));
  business.charging=false;business.battery_percent=mode==0?50:49;
  if(mode>=2){business.battery_known=false;test_usb_valid=true;}
  if(mode==3)test_usb_valid=false;
  if(mode==0||mode==2)CHECK(pre?yp001_ota_port_install_commit_prechecked(&r):yp001_ota_port_install_commit(&r));
  else CHECK(!(pre?yp001_ota_port_install_commit_prechecked(&r):yp001_ota_port_install_commit(&r)));
 }

 /* SAM | 2026-11-07 07:14 +08:00 | Unknown battery on USB confirms only after a complete continuous health interval; unplug restarts it. */
 r=setup();CHECK(validate_activation(&r)==0&&yp001_ota_port_install_prepare(&r));r.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&r));CHECK(yp001_ota_port_install_commit(&r));
 {yp_boot boot;yp001_ota_record result;static uint32_t work[1024];
 yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};
 CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&!yp_boot_resume(&boot)&&!yp_boot_trial(&boot,3));
 strcpy(yp_test_product_version,"1.5.0");running_version=1005000;business.battery_known=false;test_usb_valid=true;
 business.now_ms=0;CHECK(prime_health(&r)==0);
 for(business.now_ms=1000;business.now_ms<=61000;business.now_ms+=1000)CHECK(!yp001_ota_port_result(&r,&result));
 test_usb_valid=false;CHECK(!yp001_ota_port_result(&r,&result));test_usb_valid=true;
 for(business.now_ms=63000;business.now_ms<183000;business.now_ms+=1000)CHECK(!yp001_ota_port_result(&r,&result));
 CHECK(!yp001_ota_port_result(&r,&result));CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&boot.state==YP_BOOT_CONFIRMED);
 CHECK(yp001_ota_port_result(&r,&result)&&!strcmp(result.outcome,"success"));
 }
 /* Lost ACK after durable INSTALL is not permission to blindly repeat a write: reopen/revalidate the actual generation first. */
 r=setup();CHECK(validate_activation(&r)==0&&yp001_ota_port_install_prepare(&r));r.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&r));
 journal_fail_write=journal_writes+2;journal_write_then_fail=true;CHECK(!yp001_ota_port_install_commit(&r));
 {yp_boot b;static uint32_t work[1024];yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};CHECK(!yp_boot_open(&b,&layout,&io,work,sizeof work)&&b.state==YP_BOOT_INSTALL);}
 yp001_ota_port_install_check_reset();CHECK(!yp001_ota_port_install_commit(&r));journal_fail_write=0;CHECK(validate_activation(&r)==0);CHECK(yp001_ota_port_install_commit(&r));
 /* Re-enter from durable PREPARED after a reset between Boot prepare and the owner transition. */
 r=setup();CHECK(validate_activation(&r)==0&&yp001_ota_port_install_prepare(&r));yp001_ota_port_install_check_reset();CHECK(validate_activation(&r)==0&&yp001_ota_port_install_prepare(&r));
 r=setup();memcpy(before_owner,flash,sizeof flash);memcpy(before_boot,journalflash,sizeof journalflash);calls=running_auth_calls;
 CHECK(validate_activation(&r)==0&&running_auth_calls==calls+1);
 CHECK(!memcmp(before_owner,flash,sizeof flash)&&!memcmp(before_boot,journalflash,sizeof journalflash));
 wrong=r;wrong.epoch++;CHECK(!yp001_ota_port_install_check_ready(&wrong));
 wrong=r;strcpy(wrong.source_version,"1.0.3");CHECK(!yp001_ota_port_install_check_ready(&wrong));
 CHECK(yp001_ota_port_install_prepare(&r));r.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&r));
 calls=running_auth_calls;CHECK(yp001_ota_port_install_commit(&r)&&running_auth_calls==calls);
 yp001_ota_port_install_check_reset();CHECK(!yp001_ota_port_install_check_ready(&r)&&!yp001_ota_port_install_commit(&r));
 r=setup();CHECK(validate_activation(&r)==0);wrong=r;strcpy(wrong.source_version,"1.0.3");CHECK(yp001_ota_port_store(&wrong));CHECK(!yp001_ota_port_install_check_ready(&r));
 r=setup();CHECK(validate_activation(&r)==0);writes=0;fail_write=1;r.phase=OTA_INSTALL_PENDING;CHECK(!yp001_ota_port_store(&r));CHECK(!yp001_ota_port_install_check_ready(&r));fail_write=0;
 r=setup();flash_granted=false;CHECK(yp001_ota_port_install_check_step(&r)==0);native_ok=0;CHECK(yp001_ota_port_install_check_step(&r)==-1&&!yp001_ota_port_install_check_ready(&r));native_ok=1;
 /* SAM | 2026-11-06 +08:00 | Port diagnostics preserve this command's precise failure without changing stale first-error history or samples. */
 {uint32_t evidence[6];yp001_ota_port_activation_evidence(evidence);CHECK(evidence[0]==100&&evidence[1]==101&&evidence[2]==102&&evidence[3]==103&&evidence[4]==104&&evidence[5]==12);yp001_ota_port_install_check_reset();yp001_ota_port_activation_evidence(evidence);CHECK(evidence[5]==0);}

 r=setup();CHECK(validate_activation(&r)==0);CHECK(yp001_ota_port_install_check_step(&r)==-1&&!yp001_ota_port_install_check_ready(&r));
 r=setup();flash_granted=false;CHECK(yp001_ota_port_install_check_step(&r)==0);
 {yp_boot b;static uint32_t work[1024];yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};yp_boot_image a={4096,1000002,{0x11}},next={4096,1005000,{0x78}};
  CHECK(!yp_boot_open(&b,&layout,&io,work,sizeof work)&&!yp_boot_prepare(&b,&a,&next));}
 CHECK(yp001_ota_port_install_check_step(&r)==-1&&!yp001_ota_port_install_check_ready(&r));
 puts("PASS production install receipt: read-only stages, no short-commit crypto, owner/source/generation/restart/write-failure revocation");return 0;
}
