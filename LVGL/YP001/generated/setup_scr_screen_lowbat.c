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



void setup_scr_screen_lowbat(lv_ui *ui)
{
    //Write codes screen_lowbat
    ui->screen_lowbat = lv_obj_create(NULL);
    lv_obj_set_size(ui->screen_lowbat, 200, 200);
    lv_obj_set_scrollbar_mode(ui->screen_lowbat, LV_SCROLLBAR_MODE_OFF);

    //Write style for screen_lowbat, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_bg_opa(ui->screen_lowbat, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_lowbat_label_lowdate
    ui->screen_lowbat_label_lowdate = lv_label_create(ui->screen_lowbat);
    lv_label_set_text(ui->screen_lowbat_label_lowdate, "2026-08-20 星期四");
    lv_label_set_long_mode(ui->screen_lowbat_label_lowdate, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_lowbat_label_lowdate, 10, 134);
    lv_obj_set_size(ui->screen_lowbat_label_lowdate, 180, 20);

    //Write style for screen_lowbat_label_lowdate, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_lowbat_label_lowdate, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_lowbat_label_lowdate, &lv_font_simhei_16, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_lowbat_label_lowdate, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_lowbat_label_lowdate, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_lowbat_label_lowdate, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_lowbat_label_info
    ui->screen_lowbat_label_info = lv_label_create(ui->screen_lowbat);
    lv_label_set_text(ui->screen_lowbat_label_info, "张秀芳 1#1-102·燕园");
    lv_label_set_long_mode(ui->screen_lowbat_label_info, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_lowbat_label_info, 10, 108);
    lv_obj_set_size(ui->screen_lowbat_label_info, 180, 20);

    //Write style for screen_lowbat_label_info, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_lowbat_label_info, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_lowbat_label_info, &lv_font_simhei_16, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_lowbat_label_info, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_lowbat_label_info, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_lowbat_label_info, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_lowbat_line_low
    ui->screen_lowbat_line_low = lv_label_create(ui->screen_lowbat);
    lv_label_set_text(ui->screen_lowbat_line_low, "");
    lv_label_set_long_mode(ui->screen_lowbat_line_low, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_lowbat_line_low, 20, 98);
    lv_obj_set_size(ui->screen_lowbat_line_low, 160, 2);

    //Write style for screen_lowbat_line_low, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_lowbat_line_low, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_lowbat_line_low, &lv_font_montserratMedium_16, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_lowbat_line_low, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_lowbat_line_low, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_lowbat_line_low, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_color(ui->screen_lowbat_line_low, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_grad_dir(ui->screen_lowbat_line_low, LV_GRAD_DIR_NONE, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_lowbat_line_low, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_lowbat_label_low2
    ui->screen_lowbat_label_low2 = lv_label_create(ui->screen_lowbat);
    lv_label_set_text(ui->screen_lowbat_label_low2, "请及时充电");
    lv_label_set_long_mode(ui->screen_lowbat_label_low2, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_lowbat_label_low2, 10, 62);
    lv_obj_set_size(ui->screen_lowbat_label_low2, 180, 30);

    //Write style for screen_lowbat_label_low2, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_lowbat_label_low2, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_lowbat_label_low2, &lv_font_simhei_24, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_lowbat_label_low2, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_lowbat_label_low2, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_lowbat_label_low2, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_lowbat_label_low1
    ui->screen_lowbat_label_low1 = lv_label_create(ui->screen_lowbat);
    lv_label_set_text(ui->screen_lowbat_label_low1, "当前电量低");
    lv_label_set_long_mode(ui->screen_lowbat_label_low1, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_lowbat_label_low1, 10, 30);
    lv_obj_set_size(ui->screen_lowbat_label_low1, 180, 30);

    //Write style for screen_lowbat_label_low1, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_lowbat_label_low1, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_lowbat_label_low1, &lv_font_simhei_24, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_lowbat_label_low1, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_lowbat_label_low1, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_lowbat_label_low1, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_lowbat_img_bat
    ui->screen_lowbat_img_bat = lv_img_create(ui->screen_lowbat);
    lv_obj_add_flag(ui->screen_lowbat_img_bat, LV_OBJ_FLAG_CLICKABLE);
    lv_img_set_src(ui->screen_lowbat_img_bat, &_battery_1_alpha_20x10);
    lv_img_set_pivot(ui->screen_lowbat_img_bat, 10,5);
    lv_img_set_angle(ui->screen_lowbat_img_bat, 0);
    lv_obj_set_pos(ui->screen_lowbat_img_bat, 90, 8);
    lv_obj_set_size(ui->screen_lowbat_img_bat, 20, 10);

    //Write style for screen_lowbat_img_bat, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_img_recolor_opa(ui->screen_lowbat_img_bat, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_img_opa(ui->screen_lowbat_img_bat, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_lowbat_img_bat, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_clip_corner(ui->screen_lowbat_img_bat, true, LV_PART_MAIN|LV_STATE_DEFAULT);

    //The custom code of screen_lowbat.


    //Update current screen layout.
    lv_obj_update_layout(ui->screen_lowbat);

}
