## 合并结果 OTA 规则检查

BLOCK=65 WARN=0 INFO=1

| 级别 | 规则 | 位置 | 说明 |
|---|---|---|---|
| BLOCK | R1 OTA文件 | antenna_test.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | audio_drv.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | business_runtime.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | business_store.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | dfu_transfer.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | main.lua | 版本号/OTA_TRIAL/OTA 启动段或 require 顺序与验证版不同 |
| BLOCK | R1 OTA文件 | mqtts_sender.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | netdrv_4g.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | network_watchdog.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_boot_identity.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_bundle.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_candidates.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_cat_proof.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_crypto.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_data_inventory.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_device_options.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_download.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_gr_transfer.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_health.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_http_range.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_manager.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_native_fota.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_native_store.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_platform.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_runtime.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_seq_zip.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_store.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_trial.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_trust.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_uart_window.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | ota_wire.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | timer_app.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | tts.lua | 验证版有、这边缺失 |
| BLOCK | R1 OTA文件 | update.lua | 验证版有、这边缺失 |
| BLOCK | R7 require | main.lua:22 | require "ota_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:23 | require "ota_device_options" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:25 | require "ota_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:29 | require "audio_drv" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:30 | require "gnss_app" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:31 | require "uart_app" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:32 | require "antenna_test" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:33 | require "timer_app" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:34 | require "network_watchdog" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:35 | require "netdrv_device" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:36 | require "update" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:37 | require "ntp" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:38 | require "mqtts_main" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:39 | require "mqtts_sender" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:41 | require "sip" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:42 | require "tts" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:43 | require "dfu_transfer" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:44 | require "audio_test" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:45 | require "config" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:46 | require "fs_log" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:47 | require "business_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:48 | require "ota_platform" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | main.lua:76 | require "ota_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:130 | require "mqtts_main" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:167 | require "ota_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:216 | require "ota_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:22 | require "resident_name" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:229 | require "resident_name" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:233 | require "resident_name" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:236 | require "business_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| BLOCK | R7 require | mqtts_receiver.lua:58 | require "ota_runtime" 在目录里找不到（缺库会导致 CAT1 反复重启） |
| INFO | R9 脚本区 | - | 源码比验证版多 -743297 字节；验证版 LuaDB 482276/524288，余 42012（编译后大小以 Cat1UsbImport 为准） |
