/* SAM | 2026-10-11 00:45 +08:00 | Load GUI Guider pages on demand
 * because keeping all six screens alive wastes the 24KB LVGL pool.
 * Labels and icons retain the supplied template data; business binding
 * is deliberately separate from importing the designer's six pages. */
#include "epaper_ui.h"
#if EPAPER_UI_FACTORY_TEST
#include "epaper_ftest.h"
#endif
#include "guider/gui_guider.h"
#include "../business/yp_name_glyphs.h"
#include <string.h>
#include <stdio.h>
#ifndef EPAPER_UI_HOST_TEST
#include "cli.h"
#endif

static lv_ui s_ui;
/* SAM | 2026-10-13 09:04 +08:00 | Start on resident home because IMEI is a requested information page. */
static epaper_ui_page_t s_requested = EPAPER_UI_SCREEN;
static epaper_ui_page_t s_loaded = EPAPER_UI_PAGE_COUNT;
static bool s_loaded_ftest;
static epaper_ui_page_t s_effective = EPAPER_UI_MAIN;
static bool s_boot_default_promoted;
static uint32_t s_last_interaction_ms;
static bool s_nav_pending;
static lv_obj_t *s_main_status;
static lv_obj_t *s_network_status;
static lv_obj_t *s_notice;
static lv_obj_t *s_imei_qr;
/* SAM | 2026-10-13 09:04 +08:00 | Keep call end visible briefly, then release navigation and alarm priority. */
static yp_call_t s_last_call = YP_CALL_IDLE;
static uint32_t s_call_end_started_ms;
static yp_call_t s_last_call_state = YP_CALL_UNKNOWN;
static bool s_last_alarm_active;
static uint32_t s_rendered_revision;
static bool s_has_rendered_revision;
static epaper_ui_page_t effective_page(const yp_business_status_t *status);

/* SAM | 2026-10-13 09:04 +08:00 | Reject unsupported glyphs because the exported Chinese fonts cover a fixed subset. */
static const char *safe_text(const lv_font_t *font, const char *value)
{
    uint32_t offset = 0;
    if (value == NULL || value[0] == '\0') return "--";
    while (value[offset] != '\0') {
        lv_font_glyph_dsc_t glyph;
        uint32_t codepoint = _lv_txt_encoded_next(value, &offset);
        if (codepoint == 0 || !font->get_glyph_dsc(font, &glyph, codepoint, 0) ||
            glyph.is_placeholder) return "--";
    }
    return value;
}

static void set_label(lv_obj_t *label, const char *value)
{
    if (label != NULL && strcmp(lv_label_get_text(label), value) != 0)
        lv_label_set_text(label, value);
}

/* SAM | 2026-11-02 +08:00 | Name fonts: platform-pushed RAM glyphs first, then the built-in font_cn_16/32 through the
 * LVGL fallback chain; a glyph neither has is drawn as the LVGL placeholder box instead of hiding the whole name. */
static bool name_glyph_dsc(const lv_font_t *font, lv_font_glyph_dsc_t *dsc, uint32_t letter, uint32_t next)
{
    const yp_ng_t *g = yp_ng_find(letter, (uint8_t)(uintptr_t)font->dsc, NULL);
    (void)next;
    if (g == NULL) return false;
    dsc->adv_w = (uint16_t)((g->adv_w + 8U) >> 4);
    dsc->box_w = g->w; dsc->box_h = g->h; dsc->ofs_x = g->x; dsc->ofs_y = g->y;
    dsc->bpp = 1; dsc->is_placeholder = false;
    return true;
}
static const uint8_t *name_glyph_bitmap(const lv_font_t *font, uint32_t letter)
{
    const uint8_t *bitmap = NULL;
    return yp_ng_find(letter, (uint8_t)(uintptr_t)font->dsc, &bitmap) ? bitmap : NULL;
}
static lv_font_t s_name_font_16 = {.get_glyph_dsc = name_glyph_dsc, .get_glyph_bitmap = name_glyph_bitmap,
                                   .dsc = (const void *)16, .fallback = &font_cn_16};
