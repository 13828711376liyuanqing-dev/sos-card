/* SAM | 2026-10-23 +08:00 | Host peer runs the actual GR receiver; Flash and signature callbacks are models, not hardware acceptance. */
#include "yp001_ota_receive.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static uint8_t flash[YP_OTA_SLOT_BYTES];
static int allowed(void*c,uint32_t s,const uint8_t*h,uint32_t n){unsigned i;(void)c;if(s!=7||n!=5000)return -1;for(i=0;i<32;i++)if(h[i]!=0xbb)return -1;return 0;}
static int readb(void*c,uint32_t a,void*p,uint32_t n){(void)c;if(a<YP_OTA_B||a-YP_OTA_B>sizeof(flash)||n>sizeof(flash)-(a-YP_OTA_B))return -1;memcpy(p,flash+a-YP_OTA_B,n);return 0;}
static int eraseb(void*c,uint32_t a){(void)c;if(a<YP_OTA_B||a%4096||a-YP_OTA_B>sizeof(flash)-4096)return -1;memset(flash+a-YP_OTA_B,255,4096);return 0;}
static int writeb(void*c,uint32_t a,const void*p,uint32_t n){(void)c;if(a<YP_OTA_B||a-YP_OTA_B>sizeof(flash)||n>sizeof(flash)-(a-YP_OTA_B))return -1;memcpy(flash+a-YP_OTA_B,p,n);return 0;}
static int checkpoint(void*c,uint32_t s,const uint8_t*h,uint32_t n,uint32_t at){return allowed(c,s,h,n)||at>n?-1:0;}
static int verify(void*c,const uint8_t*h,uint32_t n){unsigned i;(void)c;(void)h;if(n!=5000)return -1;for(i=0;i<n;i++)if(flash[i]!='x')return -1;return 0;}
int main(void){
 yp_receive rx;yp_receive_io io={0,allowed,readb,eraseb,writeb,checkpoint,verify};
 uint8_t hash[32],frame[540],reply[540];char line[1100],part[3]={0};unsigned i,n,k;
 memset(hash,0xbb,sizeof(hash));memset(flash,255,sizeof(flash));
 if(yp_receive_open(&rx,&io,7,hash,5000,0))return 1;
 while(fgets(line,sizeof(line),stdin)){
  n=(unsigned)strcspn(line,"\r\n");if(n%2||n>1080)return 2;
  for(i=0;i<n/2;i++){part[0]=line[i*2];part[1]=line[i*2+1];frame[i]=(uint8_t)strtoul(part,0,16);}
  k=yp_receive_frame(&rx,frame,n/2,reply,sizeof(reply));
  for(i=0;i<k;i++){printf("%02x",reply[i]);}
  puts("");fflush(stdout);
 }
 return rx.verified?0:3;
}
