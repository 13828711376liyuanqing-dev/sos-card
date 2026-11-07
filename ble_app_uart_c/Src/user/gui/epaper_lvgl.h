#ifndef EPAPER_LVGL_H
#define EPAPER_LVGL_H

#include <stdbool.h>
#include "epaper_home.h"

/* Render the current status with LVGL and refresh the 200 x 200 DEPG0150. */
bool epaper_lvgl_show_home(const epaper_home_status_t *status);
uint8_t * get_rotated_fb(const uint8_t *src,int degree);

#endif
