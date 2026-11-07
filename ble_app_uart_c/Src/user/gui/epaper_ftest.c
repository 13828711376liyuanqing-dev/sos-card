#if EPAPER_UI_FACTORY_TEST
#include "epaper_ftest.h"
#include "lvgl.h"
#include "guider/gui_guider.h"
#include "charger/yp001_charger.h"
#include "business/yp001_business.h"
#include "gsensor_probe.h"
#include "cli.h"
#include <string.h>
#include <stdio.h>

#define FT_ITEM_COUNT 3U
#define FT_ITEM_GSENSOR 2U


static const char *const ft_start_cmds[FT_ITEM_COUNT] = {
    "cat_diag SPEAKER_TEST_START", /* 1 Speaker */
    "cat_diag MIC_TEST_START",     /* 2 Microphone */
    NULL                           /* 3 G-Sensor */
};
static const char *const ft_stop_cmds[FT_ITEM_COUNT] = {
    "cat_diag SPEAKER_TEST_STOP",
    "cat_diag MIC_TEST_STOP",
    NULL
};
static void ft_tone(uint8_t item, bool start)
{
    const char *cmd = NULL;
    if (item < FT_ITEM_COUNT)
        cmd = start ? ft_start_cmds[item] : ft_stop_cmds[item];
    if (cmd != NULL) cli_execute_string(cmd);
}

typedef enum { PHASE_TEST = 0, PHASE_RESULT, PHASE_SHIP } phase_t;
typedef enum { SHIP_ASK = 0, SHIP_WAIT, SHIP_SENT, SHIP_FAIL } ship_sub_t;

static struct {
    bool active;
    bool redraw;
    phase_t phase;
    ship_sub_t ship_sub;
    uint8_t item;
    uint16_t fail_mask;
    uint32_t wait_start_ms;
    lv_obj_t *screen;
    lv_obj_t *title;
    lv_obj_t *hint;
    lv_obj_t *pass;
    lv_obj_t *fail;
} s;

static uint32_t s_xyz_ms;

bool epaper_ftest_needs_redraw(void)
{
    bool r = s.redraw;
    s.redraw = false;
    return r;
}

static const char *const ft_titles[FT_ITEM_COUNT] = {
    "1 Speaker", "2 Microphone", "3 G-Sensor"
};
static const char *const ft_hints[FT_ITEM_COUNT] = {
    "Hear the tone?",
    "Speak to mic.",
    "Reading..."
};
static const char *const ft_short[FT_ITEM_COUNT] = {
    "1 Speaker", "2 Microphone", "3 G-Sensor"
};

bool epaper_ftest_active(void) { return s.active; }

static void set_text(lv_obj_t *o, const char *t)
{
    if (o != NULL && strcmp(lv_label_get_text(o), t) != 0)
        lv_label_set_text(o, t);
}

static lv_obj_t *make_button(lv_obj_t *parent, int16_t x, int16_t y)
{
    lv_obj_t *b = lv_label_create(parent);
    lv_obj_set_pos(b, x, y);
    /* SAM | 2026-11-05 +08:00 | Larger 24px face for factory-line readability. */
    lv_obj_set_style_text_font(b, &font_cn_24, 0);
    lv_obj_set_style_border_color(b, lv_color_black(), 0);
    lv_obj_set_style_border_width(b, 1, 0);
    lv_obj_set_style_pad_left(b, 10, 0);
    lv_obj_set_style_pad_right(b, 10, 0);
    lv_obj_set_style_pad_top(b, 7, 0);
    lv_obj_set_style_pad_bottom(b, 7, 0);
    return b;
}

static void ft_show(void)
{
    char buf[128];
    if (s.title == NULL) return;
    lv_obj_set_style_text_align(s.hint,
        (s.phase == PHASE_RESULT) ? LV_TEXT_ALIGN_LEFT : LV_TEXT_ALIGN_CENTER, 0);
    if (s.phase == PHASE_TEST) {
        set_text(s.title, ft_titles[s.item]);
        set_text(s.hint, ft_hints[s.item]);
        lv_obj_clear_flag(s.pass, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s.fail, LV_OBJ_FLAG_HIDDEN);
        set_text(s.pass, "PASS");
        set_text(s.fail, "FAIL");
    } else if (s.phase == PHASE_RESULT) {
        size_t off = 0;
        buf[0] = '\0';
        for (uint8_t i = 0; i < FT_ITEM_COUNT; ++i) {
            if (s.fail_mask & (uint16_t)(1U << i)) {
                off += (size_t)snprintf(buf + off, sizeof(buf) - off,
                                        "%s\n", ft_short[i]);
            }
        }
        if (off == 0U) (void)snprintf(buf, sizeof(buf), "--");
        set_text(s.title, "FAILED ITEMS");
        set_text(s.hint, buf);
        lv_obj_clear_flag(s.pass, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s.fail, LV_OBJ_FLAG_HIDDEN);
        set_text(s.pass, "BACK");
    } else { /* PHASE_SHIP */
        set_text(s.title, "ALL PASSED");
        if (s.ship_sub == SHIP_ASK) {
            set_text(s.hint, "Ship mode?");
            lv_obj_clear_flag(s.pass, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s.fail, LV_OBJ_FLAG_HIDDEN);
            set_text(s.pass, "ENTER");
            set_text(s.fail, "EXIT");
        } else if (s.ship_sub == SHIP_WAIT) {
            set_text(s.hint, "Preparing...");
            lv_obj_add_flag(s.pass, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s.fail, LV_OBJ_FLAG_HIDDEN);
        } else if (s.ship_sub == SHIP_SENT) {
            set_text(s.hint, "Accepted.\nPower off.");
            lv_obj_add_flag(s.pass, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s.fail, LV_OBJ_FLAG_HIDDEN);
        } else {
            set_text(s.hint, "Failed.\nPlug 5V.");
            lv_obj_clear_flag(s.pass, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s.fail, LV_OBJ_FLAG_HIDDEN);
            set_text(s.pass, "BACK");
        }
    }
    s.redraw = true;
}

