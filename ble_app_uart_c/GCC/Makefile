#########################################################################################################
# GNU Compiler makefile for Goodix BLE Application Project
# Copyright(C) 2023, Shenzhen Goodix Technology Co., Ltd
#
# Default Location of GCC Compile Ref Files
#
#   {APP_ROOT_DIR} is root directory in GR55xx SDK
#
#   1. sdk lib for gcc          : {APP_ROOT_DIR}/platform/soc/linker/gcc/libble_sdk.a
#   2. symbol file for gcc      : {APP_ROOT_DIR}/platform/soc/linker/gcc/rom_symbol_gcc.txt
#   3. link file for gcc        : {APP_ROOT_DIR}/platform/soc/linker/gcc/gcc_linker.lds & gcc_linker_graphics.lds
#   4. startup asemmbly file    : (APP_ROOT_DIR)/platform/arch/arm/cortex-m/gcc/startup_gr55xx.s
#########################################################################################################


#########################################################################################################
###                                Different Configuration For Different Project
#########################################################################################################

## Set Vars by Input Value
# target name
    
MAKE_TARGET_NAME :=  ble_app_uart_c

# SAM | 2026-10-13 08:52 +08:00 | Include business owner because BSP now dispatches real application events.
# SAM | 2026-10-13 15:00 +08:00 | Include official GUS server and factory BLE owner because sealed products use GATT.
# SAM | 2026-10-20 12:47 +08:00 | Build the YP_01 boot logo resource instead of the vendor demo image.
# Generated from Keil_6\YP001_GR5526.uvprojx (authoritative file list).
# Regenerate with: powershell -NoProfile -File _gen_makefile.ps1
# ---- SDK: platform / drivers / libraries / profiles
PRJ_C_SRC_FILES:=   \
  ../../SDK/platform/soc/common/gr_system.c  \
  ../../SDK/platform/soc/common/gr_interrupt.c  \
  ../../SDK/platform/soc/common/gr_platform.c  \
  ../../SDK/platform/soc/src/gr_soc.c  \
  ../../SDK/platform/boards/board_SK.c  \
  ../../SDK/drivers/src/app_dma.c  \
  ../../SDK/drivers/src/app_gpiote.c  \
  ../../SDK/drivers/src/app_io.c  \
  ../../SDK/drivers/src/app_pwr_mgmt.c  \
  ../../SDK/drivers/src/app_uart.c  \
  ../../SDK/drivers/src/app_uart_dma.c  \
  ../../SDK/drivers/src/app_i2c.c  \
  ../../SDK/drivers/src/app_i2c_dma.c  \
  ../../SDK/drivers/src/app_adc.c  \
  ../../SDK/drivers/src/app_adc_dma.c  \
  ../../SDK/drivers/src/app_rtc.c  \
  ../../SDK/drivers/src/app_aon_wdt.c  \
  ../../SDK/components/libraries/ble/ble_scanner/ble_scanner.c  \
  ../../SDK/components/libraries/app_key/app_key.c  \
  ../../SDK/components/libraries/app_key/app_key_core.c  \
  ../../SDK/components/libraries/ring_buffer/ring_buffer.c  \
  ../../SDK/components/libraries/utility/utility.c  \
  ../../SDK/components/libraries/sensorsim/sensorsim.c  \
  ../../SDK/components/libraries/pmu_calibration/pmu_calibration.c  \
  ../../SDK/components/libraries/app_timer/app_timer.c  \
  ../../SDK/components/libraries/app_assert/app_assert.c  \
  ../../SDK/components/libraries/app_error/app_error.c  \
  ../../SDK/components/libraries/app_log/app_log.c  \
  ../../SDK/components/libraries/ble/ble_time/ble_time.c  \
  ../../SDK/components/sdk/ble.c  \
  ../../SDK/components/profiles/common/ble_prf_utils.c  \
  ../../SDK/components/profiles/gus/gus.c  \
  ../../SDK/components/profiles/gus_c/gus_c.c  \
  ../../SDK/external/segger_rtt/SEGGER_RTT.c  \

