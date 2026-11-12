/* SAM | 2026-10-13 15:00 +08:00 | Test bounded factory commands before
 * implementation because BLE must not expose the general debug CLI. */
#include "yp001_factory_protocol.h"
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); return 1; } } while(0)
int main(void) {
    ft_request_t r;
    CHECK(ft_parse("FT INFO 1",&r) && r.op==FT_INFO && r.seq==1);
    CHECK(ft_parse("FT UNLOCK 2",&r) && r.op==FT_UNLOCK);
    CHECK(ft_parse("FT SHIP_CONFIRM 3 4294967295",&r) && r.arg==0xffffffffU);
    CHECK(ft_parse("FT PAGE 4 5",&r) && r.arg==5);
    CHECK(!ft_parse("FT PAGE 4 6",&r));
    CHECK(!ft_parse("FT INFO 0",&r));
    CHECK(!ft_parse("FT INFO 4294967296",&r));
    CHECK(!ft_parse("FT INFO -1",&r));
    CHECK(!ft_parse("FT INFO 1 extra",&r));
    CHECK(!ft_parse("FT SHIP_CONFIRM 3 0",&r));
    CHECK(!ft_parse("FT SHIP_CONFIRM 3 +1",&r));
    CHECK(!ft_parse("charger start",&r));
    CHECK(!ft_parse("FT ERASE 1",&r));
    CHECK(!ft_parse("FT INFO 1\nFT UNLOCK 2",&r));
    CHECK(ft_lease_valid(true,100U,60099U));
    CHECK(!ft_lease_valid(true,100U,60100U));
    CHECK(!ft_lease_valid(false,100U,101U));
    CHECK(ft_lease_valid(true,0xffffff00U,0x100U));
    /* SAM | 2026-11-12 +08:00 | Deep-sleep current test: only the exact fixed line is writable; status is read-only; other sleep_test forms stay closed. */
    CHECK(ft_cli_allowed("sleep_test enter force") && !ft_cli_read_only("sleep_test enter force"));
    CHECK(ft_cli_allowed("sleep_test status") && ft_cli_read_only("sleep_test status"));
    CHECK(!ft_cli_allowed("sleep_test enter") && !ft_cli_allowed("sleep_test enter low long") && !ft_cli_allowed("sleep_test enter high long") && !ft_cli_allowed("sleep_test exit"));
    puts("PASS: actual factory command grammar, overflows, whitelist and lease rollover"); return 0;
}
