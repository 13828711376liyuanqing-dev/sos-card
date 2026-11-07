/* SAM | 2026-10-11 00:45 +08:00 | Import YP001 GUI Guider assets because the six-page UI replaces the old runtime page. */
#if defined(LV_LVGL_H_INCLUDE_SIMPLE)
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif


#ifndef LV_ATTRIBUTE_MEM_ALIGN
#define LV_ATTRIBUTE_MEM_ALIGN
#endif

#ifndef LV_ATTRIBUTE_IMG__BATTERY_4_ALPHA_20X10
#define LV_ATTRIBUTE_IMG__BATTERY_4_ALPHA_20X10
#endif

const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_IMG__BATTERY_4_ALPHA_20X10 uint8_t _battery_4_alpha_20x10_map[] = {
  0xff, 0xff, 0xff, 0xff, 	/*Color of index 0*/
  0x00, 0x00, 0x00, 0xff, 	/*Color of index 1*/

  0xff, 0xff, 0xc0, 
  0x80, 0x00, 0x40, 
  0xbb, 0xbb, 0xc0, 
  0xbb, 0xbb, 0xf0, 
  0xbb, 0xbb, 0xf0, 
  0xbb, 0xbb, 0xf0, 
  0xbb, 0xbb, 0xf0, 
  0xbb, 0xbb, 0xc0, 
  0xbb, 0xbb, 0xc0, 
  0xff, 0xff, 0xc0, 
};

const lv_img_dsc_t _battery_4_alpha_20x10 = {
  .header.cf = LV_IMG_CF_INDEXED_1BIT,
  .header.always_zero = 0,
  .header.reserved = 0,
  .header.w = 20,
  .header.h = 10,
  .data_size = 38,
  .data = _battery_4_alpha_20x10_map,
};