# ---- Application (YP001)
PRJ_C_SRC_FILES +=   \
  ../Src/user/factory/yp001_factory_ble.c  \
  ../Src/platform/user_periph_setup.c  \
  ../Src/user/business/yp001_business.c  \
  ../Src/user/business/yp_name_glyphs.c  \
  ../Src/user/ota/yp001_ota.c  \
  ../Src/user/ota/yp001_ota_port.c  \
  ../Src/user/ota/yp001_ota_boot.c  \
  ../Src/user/ota/yp001_ota_wire.c  \
  ../Src/user/ota/yp001_ota_receive.c  \
  ../Src/user/ota/yp001_ota_app_crypto.c  \
  ../Src/user/ota/yp001_ota_project_verify.c  \
  ../../SDK/components/libraries/app_bootloader/sign_verify/src/rsa.c  \
  ../../SDK/components/libraries/app_bootloader/sign_verify/src/pkc.c  \
  ../Src/platform/bsp.c  \
  ../Src/user/main.c  \
  ../Src/user/app.c  \
  ../Src/user/user_app.c  \
  ../Src/user/transport_scheduler.c  \
  ../Src/user/da221.c  \
  ../Src/user/gpio_test.c  \
  ../Src/user/at_cmds.c  \
  ../Src/user/cli.c  \
  ../Src/user/gsensor_probe.c  \
  ../Src/user/log_cmd.c  \
  ../Src/user/blinky.c  \
  ../Src/user/location_servise.c  \
  ../Src/user/cat1svr.c  \
  ../Src/user/yp001_scan_sched.c  \
  ../Src/user/sensor.c  \
  ../Src/user/da221_config.c  \
  ../Src/user/epaper_depg0150.c  \
  ../Src/user/epaper_depg0150_logo_yp01.c  \
  ../Src/user/yp001_battery.c  \
  ../Src/user/gui/epaper_home.c  \
  ../Src/user/gui/epaper_lvgl.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qv/qv.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qep_hsm.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qep_msm.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_act.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_actq.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_defer.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_dyn.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_mem.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_ps.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_qact.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_qeq.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_qmact.c  \
  ../Src/external/qpc_7.3.4/qpc/src/qf/qf_time.c  \
  ../Src/external/cJSON-1.7.19/cJSON.c  \
  ../Src/external/slre-1.3/slre.c  \
  ../Src/user/charger/yp001_charger.c  \
  ../Src/user/charger/yp001_charger_cli.c  \

# ---- GUI Guider generated screens / fonts / images
PRJ_C_SRC_FILES +=   \
  ../Src/user/gui/epaper_ui.c  \
  ../Src/user/gui/guider/events_init.c  \
  ../Src/user/gui/guider/gui_guider.c  \
  ../Src/user/gui/guider/setup_scr_screen.c  \
  ../Src/user/gui/guider/setup_scr_screen_callend.c  \
  ../Src/user/gui/guider/setup_scr_screen_calling.c  \
  ../Src/user/gui/guider/setup_scr_screen_lowbat.c  \
  ../Src/user/gui/guider/setup_scr_screen_main.c  \
  ../Src/user/gui/guider/setup_scr_screen_time.c  \
  ../Src/user/gui/guider/widgets_init.c  \
  ../Src/user/gui/guider/custom/custom.c  \
  ../Src/user/gui/guider/guider_fonts/font_cn_16.c  \
  ../Src/user/gui/guider/guider_fonts/font_cn_24.c  \
  ../Src/user/gui/guider/guider_fonts/font_cn_28.c  \
  ../Src/user/gui/guider/guider_fonts/font_cn_32.c  \
  ../Src/user/gui/guider/guider_fonts/font_cn_40.c  \
  ../Src/user/gui/guider/images/_battery_1_alpha_20x10.c  \
  ../Src/user/gui/guider/images/_battery_4_alpha_20x10.c  \
  ../Src/user/gui/guider/images/_icon_call_end_alpha_60x60.c  \
  ../Src/user/gui/guider/images/_icon_sos_alpha_72x72.c  \
  ../Src/user/gui/guider/images/_qr_imei_alpha_116x116.c  \