static lv_font_t s_name_font_32 = {.get_glyph_dsc = name_glyph_dsc, .get_glyph_bitmap = name_glyph_bitmap,
                                   .dsc = (const void *)32, .fallback = &font_cn_32};
static uint32_t s_name_generation;
static uint32_t s_need_check_ms, s_need_sent_ms;
static bool s_need_sent;

static void name_fonts_init(void)
{
    if (s_name_font_32.line_height) return;
    s_name_font_16.line_height = font_cn_16.line_height; s_name_font_16.base_line = font_cn_16.base_line;
    s_name_font_32.line_height = font_cn_32.line_height; s_name_font_32.base_line = font_cn_32.base_line;
}

/* Code points of `value` that neither size can draw; returns the count (at most `max`). */
static unsigned name_missing(const char *value, uint32_t *out, unsigned max, bool both_sizes)
{
    uint32_t offset = 0;
    unsigned n = 0;
    name_fonts_init();
    while (value != NULL && value[offset] != '\0' && n < max) {
        lv_font_glyph_dsc_t g16, g32;
        uint32_t cp = _lv_txt_encoded_next(value, &offset);
        if (cp == 0) break;
        bool ok = lv_font_get_glyph_dsc(&s_name_font_16, &g16, cp, 0) && !g16.is_placeholder &&
                  (!both_sizes || (lv_font_get_glyph_dsc(&s_name_font_32, &g32, cp, 0) && !g32.is_placeholder));
        if (!ok) {
            unsigned i = 0;
            while (i < n && out[i] != cp) ++i;
            if (i == n) out[n++] = cp;
        }
    }
    return n;
}

static const char *name_text(const char *value)
{
    return value == NULL || value[0] == '\0' ? "--" : value;
}

static bool valid_imei(const yp_business_status_t *status)
{
    if (!status->imei_known) return false;
    for (unsigned i = 0; i < 15U; ++i)
        if (status->imei[i] < '0' || status->imei[i] > '9') return false;
    return status->imei[15] == '\0';
}

/* SAM | 2026-10-13 09:04 +08:00 | Give active calls and alarms priority because preview must not mask emergencies. */

static epaper_ui_page_t ui_home(const yp_business_status_t *status)
{
    if (!status->resident_known) return EPAPER_UI_SCREEN;
    if (status->battery_known && status->battery_percent < 20U) return EPAPER_UI_LOWBAT;
    return EPAPER_UI_MAIN;
}

static epaper_ui_page_t ui_apply_chord(epaper_ui_page_t cur, const char *seq)
{
    if (seq == NULL) return EPAPER_UI_PAGE_COUNT;
    if (cur == EPAPER_UI_SCREEN) {
        if (strcmp(seq, "LLL") == 0) return EPAPER_UI_MAIN;
    } else if (cur == EPAPER_UI_TIME) {
        if (strcmp(seq, "L") == 0) return EPAPER_UI_MAIN;
        else if (strcmp(seq, "RRR") == 0) return EPAPER_UI_SCREEN;
    } else if (cur == EPAPER_UI_LOWBAT) {
        if (strcmp(seq, "R") == 0) return EPAPER_UI_MAIN;
    } else {
        if (strcmp(seq, "R") == 0) return EPAPER_UI_TIME;
        else if (strcmp(seq, "RRR") == 0) return EPAPER_UI_SCREEN;
    }
    return EPAPER_UI_PAGE_COUNT; /* no-op */
}

bool epaper_ui_nav_pending(void)
{
    return s_nav_pending;
}
void epaper_ui_nav_consumed(void)
{
    s_nav_pending = false;
}

