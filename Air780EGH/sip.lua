--[[
@module  sip_cmd
@summary SIP通话AT命令封装（纯指令控制，无按键）
@version 1.3
@author  AI Assistant
@usage
原有AT命令保留：
- SIP_INIT      : 初始化SIP服务（自动初始化音频硬件）
- SIP_DEINIT    : 停止SIP服务并反初始化音频硬件
- SIP_DIAL=<号码>: 呼出指定号码（默认10003）
- SIP_ACCEPT    : 接听来电
- SIP_HANGUP    : 挂断当前通话
- SIP_STATUS    : 查询状态
新增一键通话复合命令：
- SIP_CALL=<号码> : 一键初始化+拨号，通话结束自动挂断释放
新增逻辑：通话期间持续每10s上报[SIP_ENV] BUSY，挂断/销毁停止上报
]]
local exsip = require "exsip"
local audio_drv = require "audio_drv"
local tts = require "tts"
local exaudio = require "exaudio"
-- SAM | 2026-10-14 21:09 +08:00 | Gate SIP on confirmed SIM/IP and reject callbacks from an earlier network generation.
local sim_network = require "netdrv_device"
local TASK_NAME = "sip_app_main_task"
-- SIP服务器配置（请根据实际修改）
-- local SIP_CONFIG = {
--     sip_server_addr = "car-ds.xionganbc.com",
--     sip_server_port = 51812,
--     sip_domain = "car-ds.xionganbc.com",
--     sip_username = "1241",
--     sip_password = "1123",
--     sip_transport = exsip.TRANSPORT_UDP,
--     auto_answer = false,
-- }
local SIP_CONFIG = {
    sip_server_addr = "103.169.62.13",
    sip_server_port = 5060,
    sip_domain = "103.169.62.13",
    sip_username = "10003",
    sip_password = "tk@2026",
    sip_transport = exsip.TRANSPORT_UDP,
    auto_answer = false,
}
-- 状态机状态
local g_sip_status = "STATE_IDLE"  -- IDLE, INITING, READY, DIALING, INCOMING, CONNECTED
local g_task_running = false
-- SAM | 2026-10-24 +08:00 | Export actual on-demand lifecycle without initializing SIP or returning account/peer details.
local M={}
function M.ota_status()return {state=g_sip_status,task_running=g_task_running}end
-- 一键通话等待标记
local g_wait_call_end = false
local g_call_result = nil
-- 通话BUSY定时句柄
local g_busy_timer = nil

-- SAM | 2026-10-11 09:24 +08:00 | End the active SIP session on SIM removal so the existing task retries only after IP is restored.
sys.subscribe("SIM_LOST", function()
    if g_task_running then
        sys.sendMsg(TASK_NAME, "sim", "MSG_ERROR")
    end
end)
-- SAM | 2026-10-14 21:09 +08:00 | Tear down SIP on cellular IP loss even when the SIM itself remains present.
sys.subscribe("IP_LOSE", function(adapter)
    if g_task_running and (not adapter or adapter==socket.LWIP_GP) then
        sys.sendMsg(TASK_NAME,"network","MSG_ERROR")
    end
end)

-- ==================== 内部函数 ====================
-- 启动BUSY循环上报：每10秒发一次[SIP_ENV] BUSY
local function start_busy_report()
    if g_busy_timer then
        return
    end
    log.info("sip", "5E")
    -- 循环定时器10000ms
    g_busy_timer = sys.timerLoopStart(function()
        log.info("sip", "5F")
        _G.uart_send_raw("[SIP_ENV]"," ","BUSY")
    end, 30000)
end

-- 停止BUSY上报
local function stop_busy_report()
    if g_busy_timer then
        sys.timerStop(g_busy_timer)
        g_busy_timer = nil
        log.info("sip", "5G")
    end
end

local function start()
    log.info("sip", "5H", g_sip_status)
    if SIP_CONFIG.sip_server_addr == "xxx.xxx.xxx.xxx" then
        log.error("sip", "5I")
        return false
    end
    -- 初始化音频（幂等）
    if audio_drv.initAudioDevice then
        audio_drv.initAudioDevice()
    else
        log.error("sip", "5J")
        return false
    end
    if not exsip.init(SIP_CONFIG) then
        log.error("sip", "5K")
        return false
    end
    if not exsip.start() then
        log.error("sip", "5L")
        return false
    end
    return true
end
local function stop()
    log.info("sip", "5M")
    stop_busy_report() -- 销毁时停止BUSY上报
    exsip.stop()
    -- SAM | 2026-10-14 21:09 +08:00 | Release audio after stopping the lost session so SIM recovery cannot leave PA/Codec powered indefinitely.
    if audio_drv.deinitAudioDevice then audio_drv.deinitAudioDevice() end
