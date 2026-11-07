#ifndef EPAPER_HOME_H
#define EPAPER_HOME_H

#include <stdbool.h>
#include <stdint.h>

/* A 200 x 200, one-bit frame in the DEPG0150 driver's column order. */
#define EPAPER_HOME_FRAME_BYTES 5000U

typedef struct {
    bool ble_known;
    bool ble_ready;
    bool alarm_known;
    bool alarm_active;
    bool battery_known;
    uint8_t battery_percent;
    /* SAM | 2026-10-09 15:15 +08:00 | Keep validity separate because an
     * unavailable ADC/SOC sample must never look like an empty battery. */
    bool voltage_known;
    uint16_t battery_mv;
    const char *power_text;
} epaper_home_status_t;

void epaper_home_render(uint8_t frame[EPAPER_HOME_FRAME_BYTES],
                        const epaper_home_status_t *status);

#endif
