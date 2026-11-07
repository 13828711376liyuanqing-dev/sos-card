/* SAM | 2026-11-02 +08:00 | Host-test stub: RAM NVDS (several tags, delete, length) so persistence is exercised without the SDK. */
#pragma once
#include <stdint.h>
#define NV_TAG_APP(idx) (0x4000 | ((idx) & 0x3FFF))
enum { NVDS_SUCCESS = 0, NVDS_TAG_NOT_EXISTED = 1, NVDS_SPACE_NOT_ENOUGH = 2 };
uint8_t nvds_get(uint16_t tag, uint16_t *p_len, uint8_t *p_buf);
uint8_t nvds_put(uint16_t tag, uint16_t len, const uint8_t *p_buf);
uint8_t nvds_del(uint16_t tag);
uint16_t nvds_tag_length(uint16_t tag);
