#ifndef YP001_PSRAM_MEM_H
#define YP001_PSRAM_MEM_H

#include <stdbool.h>
#include <stdint.h>

bool yp_psram_mem_init(void);
/* SAM | 2026-11-12 22:40 +08:00 | Keep data during the explicit sleep-current comparison and restore before returning to heap users. */
bool yp_psram_sleep_test_suspend(void);
void yp_psram_sleep_test_resume(void);
void *yp_psram_alloc(uint32_t size);
void yp_psram_free(void *buf_ptr);
/*Fixed PSRAM OTA staging region:usable before yp_psram_mem_init, content volatile. */
bool yp_psram_ota_region(void **base, uint32_t *size);

#endif /* YP001_PSRAM_MEM_H */
