#ifndef YP001_PSRAM_MEM_H
#define YP001_PSRAM_MEM_H

#include <stdbool.h>
#include <stdint.h>

bool yp_psram_mem_init(void);
void *yp_psram_alloc(uint32_t size);
void yp_psram_free(void *buf_ptr);
/*Fixed PSRAM OTA staging region:usable before yp_psram_mem_init, content volatile. */
bool yp_psram_ota_region(void **base, uint32_t *size);

#endif /* YP001_PSRAM_MEM_H */
