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



void setup_scr_screen_callend(lv_ui *ui)
{
    //Write codes screen_callend
    ui->screen_callend = lv_obj_create(NULL);
    lv_obj_set_size(ui->screen_callend, 200, 200);
    lv_obj_set_scrollbar_mode(ui->screen_callend, LV_SCROLLBAR_MODE_OFF);

    //Write style for screen_callend, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_bg_opa(ui->screen_callend, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_callend_label_end
    ui->screen_callend_label_end = lv_label_create(ui->screen_callend);
    lv_label_set_text(ui->screen_callend_label_end, "通话结束");
    lv_label_set_long_mode(ui->screen_callend_label_end, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_callend_label_end, 10, 118);
    lv_obj_set_size(ui->screen_callend_label_end, 180, 36);

    //Write style for screen_callend_label_end, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_callend_label_end, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_callend_label_end, &lv_font_simhei_24, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_callend_label_end, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_callend_label_end, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_callend_label_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_callend_img_end
    ui->screen_callend_img_end = lv_img_create(ui->screen_callend);
    lv_obj_add_flag(ui->screen_callend_img_end, LV_OBJ_FLAG_CLICKABLE);
    lv_img_set_src(ui->screen_callend_img_end, &_icon_call_end_alpha_60x60);
    lv_img_set_pivot(ui->screen_callend_img_end, 30,30);
    lv_img_set_angle(ui->screen_callend_img_end, 0);
    lv_obj_set_pos(ui->screen_callend_img_end, 70, 48);
    lv_obj_set_size(ui->screen_callend_img_end, 60, 60);

    //Write style for screen_callend_img_end, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_img_recolor_opa(ui->screen_callend_img_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_img_opa(ui->screen_callend_img_end, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_callend_img_end, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_clip_corner(ui->screen_callend_img_end, true, LV_PART_MAIN|LV_STATE_DEFAULT);

    //The custom code of screen_callend.


    //Update current screen layout.
    lv_obj_update_layout(ui->screen_callend);

}