void epaper_ui_poll(uint32_t now_ms)
{
    const yp_business_status_t *status = yp_business_status();
    char seq[YP_KEY_BUF_SIZE + 1];
    if (status == NULL) return;

    /* Reset the boot-promotion latch whenever the device is unbound. */
    if (!status->resident_known) {
        s_boot_default_promoted = false;
    } else if (!s_boot_default_promoted) {
        /* First detection of a binding: boot to the battery-decided home. */
        s_boot_default_promoted = true;
        s_requested = ui_home(status);
        s_nav_pending = true;
    }

    if (yp_business_take_sequence(seq, sizeof(seq))) {
        s_last_interaction_ms = now_ms;
#if EPAPER_UI_FACTORY_TEST
        if (epaper_ftest_active()) {
            uint32_t left = 0, right = 0;
            for (const char *p = seq; *p != '\0'; ++p) {
                if (*p == 'L') ++left;
                else if (*p == 'R') ++right;
            }
            if (epaper_ftest_click(left, right)) s_nav_pending = true;
        } else if (strcmp(seq, "LRLR") == 0 &&
                   effective_page(status) == EPAPER_UI_SCREEN) {
            epaper_ftest_enter();
            s_nav_pending = true;
        } else if (status->resident_known) {
            epaper_ui_page_t target = ui_apply_chord(effective_page(status), seq);
            if (target != EPAPER_UI_PAGE_COUNT && target != s_requested) {
                s_requested = target;
                s_nav_pending = true;
            }
        }
#else
        if (status->resident_known) {
            epaper_ui_page_t target = ui_apply_chord(effective_page(status), seq);
            if (target != EPAPER_UI_PAGE_COUNT && target != s_requested) {
                s_requested = target;
                s_nav_pending = true;
            }
        }
#endif	
    }
#if EPAPER_UI_FACTORY_TEST
    if (epaper_ftest_active()) {
        if (epaper_ftest_poll(now_ms)) s_nav_pending = true;
        return;
    }
#endif
    /* SAM | 2026-11-02 +08:00 | Glyphs are RAM-only: after reboot ask CAT1 for the missing ones, at most every 10 min. */
    if (status->resident_known && status->transport_ready &&
        (uint32_t)(now_ms - s_need_check_ms) >= 5000U &&
        (!s_need_sent || (uint32_t)(now_ms - s_need_sent_ms) >= 600000U)) {
        uint32_t missing[8];
        unsigned n = name_missing(status->name, missing, 8U, true);
        n += name_missing(status->campus, missing + n, 8U - n, false);
        s_need_check_ms = now_ms;
        if (n != 0U && yp_business_request_glyphs(missing, n)) {
            s_need_sent = true;
            s_need_sent_ms = now_ms;
        }
    }

    /* 30s without any click interaction falls back to the current home. */
    if (status->resident_known &&
        (uint32_t)(now_ms - s_last_interaction_ms) >= 30000U) {
        epaper_ui_page_t home = ui_home(status);
        if (s_requested != home) {
            s_requested = home;
            s_nav_pending = true;
        }
    }

    if (status->call != s_last_call_state) {
        s_last_call_state = status->call;
        s_nav_pending = true;
    }
    if (status->alarm_active != s_last_alarm_active) {
        if (!status->alarm_active) s_call_end_started_ms = status->now_ms;
        s_nav_pending = true;
    }
    s_last_alarm_active = status->alarm_active;
}

static epaper_ui_page_t effective_page(const yp_business_status_t *status)
{
    if (!status->resident_known) return EPAPER_UI_SCREEN;
    if (status->call != s_last_call) {
        if (status->call == YP_CALL_ENDED || status->call == YP_CALL_FAILED)
            s_call_end_started_ms = status->now_ms;
        s_last_call = status->call;
    }
    if (status->call == YP_CALL_DIALING || status->call == YP_CALL_INCOMING ||
        status->call == YP_CALL_CONNECTED) return EPAPER_UI_CALLING;
    if (status->alarm_active) return EPAPER_UI_CALLING;
    if ((status->call == YP_CALL_ENDED || status->call == YP_CALL_FAILED) &&
        (uint32_t)(status->now_ms - s_call_end_started_ms) < 3000U)
        return EPAPER_UI_CALLEND;
    if (s_requested == EPAPER_UI_TIME && !status->show_time)
        return EPAPER_UI_MAIN;
    return s_requested;
}

bool epaper_ui_needs_refresh(void)
{
    const yp_business_status_t *status = yp_business_status();
    if (status == NULL) return false;
#if EPAPER_UI_FACTORY_TEST
    if (epaper_ftest_active())
        return !s_loaded_ftest || epaper_ftest_needs_redraw();
#endif
    return !s_has_rendered_revision || status->revision != s_rendered_revision ||
           effective_page(status) != s_loaded;
}

