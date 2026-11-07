/* SAM | 2026-11-07 07:14 +08:00 | User-approved USB supply is an alternative OTA power source in all builds; this does not enable charging. */
#ifndef YP001_OTA_USB_BENCH_H
#define YP001_OTA_USB_BENCH_H
#include <stdbool.h>
#include <stdint.h>
#ifndef YP001_OTA_USB_BENCH_TEST
#define YP001_OTA_USB_BENCH_TEST 0
#endif
static inline bool yp001_ota_usb_supply(bool present, bool good, bool thermal,
                                      uint8_t fault, uint8_t power)
{
    /* Ignore only NTC classification while charging is disabled (USB-only).
     * Live input, power-good, no thermal/system faults and no OTG are required. */
    return present && good && !thermal && !(fault & 0xF8U) &&
           !(power & 0x20U) && (!(power & 0x10U) || !(fault & 7U));
}
#endif
