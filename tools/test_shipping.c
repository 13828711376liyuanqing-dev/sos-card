/* SAM | 2026-10-13 14:03 +08:00 | Exercise actual ship controller with bus
 * fault injection because register acceptance cannot prove physical cutoff. */
#include "yp001_shipping.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static uint8_t regs[16];
static bool guard_ok, read_ok, write_ok, verify_ok;
static unsigned writes;
static unsigned fail_at;
static bool change_during_read;
static bool rd(uint8_t reg, uint8_t *v) {
    if (!read_ok) return false;
    *v=regs[reg];
    if (change_during_read) guard_ok=false;
    return true;
}
static bool wr(uint8_t reg, uint8_t mask, uint8_t bits) {
    ++writes;
    if (writes==fail_at) {
        regs[reg]=(uint8_t)((regs[reg]&~mask)|(bits&mask));
        return false; /* Hardware accepted, host did not receive verification. */
    }
    if (!write_ok) return false;
    regs[reg]=(uint8_t)((regs[reg]&~mask)|(bits&mask));
    return verify_ok;
}
static bool guard(void) { return guard_ok; }
static yp_ship_t ship;
static void reset(void) {
    memset(&ship,0,sizeof(ship)); memset(regs,0,sizeof(regs));
    regs[0x0B]=0x3F; regs[7]=0xC7; regs[0x0D]=0xDC;
    read_ok=write_ok=verify_ok=guard_ok=true; writes=fail_at=0;
    change_during_read=false;
}
static bool ready(uint32_t start) {
    if (!yp_ship_prepare(&ship,start,rd,guard)) return false;
    yp_ship_poll(&ship,start+1999U,rd,guard);
    if (ship.phase!=YP_SHIP_CHECKING) return false;
    yp_ship_poll(&ship,start+2000U,rd,guard);
    return ship.phase==YP_SHIP_READY;
}
int main(void) {
    reset(); regs[0x0A]=0x80; CHECK(!yp_ship_prepare(&ship,100,rd,guard)); CHECK(writes==0);
    reset(); regs[8]=4; CHECK(!yp_ship_prepare(&ship,100,rd,guard)); CHECK(writes==0);
    reset(); regs[1]=0x20; CHECK(!yp_ship_prepare(&ship,100,rd,guard)); CHECK(writes==0);
    reset(); regs[5]=0x10; CHECK(!yp_ship_prepare(&ship,100,rd,guard));
    reset(); guard_ok=false; CHECK(!yp_ship_prepare(&ship,100,rd,guard));
    reset(); change_during_read=true; CHECK(!yp_ship_prepare(&ship,100,rd,guard)); CHECK(writes==0);
    reset(); CHECK(ready(100)); CHECK(writes==0); CHECK(yp_ship_locked(&ship));
    CHECK(!yp_ship_confirm(&ship,ship.token+1,2100,rd,wr,guard)); CHECK(writes==0);
    CHECK(yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard));
    CHECK(ship.phase==YP_SHIP_SENT); CHECK(regs[7]==0xEF); CHECK(regs[0x0D]==0x9C);
    CHECK(writes==3); CHECK(!yp_ship_confirm(&ship,ship.token,2101,rd,wr,guard));
    CHECK(!yp_ship_cancel(&ship)); writes=0; read_ok=false;
    yp_ship_poll(&ship,25000,rd,guard); CHECK(writes==0); CHECK(ship.phase==YP_SHIP_SENT);
    reset(); CHECK(ready(100)); regs[8]=4;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard)); CHECK(writes==0);
    CHECK(yp_ship_cancel(&ship)); CHECK(!yp_ship_locked(&ship));
    reset(); CHECK(ready(100)); read_ok=false;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard)); CHECK(writes==0);
    reset(); CHECK(ready(100)); verify_ok=false;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard));
    CHECK(ship.phase==YP_SHIP_FAILED); CHECK(!(regs[7]&0x20));
    reset(); CHECK(ready(100)); fail_at=2;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard)); CHECK(!(regs[7]&0x20));
    CHECK(yp_ship_cancel(&ship));
    reset(); CHECK(ready(100)); fail_at=3;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard));
    CHECK(ship.phase==YP_SHIP_FAILED && ship.disconnect_attempted);
    CHECK(regs[7]&0x20); CHECK(!yp_ship_cancel(&ship));
    reset(); CHECK(ready(100)); guard_ok=false;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard)); CHECK(writes==0);
    reset(); CHECK(ready(100));
    CHECK(!yp_ship_confirm(&ship,ship.token,32100,rd,wr,guard)); CHECK(writes==0);
    reset(); CHECK(ready(100)); uint32_t old_token=ship.token;
    CHECK(yp_ship_cancel(&ship)); CHECK(ready(5000)); CHECK(ship.token!=old_token);
    CHECK(!yp_ship_confirm(&ship,old_token,7000,rd,wr,guard)); CHECK(writes==0);
    reset(); CHECK(ready(100)); yp_ship_poll(&ship,32100,rd,guard);
    CHECK(ship.phase==YP_SHIP_FAILED); CHECK(writes==0);
    reset(); CHECK(ready(0xFFFFFF00U)); CHECK(yp_ship_cancel(&ship));
    reset(); CHECK(yp_ship_prepare(&ship,100,rd,guard)); regs[0x0A]=0x80;
    yp_ship_poll(&ship,400,rd,guard); CHECK(ship.phase==YP_SHIP_FAILED); CHECK(writes==0);
    reset(); CHECK(ready(100)); regs[7]|=0x20;
    CHECK(!yp_ship_confirm(&ship,ship.token,2100,rd,wr,guard)); CHECK(!yp_ship_cancel(&ship));
    puts("PASS: shipping qualification, masks, replay, supply change, failures, timeout, wraparound");
    return 0;
}