lv_obj_t *epaper_ftest_build(void)
{
    if (s.screen != NULL) return s.screen;
    s.screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s.screen, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(s.screen, LV_OPA_COVER, 0);

    s.title = lv_label_create(s.screen);
    lv_obj_set_pos(s.title, 5, 6);
    lv_obj_set_size(s.title, 190, 30);
    lv_obj_set_style_text_font(s.title, &font_cn_24, 0);
    lv_obj_set_style_text_align(s.title, LV_TEXT_ALIGN_CENTER, 0);

    s.hint = lv_label_create(s.screen);
    lv_obj_set_pos(s.hint, 5, 52);
    lv_obj_set_size(s.hint, 190, 88);
    lv_label_set_long_mode(s.hint, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_font(s.hint, &font_cn_24, 0);
    lv_obj_set_style_text_align(s.hint, LV_TEXT_ALIGN_CENTER, 0);

    s.pass = make_button(s.screen, 8, 148);
    s.fail = make_button(s.screen, 100, 148);
    ft_show();
    return s.screen;
}

void epaper_ftest_enter(void)
{
    if (s.active) return;
    s.active = true;
    s.redraw = true;
    s.phase = PHASE_TEST;
    s.ship_sub = SHIP_ASK;
    s.item = 0;
    s.fail_mask = 0;
    s.wait_start_ms = 0;
    s.screen = NULL;
    s.title = s.hint = s.pass = s.fail = NULL;
    ft_tone(0, true);
}

void epaper_ftest_exit(void)
{
    s.active = false;
    for (uint8_t i = 0; i < FT_ITEM_COUNT; ++i) ft_tone(i, false);
    s.screen = NULL;
    s.title = s.hint = s.pass = s.fail = NULL;
}

static void ft_finish(void)
{
    if (s.fail_mask != 0U) {
        s.phase = PHASE_RESULT;
    } else {
        s.phase = PHASE_SHIP;
        s.ship_sub = SHIP_ASK;
    }
}

bool epaper_ftest_click(uint32_t left, uint32_t right)
{
    if (!s.active) return false;
    bool changed = false;
    if (s.phase == PHASE_TEST) {
        bool pass_click = (left >= 1U);
        bool fail_click = (right >= 1U);
        if (fail_click) s.fail_mask |= (uint16_t)(1U << s.item);
        if (pass_click || fail_click) {
            ft_tone(s.item, false);
            if (s.item < (uint8_t)(FT_ITEM_COUNT - 1U)) {
                ++s.item;
                ft_tone(s.item, true);
            } else {
                ft_finish();
            }
            changed = true;
            s.redraw = true;
        }
    } else if (s.phase == PHASE_RESULT) {
        if (left >= 1U || right >= 1U) {
            epaper_ftest_exit();
            return true;
        }
    } else if (s.phase == PHASE_SHIP) {
        if (s.ship_sub == SHIP_ASK) {
            if (left >= 1U) {
                s.wait_start_ms = yp_business_status()->now_ms;
                if (yp001_charger_ship_prepare()) {
                    s.ship_sub = SHIP_WAIT;
                } else {
                    s.ship_sub = SHIP_FAIL;
                }
                changed = true;
                s.redraw = true;
            } else if (right >= 1U) {
                epaper_ftest_exit();
                return true;
            }
        } else if (s.ship_sub == SHIP_FAIL) {
            if (left >= 1U || right >= 1U) {
                epaper_ftest_exit();
                return true;
            }
        }
    }
    if (changed) ft_show();
    return changed;
}

bool epaper_ftest_poll(uint32_t now_ms)
{
    if (!s.active) return false;
    if (s.phase == PHASE_TEST && s.item == FT_ITEM_GSENSOR && s.hint != NULL) {
        if ((uint32_t)(now_ms - s_xyz_ms) >= 1000U) {
            s_xyz_ms = now_ms;
            int32_t xyz[3];
            char buf[64];
            if (gsensor_read_mg_fast(xyz)) {
                (void)snprintf(buf, sizeof(buf), "X %+ld\nY %+ld\nZ %+ld",
                               (long)xyz[0], (long)xyz[1], (long)xyz[2]);
            } else {
                (void)snprintf(buf, sizeof(buf), "XYZ read failed");
            }
            if (strcmp(lv_label_get_text(s.hint), buf) != 0) {
                lv_label_set_text(s.hint, buf);
                s.redraw = true;
                return true;
            }
        }
    }

    if (s.phase != PHASE_SHIP || s.ship_sub != SHIP_WAIT)
        return false;
    uint8_t ph = 0;
    uint32_t tok = 0;
    bool att = false;
    yp001_charger_ship_snapshot(&ph, &tok, &att);
    if (ph == 2U && tok != 0U) { /* READY */
        if (yp001_charger_ship_confirm(tok)) s.ship_sub = SHIP_SENT;
        else s.ship_sub = SHIP_FAIL;
        ft_show();
        return true;
    }
    if (ph == 4U) { /* FAILED */
        s.ship_sub = SHIP_FAIL;
        (void)yp001_charger_ship_cancel();
        ft_show();
        return true;
    }
    if ((uint32_t)(now_ms - s.wait_start_ms) > 35000U) {
        s.ship_sub = SHIP_FAIL;
        (void)yp001_charger_ship_cancel();
        ft_show();
        return true;
    }
    return false;
}
#endif
