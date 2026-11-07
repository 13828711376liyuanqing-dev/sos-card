#ifndef YP001_BATTERY_H
#define YP001_BATTERY_H
#include <stdint.h>
/* SAM | 2026-10-09 15:45 +08:00 | Distinguish invalid samples because
 * ADC saturation must not become a plausible voltage or SOC value. */
typedef enum {
    YP001_BATTERY_OK, YP001_BATTERY_ADC_ERROR,
    YP001_BATTERY_ADC_RANGE, YP001_BATTERY_LOW
} yp001_battery_result_t;
yp001_battery_result_t yp001_battery_read(uint16_t *millivolts);
uint8_t yp001_battery_estimate(uint16_t millivolts);
#endif

