/* SAM | 2026-10-11 00:45 +08:00 | Import YP001 GUI Guider assets because the six-page UI replaces the old runtime page. */
/*
* Copyright 2026 NXP
* NXP Proprietary. This software is owned or controlled by NXP and may only be used strictly in
* accordance with the applicable license terms. By expressly accepting such terms or by downloading, installing,
* activating and/or otherwise using the software, you are agreeing that you have read, and that you agree to
* comply with and are bound by, such license terms.  If you do not agree to be bound by the applicable license
* terms, then you may not retain, install, activate or otherwise use the software.
*/

#include "lvgl.h"
#include <stdio.h>
#include "gui_guider.h"
#include "events_init.h"
#include "widgets_init.h"
#include "custom.h"



void setup_scr_screen_time(lv_ui *ui)
{
    //Write codes screen_time
    ui->screen_time = lv_obj_create(NULL);
    lv_obj_set_size(ui->screen_time, 200, 200);
    lv_obj_set_scrollbar_mode(ui->screen_time, LV_SCROLLBAR_MODE_OFF);

    //Write style for screen_time, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_bg_opa(ui->screen_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_time_label_week
    ui->screen_time_label_week = lv_label_create(ui->screen_time);
    lv_label_set_text(ui->screen_time_label_week, "星期四");
    lv_label_set_long_mode(ui->screen_time_label_week, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_time_label_week, 10, 140);
    lv_obj_set_size(ui->screen_time_label_week, 180, 28);

    //Write style for screen_time_label_week, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_time_label_week, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_time_label_week, &font_cn_24, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_time_label_week, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_time_label_week, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_time_label_week, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_time_label_date
    ui->screen_time_label_date = lv_label_create(ui->screen_time);
    lv_label_set_text(ui->screen_time_label_date, "2026-08-20");
    lv_label_set_long_mode(ui->screen_time_label_date, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_time_label_date, 10, 108);
    lv_obj_set_size(ui->screen_time_label_date, 180, 28);

    //Write style for screen_time_label_date, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_time_label_date, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_time_label_date, &font_cn_24, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_time_label_date, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_time_label_date, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_time_label_date, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_time_line_time
    ui->screen_time_line_time = lv_label_create(ui->screen_time);
    lv_label_set_text(ui->screen_time_line_time, "");
    lv_label_set_long_mode(ui->screen_time_line_time, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_time_line_time, 20, 96);
    lv_obj_set_size(ui->screen_time_line_time, 160, 2);

    //Write style for screen_time_line_time, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_time_line_time, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_time_line_time, &font_cn_16, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_time_line_time, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_time_line_time, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_time_line_time, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_color(ui->screen_time_line_time, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_grad_dir(ui->screen_time_line_time, LV_GRAD_DIR_NONE, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_time_line_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_time_label_time
    ui->screen_time_label_time = lv_label_create(ui->screen_time);
    lv_label_set_text(ui->screen_time_label_time, "14:30");
    lv_label_set_long_mode(ui->screen_time_label_time, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_time_label_time, 10, 38);
    lv_obj_set_size(ui->screen_time_label_time, 180, 48);

    //Write style for screen_time_label_time, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_time_label_time, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_time_label_time, &font_cn_40, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_time_label_time, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_time_label_time, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_time_label_time, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_time_img_bat
    ui->screen_time_img_bat = lv_img_create(ui->screen_time);
    lv_obj_add_flag(ui->screen_time_img_bat, LV_OBJ_FLAG_CLICKABLE);
    lv_img_set_src(ui->screen_time_img_bat, &_battery_4_alpha_20x10);
    lv_img_set_pivot(ui->screen_time_img_bat, 10,5);
    lv_img_set_angle(ui->screen_time_img_bat, 0);
    lv_obj_set_pos(ui->screen_time_img_bat, 170, 8);
    lv_obj_set_size(ui->screen_time_img_bat, 20, 10);

    //Write style for screen_time_img_bat, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_img_recolor_opa(ui->screen_time_img_bat, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_img_opa(ui->screen_time_img_bat, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_time_img_bat, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_clip_corner(ui->screen_time_img_bat, true, LV_PART_MAIN|LV_STATE_DEFAULT);

    //The custom code of screen_time.


    //Update current screen layout.
    lv_obj_update_layout(ui->screen_time);

}
