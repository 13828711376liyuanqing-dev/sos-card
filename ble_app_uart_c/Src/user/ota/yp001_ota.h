/* SAM | 2026-10-12 19:23 +08:00 | Durable OTA arbitration because both targets share power and user data. */
#ifndef YP001_OTA_H
#define YP001_OTA_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define YP001_OTA_FRAME_MAX 1024U
typedef enum {
    OTA_IDLE,
    OTA_DOWNLOADING,
    OTA_PREPARED,
    OTA_INSTALL_PENDING,
    OTA_COMPLETE
} yp001_ota_phase;
typedef struct {
    uint32_t epoch;
    yp001_ota_phase phase;
    char job[65], hash[65], target[8];
    char version[64], source_version[64], actual_version[64], outcome[8];
} yp001_ota_record;
void yp001_ota_init(void);
/* SAM | 2026-10-23 19:26 +08:00 | Complete GR installs from actual local health evidence after reboot. */
void yp001_ota_poll(void);
/* SAM | 2026-10-27 +08:00 | Foreground-only pending quiet service; no reset poll, no recursive Flash execution. */
void yp001_ota_service_pending(void);
bool yp001_ota_handle_line(const char *line, size_t length);
/* SAM | 2026-10-25 +08:00 | Only a granted foreground transaction may mutate OTA Flash. */
bool yp001_ota_flash_allowed(void);
void yp001_ota_dispatch_wire(const uint8_t *frame,size_t length);
bool yp001_ota_power_change_allowed(void);
/* SAM | 2026-10-31 15:08 +08:00 | CAT1-requested OTA power hold ([OTA_HOLD] 1/0 text line). Returns true when the hold state changed. */
bool yp001_ota_cat1_hold(bool on);
/* SAM | 2026-10-28 19:00 +08:00 | Read-only: a durable GR5526 owner is mid-transaction, so CAT1 must be running to carry download/health traffic. Never true for CAT1 native installs. */
bool yp001_ota_cat1_autostart_allowed(void);
#endif
