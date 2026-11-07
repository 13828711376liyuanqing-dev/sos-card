/* SAM | 2026-10-27 +08:00 | Actual coordinator + actual application port + Boot journals together. Only HAL, signatures and business inputs are host models. */
#define yp001_ota_flash_allowed fixture_flash_allowed
#define main prior_port_suite
#include "test_gr_port.c"
#undef main
#undef yp001_ota_flash_allowed
#include "../../ble_app_uart_c/Src/user/ota/yp001_ota.c"
uint32_t yp001_uart_clock_ms(void){return business.now_ms;}
void yp001_ota_measure_begin(uint32_t kind,uint32_t token){(void)kind;(void)token;}
void yp001_ota_measure_end(void){}
int main(int argc,char **argv){
 (void)argv;
 yp001_ota_record r,loaded;uint32_t provision[27];char line[600];uint8_t frame[44];static uint8_t before_a[442368],before_b[442368],before_boot[8192],before_owner[8192];
 memset(&r,0,sizeof r);r.epoch=4;r.phase=OTA_DOWNLOADING;memset(r.job,'a',64);memset(r.hash,'b',64);strcpy(r.target,"GR5526");strcpy(r.source_version,"1.0.2");strcpy(r.version,"1.5.0");
 memset(flash,255,sizeof flash);memset(journalflash,255,sizeof journalflash);memset(bootflash,255,sizeof bootflash);memset(bflash,255,sizeof bflash);memset(aflash,0x11,sizeof aflash);
 memset(provision,0,sizeof provision);provision[0]=provision[1]=provision[2]=1;memcpy(provision+3,yp_ota_layout_pin,32);memcpy(provision+11,yp_ota_data_pin,32);memcpy(provision+19,yp_ota_public_pin,32);memcpy(bootflash+256,provision,sizeof provision);
 sca[0]=sizeof bootflash;sca[2]=sca[3]=0x2ec000;native_ok=1;input=(yp_business_ota_inputs_t){true,true,false};business.battery_percent=89;business.charging=true;business.transport_ready=true;business.network=YP_NET_MQTT;business.call=YP_CALL_IDLE;
 /* Host-only fixture seeding before real coordinator init; no target or attached-device writes. */
 quiet.allowed=true;CHECK(yp001_ota_port_store(&r)&&yp001_ota_port_progress_store(&r,5000,0));memset(bflash,0x78,sizeof bflash);CHECK(yp001_ota_port_progress_store(&r,5000,4096)&&yp001_ota_port_progress_store(&r,5000,5000));r.phase=OTA_PREPARED;CHECK(yp001_ota_port_store(&r));
 if(argc>1){
  yp_boot b;static uint32_t work[1024];yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};yp_boot_image old={4096,1000002,{0x11}},next={4096,1005000,{0x78}};
  r.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&r));
  CHECK(!yp_boot_open(&b,&layout,&io,work,sizeof work)&&!yp_boot_prepare(&b,&old,&next)&&!yp_boot_activate(&b)&&!yp_boot_resume(&b)&&!yp_boot_trial(&b,3));
  strcpy(yp_test_product_version,"1.5.0");running_version=1005000;yp001_ota_init();running_auth_calls=native_auth_calls=image_auth_calls=0;
  memcpy(before_a,aflash,sizeof aflash);memcpy(before_b,bflash,sizeof bflash);memcpy(before_boot,journalflash,sizeof journalflash);memcpy(before_owner,flash,sizeof flash);
  for(business.now_ms=1000;business.now_ms<135000;business.now_ms+=1000){
   business.network=business.now_ms>=10000&&business.now_ms<15000?YP_NET_UNKNOWN:YP_NET_MQTT;
   yp001_ota_poll();CHECK(quiet.phase==0&&state.phase==OTA_INSTALL_PENDING);
  }
  CHECK(running_auth_calls==1&&native_auth_calls==0&&image_auth_calls==0);
  CHECK(!memcmp(before_boot,journalflash,sizeof journalflash)&&!memcmp(before_owner,flash,sizeof flash));
  yp001_ota_poll();CHECK(quiet.phase==1&&quiet.kind==3&&reply[5]==240);
  CHECK(yp001_ota_wire_encode(frame,sizeof frame,241,1,quiet.token,0,quiet.nonce,16)==44);yp001_ota_dispatch_wire(frame,44);yp001_ota_poll();
  /* SAM | 2026-10-29 21:56 +08:00 | Round-2 defect 3: lease one confirms Boot only (owner stays INSTALL_PENDING); after the release, the next 1 s pass takes a
   * second short lease that writes the owner result. */
  CHECK(state.phase==OTA_INSTALL_PENDING&&quiet.phase==3&&!yp_boot_open(&b,&layout,&io,work,sizeof work)&&b.state==YP_BOOT_CONFIRMED);
  CHECK(yp001_ota_wire_encode(frame,sizeof frame,243,1,quiet.token,0,quiet.nonce,16)==44);yp001_ota_dispatch_wire(frame,44);yp001_ota_poll();CHECK(quiet.phase==0);
  business.now_ms+=1000;yp001_ota_poll();CHECK(quiet.phase==1&&quiet.kind==3&&reply[5]==240);
  CHECK(yp001_ota_wire_encode(frame,sizeof frame,241,1,quiet.token,0,quiet.nonce,16)==44);yp001_ota_dispatch_wire(frame,44);yp001_ota_poll();
  CHECK(state.phase==OTA_COMPLETE&&!strcmp(state.outcome,"success")&&running_auth_calls==1&&image_auth_calls==0);
  CHECK(!yp_boot_open(&b,&layout,&io,work,sizeof work)&&b.state==YP_BOOT_CONFIRMED);
  CHECK(!memcmp(before_a,aflash,sizeof aflash)&&!memcmp(before_b,bflash,sizeof bflash));
  puts("PASS combined health path: one postboot auth, no lease during 120s observations, network gap restarts interval, short confirmation and durable result");return 0;
 }
 memcpy(before_a,aflash,sizeof aflash);memcpy(before_b,bflash,sizeof bflash);memcpy(before_boot,journalflash,sizeof journalflash);memcpy(before_owner,flash,sizeof flash);
 yp001_ota_init();running_auth_calls=native_auth_calls=image_auth_calls=0;modeled_auth_ms=1000;
 snprintf(line,sizeof line,"OTA_CTL={\"op\":\"ACTIVATE\",\"job\":\"%s\",\"hash\":\"%s\",\"target\":\"GR5526\",\"version\":\"1.5.0\",\"epoch\":4}",r.job,r.hash);
 CHECK(yp001_ota_handle_line(line,strlen(line))&&quiet.phase==5&&!quiet.allowed);
 yp001_ota_poll();CHECK(running_auth_calls==1&&quiet.phase==5);
 yp001_ota_poll();CHECK(native_auth_calls==1&&quiet.phase==5);
 CHECK(!memcmp(before_boot,journalflash,sizeof journalflash)&&!memcmp(before_owner,flash,sizeof flash));
 yp001_ota_poll();CHECK(quiet.phase==1&&quiet.at==2000&&reply_size==44&&reply[5]==240);
 /* SAM | 2026-10-29 21:56 +08:00 | Round-2 defect 1: the Boot-journal/owner writes inside the lease leave a stale motion sample; the commit reuses the
  * pre-Flash gate result (1.5.1 denied boot_commit_failed here and Boot stayed PREPARED). */
 fixture_stale_on_write=1;
 business.now_ms+=100;CHECK(yp001_ota_wire_encode(frame,sizeof frame,241,1,quiet.token,0,quiet.nonce,16)==44);yp001_ota_dispatch_wire(frame,44);yp001_ota_poll();
 fixture_stale_on_write=0;CHECK(!input.stable);input.stable=true;
 CHECK(quiet.phase==3&&!quiet.allowed&&running_auth_calls==1&&native_auth_calls==1&&image_auth_calls==0);
 CHECK(yp001_ota_port_load(&loaded)==1&&loaded.phase==OTA_INSTALL_PENDING);
 {yp_boot boot;static uint32_t work[1024];yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&boot.state==YP_BOOT_INSTALL);}
 CHECK(!memcmp(before_a,aflash,sizeof aflash)&&!memcmp(before_b,bflash,sizeof bflash));
 CHECK(!yp001_ota_port_install_check_ready(&loaded));
 CHECK(g_ota_quiet_trace[6]==2100&&g_ota_quiet_trace[7]==2100);
 business.now_ms=2349;yp001_ota_port_poll();CHECK(!resets);business.now_ms=2350;yp001_ota_port_poll();CHECK(resets==1);
 puts("PASS combined production path: two 1s modeled auth stages before lease, no auth within commit, durable INSTALL, reset armed, A/B bytes unchanged");return 0;
}
