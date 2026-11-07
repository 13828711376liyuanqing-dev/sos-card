--[[
@module  ntp_at_cmd
@summary NTP时间同步AT命令封装
@version 1.0
@date    2026-01-21
@author  AI Assistant
@usage
提供以下AT命令控制NTP同步：
- NTPSTATUS   : 查询当前时间同步状态及系统时间
- NTPSYNC     : 立即触发一次NTP时间同步
- NTPSERVER   : 设置自定义NTP服务器（参数: 服务器地址[,立即同步标志]）
- NTPCFG      : 配置同步间隔（参数: 成功间隔秒数,失败间隔秒数）
- NTPSTART    : 启动SNTP同步循环任务
- NTPSTOP     : 停止SNTP同步循环任务
]]

-- =================== 原ntp_test模块代码（按需保留） ===================
local ntp_servers = {
    "ntp.aliyun.com",
    "ntp.air32.cn",
    "time1.cloud.tencent.com"
}

-- 运行时配置
local g_ntp_ok_interval = 3600 * 1000   -- 成功同步后等待毫秒数（默认1小时）
local g_ntp_fail_interval = 10 * 1000    -- 失败后重试间隔毫秒数（默认10秒）

-- 任务控制变量
local ntp_keep_running = false
local ntp_task_co = nil

-- 打印时间信息的工具函数
local function print_time_details()
    log.info("sntp", "5k", os.date())
    log.info("sntp", "5l", os.date("!%c"))
    log.info("sntp", "5m", os.date("%Y-%m-%d %H:%M:%S"))
    log.info("sntp", "5n", os.date("!%Y-%m-%d %H:%M:%S"))
    local rtc_time = rtc.get()
    log.info("sntp", "5o", json.encode(rtc_time))
    log.info("sntp", "5p", os.time())
    local local_struct_time = os.date("*t")
    log.info("sntp", "5q", json.encode(local_struct_time))
    log.info("sntp", "5r", os.time(local_struct_time))
end

local function print_high_precision_time()
    local ntp_time = socket.ntptm()
    if ntp_time and ntp_time.tsec then
        log.info("5s", json.encode(ntp_time))
        log.info("sntp", "5t", string.format("%u.%03d", ntp_time.tsec, ntp_time.tms))
    else
        log.warn("sntp", "5u")
    end
end

-- 订阅NTP错误消息（保留）
sys.subscribe("NTP_ERROR", function(err_info)
    log.error("sntp", "5v", err_info or "5w")
end)

-- =================== 可控的SNTP同步循环 ===================
local function sntp_sync_loop_ctrl()
    -- 等待网络就绪（支持中途停止）
    while not socket.adapter(socket.dft()) do
        if not ntp_keep_running then return end
        log.warn("sntp", "q", socket.dft())
        sys.waitUntil("IP_READY", 1000)
    end
    log.info("sntp", "V", socket.dft())

    while ntp_keep_running do
        log.info("sntp", "5x")
        -- 使用当前设置的NTP服务器（若自定义列表非空则用第一个）
        local server = ntp_servers[1]  -- 默认使用列表第一个
        if server then
            socket.sntp(server)
        else
            socket.sntp()   -- 使用内置默认
        end

        local sync_success = sys.waitUntil("NTP_UPDATE", 5000)
        if sync_success then
            log.info("sntp", "5y")
            print_time_details()
            print_high_precision_time()
            -- 等待成功间隔，期间可被停止命令中断
            local remain = g_ntp_ok_interval
            while remain > 0 and ntp_keep_running do
                local step = math.min(remain, 1000)
                sys.wait(step)
                remain = remain - step
            end
        else
            log.warn("sntp", "5z")
            local remain = g_ntp_fail_interval
            while remain > 0 and ntp_keep_running do
                local step = math.min(remain, 1000)
                sys.wait(step)
                remain = remain - step
            end
        end
    end
    log.info("sntp", "5A")
end

-- =================== AT命令处理函数注册 ===================
_G.at_cmd_handlers = _G.at_cmd_handlers or {}

