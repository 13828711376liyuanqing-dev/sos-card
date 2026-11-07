#include "epaper_lvgl.h"
/* SAM | 2026-10-11 00:45 +08:00 | Delegate page objects to GUI Guider
 * because the driver and flush must retain their validated behavior. */
#include "epaper_ui.h"
#include "business/yp001_business.h"

#include <string.h>

#include "lvgl.h"
#include "app_log.h"
#include "epaper_depg0150.h"
#include "yp001_psram_mem.h"

#define EPD_WIDTH 200
#define EPD_HEIGHT 200
#define EPD_STRIDE 25
#define EPD_DRAW_LINES 16

static lv_color_t s_draw_pixels[EPD_WIDTH * EPD_DRAW_LINES];
static lv_disp_draw_buf_t s_draw_buf;
static lv_disp_drv_t s_disp_drv;
static uint8_t *s_frame;
static bool s_ready;
static bool s_flush_ok;
#define DISPLAY_ROTATION_SUPPORT 1

#if DISPLAY_ROTATION_SUPPORT
static uint8_t * s_rotate_frame;

// 读 (x,y)，MSB在前：bit7对应x%8==0
static inline uint8_t fb_get_bit(const uint8_t *src, int x, int y)
{
    int byte_idx = y * 25 + (x / 8);
    int bit_pos  = 7 - (x % 8);
    return (src[byte_idx] >> bit_pos) & 1U;
}

// 写 (x,y)，MSB在前
static inline void fb_set_bit(uint8_t *dst, int x, int y, uint8_t val)
{
    int byte_idx = y * 25 + (x / 8);
    int bit_pos  = 7 - (x % 8);
    if(val)
        dst[byte_idx] |= (1U << bit_pos);
    else
        dst[byte_idx] &= ~(1U << bit_pos);
}

static void fb_rotate90_ccw_msb(const uint8_t *src, uint8_t *dst)
{
    int x, y;
    memset(dst, 0, EPD_WIDTH * EPD_HEIGHT / 8);

    for (y = 0; y < EPD_HEIGHT; y++)
    {
        for (x = 0; x < EPD_WIDTH; x++)
        {
            uint8_t pix = fb_get_bit(src, x, y);
            int nx = EPD_HEIGHT-1 - y;
            int ny = x;
            fb_set_bit(dst, nx, ny, pix);
        }
    }
}

#endif


uint8_t * get_rotated_fb(const uint8_t *src,int degree)
{
	#if DISPLAY_ROTATION_SUPPORT
	if(degree == 0)return src;
	if (s_rotate_frame == NULL) {
        s_rotate_frame = (uint8_t *)yp_psram_alloc(EPAPER_HOME_FRAME_BYTES);
        if (s_rotate_frame == NULL) {
            APP_LOG_ERROR("EPD frame PSRAM alloc s_rotate_frame failed");
			return src;
        }
    }
	fb_rotate90_ccw_msb(src,s_rotate_frame);
	return s_rotate_frame;
	#else
	return src;
	#endif
}


static void epaper_flush(lv_disp_drv_t *drv, const lv_area_t *area,
                         lv_color_t *pixels)
{
    int32_t x, y;
    uint32_t index = 0;
	#if DISPLAY_ROTATION_SUPPORT
	if (s_frame == NULL || s_rotate_frame == NULL)
	#else
    if (s_frame == NULL )
	#endif
	{
        lv_disp_flush_ready(drv);
        return;
    }

    for (y = area->y1; y <= area->y2; ++y) {
        for (x = area->x1; x <= area->x2; ++x, ++index) {
            if (x >= 0 && x < EPD_WIDTH && y >= 0 && y < EPD_HEIGHT &&
                lv_color_brightness(pixels[index]) < 128U) {
                s_frame[(uint32_t)x * EPD_STRIDE + (uint32_t)y / 8U] &=
                    (uint8_t)~(0x80U >> ((uint32_t)y & 7U));
            }
        }
    }

    if (lv_disp_flush_is_last(drv)) {
		#if DISPLAY_ROTATION_SUPPORT
		fb_rotate90_ccw_msb(s_frame,s_rotate_frame);
        s_flush_ok = epaper_depg0150_display_frame(s_rotate_frame);
		#else
		s_flush_ok = epaper_depg0150_display_frame(s_frame);
		#endif
    }
    lv_disp_flush_ready(drv);
}

static void epaper_lvgl_init(void)
{
    lv_disp_t *disp;

    if (s_frame == NULL) {
        s_frame = (uint8_t *)yp_psram_alloc(EPAPER_HOME_FRAME_BYTES);
        if (s_frame == NULL) {
            APP_LOG_ERROR("EPD frame PSRAM alloc failed, display disabled");
        }
    }

	#if DISPLAY_ROTATION_SUPPORT
    if (s_rotate_frame == NULL) {
        s_rotate_frame = (uint8_t *)yp_psram_alloc(EPAPER_HOME_FRAME_BYTES);
        if (s_rotate_frame == NULL) {
            APP_LOG_ERROR("EPD frame PSRAM alloc s_rotate_frame failed, display disabled");
        }
    }
	#endif
	
    lv_init();
    lv_disp_draw_buf_init(&s_draw_buf, s_draw_pixels,
                          NULL, EPD_WIDTH * EPD_DRAW_LINES);
    lv_disp_drv_init(&s_disp_drv);
    s_disp_drv.hor_res = EPD_WIDTH;
    s_disp_drv.ver_res = EPD_HEIGHT;
    s_disp_drv.draw_buf = &s_draw_buf;
    s_disp_drv.flush_cb = epaper_flush;
    s_disp_drv.full_refresh = 1;
    disp = lv_disp_drv_register(&s_disp_drv);
    if (disp == NULL) return;

    lv_disp_set_theme(disp, lv_theme_mono_init(disp, false, &lv_font_montserrat_20));
    s_ready = true;
}

bool epaper_lvgl_show_home(const epaper_home_status_t *status)
{
    const yp_business_status_t *business;
    uint32_t rendered_revision;
    /* SAM | 2026-10-13 09:04 +08:00 | Bind foreground business state before flush because generated labels are samples. */
    if (status == NULL) return false;
    if (!s_ready) epaper_lvgl_init();
    business = yp_business_status();
    if (!s_ready || !epaper_ui_bind_status(business)) return false;
	#if DISPLAY_ROTATION_SUPPORT
	 if (s_frame == NULL || s_rotate_frame==NULL) return false;   /* PSRAM frame unavailable */
	#else
    if (s_frame == NULL) return false;   /* PSRAM frame unavailable */
	#endif
    /* SAM | 2026-10-13 09:04 +08:00 | Snapshot before blocking BUSY waits because service may advance state during flush. */
    rendered_revision = business->revision;

    memset(s_frame, 0xff, EPAPER_HOME_FRAME_BYTES);
	#if DISPLAY_ROTATION_SUPPORT
	memset(s_rotate_frame, 0xff, EPAPER_HOME_FRAME_BYTES);
	#endif
    s_flush_ok = false;
    /* SAM | 2026-10-13 09:04 +08:00 | Mark the frame pending until the physical display call succeeds. */
    epaper_ui_invalidate_rendered();
    lv_obj_invalidate(lv_scr_act());
    lv_refr_now(NULL);
    if (s_flush_ok) epaper_ui_mark_rendered(rendered_revision);
    return s_flush_ok;
}