# ---- LVGL 8.3.1 (built from source, same file set as Keil)
PRJ_C_SRC_FILES +=   \
  ../Src/external/lvgl_8.3.1/src/core/lv_disp.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_event.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_group.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_indev.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_indev_scroll.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_class.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_draw.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_pos.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_scroll.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_style.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_style_gen.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_obj_tree.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_refr.c  \
  ../Src/external/lvgl_8.3.1/src/core/lv_theme.c  \
  ../Src/external/lvgl_8.3.1/src/draw/arm2d/lv_gpu_arm2d.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_arc.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_img.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_label.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_layer.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_line.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_mask.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_rect.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_transform.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_draw_triangle.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_img_buf.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_img_cache.c  \
  ../Src/external/lvgl_8.3.1/src/draw/lv_img_decoder.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/lv_gpu_nxp.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/pxp/lv_draw_pxp_blend.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/pxp/lv_gpu_nxp_pxp.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/pxp/lv_gpu_nxp_pxp_osa.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/vglite/lv_draw_vglite_arc.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/vglite/lv_draw_vglite_blend.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/vglite/lv_draw_vglite_rect.c  \
  ../Src/external/lvgl_8.3.1/src/draw/nxp/vglite/lv_gpu_nxp_vglite.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_arc.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_bg.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_composite.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_img.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_label.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_layer.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_line.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_mask.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_polygon.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_rect.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_stack_blur.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_texture_cache.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sdl/lv_draw_sdl_utils.c  \
  ../Src/external/lvgl_8.3.1/src/draw/stm32_dma2d/lv_gpu_stm32_dma2d.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_arc.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_blend.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_dither.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_gradient.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_img.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_layer.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_letter.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_line.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_polygon.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_rect.c  \
  ../Src/external/lvgl_8.3.1/src/draw/sw/lv_draw_sw_transform.c  \
  ../Src/external/lvgl_8.3.1/src/draw/swm341_dma2d/lv_gpu_swm341_dma2d.c  \
  ../Src/external/lvgl_8.3.1/src/extra/layouts/flex/lv_flex.c  \
  ../Src/external/lvgl_8.3.1/src/extra/layouts/grid/lv_grid.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/bmp/lv_bmp.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/ffmpeg/lv_ffmpeg.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/freetype/lv_freetype.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/fsdrv/lv_fs_fatfs.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/fsdrv/lv_fs_posix.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/fsdrv/lv_fs_stdio.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/fsdrv/lv_fs_win32.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/gif/gifdec.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/gif/lv_gif.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/png/lodepng.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/png/lv_png.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/qrcode/qrcodegen.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/qrcode/lv_qrcode.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/rlottie/lv_rlottie.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/sjpg/lv_sjpg.c  \
  ../Src/external/lvgl_8.3.1/src/extra/libs/sjpg/tjpgd.c  \
  ../Src/external/lvgl_8.3.1/src/extra/lv_extra.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/fragment/lv_fragment.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/fragment/lv_fragment_manager.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/gridnav/lv_gridnav.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/ime/lv_ime_pinyin.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/imgfont/lv_imgfont.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/monkey/lv_monkey.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/msg/lv_msg.c  \
  ../Src/external/lvgl_8.3.1/src/extra/others/snapshot/lv_snapshot.c  \
  ../Src/external/lvgl_8.3.1/src/extra/themes/basic/lv_theme_basic.c  \
  ../Src/external/lvgl_8.3.1/src/extra/themes/default/lv_theme_default.c  \
  ../Src/external/lvgl_8.3.1/src/extra/themes/mono/lv_theme_mono.c  \
  ../Src/external/lvgl_8.3.1/src/extra/themes/simplify/lv_theme_simplify.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/animimg/lv_animimg.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/calendar/lv_calendar.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/calendar/lv_calendar_header_arrow.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/calendar/lv_calendar_header_dropdown.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/chart/lv_chart.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/colorwheel/lv_colorwheel.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/imgbtn/lv_imgbtn.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/keyboard/lv_keyboard.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/led/lv_led.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/list/lv_list.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/menu/lv_menu.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/meter/lv_meter.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/msgbox/lv_msgbox.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/span/lv_span.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/spinbox/lv_spinbox.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/spinner/lv_spinner.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/tabview/lv_tabview.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/tileview/lv_fast_tileview.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/tileview/lv_tileview.c  \
  ../Src/external/lvgl_8.3.1/src/extra/widgets/win/lv_win.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_dejavu_16_persian_hebrew.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_fmt_txt.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_loader.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_10.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_12.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_12_subpx.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_14.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_16.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_18.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_20.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_22.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_24.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_26.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_28.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_28_compressed.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_30.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_32.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_34.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_36.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_38.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_40.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_42.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_44.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_46.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_48.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_8.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_simsun_16_cjk.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_unscii_16.c  \
  ../Src/external/lvgl_8.3.1/src/font/lv_font_unscii_8.c  \
  ../Src/external/lvgl_8.3.1/src/hal/lv_hal_disp.c  \
  ../Src/external/lvgl_8.3.1/src/hal/lv_hal_indev.c  \
  ../Src/external/lvgl_8.3.1/src/hal/lv_hal_tick.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_anim.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_anim_timeline.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_area.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_async.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_bidi.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_color.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_fs.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_gc.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_ll.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_log.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_lru.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_math.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_mem.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_printf.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_style.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_style_gen.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_templ.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_timer.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_tlsf.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_txt.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_txt_ap.c  \
  ../Src/external/lvgl_8.3.1/src/misc/lv_utils.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_arc.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_bar.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_btn.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_btnmatrix.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_canvas.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_checkbox.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_dropdown.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_img.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_label.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_line.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_objx_templ.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_roller.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_slider.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_switch.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_table.c  \
  ../Src/external/lvgl_8.3.1/src/widgets/lv_textarea.c  \