void epaper_ui_invalidate_rendered(void)
{
    /* SAM | 2026-10-13 09:04 +08:00 | Keep a failed EPD flush eligible for retry. */
    s_has_rendered_revision = false;
}

void epaper_ui_mark_rendered(uint32_t revision)
{
    s_rendered_revision = revision;
    s_has_rendered_revision = true;
}

/* SAM | 2026-10-12 16:05 +08:00 | Keep the GUI Guider battery image object
 * and vary only its same-size bitmap, because adding a second progress widget
 * changes the approved screen layout. */
static const uint8_t s_battery_maps[5][38] = {
    {0xff,0xff,0xff,0xff,0x00,0x00,0x00,0xff,0x7f,0xff,0x80,0x40,0x00,0x80,0x40,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0x80,0x7f,0xff,0x80},
    {0xff,0xff,0xff,0xff,0x00,0x00,0x00,0xff,0x7f,0xff,0x80,0x40,0x00,0x80,0x40,0x00,0xb0,0x78,0x00,0xb0,0x78,0x00,0xb0,0x78,0x00,0xb0,0x78,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0x80,0x7f,0xff,0x80},
    {0xff,0xff,0xff,0xff,0x00,0x00,0x00,0xff,0x7f,0xff,0x80,0x40,0x00,0x80,0x40,0x00,0xb0,0x7f,0x00,0xb0,0x7f,0x00,0xb0,0x7f,0x00,0xb0,0x7f,0x00,0xb0,0x40,0x00,0xb0,0x40,0x00,0x80,0x7f,0xff,0x80},
    {0xff,0xff,0xff,0xff,0x00,0x00,0x00,0xff,0x7f,0xff,0x80,0x40,0x00,0x80,0x40,0x00,0xb0,0x7f,0xe0,0xb0,0x7f,0xe0,0xb0,0x7f,0xe0,0xb0,0x7f,0xe0,0xb0,0x40,0x00,0xb0,0x40,0x00,0x80,0x7f,0xff,0x80},
    {0xff,0xff,0xff,0xff,0x00,0x00,0x00,0xff,0x7f,0xff,0x80,0x40,0x00,0x80,0x40,0x00,0xb0,0x7f,0xfc,0xb0,0x7f,0xfc,0xb0,0x7f,0xfc,0xb0,0x7f,0xfc,0xb0,0x40,0x00,0xb0,0x40,0x00,0x80,0x7f,0xff,0x80}
};
static lv_img_dsc_t s_battery_desc[5] = {
    {.header.cf=LV_IMG_CF_INDEXED_1BIT,.header.w=20,.header.h=10,.data_size=38,.data=s_battery_maps[0]},
    {.header.cf=LV_IMG_CF_INDEXED_1BIT,.header.w=20,.header.h=10,.data_size=38,.data=s_battery_maps[1]},
    {.header.cf=LV_IMG_CF_INDEXED_1BIT,.header.w=20,.header.h=10,.data_size=38,.data=s_battery_maps[2]},
    {.header.cf=LV_IMG_CF_INDEXED_1BIT,.header.w=20,.header.h=10,.data_size=38,.data=s_battery_maps[3]},
    {.header.cf=LV_IMG_CF_INDEXED_1BIT,.header.w=20,.header.h=10,.data_size=38,.data=s_battery_maps[4]}
};

bool epaper_ui_select_page(epaper_ui_page_t page)
{
    if ((unsigned)page >= EPAPER_UI_PAGE_COUNT) return false;
    s_requested = page;
    return true;
}

