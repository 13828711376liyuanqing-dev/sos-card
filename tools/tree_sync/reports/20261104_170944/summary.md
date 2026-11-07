# 目录同步报告 20261104_170944

## gr_src  (two-way)  new_in_prj=2 prj_changed=7 same=3424
- prj_changed    config/yp001_fw_version.h
- prj_changed    user/business/yp001_business.c
- prj_changed    user/business/yp001_business.h
- prj_changed    user/gui/epaper_ui.c
- prj_changed    user/gui/guider/guider_fonts/font_cn_24.c
- prj_changed    user/gui/guider/guider_fonts/font_cn_28.c
- prj_changed    user/gui/guider/guider_fonts/font_cn_32.c
- new_in_prj     user/business/yp_name_glyphs.c
- new_in_prj     user/business/yp_name_glyphs.h

## gr_keil  (two-way)  prj_changed=2 same=5
- prj_changed    YP001_GR5526.uvoptx
- prj_changed    YP001_GR5526.uvprojx

## gr_logo  (two-way)  same=1

## gr_gcc  (report-only)  prj_changed=1 same=1
- prj_changed    Makefile

## sdk  (two-way)  same=5703

## productdoc  (two-way)  same=6

## cat1  (two-way)  new_in_prj=6 prj_changed=10 same=46
- prj_changed    fs_log.lua
- prj_changed    main.lua
- prj_changed    mqtts_receiver.lua
- prj_changed    ota_bundle.lua
- prj_changed    ota_candidates.lua
- prj_changed    ota_device_options.lua
- prj_changed    ota_http_range.lua
- prj_changed    ota_manager.lua
- prj_changed    ota_runtime.lua
- prj_changed    update.lua
- new_in_prj     resident_name.lua
- new_in_prj     vendor_luac/air1103.luac
- new_in_prj     vendor_luac/es8311.luac
- new_in_prj     vendor_luac/exsipclient.luac
- new_in_prj     vendor_luac/exsipproto.luac
- new_in_prj     vendor_luac/vendor.json

## CAT1 OTA 规则检查（SVN 侧 对 项目验证版）

BLOCK=9 WARN=1 INFO=3

| 级别 | 规则 | 位置 | 说明 |
|---|---|---|---|
| BLOCK | R1 OTA文件 | main.lua | 版本号/OTA_TRIAL/OTA 启动段或 require 顺序与验证版不同 |
| BLOCK | R1 OTA文件 | ota_bundle.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_candidates.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_device_options.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_http_range.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_manager.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_runtime.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | update.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R3 重启 | mqtts_receiver.lua:52 | pm.reboot()  ← 重启前没有检查 ota_runtime.instance():reboot_allowed() |
| WARN | R8 空间 | fs_log.lua | LOG_MAX=131072 字节（加备份共 262144），建议 ≤ 16384：写满后 OTA 报 COMPONENT_SPACE |
| INFO | R2 新建目录 | fs_log.lua:12 | local ok, err = io.mkdir(LOG_DIR)  （已放行的 /log、/ble） |
| INFO | R2 新建目录 | fs_log.lua:17 | local ok, err = io.mkdir(BLE_DIR)  （已放行的 /log、/ble） |
| INFO | R9 脚本区 | - | 源码比验证版多 -21636 字节；验证版 LuaDB 482276/524288，余 42012（编译后大小以 Cat1UsbImport 为准） |