# ---- QPC 7.3.4 kernel port (GCC flavour of qv_port.c)
PRJ_C_SRC_FILES +=   \
  ../Src/external/qpc_7.3.4/qpc/ports/arm-cm/qv/gnu/qv_port.c  \


PRJ_ASM_SRC_FILES :=   \


PRJ_C_INCLUDE_PATH :=   \
  ../../SDK/components/libraries/app_bootloader/sign_verify/inc  \
  ../Src/user/gui/guider  \
  ../Src/user/gui/guider/custom  \
  ../Src/config  \
  ../Src/platform  \
  ../Src/user  \
  ../Src/external/qpc_7.3.4/qpc/include  \
  ../Src/external/cJSON-1.7.19  \
  ../Src/external/slre-1.3  \
  ../Src/external/lvgl_8.3.1  \
  ../../SDK/components/drivers_ext/gr55xx  \
  ../../SDK/components/libraries/app_alarm  \
  ../../SDK/components/libraries/app_assert  \
  ../../SDK/components/libraries/app_error  \
  ../../SDK/components/libraries/app_key  \
  ../../SDK/components/libraries/app_log  \
  ../../SDK/components/libraries/app_queue  \
  ../../SDK/components/libraries/app_timer  \
  ../../SDK/components/libraries/at_cmd  \
  ../../SDK/components/libraries/ble/ble_time  \
  ../../SDK/components/libraries/dfu_master  \
  ../../SDK/components/libraries/dfu_port  \
  ../../SDK/components/libraries/hal_flash  \
  ../../SDK/components/libraries/hci_uart  \
  ../../SDK/components/libraries/pmu_calibration  \
  ../../SDK/components/libraries/ring_buffer  \
  ../../SDK/components/libraries/sensorsim  \
  ../../SDK/components/libraries/utility  \
  ../../SDK/components/libraries/ble/ble_scanner  \
  ../../SDK/components/profiles/ams_c  \
  ../../SDK/components/profiles/ancs_c  \
  ../../SDK/components/profiles/ans  \
  ../../SDK/components/profiles/ans_c  \
  ../../SDK/components/profiles/bas  \
  ../../SDK/components/profiles/bas_c  \
  ../../SDK/components/profiles/bps  \
  ../../SDK/components/profiles/common  \
  ../../SDK/components/profiles/cscs  \
  ../../SDK/components/profiles/cts  \
  ../../SDK/components/profiles/cts_c  \
  ../../SDK/components/profiles/dis  \
  ../../SDK/components/profiles/dis_c  \
  ../../SDK/components/profiles/gus  \
  ../../SDK/components/profiles/gus_c  \
  ../../SDK/components/profiles/hids  \
  ../../SDK/components/profiles/hrrcps  \
  ../../SDK/components/profiles/hrs  \
  ../../SDK/components/profiles/hrs_c  \
  ../../SDK/components/profiles/hts  \
  ../../SDK/components/profiles/ias  \
  ../../SDK/components/profiles/lls  \
  ../../SDK/components/profiles/ndcs  \
  ../../SDK/components/profiles/otas  \
  ../../SDK/components/profiles/otas_c  \
  ../../SDK/components/profiles/pass  \
  ../../SDK/components/profiles/pass_c  \
  ../../SDK/components/profiles/pcs  \
  ../../SDK/components/profiles/rscs  \
  ../../SDK/components/profiles/rscs_c  \
  ../../SDK/components/profiles/rtus  \
  ../../SDK/components/profiles/sample  \
  ../../SDK/components/profiles/ths  \
  ../../SDK/components/profiles/ths_c  \
  ../../SDK/components/profiles/tps  \
  ../../SDK/components/sdk/  \
  ../../SDK/drivers/inc  \
  ../../SDK/drivers/inc/hal  \
  ../../SDK/external/freertos/include  \
  ../../SDK/external/segger_rtt  \
  ../../SDK/platform/arch/arm/cortex-m/cmsis/core/include  \
  ../../SDK/platform/boards  \
  ../../SDK/platform/include  \
  ../../SDK/platform/soc/include  \
  ../../SDK/platform/soc/linker/keil  \
  ../Src/external/qpc_7.3.4/qpc/ports/arm-cm/qv/gnu  \
  ../Src/external/qpc_7.3.4/qpc/ports/arm-cm/qv/config  \
  ../Src/user/gui  \
  ../../SDK/components/boards  \
  ../../SDK/components/libraries/gui  \
  ../../SDK/components/libraries/gui/gui_config  \
  ../../SDK/components/drivers_ext/st7735  \
  ../../SDK/components/drivers_ext/vs1005  \


