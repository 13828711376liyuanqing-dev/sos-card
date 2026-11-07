/* SAM | 2026-10-25 +08:00 | Exercise first-fault retention independently of UART hardware. */
#include <assert.h>
#include <stdio.h>
#include "yp001_uart_fault.h"
int main(void) {
    volatile yp_uart_fault f = {0};
    assert(!yp_uart_fault_capture(&f, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7));
    assert(f.valid == 0);
    assert(yp_uart_fault_capture(&f, 1, 8, 2, 11, 12, 13, 14, 15, 16, 17));
    assert(f.valid == YP_UART_FAULT_VALID && f.driver_error == 8 && f.rearm_result == 2);
    assert(f.time_ms == 11 && f.rx_before == 12 && f.rx_after == 13);
    assert(f.read_index == 14 && f.write_index == 15 && f.dropped == 16 && f.rx_bytes == 17);
    assert(!yp_uart_fault_capture(&f, 1, 32, 3, 21, 22, 23, 24, 25, 26, 27));
    assert(f.driver_error == 8 && f.time_ms == 11);
    volatile yp_uart_fault g = {0};
    assert(yp_uart_fault_capture(&g, 0, 0, 3, 1, 2, 3, 4, 5, 6, 7));
    assert(g.source == 2 && g.driver_error == 0 && g.rearm_result == 3);
    volatile yp_uart_fault h = {0};
    assert(yp_uart_fault_capture(&h, 1, 0, 0, 1, 2, 3, 4, 5, 6, 7));
    assert(h.source == 1 && h.driver_error == 0 && h.rearm_result == 0);
    puts("UART first-fault cases passed");
    return 0;
}
