#ifndef EPAPER_UI_H
#define EPAPER_UI_H

#include <stdbool.h>
#include <stdint.h>
#include "business/yp001_business.h"

/* SAM | 2026-10-11 00:45 +08:00 | Queue page selection because LVGL
 * objects must only be changed by the existing display polling context. */
typedef enum {
    EPAPER_UI_SCREEN = 0,
    EPAPER_UI_MAIN,
    EPAPER_UI_TIME,
    EPAPER_UI_LOWBAT,
    EPAPER_UI_CALLING,
    EPAPER_UI_CALLEND,
    EPAPER_UI_PAGE_COUNT
} epaper_ui_page_t;

bool epaper_ui_select_page(epaper_ui_page_t page);
bool epaper_ui_update(void);
bool epaper_ui_set_battery(uint8_t percent, bool known);
/* SAM | 2026-10-13 09:04 +08:00 | Bind a foreground snapshot because generated pages contain example data. */
bool epaper_ui_bind_status(const yp_business_status_t *status);
/* SAM | 2026-10-13 09:04 +08:00 | Gate EPD updates by actual page or business changes to limit power use. */
bool epaper_ui_needs_refresh(void);
void epaper_ui_invalidate_rendered(void);
void epaper_ui_mark_rendered(uint32_t revision);
void epaper_ui_poll(uint32_t now_ms);
bool epaper_ui_nav_pending(void);
void epaper_ui_nav_consumed(void);

#endif