PRJ_C_MICRO_DEFINES :=   \
  ENV_USE_FREERTOS  \
  TK_Board_UART_DBG=1  \
  YP001_BOARD  \
  LV_LVGL_H_INCLUDE_SIMPLE  \
  YP001_OTA_USB_BENCH_TEST=1  \
  $(if $(filter 1,$(USE_BOARD_TK)),TK_Board_UART_DBG)  \
  $(if $(filter 1,$(USE_BOARD_TK_1_1)),TK_Board_1_1_UART_DBG)  \
  $(if $(filter 1,$(USE_BOARD_TK_PAD)),TK_Board_PAD_UART_DBG)  \


PRJ_ASM_INCLUDE_PATH :=   \


PRJ_ASM_MICRO_DEFINES :=   \


IS_WIN_OS :=  true


# Set echo cmd
ECHO = @echo

#########################################################################################################
###                                   Common Configuration Area, Change carefully
#########################################################################################################

## Set Compiler (CC/ASM use same compile cmd for now)
CROSS_COMPILE 	= arm-none-eabi-
CC 				= $(CROSS_COMPILE)gcc
ASM				= $(CROSS_COMPILE)gcc
CPP 			= $(CROSS_COMPILE)cpp
LINK			= $(CROSS_COMPILE)gcc
OBJCOPY 		= $(CROSS_COMPILE)objcopy

