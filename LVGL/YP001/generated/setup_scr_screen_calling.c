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



void setup_scr_screen_calling(lv_ui *ui)
{
    //Write codes screen_calling
    ui->screen_calling = lv_obj_create(NULL);
    lv_obj_set_size(ui->screen_calling, 200, 200);
    lv_obj_set_scrollbar_mode(ui->screen_calling, LV_SCROLLBAR_MODE_OFF);

    //Write style for screen_calling, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_bg_opa(ui->screen_calling, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_calling_label_status
    ui->screen_calling_label_status = lv_label_create(ui->screen_calling);
    lv_label_set_text(ui->screen_calling_label_status, "正在呼叫...");
    lv_label_set_long_mode(ui->screen_calling_label_status, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_calling_label_status, 10, 125);
    lv_obj_set_size(ui->screen_calling_label_status, 180, 30);

    //Write style for screen_calling_label_status, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_calling_label_status, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_calling_label_status, &lv_font_simhei_24, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_calling_label_status, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_calling_label_status, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_calling_label_status, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_calling_line_call
    ui->screen_calling_line_call = lv_label_create(ui->screen_calling);
    lv_label_set_text(ui->screen_calling_line_call, "");
    lv_label_set_long_mode(ui->screen_calling_line_call, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(ui->screen_calling_line_call, 50, 110);
    lv_obj_set_size(ui->screen_calling_line_call, 100, 2);

    //Write style for screen_calling_line_call, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_border_width(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(ui->screen_calling_line_call, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(ui->screen_calling_line_call, &lv_font_montserratMedium_16, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_opa(ui->screen_calling_line_call, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_letter_space(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_line_space(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(ui->screen_calling_line_call, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(ui->screen_calling_line_call, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_color(ui->screen_calling_line_call, lv_color_hex(0x000000), LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_bg_grad_dir(ui->screen_calling_line_call, LV_GRAD_DIR_NONE, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_top(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_right(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_bottom(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_pad_left(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_shadow_width(ui->screen_calling_line_call, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_calling_img_sos
    ui->screen_calling_img_sos = lv_img_create(ui->screen_calling);
    lv_obj_add_flag(ui->screen_calling_img_sos, LV_OBJ_FLAG_CLICKABLE);
    lv_img_set_src(ui->screen_calling_img_sos, &_icon_sos_alpha_72x72);
    lv_img_set_pivot(ui->screen_calling_img_sos, 36,36);
    lv_img_set_angle(ui->screen_calling_img_sos, 0);
    lv_obj_set_pos(ui->screen_calling_img_sos, 64, 26);
    lv_obj_set_size(ui->screen_calling_img_sos, 72, 72);

    //Write style for screen_calling_img_sos, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_img_recolor_opa(ui->screen_calling_img_sos, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_img_opa(ui->screen_calling_img_sos, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_calling_img_sos, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_clip_corner(ui->screen_calling_img_sos, true, LV_PART_MAIN|LV_STATE_DEFAULT);

    //The custom code of screen_calling.


    //Update current screen layout.
    lv_obj_update_layout(ui->screen_calling);

}
