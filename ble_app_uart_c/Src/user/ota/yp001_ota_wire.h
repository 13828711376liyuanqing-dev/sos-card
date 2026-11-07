/* SAM | 2026-10-23 +08:00 | Bound OTA2 frames independently of flash authorization. */
#ifndef YP001_OTA_WIRE_H
#define YP001_OTA_WIRE_H
#include <stddef.h>
#include <stdint.h>
#define YP001_OTA_WIRE_MAX 540U
typedef struct { uint8_t bytes[YP001_OTA_WIRE_MAX]; uint16_t used, expected; } yp001_ota_wire_rx;
/* Callback bytes are valid only during the call; consumer must not reenter feed. */
typedef void (*yp001_ota_wire_sink)(const uint8_t *, size_t, void *);
int yp001_ota_wire_valid(const uint8_t *frame, size_t length);
size_t yp001_ota_wire_encode(uint8_t *out, size_t capacity, uint8_t type,
    uint32_t session, uint32_t sequence, uint32_t offset, const uint8_t *payload, size_t length);
unsigned yp001_ota_wire_feed(yp001_ota_wire_rx *rx, uint8_t byte, yp001_ota_wire_sink sink, void *context);
/* SAM | 2026-10-23 +08:00 | One foreground consumer multiplexes whole binary frames and text lines. */
typedef struct { yp001_ota_wire_rx wire; uint32_t last_ms; uint8_t mode; } yp001_ota_mux;
void yp001_ota_mux_lost(yp001_ota_mux *mux);
void yp001_ota_mux_feed(yp001_ota_mux *mux, uint8_t byte, uint32_t now_ms,
    yp001_ota_wire_sink text, yp001_ota_wire_sink frame, void *context);
#endif