## Set Common Flags for C/ASM
COMMON_COMPILE_FLAGS += -std=gnu99 --inline
COMMON_COMPILE_FLAGS += -ggdb3
COMMON_COMPILE_FLAGS += -ffunction-sections -fdata-sections
COMMON_COMPILE_FLAGS += -mfloat-abi=softfp -mfpu=fpv4-sp-d16  -mapcs-frame -mthumb-interwork -mthumb -mcpu=cortex-m4
COMMON_COMPILE_FLAGS += -gdwarf-2 -MD

## Set CFLAGS
# Set include path
CFLAGS += $(foreach inc,$(PRJ_C_INCLUDE_PATH),-I $(inc))
# Set macro-defines Flags
CFLAGS += $(foreach md,$(PRJ_C_MICRO_DEFINES),-D$(md))
CFLAGS += $(COMMON_COMPILE_FLAGS)
CFLAGS += -O2

## Set ASMFLAGS
ASMFLAGS += $(foreach inc,$(PRJ_ASM_INCLUDE_PATH),-I $(inc))
# Set macro-defines Flags
ASMFLAGS += $(foreach md,$(PRJ_ASM_MICRO_DEFINES),-D$(md))
ASMFLAGS += $(COMMON_COMPILE_FLAGS)

## Set default compile ref files
LINK_SCRIPT 		= ./gcc_linker.lds
# LINK_SCRIPT 		= ../../SDK/platform/soc/linker/gcc/gcc_linker_graphics.lds

PATCH_FILE  		= ../../SDK/platform/soc/linker/gcc/rom_symbol_gcc.txt

GCC_STARTUP_ASM_FILE 	= ../../SDK/platform/arch/arm/cortex-m/gcc/startup_gr55xx.s

ifeq ($(IS_WIN_OS),true)
	BLE_TOOL_BIN		= ..\..\..\..\..\build\binaries\ble_tools\Keil\ble_tools.exe
else
	BLE_TOOL_BIN		= ..\..\..\..\..\build\binaries\ble_tools\GCC\ble_tools.gcc
endif


## Set LDFLAGS
LDFLAGS += -Wl,--gc-sections
#LDFLAGS += -specs=nano.specs
LDFLAGS += -L../../SDK/platform/soc/linker/gcc/ -lble_sdk
# LDFLAGS += -L../../SDK/platform/soc/linker/gcc/ -lgraphics_lvgl
# LDFLAGS += -L../../SDK/platform/soc/linker/gcc/ -lgraphics_sdk

## Set compile output directory
BUILD 		?= out
BUILD_OBJ	?= $(BUILD)/obj
BUILD_LST	?= $(BUILD)/lst


## Set source files and objects
SRC_C	:= $(PRJ_C_SRC_FILES)
SRC_ASM := $(GCC_STARTUP_ASM_FILE) $(PRJ_ASM_SRC_FILES)
OBJ_C 	:= $(SRC_C:.c=.o)
OBJ_ASM := $(SRC_ASM:.s=.o)

# Keep the C objects BEFORE the startup object, as the upstream SDK Makefile does.
# The startup asm (startup_gr55xx.s) installs weak aliases such as
# `.weak SVC_Handler` + `.set SVC_Handler, Default_Handler`, while gr_interrupt.c
# also provides __WEAK real handlers (SVC_Handler -> gr5xx_svc_process, etc.).
# GNU ld resolves colliding weak definitions in favour of the FIRST one it sees, so
# startup.o must NOT come first: otherwise SVC_Handler resolves to the `b .`
# Default_Handler and the firmware deadlocks on the first SVC (IPSR=0x0B) issued by
# the SDK's flash/NVDS path. The vector table is still placed at 0x00202000 by
# KEEP(*(.vectors)) in gcc_linker.lds, so this ordering does not affect the layout.
OBJ 	:= $(OBJ_C) $(OBJ_ASM)
OBJ_ADJUST 	= $(patsubst %.o,$(BUILD_OBJ)/%.o,$(notdir $(OBJ)))


