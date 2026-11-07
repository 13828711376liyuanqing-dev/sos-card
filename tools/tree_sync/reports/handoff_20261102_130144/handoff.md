# 交接前检查 2026-11-02 13:00

## 1. 两边一致性：5 个文件不一致

- cat1:vendor_luac/air1103.luac new_in_prj
- cat1:vendor_luac/es8311.luac new_in_prj
- cat1:vendor_luac/exsipclient.luac new_in_prj
- cat1:vendor_luac/exsipproto.luac new_in_prj
- cat1:vendor_luac/vendor.json new_in_prj

## 2. CAT1 OTA 规则（SVN 侧）

BLOCK=1 WARN=1 INFO=3

| 级别 | 规则 | 位置 | 说明 |
|---|---|---|---|
| BLOCK | R3 重启 | mqtts_receiver.lua:52 | pm.reboot()  ← 重启前没有检查 ota_runtime.instance():reboot_allowed() |
| WARN | R8 空间 | fs_log.lua | LOG_MAX=131072 字节（加备份共 262144），建议 ≤ 16384：写满后 OTA 报 COMPONENT_SPACE |
| INFO | R2 新建目录 | fs_log.lua:12 | local ok, err = io.mkdir(LOG_DIR)  （已放行的 /log、/ble） |
| INFO | R2 新建目录 | fs_log.lua:17 | local ok, err = io.mkdir(BLE_DIR)  （已放行的 /log、/ble） |
| INFO | R9 脚本区 | - | 源码比验证版多 +0 字节；验证版 LuaDB 482276/524288，余 42012（编译后大小以 Cat1UsbImport 为准） |

## 3. 密钥 / 临时文件（SDK/external 第三方目录除外）

- 无

## 4. 版本号：CAT1 1.5.8/b12，GR 1.5.8/b12 —— 一致
