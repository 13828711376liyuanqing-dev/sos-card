#ifndef YP001_UART_FAULT_H
#define YP001_UART_FAULT_H
#include <stdint.h>
#include <stdbool.h>
/* SAM | 2026-10-25 +08:00 | Publish a boot-lifetime RAM first fault after
 * storing both driver and rearm outcomes; foreground must never clear it.
 * Single UART IRQ writer; debugger reads valid/payload/valid while running. */
#define YP_UART_FAULT_VALID 0x55415254UL
#ifndef YP_UART_FAULT_BARRIER
#define YP_UART_FAULT_BARRIER() ((void)0)
#endif
typedef struct {
    uint32_t valid, source, driver_error, rearm_result, time_ms;
    uint32_t rx_before, rx_after, read_index, write_index, dropped, rx_bytes;
} yp_uart_fault;
/* SAM | 2026-10-25 +08:00 | Keep immutable first cause separate from the
 * foreground recovery outcome; phase 3 blocks further automatic attempts. */
typedef struct {
    uint32_t phase, abort_done, abort_result, rearm_result;
    uint32_t started_ms, completed_ms, count;
    /* SAM | 2026-10-25 +08:00 | Deadline belongs to the actual abort call;
     * record completion in IRQ so foreground scheduling cannot falsify it. */
    uint32_t abort_started_ms, abort_completed_ms;
} yp_uart_recovery;
static inline bool yp_uart_fault_capture(volatile yp_uart_fault *f,
    bool driver_event, uint32_t driver_error, uint32_t rearm_result,
    uint32_t time_ms, uint32_t rx_before, uint32_t rx_after,
    uint32_t read_index, uint32_t write_index, uint32_t dropped, uint32_t rx_bytes)
{
    if (f->valid || (!driver_event && !rearm_result)) return false;
    f->source = driver_event ? 1U : 2U;
    f->driver_error = driver_error;
    f->rearm_result = rearm_result;
    f->time_ms = time_ms;
    f->rx_before = rx_before;
    f->rx_after = rx_after;
    f->read_index = read_index;
    f->write_index = write_index;
    f->dropped = dropped;
    f->rx_bytes = rx_bytes;
    YP_UART_FAULT_BARRIER();
    f->valid = YP_UART_FAULT_VALID;
    return true;
}
#endif
