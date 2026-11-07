#include "epaper_home.h"

#include <string.h>
/* SAM | 2026-10-09 15:15 +08:00 | Format measured voltage without
 * deriving a fictitious SOC from charger voltage setpoints. */
#include <stdio.h>

/* The SVN LVGL screen hierarchy is reduced to three status rows. No color,
 * touch, animation, FreeRTOS or external image flash is required here. */
static const char s_chars[] = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.-%";
static const uint8_t s_glyphs[][5] = {
    {0,0,0,0,0}, {0x7e,0x11,0x11,0x11,0x7e}, {0x7f,0x49,0x49,0x49,0x36},
    {0x3e,0x41,0x41,0x41,0x22}, {0x7f,0x41,0x41,0x22,0x1c},
    {0x7f,0x49,0x49,0x49,0x41}, {0x7f,0x09,0x09,0x09,0x01},
    {0x3e,0x41,0x49,0x49,0x7a}, {0x7f,0x08,0x08,0x08,0x7f},
    {0x41,0x41,0x7f,0x41,0x41}, {0x20,0x40,0x41,0x3f,0x01},
    {0x7f,0x08,0x14,0x22,0x41}, {0x7f,0x40,0x40,0x40,0x40},
    {0x7f,0x02,0x0c,0x02,0x7f}, {0x7f,0x04,0x08,0x10,0x7f},
    {0x3e,0x41,0x41,0x41,0x3e}, {0x7f,0x09,0x09,0x09,0x06},
    {0x3e,0x41,0x51,0x21,0x5e}, {0x7f,0x09,0x19,0x29,0x46},
    {0x46,0x49,0x49,0x49,0x31}, {0x01,0x01,0x7f,0x01,0x01},
    {0x3f,0x40,0x40,0x40,0x3f}, {0x1f,0x20,0x40,0x20,0x1f},
    {0x7f,0x20,0x18,0x20,0x7f}, {0x63,0x14,0x08,0x14,0x63},
    {0x07,0x08,0x70,0x08,0x07}, {0x61,0x51,0x49,0x45,0x43},
    {0x3e,0x51,0x49,0x45,0x3e}, {0x00,0x42,0x7f,0x40,0x00},
    {0x62,0x51,0x49,0x49,0x46}, {0x22,0x41,0x49,0x49,0x36},
    {0x18,0x14,0x12,0x7f,0x10}, {0x27,0x45,0x45,0x45,0x39},
    {0x3c,0x4a,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03},
    {0x36,0x49,0x49,0x49,0x36}, {0x06,0x49,0x49,0x29,0x1e},
    {0x00,0x36,0x36,0x00,0x00}, {0x40,0x40,0x40,0x40,0x40},
    {0x00,0x60,0x60,0x00,0x00}, {0x63,0x13,0x08,0x64,0x63}
};

static void pixel(uint8_t *frame, unsigned x, unsigned y)
{
    if (x < 200U && y < 200U)
        frame[x * 25U + y / 8U] &= (uint8_t)~(0x80U >> (y & 7U));
}

static void text(uint8_t *frame, unsigned x, unsigned y, const char *s,
                 unsigned scale)
{
    while (*s != '\0') {
        const char *found = strchr(s_chars, *s++);
        unsigned glyph = found ? (unsigned)(found - s_chars) : 0U;
        for (unsigned col = 0; col < 5U; ++col)
            for (unsigned row = 0; row < 7U; ++row)
                if ((s_glyphs[glyph][col] & (1U << row)) != 0U)
                    for (unsigned dx = 0; dx < scale; ++dx)
                        for (unsigned dy = 0; dy < scale; ++dy)
                            pixel(frame, x + col * scale + dx,
                                  y + row * scale + dy);
        x += 6U * scale;
    }
}

static void line(uint8_t *frame, unsigned y)
{
    for (unsigned x = 12U; x < 188U; ++x) pixel(frame, x, y);
}

void epaper_home_render(uint8_t frame[EPAPER_HOME_FRAME_BYTES],
                        const epaper_home_status_t *status)
{
    if (frame == NULL || status == NULL) return;
    memset(frame, 0xff, EPAPER_HOME_FRAME_BYTES);
    text(frame, 26U, 13U, "SOS CARD", 3U);
    line(frame, 47U);
    text(frame, 14U, 59U, "BLE", 2U);
    text(frame, 108U, 59U, status->ble_known ?
         (status->ble_ready ? "READY" : "FAIL") : "--", 2U);
    line(frame, 90U);
    text(frame, 14U, 102U, "ALARM", 2U);
    text(frame, 108U, 102U, status->alarm_known ?
         (status->alarm_active ? "ON" : "OFF") : "--", 2U);
    line(frame, 133U);
    /* SAM | 2026-10-09 15:15 +08:00 | Compact battery rows so voltage,
     * charging state and a static SOC bar fit below the original header. */
    text(frame, 14U, 140U, "BAT", 2U);
    if (status->battery_known && status->battery_percent <= 100U) {
        uint8_t value = status->battery_percent;
        char label[] = "000%";
        label[0] = (char)('0' + value / 100U);
        label[1] = (char)('0' + (value / 10U) % 10U);
        label[2] = (char)('0' + value % 10U);
        /* SAM | 2026-10-09 15:45 +08:00 | Mark the voltage-based estimate. */
        text(frame, 108U, 140U, label, 2U);
        text(frame, 164U, 145U, "EST", 1U);
    } else {
        text(frame, 108U, 140U, "--", 2U);
    }
    char voltage[16] = "--.-- V";
    if (status->voltage_known)
        (void)snprintf(voltage, sizeof(voltage), "%u.%02u V",
                       (unsigned)(status->battery_mv / 1000U),
                       (unsigned)((status->battery_mv % 1000U) / 10U));
    text(frame, 14U, 157U, voltage, 1U);
    text(frame, 14U, 169U, status->power_text ? status->power_text : "UNKNOWN", 1U);
    for (unsigned x = 14U; x < 186U; ++x) {
        pixel(frame, x, 182U);
        pixel(frame, x, 193U);
        for (unsigned y = 183U; y < 193U; ++y)
            if (x == 14U || x == 185U ||
                (status->battery_known && status->battery_percent <= 100U &&
                 x < 15U + 170U * status->battery_percent / 100U))
                pixel(frame, x, y);
    }
}
