# 目录同步报告 20261102_121841

## gr_src  (two-way)  same=3431

## gr_keil  (two-way)  same=7

## gr_logo  (two-way)  same=1

## gr_gcc  (report-only)  same=2

## sdk  (two-way)  same=5703

## productdoc  (two-way)  same=6

## cat1  (two-way)  new_in_prj=5 same=56
- new_in_prj     vendor_luac/air1103.luac
- new_in_prj     vendor_luac/es8311.luac
- new_in_prj     vendor_luac/exsipclient.luac
- new_in_prj     vendor_luac/exsipproto.luac
- new_in_prj     vendor_luac/vendor.json

## CAT1 OTA 规则检查（SVN 侧 对 项目验证版）

BLOCK=1 WARN=1 INFO=3

| 级别 | 规则 | 位置 | 说明 |
|---|---|---|---|
| BLOCK | R3 重启 | mqtts_receiver.lua:52 | pm.reboot()  ← 重启前没有检查 ota_runtime.instance():reboot_allowed() |
| WARN | R8 空间 | fs_log.lua | LOG_MAX=131072 字节（加备份共 262144），建议 ≤ 16384：写满后 OTA 报 COMPONENT_SPACE |
| INFO | R2 新建目录 | fs_log.lua:12 | local ok, err = io.mkdir(LOG_DIR)  （已放行的 /log、/ble） |
| INFO | R2 新建目录 | fs_log.lua:17 | local ok, err = io.mkdir(BLE_DIR)  （已放行的 /log、/ble） |
| INFO | R9 脚本区 | - | 源码比验证版多 +0 字节；验证版 LuaDB 482276/524288，余 42012（编译后大小以 Cat1UsbImport 为准） |
