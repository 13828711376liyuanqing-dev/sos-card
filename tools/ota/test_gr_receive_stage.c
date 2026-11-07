/* SAM | 2026-11-01 +08:00 | PSRAM-staged receive: no Flash access before the last byte, commit through flush, fault fallback. Host only. */
#include "yp001_ota_receive.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define C(x) do{if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static unsigned char flash[YP_OTA_SLOT_BYTES],payload[10000],stage[16384],hash[32]={1};
static int calls,fail;static unsigned saved;
static int step(void){return ++calls==fail;}
static int auth(void*c,uint32_t s,const uint8_t*h,uint32_t n){(void)c;return s!=7||memcmp(h,hash,32)||n!=sizeof(payload);}
static int readb(void*c,uint32_t a,void*p,uint32_t n){(void)c;if(step())return -1;memcpy(p,flash+a-YP_OTA_B,n);return 0;}
static int eraseb(void*c,uint32_t a){(void)c;C(a%4096==0);if(step())return -1;memset(flash+a-YP_OTA_B,255,4096);return 0;}
static int writeb(void*c,uint32_t a,const void*p,uint32_t n){unsigned i;(void)c;if(step())return -1;for(i=0;i<n;i++)flash[a-YP_OTA_B+i]&=((const unsigned char*)p)[i];return 0;}
static int checkpoint(void*c,uint32_t s,const uint8_t*h,uint32_t t,uint32_t at){(void)c;(void)s;(void)h;(void)t;if(step())return -1;saved=at;return 0;}
static int verify(void*c,const uint8_t*h,uint32_t n){(void)c;(void)h;return memcmp(flash,payload,n);}
static yp_receive_io io={0,auth,readb,eraseb,writeb,checkpoint,verify};
static int feed(yp_receive*r,unsigned from,unsigned end){unsigned at,n;for(at=from;at<end;at+=n){n=end-at;if(n>512)n=512;if(yp_receive_data(r,7,at,payload+at,n))return -1;}return 0;}
int main(void){yp_receive r;unsigned i,total_calls;
 for(i=0;i<sizeof(payload);i++)payload[i]=(unsigned char)(i*7+3);
 /* 1. staged happy path: zero Flash calls until the final frame */
 memset(flash,255,sizeof flash);calls=0;saved=0;
 C(!yp_receive_open(&r,&io,7,hash,sizeof payload,0));
 C(yp_receive_stage(&r,stage,sizeof payload-1));            /* too small */
 C(!yp_receive_stage(&r,stage,sizeof stage));
 C(!feed(&r,0,sizeof payload-(sizeof payload%512)));C(calls==0&&r.durable==0&&saved==0);
 C(!yp_receive_data(&r,7,0,payload,512));                   /* replay matches */
 payload[5]^=1;C(yp_receive_data(&r,7,0,payload,512));payload[5]^=1;C(calls==0);
 C(!feed(&r,sizeof payload-(sizeof payload%512),sizeof payload));
 C(r.durable==sizeof payload&&saved==sizeof payload&&!memcmp(flash,payload,sizeof payload));
 C(!yp_receive_verify(&r)&&r.verified);total_calls=calls;
 C(!yp_receive_data(&r,7,512,payload+512,512));             /* post-commit replay */
 /* 2. stage refused once data accepted */
 C(!yp_receive_open(&r,&io,7,hash,sizeof payload,0));C(!feed(&r,0,512));C(yp_receive_stage(&r,stage,sizeof stage));
 /* 3. every commit fault: receiver closes, durable is a good sector boundary, classic resume completes */
 for(fail=1;fail<=(int)total_calls;fail++){
  memset(flash,255,sizeof flash);calls=0;saved=0;
  C(!yp_receive_open(&r,&io,7,hash,sizeof payload,0));C(!yp_receive_stage(&r,stage,sizeof stage));
  C(feed(&r,0,sizeof payload));C(!r.ready&&saved%4096==0&&saved<sizeof payload);
  {int f=fail;fail=0;
   C(!yp_receive_open(&r,&io,7,hash,sizeof payload,saved));C(!feed(&r,saved,sizeof payload));
   C(!yp_receive_verify(&r)&&!memcmp(flash,payload,sizeof payload));fail=f;}
 }
 printf("PASS staged receive (%u commit fault points)\n",total_calls);return 0;}
