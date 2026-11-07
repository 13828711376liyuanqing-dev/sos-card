# 目录同步报告 20261106_175620

## gr_src  (two-way)  conflict=6 new_in_prj=1 prj_changed=11 same=3422
- conflict       platform/bsp.c
- conflict       user/business/yp001_business.c
- conflict       user/business/yp001_business.h
- conflict       user/cat1svr.c
- conflict       user/charger/yp001_charger.c
- conflict       user/yp001_scan_sched.c
- prj_changed    config/yp001_fw_version.h
- prj_changed    platform/user_periph_setup.c
- prj_changed    platform/user_periph_setup.h
- prj_changed    user/app.h
- prj_changed    user/cli.c
- prj_changed    user/cli.h
- prj_changed    user/factory/yp001_factory_ble.c
- prj_changed    user/factory/yp001_factory_ble.h
- prj_changed    user/factory/yp001_factory_protocol.h
- prj_changed    user/user_app.c
- prj_changed    user/user_app.h
- new_in_prj     user/factory/yp001_factory_stream.h

## gr_keil  (two-way)  same=7

## gr_logo  (two-way)  same=1

## gr_gcc  (report-only)  conflict=1 same=1
- conflict       Makefile

## sdk  (two-way)  prj_changed=1 same=5702
- prj_changed    components/libraries/ble/ble_scanner/ble_scanner.c

## productdoc  (two-way)  same=6

## cat1  (two-way)  conflict=3 new_in_prj=1 new_in_svn=1 prj_changed=3 same=55 svn_changed=1
- conflict       business_core.lua
- conflict       main.lua
- conflict       mqtts_receiver.lua
- svn_changed    ota_trial.lua
- prj_changed    ota_http_range.lua
- prj_changed    ota_runtime.lua
- prj_changed    update.lua
- new_in_svn     soc/LuatOS-SoC_V2056_Air780EGH_124.soc
- new_in_prj     soc/LuatOS-SoC_V2055_Air780EGH_124_20261104_1825.soc

## CAT1 OTA 规则检查（SVN 侧 对 项目验证版）

BLOCK=6 WARN=0 INFO=3

| 级别 | 规则 | 位置 | 说明 |
|---|---|---|---|
| BLOCK | R1 OTA文件 | business_core.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | main.lua | 版本号/OTA_TRIAL/OTA 启动段或 require 顺序与验证版不同 |
| BLOCK | R1 OTA文件 | ota_http_range.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_runtime.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | ota_trial.lua | 内容与实板验证版不同（只允许我们改） |
| BLOCK | R1 OTA文件 | update.lua | 内容与实板验证版不同（只允许我们改） |
| INFO | R2 新建目录 | fs_log.lua:13 | local ok, err = io.mkdir(LOG_DIR)  （已放行的 /log、/ble） |
| INFO | R2 新建目录 | fs_log.lua:18 | local ok, err = io.mkdir(BLE_DIR)  （已放行的 /log、/ble） |
| INFO | R9 脚本区 | - | 源码比验证版多 -4598 字节；验证版 LuaDB 482276/524288，余 42012（编译后大小以 Cat1UsbImport 为准） |
