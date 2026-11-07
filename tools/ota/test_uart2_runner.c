/* SAM | 2026-10-23 +08:00 | Native process avoids host/compiler bitness coupling in wire tests. */
#include "../../ble_app_uart_c/Src/user/ota/yp001_ota_wire.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static unsigned count;
static void received(const uint8_t *p,size_t n,void *ctx)
{ (void)ctx; if(yp001_ota_wire_valid(p,n)) ++count; }
static uint32_t u32(const uint8_t *p)
{return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
int main(void)
{
    char line[4096]; uint8_t data[2048],encoded[540];
    while(fgets(line,sizeof(line),stdin)) {
        size_t i,n=strcspn(line,"\r\n")/2; int valid,same=0;
        yp001_ota_wire_rx rx={{0},0,0}; count=0;
        for(i=0;i<n;++i) {char h[3]={line[2*i],line[2*i+1],0}; data[i]=(uint8_t)strtoul(h,NULL,16);}
        valid=yp001_ota_wire_valid(data,n);
        if(valid) {
            size_t size=yp001_ota_wire_encode(encoded,sizeof(encoded),data[5],u32(data+8),u32(data+12),u32(data+16),data+24,n-28);
            same=size==n && !memcmp(encoded,data,n);
        }
        for(i=0;i<n;++i) yp001_ota_wire_feed(&rx,data[i],received,NULL);
        printf("%d %u %d\n",valid,count,same);
    }
    return 0;
}
