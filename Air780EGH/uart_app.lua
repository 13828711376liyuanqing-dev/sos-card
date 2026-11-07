-- [FIX] 用 pcall 包裹 require，避免 exgnss 不存在时导致 Lua VM 崩溃
local exgnss = nil
local _exgnss_ok, _exgnss_err = pcall(function() exgnss = require("exgnss") end)
if not _exgnss_ok or not exgnss then
    log.warn("5", "6c" .. tostring(_exgnss_err) .. "6d")
    exgnss = { rmc = function() return nil end, setup = function() end, open = function() end }
end
local UART_ID = 1
--local UART_ID = uart.VUART_0

-- DFU 主机模块（GR5526 固件升级），升级期间切换 UART 接收为二进制帧解析
_G.dfu_transfer = require("dfu_transfer")

-- 1. 接收帧缓存：解决命令被吃掉、分包粘连
local recv_raw_buf = ""
local FRAME_END = "\r\n"
-- SAM | 2026-10-10 16:48 +08:00 | Bound UART buffers because malformed input must not exhaust memory.
local RX_LIMIT, TX_LIMIT, TX_BYTES = 4096, 64, 32768
local recv_discard, recv_prev_cr = false, false
local send_bytes = 0

-- 2. 异步发送队列 + 发送协程：异步输出不阻塞
local send_queue = {}
-- SAM | 2026-10-23 +08:00 | Binary uses the same serialized writer; reserve queue capacity for business traffic.
local ota_wire = require("ota_wire")
-- SAM | 2026-10-25 +08:00 | All UART1 traffic shares physical-completion and GR Flash-silence ownership.
local window_module=require("ota_uart_window")
local window=window_module.new({
    now=function()return mcu.ticks()end,
    write=function(s)return uart.write(UART_ID,s)end,
    event=function(e,v)
        if e=='DFU_TX_SENT' and _G.dfu_transfer and _G.dfu_transfer.on_sent then _G.dfu_transfer.on_sent(UART_ID)
        else sys.publish(e,v) end
    end,
    idle=function()return not _G.dfu_transfer_active and type(_G.ota_uart_idle)=='function' and _G.ota_uart_idle()==true end})
_G.ota_uart_owned=function()return window:busy() or window:blocked() or #send_queue>0 end
-- SAM | 2026-10-26 +08:00 | Read fault latch separately from queue ownership; historical quiet denial is not a permanent writer fault.
_G.ota_uart_faulted=function()return window:blocked()end
-- SAM | 2026-10-25 +08:00 | Legacy binary frames share the physical writer; no second sent callback registration.
_G.dfu_uart_write=function(raw)
    if not _G.dfu_transfer_active or window:blocked() or not window:available() then return 0 end
    return window:write(raw,nil,244) and #raw or 0
