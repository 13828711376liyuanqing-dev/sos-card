/* 摘录自 ble_app_uart_c/Src/user/gui/epaper_ui.c（姓名/园区动态字体，参考用，以项目源码为准） */

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
