--[[
最小化 OTA 专用 main.lua（完整版模块探测）
用 pcall 包裹加载所有完整版本模块，避免缺失模块导致崩溃
用于探测哪个模块的初始化是 UART1 正常通信所必需的
]]
PROJECT = "YP01_CAT1"
-- SAM | 2026-11-07 11:58 +08:00 | Source identity set by YpVersionTool; rebuild GR and CAT1 before use.
VERSION = "001.005.017"
PRODUCT_VERSION = "1.5.17"
FW_RELEASE_BUILD = 21

-- 全局 AT 命令表初始化
_G.at_cmd_handlers = {}
-- SAM | 2026-10-30 09:13 +08:00 | Receiver for the device now on 1.5.2/b6; next range 1.5.2->1.5.3, MD5 not frozen yet.
-- OTA receiver settings. VERSION/PRODUCT_VERSION/FW_RELEASE_BUILD must equal what the device runs now.
-- OTA_TRIAL_MD5 freezes the only bundle `cat_at OTA_TRIAL=<url>` may start (all zeros = none); source/target give its range.
-- The OTA runtime and the boot-time user-data read must start before the business modules below.
OTA_TRIAL_MD5='00000000000000000000000000000000'
OTA_TRIAL_SOURCE='1.5.7'
OTA_TRIAL_TARGET='1.5.8'
local first_trial_profile={source=OTA_TRIAL_SOURCE,target=OTA_TRIAL_TARGET,core_sha256='29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec',evidence_sha256='e47561bd6b33ff2926aea08fd56bebd264a83d754571b41565bfb07916b2877b'}
local trial_runtime=require('ota_runtime')
local manual_options=require('ota_device_options')
trial_runtime.set_instance(trial_runtime.new(manual_options.new(first_trial_profile)))
require("ota_runtime").instance():observe_boot_data()

-- 用 pcall 包裹加载所有完整版本模块

require"audio_drv"
require"gnss_app"
require"uart_app"
require"antenna_test"
require"timer_app"
require"network_watchdog"
require"netdrv_device"
require"update"
require"ntp"
local ota_mqtt_service=require"mqtts_main"
require"mqtts_sender"
require"mqtts_receiver"
local ota_sip_service=require"sip"
require"tts"
require"dfu_transfer"
require"audio_test"
require"config"
require"fs_log"
local ota_business_service=require"business_runtime"
local ota_platform_service=require"ota_platform"
ota_platform_service.bind_services(ota_mqtt_service,ota_business_service)
ota_business_service.bind_sip_status(ota_sip_service.ota_status)

--for _, mod in ipairs(modules) do
--    local ok, err = pcall(function() require(mod) end)
--    if ok then
--        log.info("main", "module loaded: " .. mod)
--    else
--        log.warn("main", "module FAILED: " .. mod .. " (" .. tostring(err) .. ")")
--    end
--end

-- 显式 require dfu_transfer（确保 AT 命令注册）
--local ok, err = pcall(function() require("dfu_transfer") end)
--if ok then
--    log.info("main", "dfu_transfer loaded")
--else
--    log.warn("main", "dfu_transfer FAILED: " .. tostring(err))
--end

-- 电源管理
pm.lastReson()
pm.power(pm.WORK_MODE, 0)
mcu.hardfault(0) -- 增加调试

-- 简单的 AT 命令用于测试
_G.at_cmd_handlers["ATREBOOT"] = function(cmd, uart_send)
    if not require("ota_runtime").instance():reboot_allowed() then
        uart_send("REJECTED OTA_PENDING_OR_UNKNOWN")
        return
    end
    uart_send("reboot")
    rtos.reboot()
end

_G.at_cmd_handlers["HELP"] = function(cmd, uart_send)
    local cmd_list = {}
    for name, _ in pairs(_G.at_cmd_handlers) do
        table.insert(cmd_list, name)
    end
    table.sort(cmd_list)
    local output = "HELP: Available AT commands:\n"
    for _, name in ipairs(cmd_list) do
        output = output .. "  " .. name .. "\n"
    end
    output = output .. "HELP: done"
    uart_send(output)
end

-- SAM | 2026-11-06 +08:00 | From the colleague tree (11-06): alive check command and the product version in the 4O log line.
_G.at_cmd_handlers["CHECKALIVE"] = function(cmd, uart_send)
    uart_send("ALIVE")
end

log.info("main", "4O", PRODUCT_VERSION)

log_write("I", "main", "cat1 boot up")

local tol, use, max_use = rtos.meminfo("sys")
local last_max_use = max_use
local function mem_test()
    while true do
        sys.wait(10000)
        tol, use, max_use = rtos.meminfo("sys")
        log.info("U", max_use )
        if max_use > last_max_use then
            log.info("U", max_use ,"4P", last_max_use)
            last_max_use = max_use
        end
    end
end

sys.taskInit(mem_test)

sys.run()