-- 1. NTPSTATUS : 查询状态及当前时间
_G.at_cmd_handlers["NTPSTATUS"] = function(cmd, uart_send)
    local rtc_time = rtc.get()
    local is_synced = (rtc_time.year > 2020)   -- 简单判断：RTC年份大于2020认为已同步过
    if is_synced then
        local local_str = os.date("%Y-%m-%d %H:%M:%S")
        local utc_str = os.date("!%Y-%m-%d %H:%M:%S")
        local timestamp = os.time()   -- 新增：秒级时间戳
        local high_prec = ""
        local ntp_tm = socket.ntptm()
        if ntp_tm and ntp_tm.tsec then
            high_prec = string.format("%u.%03d", ntp_tm.tsec, ntp_tm.tms)
        end
        local response = string.format("+NTP: OK,local_str=%s,utc_str=%s,timestamp=%d,high_prec=%s", local_str, utc_str, timestamp, high_prec)
        uart_send(response)
    else
        uart_send("+NTP: NOT_SYNCED")
    end
end

-- 2. NTPSYNC : 立即触发一次同步（同步等待结果）

sys.taskInit(function()
    -- 确保网络就绪
    while not socket.adapter(socket.dft()) do
        sys.waitUntil("IP_READY", 1000)
    end
    
    local success = false
    local timestamp = nil
    
    -- 确定要尝试的服务器列表：若自定义列表非空则用它，否则使用一次默认同步（传 nil）
    local servers = (ntp_servers and #ntp_servers > 0) and ntp_servers or { nil }
    
    for _, server in ipairs(servers) do
        log.info("t", "5B", server or "07")
        if server then
            socket.sntp(server)
        else
            socket.sntp()   -- 使用内置默认服务器
        end
        
        -- 等待同步结果，超时5秒
        local succ = sys.waitUntil("NTP_UPDATE", 5000)
        if succ then
            success = true
            timestamp = os.time()
            log.info("t", "5C", timestamp)
            break
        else
            log.warn("t", "5D", server or "07")
            sys.wait(500)   -- 失败后短暂延迟再试下一个
        end
    end
    
    if success then
        _G.uart_send_raw("[NTPSYNC]" .. tostring(timestamp))
    else
        _G.uart_send_raw("[NTPSYNC]" .. "ERROR")
    end
end)

-- 3. NTPSERVER : 设置NTP服务器 [服务器地址[,立即同步标志]]
-- 参数示例： ntp.aliyun.com,1  或  time.google.com,0
_G.at_cmd_handlers["NTPSERVER"] = function(cmd, uart_send)
    if not cmd or cmd == "" then
        uart_send("ERROR")
        return
    end
    local server, sync_now = cmd:match("([^,]+),?(%d*)")
    if server and #server > 0 then
        -- 修改服务器列表，将第一个改为新服务器
        ntp_servers[1] = server
        -- 可选：立即同步一次
        if sync_now == "1" then
            sys.taskInit(function()
                while not socket.adapter(socket.dft()) do
                    sys.waitUntil("IP_READY", 1000)
                end
                socket.sntp(server)
                sys.waitUntil("NTP_UPDATE", 5000)
                uart_send("OK")
            end)
        else
            uart_send("OK")
        end
    else
        uart_send("ERROR")
    end
end

-- 4. NTPCFG : 配置间隔 [成功间隔秒数,失败间隔秒数] 如: 3600,10
_G.at_cmd_handlers["NTPCFG"] = function(cmd, uart_send)
    local ok_sec, fail_sec = cmd:match("(%d+),?(%d*)")
    if ok_sec then
        g_ntp_ok_interval = tonumber(ok_sec) * 1000
        if fail_sec and fail_sec ~= "" then
            g_ntp_fail_interval = tonumber(fail_sec) * 1000
        end
        uart_send("OK")
    else
        uart_send("ERROR")
    end
end


-- 6. NTPSTART : 启动同步循环任务
_G.at_cmd_handlers["NTPSTART"] = function(cmd, uart_send)
    if ntp_keep_running then
        uart_send("ALREADY_RUNNING")
        return
    end
    ntp_keep_running = true
    ntp_task_co = sys.taskInit(sntp_sync_loop_ctrl)
    uart_send("OK")
end

-- 7. NTPSTOP : 停止同步循环任务
_G.at_cmd_handlers["NTPSTOP"] = function(cmd, uart_send)
    if not ntp_keep_running then
        uart_send("NOT_RUNNING")
        return
    end
    ntp_keep_running = false
    -- 发送一个空事件可以唤醒正在等待中的协程（可选）
    sys.publish("NTP_STOP_WAKE")
    -- 短暂延时等待协程退出
    sys.wait(200)
    ntp_task_co = nil
    uart_send("OK")
end

-- =================== 移除原始自动启动（注释原末尾的 sys.taskInit(sntp_sync_loop)） ===================
-- 原文件最后的 sys.taskInit(sntp_sync_loop) 已被删除，改为AT命令手动控制启动