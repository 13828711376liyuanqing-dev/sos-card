#ifndef EPAPER_DEPG0150_H
#define EPAPER_DEPG0150_H

#include <stdbool.h>
#include <stdint.h>
#include "gui/epaper_home.h"

bool epaper_depg0150_init(void);
bool epaper_depg0150_display_demo_image(void);
bool epaper_depg0150_display_home(const epaper_home_status_t *status);
bool epaper_depg0150_display_frame(const uint8_t frame[EPAPER_HOME_FRAME_BYTES]);
/* SAM | 2026-10-09 17:51 +08:00 | Request one full frame because first
 * valid battery digits did not reach the panel via partial refresh. */
void epaper_depg0150_force_full_next(void);

#endif /* EPAPER_DEPG0150_H */
