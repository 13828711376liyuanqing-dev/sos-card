#ifndef EPAPER_FTEST_H
#define EPAPER_FTEST_H
#include <stdbool.h>
#include <stdint.h>

bool epaper_ftest_active(void);
bool epaper_ftest_needs_redraw(void);
void epaper_ftest_enter(void);
void epaper_ftest_exit(void);
bool epaper_ftest_click(uint32_t left, uint32_t right);
struct _lv_obj_t *epaper_ftest_build(void);
bool epaper_ftest_poll(uint32_t now_ms);
#endif
