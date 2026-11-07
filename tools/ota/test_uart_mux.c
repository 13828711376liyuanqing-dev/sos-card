/* SAM | 2026-10-23 +08:00 | Assert binary payload never reaches the business text consumer. */
#include "../../ble_app_uart_c/Src/user/ota/yp001_ota_wire.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#undef assert
#define assert(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static char text[2048]; static size_t used; static unsigned frames;
static void line(const uint8_t *p,size_t n,void *ctx){(void)ctx;assert(used+n<sizeof(text));memcpy(text+used,p,n);used+=n;}
static void frame(const uint8_t *p,size_t n,void *ctx){(void)ctx;assert(yp001_ota_wire_valid(p,n));++frames;}
static void feed(yp001_ota_mux *m,const uint8_t *p,size_t n,uint32_t t){while(n--)yp001_ota_mux_feed(m,*p++,t,line,frame,NULL);}
int main(void){
    yp001_ota_mux m={0}; uint8_t packet[540]; size_t n;
    const char payload[]="\r\nOTA_CTL={\"op\":\"ACTIVATE\"}\r\n\0tail";
    n=yp001_ota_wire_encode(packet,sizeof(packet),4,1,2,0,(const uint8_t*)payload,sizeof(payload)-1);
    feed(&m,(const uint8_t*)"OTA_CTL={}\r\n",12,0);
    feed(&m,packet,n,1);
    feed(&m,(const uint8_t*)"BUS_EVT={}\r\n",12,2);
    assert(frames==1 && used==24 && !memcmp(text,"OTA_CTL={}\r\nBUS_EVT={}\r\n",24));
    /* CRC-bad payload must not inject a text command; next valid frame resyncs. */
    packet[n-1]^=1;feed(&m,packet,n,3);assert(used==24);
    packet[n-1]^=1;feed(&m,packet,n,4);assert(frames==2 && used==24);
    /* Incomplete binary times out and discards through a text boundary. */
    feed(&m,packet,10,5);feed(&m,(const uint8_t*)"tail\n",5,3000);
    feed(&m,(const uint8_t*)"OK\r\n",4,3001);assert(used==28);
    /* Overflow reset cannot replay a buffered partial prefix. */
    feed(&m,(const uint8_t*)"OTA",3,3002);yp001_ota_mux_lost(&m);
    feed(&m,(const uint8_t*)"2BAD\nOK\n",8,3003);assert(used==31);
    /* A bad outer CRC may contain a valid frame and a partial next frame.
     * Retained bytes stay binary, never index beyond the four-byte magic. */
    {
        yp001_ota_mux nested={0}; uint8_t inner[540],outer[540],body[40];
        size_t k=yp001_ota_wire_encode(inner,sizeof(inner),1,1,1,0,NULL,0);
        memcpy(body,inner,k);memcpy(body+k,inner,12);
        n=yp001_ota_wire_encode(outer,sizeof(outer),4,1,3,0,body,sizeof(body));
        outer[n-1]^=1;
        feed(&nested,outer,n,4000);
        assert(nested.mode==2 && nested.wire.used>4 && used==31);
    }
    puts("PASS UART mux: binary isolation, text continuity, CRC resync, timeout and overflow");
    return 0;
}
