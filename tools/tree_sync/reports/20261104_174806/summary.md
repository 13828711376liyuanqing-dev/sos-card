# 目录同步报告 20261104_174806

## gr_src  (two-way)  same=3433

## gr_keil  (two-way)  same=7

## gr_logo  (two-way)  same=1

## gr_gcc  (report-only)  prj_changed=1 same=1
- prj_changed    Makefile

## sdk  (two-way)  same=5703

## productdoc  (two-way)  same=6

## cat1  (two-way)  same=62

## CAT1 OTA 规则检查（SVN 侧 对 项目验证版）

BLOCK=0 WARN=0 INFO=3

| 级别 | 规则 | 位置 | 说明 |
|---|---|---|---|
| INFO | R2 新建目录 | fs_log.lua:13 | local ok, err = io.mkdir(LOG_DIR)  （已放行的 /log、/ble） |
| INFO | R2 新建目录 | fs_log.lua:18 | local ok, err = io.mkdir(BLE_DIR)  （已放行的 /log、/ble） |
| INFO | R9 脚本区 | - | 源码比验证版多 +0 字节；验证版 LuaDB 482276/524288，余 42012（编译后大小以 Cat1UsbImport 为准） |
