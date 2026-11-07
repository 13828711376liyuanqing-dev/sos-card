/* SAM | 2026-10-25 +08:00 | Replay sixth denial offsets with production receiver;
 * distinguish buffered reception from Flash activity without touching hardware. */
#include "yp001_ota_receive.h"
#include "yp001_ota_wire.h"
#include <assert.h>
#include <stdio.h>
static unsigned reads,erases,writes,checkpoints;
static int denied;
static int allow(void *c,uint32_t s,const uint8_t *h,uint32_t n){(void)c;(void)s;(void)h;(void)n;return denied;}
static int rd(void *c,uint32_t a,void *p,uint32_t n){(void)c;(void)a;(void)p;(void)n;++reads;return -1;}
static int er(void *c,uint32_t a){(void)c;(void)a;++erases;return -1;}
static int wr(void *c,uint32_t a,const void *p,uint32_t n){(void)c;(void)a;(void)p;(void)n;++writes;return -1;}
static int cp(void *c,uint32_t s,const uint8_t *h,uint32_t n,uint32_t o){(void)c;(void)s;(void)h;(void)n;(void)o;++checkpoints;return -1;}
static int vf(void *c,const uint8_t *h,uint32_t n){(void)c;(void)h;(void)n;return -1;}
int main(void){
 yp_receive r;yp_receive_io io={0,allow,rd,er,wr,cp,vf};
 uint8_t hash[32]={1},payload[512]={0},frame[540],reply[44];unsigned i;size_t n;
 assert(yp_receive_open(&r,&io,2,hash,429256,212992)==0);
 for(i=0;i<3;++i){
  n=yp001_ota_wire_encode(frame,sizeof(frame),YP_RX_DATA,2,i,212992+i*512,payload,512);
  assert(yp_receive_frame(&r,frame,(uint32_t)n,reply,sizeof(reply))==44);
  assert(reply[5]==YP_RX_ACK);
 }
 assert(r.accepted==214528 && r.durable==212992);
 denied=1;
 n=yp001_ota_wire_encode(frame,sizeof(frame),YP_RX_DATA,2,3,214528,payload,512);
 assert(yp_receive_frame(&r,frame,(uint32_t)n,reply,sizeof(reply))==44);
 assert(reply[5]==YP_RX_NACK && reply[25]==7);
 assert(r.accepted==214528 && r.durable==212992);
 assert(!reads && !erases && !writes && !checkpoints);
 puts("PASS: accepted=214528 durable=212992; fourth frame NACK7; receiver read/erase/write/checkpoint=0");
 return 0;
}
