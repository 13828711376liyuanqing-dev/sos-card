/* SAM | 2026-11-04 +08:00 | Host-test stub of the SDK hal_flash API (implemented in test_name_push.c over a RAM image of the
 * two name-glyph pages; writes only clear bits like NOR Flash, faults can be injected). */
#pragma once
#include <stdbool.h>
#include <stdint.h>
uint32_t hal_flash_read(const uint32_t addr, uint8_t *buf, const uint32_t size);
uint32_t hal_flash_write(const uint32_t addr, const uint8_t *buf, const uint32_t size);
bool hal_flash_erase(const uint32_t addr, const uint32_t size);