end
local binary_pending = 0
_G.ota_uart_send = function(frame)
    if _G.dfu_transfer_active or window:blocked() or not ota_wire.decode(frame) then return false end
    if window:owns(frame) then return true end
    for _,item in ipairs(send_queue) do if type(item)=='table' and item.binary==frame then return true end end
    if binary_pending >= 4 or
       #send_queue >= TX_LIMIT-4 or send_bytes + #frame > TX_BYTES-4096 then return false end
    send_queue[#send_queue+1]={binary=frame}
    binary_pending=binary_pending+1;send_bytes=send_bytes+#frame
    return true
end
-- SAM | 2026-10-23 +08:00 | A pause cancels only queued OTA frames; retain SOS and all other business text.
_G.ota_uart_cancel = function()
    window:cancel()
    for i=#send_queue,1,-1 do
        local item=send_queue[i]
        if type(item)=="table" or (type(item)=='string' and item:sub(1,8)=='OTA_CTL=') then
            send_bytes=send_bytes-#(type(item)=='table' and item.binary or item)
            if type(item)=='table' then binary_pending=binary_pending-1 end
            table.remove(send_queue,i)
        end
    end
    return true
end
local send_task_running = false

-- ========== 全局AT命令注册表（兼容原有sip.lua） ==========
_G.at_cmd_handlers = _G.at_cmd_handlers or {}

-- ==================== 异步发送底层封装 ====================
local ota_reject=require('ota_platform').diag
local function decode_json(s,n) return pcall(function()return json.decode(s:sub(n))end) end
local function uart_async_push(...)
    -- 组装一行字符串
    local parts = {}
    for _, v in ipairs({...}) do
        parts[#parts+1]=tostring(v)
    end
    local line = table.concat(parts, " ") .. FRAME_END
    local is_ota=line:sub(1,8)=='OTA_CTL='
    if is_ota and window:blocked() then return ota_reject('LOCKED') end

    -- ====================================================================
    --  DFU 传输期间 UART 通道独占过滤
    --  当 _G.dfu_transfer_active == true 时，只允许 "+DFU:" 开头的
    --  DFU 流程控制文本（STARTED/DONE/ERROR/PROGRESS/ABORTED）通过，
    --  其他所有业务文本（[MQTT_STAT]/[NET_ENV]/[SIM_ENV]/[TTS]/GNSS 等）
    --  全部静默丢弃，不进入发送队列，避免文本数据污染 GR5526 端
    --  dfu_port 的逐字节帧解析状态机。
    --  注意：DFU 二进制帧通过 uart.write() 直接发送（dfu_transfer.lua），
    --  不走此函数，不受此过滤影响。
    -- ====================================================================
    if _G.dfu_transfer_active and not line:find("^%+DFU:") then
        if is_ota then ota_reject('DFU') end
        return  -- 静默丢弃，不入队
    end

    if #line > 4096 or #send_queue >= TX_LIMIT or send_bytes + #line > TX_BYTES then
        if is_ota then return ota_reject('QUEUE') end
        log.error("5", "6e")
        return false
    end
    send_queue[#send_queue+1]=line
    if is_ota then ota_reject(nil) end
    send_bytes = send_bytes + #line
    return true
end

-- 原始对外发送接口（全局，给sip模块调用 _G.uart_send_raw）
_G.uart_send_raw = uart_async_push
-- SAM | 2026-11-01 +08:00 | Lets update.lua stop the OTA power hold once the OTA UART window has failed (it stays failed until reboot).
_G.ota_window_blocked = function() return window:blocked() end

-- 带命令前缀的发送包装器（原有AT handler使用）
local function make_uart_sender(cmd_name)
    return function(...)
        local prefix = "[" .. cmd_name .. "] "
        uart_async_push(prefix, ...)
    end
end

-- 独立发送协程，循环消费发送队列
local function send_worker()
    send_task_running = true
    while true do
        -- SAM | 2026-10-10 16:51 +08:00 | Release the antenna tag on DFU takeover because binary UART owns the session.
        if _G.dfu_transfer_active and _G.antenna_test_stop then _G.antenna_test_stop() end
        window:pump()
        if #send_queue > 0 and window:available() and (not _G.dfu_transfer_active or (type(send_queue[1])=="string" and send_queue[1]:find("^%+DFU:"))) then
            local item = table.remove(send_queue, 1)
            local binary = type(item)=="table"
            local line = binary and item.binary or item
            if binary then binary_pending=binary_pending-1 end
            send_bytes = send_bytes - #line
            -- SAM | 2026-10-10 16:48 +08:00 | Recheck ownership at dequeue because DFU may start after enqueue.
            if not _G.dfu_transfer_active or line:find("^%+DFU:") then
                local request=binary and true or nil
                if not binary and line:sub(1,8)=='OTA_CTL=' then
                    local ok,v=decode_json(line,9)
                    if ok and type(v)=='table' then request=v end
                end
                -- SAM | 2026-10-25 +08:00 | Recheck the fault latch at dequeue because runtime cancellation is asynchronous.
                if window:blocked() and (binary or line:sub(1,8)=='OTA_CTL=') then
                    sys.publish("OTA2_TX_FAILED",binary and ota_wire.decode(line) or nil)
                else window:write(line,request) end
            elseif binary then
                sys.publish("OTA2_TX_FAILED", ota_wire.decode(line))
            end
            if not binary then log.info("6f", "6g", line:sub(1, #line-2)) end
        else
            -- 队列为空休眠，降低CPU
            sys.wait(10)
        end
    end
end

-- 启动发送异步协程
local function start_send_worker()
    if not send_task_running then
        sys.taskInit(send_worker)
        log.info("5", "6h")
    end
end

-- SAM | 2026-10-10 16:48 +08:00 | Anchor routing and bound stream parsing because GNSS substrings swallowed registered commands.
local function dispatch_frame(frame)
    if frame == "" then return end
    if frame:sub(1,7)=='OTA_GR=' then
        local ok,v=decode_json(frame,8)
        if ok then window:on_control(v) end
    end
    -- SAM | 2026-10-13 09:14 +08:00 | Route only complete internal business frames before legacy AT parsing; DFU still owns binary mode.
    if frame:sub(1,8)=="BUS_CMD=" then
        local ok,v=decode_json(frame,9)
        if ok and type(v)=='table' and v.op=='hello' then window:hello() end
        require("business_runtime").command(frame:sub(9))
        return
    end
    local key
    for candidate in pairs(_G.at_cmd_handlers) do
        if frame:sub(1, #candidate) == candidate then
            local tail = frame:sub(#candidate + 1, #candidate + 1)
            if tail == "" or candidate:sub(-1) == "=" or tail:match("[=,%s]") then
                if not key or #candidate > #key then key = candidate end
            end
        end
    end
    if key then
        local ok, err = pcall(_G.at_cmd_handlers[key], frame, make_uart_sender(key))
        if not ok then log.error("5", "6i", key, tostring(err)) end
    elseif frame:match("^ATD%d+;?$") then
        cc.dial(0, frame:match("^ATD(%d+)"))
    elseif frame == "ATH" then cc.hangUp(0)
    elseif frame == "ATA" then cc.accept(0)
    elseif frame == "GNSS" then
        local rmc = exgnss.rmc(0)
        if rmc then
            uart_async_push("GNSS: ", string.format("lat=%.5f, lng=%.5f", rmc.lat or 0, rmc.lng or 0))
        else uart_async_push("GNSS: ", "未定位") end
    else log.info("5", "6j", frame) end
end

-- SAM | 2026-10-23 +08:00 | Preserve text framing while OTA2 payload bypasses all command handlers.
local function receive_text(s)
    for i=1,#s do
        local c=s:sub(i,i)
        if recv_discard then
            if recv_prev_cr and c=="\n" then recv_discard=false end
        else
            recv_raw_buf=recv_raw_buf..c
            if recv_prev_cr and c=="\n" then
                local frame=recv_raw_buf:sub(1,-3);recv_raw_buf="";dispatch_frame(frame)
            elseif #recv_raw_buf>RX_LIMIT then
                recv_raw_buf,recv_discard="",true;log.error("5","6k")
            end
        end
        recv_prev_cr=c=="\r"
    end
end
local rx_mux=ota_wire.mux(receive_text,function(frame)
    if not window:on_frame(frame) then sys.publish("OTA2_FRAME",frame) end
end)
local function uart_recv_cb()
    while true do
        local s=uart.read(UART_ID,1024)
        if not s or #s==0 then break end
        local now=nil
        if mcu and type(mcu.ticks)=="function" then
            local ok,value=pcall(mcu.ticks);if ok and type(value)=="number" then now=value end
        end
        for i=1,#s do
            if _G.dfu_transfer and _G.dfu_transfer.is_binary_mode() then
                recv_raw_buf,recv_discard,recv_prev_cr="",false,false
                rx_mux:lost();_G.dfu_transfer.binary_recv(s:sub(i));break
            end
            rx_mux:feed(s:sub(i,i),now)
        end
    end
end

-- ==================== 服务器下行消息订阅（改用异步队列发送） ====================
local function recv_data_from_server_proc(prefix, topic, payload)
    -- SAM | 2026-10-13 09:14 +08:00 | Never turn untrusted MQTT bytes into internal UART frames or echo unknown customer commands.
    if type(topic)~="string" or type(payload)~="string" or
       topic:find("[%c]") or payload:find("[%c]") then
        log.warn("5", "6l")
        return
    end
    if topic:find("^/iotplat/render3/WARNCARD3/") then
        log.warn("5", "6m", #payload)
        return
    end
    log.info("5", "6n", prefix, topic, #payload)
    uart_async_push(prefix..topic..","..payload)
    sys.publish("SEND_DATA_REQ", "timer", mobile.imei().."/timer/up", payload, 1)
end

-- ==================== 初始化 & 注册 ====================
-- 串口硬件初始化
-- 恢复原始 4 参数版本，避免额外参数导致 UART 配置错误
-- 原始版本已验证可正常通信（GR5526 能收到数据并进入 RECEIVING 状态）
uart.setup(UART_ID, 460800, 8, 1)
uart.on(UART_ID, "receive", uart_recv_cb)
-- SAM | 2026-10-25 +08:00 | One sent callback owner; legacy DFU is rejected while the OTA writer owns UART1.
uart.on(UART_ID, "sent",function()window:sent()end)

--uart.setup(UART_ID, 115200)
--uart.on(UART_ID, "receive", uart_recv_cb)

-- 启动异步发送队列
start_send_worker()

-- 订阅服务器下行推送
sys.subscribe("RECV_DATA_FROM_SERVER", recv_data_from_server_proc)
sys.subscribe("UART_SEND_DATA", function(data)
    uart_async_push("", data)
end)

-- 内置测试命令 SEND55ON
_G.at_cmd_handlers["SEND55ON"] = function(cmd, uart_send)
    -- 直接写入发送队列，不阻塞
    uart_async_push(string.rep(string.char(0x55), 10))
end

-- ====================================================================
--  AT INFO: 查询 Cat1 模组完整状态
--  GR5526 端发送 "AT INFO\r\n" -> Cat1 返回状态信息
--  用于诊断 Cat1 是否上电、网络是否正常、固件文件是否存在
-- ====================================================================
_G.at_cmd_handlers["AT_INFO"] = function(cmd, uart_send)
    -- 安全调用辅助：任何 API 不存在都返回默认值，不崩溃
    local function safe_call(fn, ...)
        if type(fn) ~= "function" then return nil end
        local ok, result = pcall(fn, ...)
        if ok then return result end
        return nil
    end

    -- 1. 基础信息（全部 pcall 包裹，避免 API 不存在导致崩溃）
    local ver = _G.VERSION or "unknown"
    local model = safe_call(hmeta and hmeta.model) or "unknown"
    local imei = safe_call(mobile and mobile.imei) or "unknown"
    local imsi = safe_call(mobile and mobile.imsi) or "无SIM"
    local sim_id = safe_call(mobile and mobile.simid) or 0

    -- 2. 网络状态
    -- SAM | 2026-10-20 16:36 +08:00 | Report the real numeric registration value because nonexistent getStatus falsely reported an unregistered working modem.
    local net_info = safe_call(mobile and mobile.status)
    local net_status = type(net_info)=="number" and ("REG="..tostring(net_info)) or "UNKNOWN"

    -- 3. 信号强度
    -- SAM | 2026-10-20 16:36 +08:00 | Reuse the SIM-gated mobile.csq reading so AT_INFO and business signal cannot diverge.
    local csq_val = require("netdrv_device").csq()

    -- 4. 固件文件检查（DFU 升级包）
    local fw_exists = false
    local fw_size = 0
    local fw_path = "/gr5526_fw.bin"
    local f = io.open(fw_path, "rb")
    if f then
        fw_exists = true
        fw_size = f:seek("end") or 0
        f:close()
    end

    -- 5. DFU 传输状态
    local dfu_state = "空闲"
    if _G.dfu_transfer_active then
        dfu_state = "传输中"
    end

    -- 6. 组装响应（多行，每行一个字段）
    uart_send("=== CAT1 STATUS ===")
    uart_send("LuatOS Ver: ", ver)
    uart_send("Model: ", model)
    uart_send("IMEI: ", imei)
    uart_send("IMSI: ", imsi)
    uart_send("SIM ID: ", sim_id)
    uart_send("Network: ", net_status)
    uart_send("CSQ: ", csq_val)
    uart_send("FW File: ", fw_path)
    uart_send("FW Exists: ", fw_exists and "YES" or "NO")
    uart_send("FW Size: ", fw_size, " bytes")
    uart_send("DFU State: ", dfu_state)
    uart_send("=== END ===")
end

log.info("5", "6o")