## verbosity switch
V ?= 0
ifeq ($(V),0)
ifeq ($(IS_WIN_OS),true)
	V_CC =
	V_ASM =
	V_CPP =
	V_LINK =
	V_OBJCOPY =
else
	V_CC = @echo " $(CC) " $<;
	V_ASM = @echo " $(ASM) " $<;
	V_CPP = @echo " $(CPP) " $<;
	V_LINK = @echo " $(LINK) " $<;
	V_OBJCOPY = @echo " $(OBJCOPY) " $<;
endif
else
	V_OPT = '-v'
endif


SRC_PATH += $(dir $(SRC_C))
SRC_PATH += $(dir $(SRC_ASM))
MAKE_PATH = $(foreach n,$(SRC_PATH),:$(n))
vpath %.c ./$(MAKE_PATH)
vpath %.s ./$(MAKE_PATH)
## default make goal
all: mk_path $(BUILD)/$(MAKE_TARGET_NAME).bin $(BUILD)/$(MAKE_TARGET_NAME).hex

##  compile C & asm files
# NOTE: '| mk_path' is an order-only prerequisite; without it `make -j` races the
# directory creation against the first compiles and -MD fails to open out/obj/*.d
$(BUILD_OBJ)/%.o : %.c | mk_path
	$(V_CC) $(CC) $(CFLAGS) -c $< -o $@

## how to compile assembly files
$(BUILD_OBJ)/%.o : %.s | mk_path
	$(V_ASM) $(ASM) $(ASMFLAGS) -c $< -o $@

## make depends
$(BUILD)/$(MAKE_TARGET_NAME).hex: $(BUILD_LST)/$(MAKE_TARGET_NAME).elf
	$(ECHO) "compile hex file ..."
	$(V_OBJCOPY) $(OBJCOPY) -O ihex $< $@

$(BUILD)/$(MAKE_TARGET_NAME).bin: $(BUILD_LST)/$(MAKE_TARGET_NAME).elf
	$(ECHO) "compile binary file ..."
	$(V_OBJCOPY) $(OBJCOPY) -O binary $< $@

$(BUILD_LST)/$(MAKE_TARGET_NAME).elf: $(OBJ_ADJUST) | mk_path
	$(ECHO) "compile .elf file ..."
	$(V_LINK) $(LINK) $(CFLAGS) -T $(LINK_SCRIPT) $(PATCH_FILE) $(OBJ_ADJUST) $(LDFLAGS) -Wl,-Map=$(BUILD_LST)/$(MAKE_TARGET_NAME).map -o $@
	$(ECHO) "========== Memory usage =========="
	arm-none-eabi-size -B $@
	arm-none-eabi-size -A $@
	$(ECHO) "========== Top 10 largest objects =========="
	arm-none-eabi-nm --print-size --size-sort -r $@ > $(BUILD_LST)/$(MAKE_TARGET_NAME).symbols.txt

ifeq ($(IS_WIN_OS),true)
mk_path :
	powershell -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Force -Path '$(BUILD)','$(BUILD_OBJ)','$(BUILD_LST)' | Out-Null"
clean:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path -LiteralPath '$(BUILD)') { Remove-Item -LiteralPath '$(BUILD)' -Recurse -Force }"
else
mk_path :
	mkdir -p $(BUILD) $(BUILD_OBJ) $(BUILD_LST)
clean:
	rm -rf $(BUILD)
endif

flash: $(BUILD)/$(MAKE_TARGET_NAME).bin
	$(ECHO) "Writing $< to the GR55xx-SK board"
	GR5xxx_console.exe eraseall 1 0
	GR5xxx_console.exe program $(BUILD)/$(MAKE_TARGET_NAME).bin 'y' 0x200000 1024 1 0

memory_report: $(BUILD_LST)/$(MAKE_TARGET_NAME).elf
	@arm-none-eabi-size -B $<
	@arm-none-eabi-size -A $<
	@arm-none-eabi-nm --print-size --size-sort -r $< | head -20