end
-- ==================== 回调处理 ====================
local function sip_callback(event, arg1, arg2, arg3)
    log.info("sip_cb", g_sip_status, event, arg1, arg2, arg3)
    if event == "register" then
        local action = arg1
        if action == "ok" then
            log.info("sip", "5N")
        elseif action == "challenge" then
            log.info("sip", "5O")
        else
            log.error("sip", "5P", action)
            sys.sendMsg(TASK_NAME, "cb", "MSG_ERROR")
        end
    elseif event == "ready" then
        sys.sendMsg(TASK_NAME, "cb", "MSG_READY")
    elseif event == "call" then
        local sub_event, data = arg1, arg2
        if sub_event == "incoming" then
            sys.sendMsg(TASK_NAME, "cb", "MSG_INCOMING", data.from)
        elseif sub_event == "connected" or sub_event == "established" then
            sys.sendMsg(TASK_NAME, "cb", "MSG_CONNECTED")
        elseif sub_event == "ended" then
            sys.sendMsg(TASK_NAME, "cb", "MSG_DISCONNECTED")
        end
    elseif event == "media" then
        -- 可选日志
    elseif event == "error" then
        sys.sendMsg(TASK_NAME, "cb", "MSG_ERROR")
    end
end
local function number_to_digits_chinese(num_str)
    local digit_map = {
        ["0"] = "零", ["1"] = "一", ["2"] = "二", ["3"] = "三", ["4"] = "四",
        ["5"] = "五", ["6"] = "六", ["7"] = "七", ["8"] = "八", ["9"] = "九",
    }
    local chars = {}
    for i = 1, #num_str do
        local c = num_str:sub(i, i)
        chars[#chars + 1] = digit_map[c] or c
    end
    return table.concat(chars)
end
-- ==================== 主任务（状态机） ====================
local function sip_app_main_task_func()
    local stop_requested = false  -- 标志：是否主动停止
    while true do
        g_sip_status = "STATE_INITING"
        -- 等待网络就绪
        while not sim_network.ip_ready() or not socket.adapter(socket.dft()) do
            log.warn("c", "5Q", socket.dft())
            sys.waitUntil("IP_READY", 1000)
        end
        log.info("c", "5R", socket.dft())
        sys.cleanMsg(TASK_NAME)
        -- SAM | 2026-10-14 21:09 +08:00 | Bind callbacks and queued commands to this network generation before starting a new SIP session.
        local session_generation=sim_network.generation()
        exsip.on(function(...)
            if session_generation==sim_network.generation() and sim_network.ip_ready() then
                sip_callback(...)
            end
        end)
        if not start() then
            log.error("c", "5S")
            goto EXCEPTION_PROC
        end
        
        while true do
            local msg = sys.waitMsg(TASK_NAME)
            local _, event, para = msg[1], msg[2], msg[3]
            -- SAM | 2026-10-14 21:09 +08:00 | Convert stale queued actions into cleanup instead of executing them on a replacement network.
            if event~="MSG_STOP" and event~="MSG_ERROR" and
                (session_generation~=sim_network.generation() or not sim_network.ip_ready()) then
                event="MSG_ERROR"
            end
            log.info("c", g_sip_status, event, para)
            if event == "MSG_STOP" then
                stop_requested = true
                break
            elseif event == "MSG_ERROR" then
                stop_busy_report() -- 异常断开，停止BUSY
                if g_wait_call_end then
                    g_call_result = "ERROR"
                    g_wait_call_end = false
                end
                break
            elseif event == "MSG_READY" then
                if g_sip_status == "STATE_INITING" then
                    g_sip_status = "STATE_READY"
                    sys.publish("SIP_APP_MAIN_READY")
                    _G.uart_send_raw("[SIP_ENV]"," ","SIP_APP_MAIN_READY")
                end
            elseif event == "MSG_DIAL" then
                if g_sip_status == "STATE_READY" then
                    if not exsip.dial(para) then
                        log.error("c", "5T")
                        sys.publish("SIP_APP_MAIN_DIAL_RSP", false, "exsip.dial")
                        if g_wait_call_end then
                            g_call_result = "DIAL_FAIL"
                            g_wait_call_end = false
                        end
                    else
                        g_sip_status = "STATE_DIALING"
                        start_busy_report() -- 呼出拨号后开启BUSY上报
                    end
                else
                    sys.publish("SIP_APP_MAIN_DIAL_RSP", false, g_sip_status)
                    if g_wait_call_end then
                        g_call_result = "BUSY"
                        g_wait_call_end = false
                    end
                end
            elseif event == "MSG_ACCEPT" then
                if g_sip_status == "STATE_INCOMING" then
                    if not exsip.accept() then
                        log.error("c", "5U")
                    else
                        start_busy_report() -- 接听来电后开启BUSY上报
                    end
                end
            elseif event == "MSG_HANGUP" then
                if g_sip_status == "STATE_DIALING" or g_sip_status == "STATE_INCOMING" or g_sip_status == "STATE_CONNECTED" then
                    exsip.hangUp()
                end
            elseif event == "MSG_INCOMING" then
                if g_sip_status == "STATE_READY" then
                    g_sip_status = "STATE_INCOMING"
                    sys.publish("SIP_APP_MAIN_INCOMING", para)
                    _G.uart_send_raw("[SIP_ENV]"," ","SIP_APP_MAIN_INCOMING")
                    -- 提取号码播报来电
                    local caller_str = tostring(para or "")
                    local number = caller_str:match("(%d+)")
                    if number then
                        local digits_chinese = number_to_digits_chinese(number)
                        tts.init()
                        tts.play("[m53]" .. digits_chinese .. "，来电")
                    end
                end
            elseif event == "MSG_CONNECTED" then
                if g_sip_status == "STATE_DIALING" or g_sip_status == "STATE_INCOMING" then
                    g_sip_status = "STATE_CONNECTED"
                    sys.publish("SIP_APP_MAIN_CONNECTED")
                    _G.uart_send_raw("[SIP_ENV]"," ","SIP_APP_MAIN_CONNECTED")
                    start_busy_report()
                end
            elseif event == "MSG_DISCONNECTED" then
                if g_sip_status == "STATE_DIALING" or g_sip_status == "STATE_INCOMING" or g_sip_status == "STATE_CONNECTED" then
                    g_sip_status = "STATE_READY"
                    stop_busy_report() -- 通话挂断，停止BUSY上报
                    sys.publish("SIP_APP_MAIN_DISCONNECTED")
                    _G.uart_send_raw("[SIP_ENV]"," ","SIP_APP_MAIN_DISCONNECTED")
                    if g_wait_call_end then
                        g_call_result = "COMPLETE"
                        g_wait_call_end = false
                    end
                end
            else
                log.warn("c", "5V", event)
            end
        end
        ::EXCEPTION_PROC::
        stop() -- stop内部会调用stop_busy_report
        if g_sip_status ~= "STATE_INITING" then
            sys.publish("SIP_APP_MAIN_LOSE")
        end
        sys.cleanMsg(TASK_NAME)
        if stop_requested then
            break
        else
            sys.wait(5000)
        end
    end
    stop_busy_report()
    exsip.on(nil)
    g_sip_status = "STATE_IDLE"
    g_task_running = false
    -- SAM | 2026-10-24 +08:00 | Only announce stopped after task cleanup; consumers recheck the live snapshot before marking an idle call.
    sys.publish("SIP_APP_MAIN_STOPPED")
    log.info("c", "5W")
end
-- ==================== 任务启停控制（异步） ====================
local function start_task()
    if g_task_running then
        log.info("sip", "5X")
        return true
    end

    -- SAM | 2026-11-02 +08:00 | user_cfg is loaded by config.lua's task; keep built-in SIP_CONFIG until it exists.
    if type(user_cfg) == "table" then
        SIP_CONFIG.sip_server_addr = user_cfg.sip_url
        SIP_CONFIG.sip_server_port = user_cfg.sip_port
        SIP_CONFIG.sip_username = user_cfg.username
        SIP_CONFIG.sip_password = user_cfg.password
    end

    log.info("sip", SIP_CONFIG.sip_server_addr,SIP_CONFIG.sip_server_port,SIP_CONFIG.sip_username,SIP_CONFIG.sip_password)

    g_task_running = true
    g_sip_status = "STATE_INITING"
    -- SAM | 2026-10-24 +08:00 | Retire stopped/ready permission before starting a new SIP session.
    sys.publish("SIP_APP_MAIN_STARTING")
    sys.taskInitEx(sip_app_main_task_func, TASK_NAME)
    log.info("sip", "08")
    --tts.init()
    --tts.play("[m53]" .. "sip init ok")
    return true
end
local function stop_task_async()
    if not g_task_running then
        return true
    end
    sys.sendMsg(TASK_NAME, "cmd", "MSG_STOP")
    log.info("sip", "09")
    return true
end
-- ==================== AT命令注册 ====================
_G.at_cmd_handlers = _G.at_cmd_handlers or {}
-- 1. SIP_INIT
_G.at_cmd_handlers["SIP_INIT"] = function(cmd, uart_send)
    if g_task_running then
        uart_send("ERROR: already initialized")
        return
    end
    start_task()
    uart_send("OK")
end
-- 2. SIP_DEINIT
_G.at_cmd_handlers["SIP_DEINIT"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: not initialized")
        return
    end
    sys.taskInit(function()
        stop_task_async()
        local timeout = 0
        while g_task_running and timeout < 30 do
            sys.wait(100)
            timeout = timeout + 1
        end
        if audio_drv.deinitAudioDevice then
            audio_drv.deinitAudioDevice()
        else
            log.warn("sip", "5Y")
        end
        uart_send("OK")
    end)
end
-- 3. SIP_DIAL
_G.at_cmd_handlers["SIP_DIAL"] = function(cmd, uart_send)
    -- SAM | 2026-10-14 21:09 +08:00 | Reject a new dial on unavailable SIM/IP instead of queuing it for a later replacement card.
    if not sim_network.ip_ready() then uart_send("ERROR: SIM/IP unavailable"); return end
    if not g_task_running then
        uart_send("ERROR: SIP not initialized")
        return
    end
    local number = cmd and cmd:match("SIP_DIAL=(.+)") or "110119"
    if not number or number == "" then
        number = "110119"
    end
    sys.sendMsg(TASK_NAME, "at", "MSG_DIAL", number)
    uart_send("OK")
end
-- 4. SIP_ACCEPT
_G.at_cmd_handlers["SIP_ACCEPT"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: SIP not initialized")
        return
    end
    if g_sip_status == "STATE_INCOMING" then
        sys.sendMsg(TASK_NAME, "at", "MSG_ACCEPT")
        uart_send("OK")
    else
        uart_send("ERROR: no incoming call")
    end
end
-- 5. SIP_HANGUP
_G.at_cmd_handlers["SIP_HANGUP"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: SIP not initialized")
        return
    end
    sys.sendMsg(TASK_NAME, "at", "MSG_HANGUP")
    uart_send("OK")
end
-- 6. SIP_STATUS
_G.at_cmd_handlers["SIP_STATUS"] = function(cmd, uart_send)
    local status_str = g_sip_status
    uart_send("+SIP: " .. status_str)
end

-- 一键通话 SIP_CALL
_G.at_cmd_handlers["SIP_CALL"] = function(cmd, uart_send)
    if not sim_network.ip_ready() then uart_send("ERROR: SIM/IP unavailable"); return end
    local request_generation=sim_network.generation()
    local number = cmd and cmd:match("SIP_CALL=(.+)") or "10003"
    if not number or number == "" then
        number = "10003"
    end
    sys.taskInit(function()
        -- SAM | 2026-10-14 21:09 +08:00 | A deferred call belongs to its original network; SIM replacement must not start a new dial.
        if request_generation~=sim_network.generation() or not sim_network.ip_ready() then
            uart_send("ERROR: network changed"); return
        end
        if not g_task_running then
            start_task()
            local ready_wait = 0
            while g_sip_status ~= "STATE_READY" and ready_wait < 100 and request_generation==sim_network.generation() do
                sys.wait(100)
                ready_wait = ready_wait + 1
            end
            if g_sip_status ~= "STATE_READY" then
                uart_send("ERROR: sip register timeout")
                return
            end
        end
        if request_generation~=sim_network.generation() or not sim_network.ip_ready() then
            uart_send("ERROR: network changed"); return
        end
        g_wait_call_end = true
        g_call_result = nil
        sys.sendMsg(TASK_NAME, "at", "MSG_DIAL", number)
        local total_wait = 0
        while g_wait_call_end and total_wait < 600 do
            sys.wait(100)
            total_wait = total_wait + 1
        end
        if g_call_result == "COMPLETE" then
            uart_send("OK: call finished")
        elseif g_call_result == "DIAL_FAIL" then
            uart_send("ERROR: dial failed")
        elseif g_call_result == "BUSY" then
            uart_send("ERROR: sip busy")
        elseif g_call_result == "ERROR" then
            uart_send("ERROR: sip runtime error")
        else
            uart_send("ERROR: call timeout")
        end
        -- 通话结束自动销毁SIP，按需开启
        -- stop_task_async()
        -- while g_task_running do sys.wait(100) end
    end)
    uart_send("OK: call start")
end

log.info("5Z", "60")
return M
