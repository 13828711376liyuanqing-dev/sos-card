/* SAM | 2026-10-23 +08:00 | Fault-inject staged writes and durable replay; no device access. */
#include "yp001_ota_receive.h"
#include "yp001_ota_wire.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define C(x) do{if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static unsigned char flash[YP_OTA_SLOT_BYTES],payload[5000],hash[32]={1};
static int calls,fail,allowed=1,verify_fail;static unsigned saved;
static int step(void){return ++calls==fail;}
static int auth(void*c,uint32_t s,const uint8_t*h,uint32_t n){(void)c;return !allowed||s!=7||memcmp(h,hash,32)||n!=sizeof(payload);}
static int readb(void*c,uint32_t a,void*p,uint32_t n){(void)c;C(a>=YP_OTA_B&&a-YP_OTA_B+n<=sizeof(flash));if(step())return -1;memcpy(p,flash+a-YP_OTA_B,n);return 0;}
static int eraseb(void*c,uint32_t a){(void)c;C(a>=YP_OTA_B&&a-YP_OTA_B<=sizeof(flash)-4096&&a%4096==0);if(step())return -1;memset(flash+a-YP_OTA_B,255,4096);return 0;}
static int writeb(void*c,uint32_t a,const void*p,uint32_t n){unsigned i;(void)c;C(a>=YP_OTA_B&&a-YP_OTA_B+n<=sizeof(flash));if(step())return -1;for(i=0;i<n;i++)flash[a-YP_OTA_B+i]&=((const unsigned char*)p)[i];return 0;}
static int checkpoint(void*c,uint32_t s,const uint8_t*h,uint32_t total,uint32_t at){C(!auth(c,s,h,total));if(step())return -1;saved=at;return 0;}
static int verify(void*c,const uint8_t*h,uint32_t n){(void)c;C(!memcmp(h,hash,32)&&n==sizeof(payload));return verify_fail||memcmp(flash,payload,n);}
static yp_receive_io io={0,auth,readb,eraseb,writeb,checkpoint,verify};
static void feed(yp_receive*r,unsigned from,unsigned end){unsigned at,n;for(at=from;at<end;at+=n){n=end-at;if(n>512)n=512;C(!yp_receive_data(r,7,at,payload+at,n));}}
int main(void){yp_receive r;unsigned i;int boundary,before;
 for(i=0;i<sizeof(payload);i++)payload[i]=(unsigned char)i;
 memset(flash,255,sizeof(flash));C(!yp_receive_open(&r,&io,7,hash,sizeof(payload),0));
 C(yp_receive_data(&r,8,0,payload,512));C(yp_receive_data(&r,7,512,payload,512));C(!calls);
 feed(&r,0,512);C(r.accepted==512&&r.durable==0&&calls==0);
 C(!yp_receive_data(&r,7,0,payload,512));payload[0]^=1;C(yp_receive_data(&r,7,0,payload,512));payload[0]^=1;
 allowed=0;C(yp_receive_data(&r,7,512,payload+512,512));allowed=1;
 feed(&r,512,4096);C(saved==4096&&r.durable==4096);boundary=calls;
 C(!yp_receive_open(&r,&io,7,hash,sizeof(payload),saved));feed(&r,4096,sizeof(payload));
 C(r.accepted==sizeof(payload)&&saved==sizeof(payload));C(!yp_receive_verify(&r)&&r.verified);
 C(!yp_receive_data(&r,7,4608,payload+4608,392));C(!memcmp(flash,payload,sizeof(payload)));
 for(i=sizeof(payload);i<8192;i++)C(flash[i]==255);
 /* Every erase/write/read/checkpoint failure requires reopen; no false durable advance. */
 for(fail=1;fail<=boundary;fail++){
  calls=0;saved=0;C(!yp_receive_open(&r,&io,7,hash,sizeof(payload),0));feed(&r,0,3584);
  C(yp_receive_data(&r,7,3584,payload+3584,512));C(!r.ready&&saved==0&&r.durable==0);
  before=calls;C(yp_receive_data(&r,7,3584,payload+3584,512));C(before==calls);
 }
 fail=0;calls=0;C(yp_receive_open(&r,&io,7,hash,YP_OTA_SLOT_BYTES+1,0));C(!calls);
 C(yp_receive_open(&r,&io,7,hash,sizeof(payload),512));C(!calls);
 C(!yp_receive_open(&r,&io,7,hash,sizeof(payload),0));feed(&r,0,sizeof(payload));
 verify_fail=1;C(yp_receive_verify(&r)&&!r.ready&&!r.verified);
 /* SAM | 2026-10-23 +08:00 | No authority can be created by BEGIN/ACTIVATE or a forged session. */
 {unsigned char request[540],reply[540],begin[36];unsigned n,k;yp_receive closed;
  memset(&closed,0,sizeof closed);
  n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_HELLO,7,1,0,0,0);
  k=yp_receive_frame(&closed,request,n,reply,sizeof reply);C(k&&yp001_ota_wire_valid(reply,k)&&reply[5]==YP_RX_CAPS);
  n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_DATA,7,2,0,payload,512);
  k=yp_receive_frame(&closed,request,n,reply,sizeof reply);C(k&&reply[5]==YP_RX_NACK&&reply[25]==5);
  fail=0;verify_fail=0;C(!yp_receive_open(&r,&io,7,hash,sizeof(payload),0));
  begin[0]=(unsigned char)sizeof(payload);begin[1]=(unsigned char)(sizeof(payload)>>8);begin[2]=begin[3]=0;memcpy(begin+4,hash,32);
  n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_BEGIN,7,1,0,begin,sizeof begin);
  k=yp_receive_frame(&r,request,n,reply,sizeof reply);C(k&&reply[5]==YP_RX_ACK&&r.accepted==0);
  begin[4]^=1;n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_BEGIN,7,1,0,begin,sizeof begin);
  k=yp_receive_frame(&r,request,n,reply,sizeof reply);C(k&&reply[5]==YP_RX_NACK&&r.accepted==0);
  n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_DATA,8,2,0,payload,512);
  k=yp_receive_frame(&r,request,n,reply,sizeof reply);C(k&&reply[5]==YP_RX_NACK&&r.accepted==0);
  n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_DATA,7,2,0,payload,512);
  C(!yp_receive_frame(&r,request,n,reply,43)&&r.accepted==0);
  k=yp_receive_frame(&r,request,n,reply,sizeof reply);C(k&&reply[5]==YP_RX_ACK&&r.accepted==512&&r.durable==0);
  n=(unsigned)yp001_ota_wire_encode(request,sizeof request,YP_RX_ACTIVATE,7,3,0,0,0);
  k=yp_receive_frame(&r,request,n,reply,sizeof reply);C(k&&reply[5]==YP_RX_NACK);
  request[n-1]^=1;C(!yp_receive_frame(&r,request,n,reply,sizeof reply));
 }
 puts("PASS B-slot bounds, duplicates, gaps, pause, durable failure/replay, UART dispatch and no forged activation");return 0;
}