bool epaper_ui_update(void)
{
    lv_obj_t *screen = NULL;
    lv_obj_t *old;
    if (lv_disp_get_default() == NULL) return false;
#if EPAPER_UI_FACTORY_TEST
    if (epaper_ftest_active()) {
        if (s_loaded_ftest) return true;
        old = lv_scr_act();
        screen = epaper_ftest_build();
        if (screen == NULL) return false;
        lv_scr_load(screen);
        if (old != screen) lv_obj_del(old);
        s_loaded_ftest = true;
        s_loaded = EPAPER_UI_PAGE_COUNT; /* not a regular page */
        return true;
    }
#endif
    s_loaded_ftest = false;
    if (s_loaded == s_effective) return true;
    old = lv_scr_act();
    memset(&s_ui, 0, sizeof(s_ui));
    s_main_status = NULL;
    s_network_status = NULL;
    s_notice = NULL;
    s_imei_qr = NULL;
    switch (s_effective) {
    case EPAPER_UI_SCREEN:  setup_scr_screen(&s_ui);         screen = s_ui.screen;         break;
    case EPAPER_UI_MAIN:    setup_scr_screen_main(&s_ui);    screen = s_ui.screen_main;    break;
    case EPAPER_UI_TIME:    setup_scr_screen_time(&s_ui);    screen = s_ui.screen_time;    break;
    case EPAPER_UI_LOWBAT:  setup_scr_screen_lowbat(&s_ui);  screen = s_ui.screen_lowbat;  break;
    case EPAPER_UI_CALLING: setup_scr_screen_calling(&s_ui); screen = s_ui.screen_calling; break;
    case EPAPER_UI_CALLEND: setup_scr_screen_callend(&s_ui); screen = s_ui.screen_callend; break;
    default: return false;
    }
    if (screen == NULL) return false;
    /* SAM | 2026-10-13 09:04 +08:00 | Keep a compact actual battery/network/arrears line within the main layout. */
    name_fonts_init();
    if (s_effective == EPAPER_UI_MAIN) {
        lv_obj_set_style_text_font(s_ui.screen_main_label_name, &s_name_font_32, LV_PART_MAIN | LV_STATE_DEFAULT);
        lv_obj_set_style_text_font(s_ui.screen_main_label_campus, &s_name_font_16, LV_PART_MAIN | LV_STATE_DEFAULT);
    }
    if (s_effective == EPAPER_UI_LOWBAT)
        lv_obj_set_style_text_font(s_ui.screen_lowbat_label_info, &s_name_font_16, LV_PART_MAIN | LV_STATE_DEFAULT);
    if (s_effective == EPAPER_UI_MAIN) {
        s_main_status = lv_label_create(screen);
        lv_obj_set_pos(s_main_status, 10, 1);
        lv_obj_set_size(s_main_status, 180, 34);
        lv_label_set_long_mode(s_main_status, LV_LABEL_LONG_WRAP);
        lv_obj_set_style_text_font(s_main_status, &font_cn_16, 0);
        lv_obj_set_style_text_align(s_main_status, LV_TEXT_ALIGN_CENTER, 0);
        /* SAM | 2026-10-13 09:04 +08:00 | Show network state independently of arrears so offline is never presented as unpaid. */
        s_network_status = lv_label_create(screen);
        lv_obj_set_pos(s_network_status, 10, 178);
        lv_obj_set_size(s_network_status, 180, 20);
        lv_obj_set_style_text_font(s_network_status, &font_cn_16, 0);
        lv_obj_set_style_text_align(s_network_status, LV_TEXT_ALIGN_CENTER, 0);
    }
    /* SAM | 2026-10-13 09:04 +08:00 | Replace the fixed QR artwork with an IMEI canvas and four-module white margin. */
    if (s_effective == EPAPER_UI_SCREEN) {
        lv_obj_add_flag(s_ui.screen_img_1, LV_OBJ_FLAG_HIDDEN);
        s_imei_qr = lv_qrcode_create(screen, 108, lv_color_black(), lv_color_white());
        if (s_imei_qr != NULL) {
            lv_obj_set_pos(s_imei_qr, 46, 88);
            lv_obj_add_flag(s_imei_qr, LV_OBJ_FLAG_HIDDEN);
        }
    }
    /* SAM | 2026-10-11 00:45 +08:00 | Use an opaque white root because
     * the exported transparent root can expose the previous EPD page. */
    lv_obj_set_style_bg_color(screen, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_scr_load(screen);
    if (old != screen) lv_obj_del(old);
    s_loaded = s_effective;
    return true;
}

/* SAM | 2026-10-12 16:47 +08:00 | Bind validated SOC to all four existing
 * battery images because the low-battery page still showed a fixed bitmap. */
bool epaper_ui_set_battery(uint8_t percent, bool known)
{
    lv_obj_t *image = NULL;
    if (s_loaded == EPAPER_UI_SCREEN) image = s_ui.screen_img_bat;
    else if (s_loaded == EPAPER_UI_MAIN) image = s_ui.screen_main_img_bat;
    else if (s_loaded == EPAPER_UI_TIME) image = s_ui.screen_time_img_bat;
    else if (s_loaded == EPAPER_UI_LOWBAT) image = s_ui.screen_lowbat_img_bat;
    if (image == NULL) return false;
    if (percent > 100U) percent = 100U;
    /* SAM | 2026-10-13 09:04 +08:00 | Hide an unknown SOC icon because fixed full/low artwork misstates battery state. */
    if (!known) {
        lv_obj_add_flag(image, LV_OBJ_FLAG_HIDDEN);
        return true;
    }
    lv_obj_clear_flag(image, LV_OBJ_FLAG_HIDDEN);
    {
        uint8_t level = (uint8_t)((percent + 12U) / 25U);
        if (level > 4U) level = 4U;
        lv_img_set_src(image, &s_battery_desc[level]);
    }
    lv_obj_invalidate(image);
    return true;
}

/* SAM | 2026-10-13 09:04 +08:00 | Replace every example field with validated live state on the display polling thread. */
bool epaper_ui_bind_status(const yp_business_status_t *status)
{
    char line[128];
    if (status == NULL) return false;
    s_effective = effective_page(status);
    if (!epaper_ui_update()) return false;
    (void)epaper_ui_set_battery(status->battery_percent, status->battery_known);
    switch (s_loaded) {
    case EPAPER_UI_SCREEN:
        set_label(s_ui.screen_label_imei, valid_imei(status) ? status->imei : "--");
        if (s_imei_qr != NULL && valid_imei(status) &&
            lv_qrcode_update(s_imei_qr, status->imei, 15U) == LV_RES_OK)
            lv_obj_clear_flag(s_imei_qr, LV_OBJ_FLAG_HIDDEN);
        else if (s_imei_qr != NULL)
            lv_obj_add_flag(s_imei_qr, LV_OBJ_FLAG_HIDDEN);
        break;
    case EPAPER_UI_MAIN:
        /* SAM | 2026-11-02 +08:00 | Name uses the pushed-glyph font; force a redraw when only the glyph set changed. */
        if (s_name_generation != yp_ng_generation()) lv_label_set_text(s_ui.screen_main_label_name, "");
        set_label(s_ui.screen_main_label_name, status->resident_known ? name_text(status->name) : "--");
        set_label(s_ui.screen_main_label_room,
                  status->resident_known ? safe_text(&font_cn_28, status->room) : "--");
        /* SAM | 2026-11-03 +08:00 | Campus changes per site, so it uses the pushed 16px glyphs too (built-in font as fallback). */
        if (s_name_generation != yp_ng_generation()) lv_label_set_text(s_ui.screen_main_label_campus, "");
        set_label(s_ui.screen_main_label_campus, status->resident_known ? name_text(status->campus) : "--");
        (void)snprintf(line, sizeof(line), "B:-- S:--\nFEE:%s",
                       status->arrears_known ? (status->arrears ? "DUE" : "OK") : "--");
        if (status->battery_known && status->signal_known)
            (void)snprintf(line, sizeof(line), "B:%u%% S:%u\nFEE:%s",
                           status->battery_percent, status->signal,
                           status->arrears_known ? (status->arrears ? "DUE" : "OK") : "--");
        else if (status->battery_known)
            (void)snprintf(line, sizeof(line), "B:%u%% S:--\nFEE:%s",
                           status->battery_percent,
                           status->arrears_known ? (status->arrears ? "DUE" : "OK") : "--");
        else if (status->signal_known)
            (void)snprintf(line, sizeof(line), "B:-- S:%u\nFEE:%s",
                           status->signal,
                           status->arrears_known ? (status->arrears ? "DUE" : "OK") : "--");
        set_label(s_main_status, line);
        switch (status->network) {
        case YP_NET_NO_SIM: set_label(s_network_status, "NET:NO SIM"); break;
        case YP_NET_REGISTERING: set_label(s_network_status, "NET:WAIT"); break;
        case YP_NET_IP: set_label(s_network_status, "NET:IP"); break;
        case YP_NET_MQTT: set_label(s_network_status, "NET:MQTT"); break;
        case YP_NET_OFFLINE: set_label(s_network_status, "NET:OFFLINE"); break;
        default: set_label(s_network_status, "NET:--"); break;
        }
        break;
    case EPAPER_UI_TIME:
        set_label(s_ui.screen_time_label_time,
                  status->time_known ? safe_text(&font_cn_40, status->clock) : "--:--");
        set_label(s_ui.screen_time_label_date,
                  status->time_known ? safe_text(&font_cn_24, status->date) : "--");
        set_label(s_ui.screen_time_label_week,
                  status->time_known ? safe_text(&font_cn_24, status->weekday) : "--");
        break;
    case EPAPER_UI_LOWBAT:
        set_label(s_ui.screen_lowbat_label_lowdate,
                  status->show_time && status->time_known ? safe_text(&font_cn_16, status->date) : "");
        (void)snprintf(line, sizeof(line), "%s %s",
                       status->resident_known ? name_text(status->name) : "--",
                       status->resident_known ? safe_text(&font_cn_16, status->room) : "--");
        if (s_name_generation != yp_ng_generation()) lv_label_set_text(s_ui.screen_lowbat_label_info, "");
        set_label(s_ui.screen_lowbat_label_info, line);
        break;
    case EPAPER_UI_CALLING:
        if (status->call == YP_CALL_CONNECTED) {
            if (lv_img_get_src(s_ui.screen_calling_img_sos) !=
                (const void *)&_icon_call_connected_alpha_200x200) {
                lv_img_set_src(s_ui.screen_calling_img_sos,
                               &_icon_call_connected_alpha_200x200);
                lv_obj_invalidate(s_ui.screen_calling_img_sos);
            }
        } else {
            if (lv_img_get_src(s_ui.screen_calling_img_sos) !=
                (const void *)&_icon_sos_alpha_200x200) {
                lv_img_set_src(s_ui.screen_calling_img_sos,
                               &_icon_sos_alpha_200x200);
                lv_obj_invalidate(s_ui.screen_calling_img_sos);
            }
        }
        break;
    case EPAPER_UI_CALLEND:
        break;
    default: break;
    }
    if (s_loaded == EPAPER_UI_MAIN || s_loaded == EPAPER_UI_LOWBAT) s_name_generation = yp_ng_generation();
    return true;
}

#ifndef EPAPER_UI_HOST_TEST
/* SAM | 2026-10-11 00:45 +08:00 | Expose all six pages for board
 * acceptance without adding touch, timers or fictitious call events. */
static int cmd_epd_page(int argc, char *argv[])
{
    static const char *const names[EPAPER_UI_PAGE_COUNT] = {
        "screen", "screen_main", "screen_time", "screen_lowbat",
        "screen_calling", "screen_callend"
    };
    if (argc == 2) {
        for (unsigned i = 0; i < EPAPER_UI_PAGE_COUNT; ++i) {
            if (strcmp(argv[1], names[i]) == 0) {
                (void)epaper_ui_select_page((epaper_ui_page_t)i);
                cli_printf("[GUI] queued %s; live business state may take priority\r\n", names[i]);
                return 0;
            }
        }
    }
    cli_printf("Usage: epd_page <screen|screen_main|screen_time|screen_lowbat|screen_calling|screen_callend>\r\n");
    return -1;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("epd_page", "Preview GUI page", cmd_epd_page);
#endif

#if EPAPER_UI_FACTORY_TEST
static int cmd_epd_ftest(int argc, char *argv[])
{
    (void)argc; (void)argv;
    epaper_ftest_enter();
    cli_printf("[GUI] factory test queued; refresh on next poll\r\n");
    return 0;
}
CLI_CMD_REGISTER("epd_ftest", "Enter factory test screen", cmd_epd_ftest);
#endif
