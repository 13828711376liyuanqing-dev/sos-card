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



void setup_scr_screen_calling(lv_ui *ui)
{
    //Write codes screen_calling
    ui->screen_calling = lv_obj_create(NULL);
    lv_obj_set_size(ui->screen_calling, 200, 200);
    lv_obj_set_scrollbar_mode(ui->screen_calling, LV_SCROLLBAR_MODE_OFF);

    //Write style for screen_calling, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_bg_opa(ui->screen_calling, 0, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Write codes screen_calling_img_sos
    ui->screen_calling_img_sos = lv_img_create(ui->screen_calling);
    lv_obj_add_flag(ui->screen_calling_img_sos, LV_OBJ_FLAG_CLICKABLE);
    lv_img_set_src(ui->screen_calling_img_sos, &_icon_sos_alpha_200x200);
    lv_img_set_angle(ui->screen_calling_img_sos, 0);
    lv_obj_set_pos(ui->screen_calling_img_sos, 0, 0);
    lv_obj_set_size(ui->screen_calling_img_sos, 200, 200);

    //Write style for screen_calling_img_sos, Part: LV_PART_MAIN, State: LV_STATE_DEFAULT.
    lv_obj_set_style_img_recolor_opa(ui->screen_calling_img_sos, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_img_opa(ui->screen_calling_img_sos, 255, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_radius(ui->screen_calling_img_sos, 0, LV_PART_MAIN|LV_STATE_DEFAULT);
    lv_obj_set_style_clip_corner(ui->screen_calling_img_sos, true, LV_PART_MAIN|LV_STATE_DEFAULT);

    //Update current screen layout.
    lv_obj_update_layout(ui->screen_calling);

}
