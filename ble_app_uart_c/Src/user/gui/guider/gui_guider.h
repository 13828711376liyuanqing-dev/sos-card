/* SAM | 2026-10-11 00:45 +08:00 | Import YP001 GUI Guider assets because the six-page UI replaces the old runtime page. */
/*
* Copyright 2026 NXP
* NXP Proprietary. This software is owned or controlled by NXP and may only be used strictly in
* accordance with the applicable license terms. By expressly accepting such terms or by downloading, installing,
* activating and/or otherwise using the software, you are agreeing that you have read, and that you agree to
* comply with and are bound by, such license terms.  If you do not agree to be bound by the applicable license
* terms, then you may not retain, install, activate or otherwise use the software.
*/

#ifndef GUI_GUIDER_H
#define GUI_GUIDER_H
#ifdef __cplusplus
extern "C" {
#endif

#include "lvgl.h"

typedef struct
{
  
	lv_obj_t *screen;
	bool screen_del;
	lv_obj_t *screen_label_imei;
	lv_obj_t *screen_line_1;
	lv_obj_t *screen_label_title;
	lv_obj_t *screen_img_1;
	lv_obj_t *screen_img_bat;
	lv_obj_t *screen_main;
	bool screen_main_del;
	lv_obj_t *screen_main_label_campus;
	lv_obj_t *screen_main_label_room;
	lv_obj_t *screen_main_line_main;
	lv_obj_t *screen_main_label_name;
	lv_obj_t *screen_main_img_bat;
	lv_obj_t *screen_time;
	bool screen_time_del;
	lv_obj_t *screen_time_label_week;
	lv_obj_t *screen_time_label_date;
	lv_obj_t *screen_time_line_time;
	lv_obj_t *screen_time_label_time;
	lv_obj_t *screen_time_img_bat;
	lv_obj_t *screen_lowbat;
	bool screen_lowbat_del;
	lv_obj_t *screen_lowbat_label_lowdate;
	lv_obj_t *screen_lowbat_label_info;
	lv_obj_t *screen_lowbat_line_low;
	lv_obj_t *screen_lowbat_label_low2;
	lv_obj_t *screen_lowbat_label_low1;
	lv_obj_t *screen_lowbat_img_bat;
	lv_obj_t *screen_calling;
	bool screen_calling_del;
	lv_obj_t *screen_calling_img_sos;
	lv_obj_t *screen_callend;
	bool screen_callend_del;
	lv_obj_t *screen_callend_label_end;
	lv_obj_t *screen_callend_img_end;
}lv_ui;

typedef void (*ui_setup_scr_t)(lv_ui * ui);

void ui_init_style(lv_style_t * style);

void ui_load_scr_animation(lv_ui *ui, lv_obj_t ** new_scr, bool new_scr_del, bool * old_scr_del, ui_setup_scr_t setup_scr,
                           lv_scr_load_anim_t anim_type, uint32_t time, uint32_t delay, bool is_clean, bool auto_del);

void ui_animation(void * var, int32_t duration, int32_t delay, int32_t start_value, int32_t end_value, lv_anim_path_cb_t path_cb,
                       uint16_t repeat_cnt, uint32_t repeat_delay, uint32_t playback_time, uint32_t playback_delay,
                       lv_anim_exec_xcb_t exec_cb, lv_anim_start_cb_t start_cb, lv_anim_ready_cb_t ready_cb, lv_anim_deleted_cb_t deleted_cb);


void init_scr_del_flag(lv_ui *ui);

void setup_ui(lv_ui *ui);

void init_keyboard(lv_ui *ui);

extern lv_ui guider_ui;


void setup_scr_screen(lv_ui *ui);
void setup_scr_screen_main(lv_ui *ui);
void setup_scr_screen_time(lv_ui *ui);
void setup_scr_screen_lowbat(lv_ui *ui);
void setup_scr_screen_calling(lv_ui *ui);
void setup_scr_screen_callend(lv_ui *ui);
LV_IMG_DECLARE(_qr_imei_alpha_116x116);
LV_IMG_DECLARE(_battery_4_alpha_20x10);
LV_IMG_DECLARE(_battery_4_alpha_20x10);
LV_IMG_DECLARE(_battery_4_alpha_20x10);
LV_IMG_DECLARE(_battery_1_alpha_20x10);
LV_IMG_DECLARE(_icon_sos_alpha_200x200);
LV_IMG_DECLARE(_icon_call_connected_alpha_200x200);
LV_IMG_DECLARE(_icon_call_end_alpha_200x200);

LV_FONT_DECLARE(font_cn_16)
LV_FONT_DECLARE(font_cn_16)
LV_FONT_DECLARE(font_cn_28)
LV_FONT_DECLARE(font_cn_32)
LV_FONT_DECLARE(font_cn_24)
LV_FONT_DECLARE(font_cn_40)


#ifdef __cplusplus
}
#endif
#endif
