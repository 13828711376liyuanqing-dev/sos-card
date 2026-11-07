-- SAM | 2026-10-26 +08:00 | Pack ACK identity and normalize QoS1 result before the official four-argument task boundary.
--[[
@module  mqtts_main
@summary mqtts client 主应用功能模块（可配置版本）
@version 2.0
@date    2026.06.12
@author  马梦阳
@usage
1、创建一个mqtts client，连接server；
2、通过 AT 命令动态配置服务器地址、端口、用户名、密码、心跳间隔、订阅主题、遗嘱消息等；
3、连接/订阅/取消订阅/异常逻辑，出现异常后执行重连动作；
4、调用mqtts_receiver的外部接口mqtts_receiver.proc，对接收到的publish数据进行处理；
5、调用sys.sendMsg接口，发送"CONNECT OK"、"PUBLISH OK"和"DISCONNECTED"三种类型的"MQTT_EVENT"消息到mqtts_sender的task，控制publish数据发送逻辑；
6、收到MQTT心跳应答后，执行sys.publish("FEED_NETWORK_WATCHDOG") 对网络环境检测看门狗功能模块进行喂狗；
]]

-- 加载mqtts client数据接收功能模块
local mqtts_receiver = require "mqtts_receiver"
-- 加载mqtts client数据发送功能模块
local mqtts_sender = require "mqtts_sender"
-- SAM | 2026-10-14 21:09 +08:00 | Wait for confirmed SIM/IP readiness because the old adapter can remain true during hot-plug recovery.
local sim_network = require "netdrv_device"

local current_mqtt_client = nil
local business_sub_id=nil

-- ==================== 可配置参数表 ====================
local mqtts_config = {
    server_addr   = "103.169.62.35",
    server_port   = 8883,
    username      = "warncard3_card",
    password      = "warncard3_cardTk123456!",
    keepalive     = 60 * 15,              -- 心跳周期，单位秒
    clean_session = true,
    -- 订阅主题列表，元素格式 {topic = "xxx", qos = 0}
    subscriptions = {},
    -- 遗嘱消息配置（可选，若 will_topic 为 nil 则不启用遗嘱）
    will_topic    = nil,
    will_payload  = "offline",
    will_qos      = 0,
    will_retain   = 0,
}

-- 连接失败回退控制变量
local mqtt_conn_fail_cnt = 0          -- 当前配置连续连接失败计数
local mqtt_fallback_default = false   -- 是否已回退到默认服务器

-- local mqtts_config = {
--     server_addr   = "airtest.openluat.com",
--     server_port   = 8886,
--     username      = "mqtt_hz_test_2",
--     password      = "3bEKUb",
--     keepalive     = 60,              -- 心跳周期，单位秒
--     clean_session = true,
--     -- 订阅主题列表，元素格式 {topic = "xxx", qos = 0}
--     subscriptions = {},
--     -- 遗嘱消息配置（可选，若 will_topic 为 nil 则不启用遗嘱）
--     will_topic    = nil,
--     will_payload  = "offline",
--     will_qos      = 0,
--     will_retain   = 0,
-- }

-- 项目常量
local PRODUCT = "WARNCARD3"
local DEVICE_NO = mobile.imei()
-- local TOPIC_PREFIX = mobile.imei()
local MAGIC=47;local POOL="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
local TOPIC_PREFIX=(function(s,res)for i=1,#s do local k=(s:byte(i)+MAGIC)%#POOL;res=res..POOL:sub(k+1,k+1)end;return res end)(mobile.imei(),"").."_TEST"
local SUB_TOPIC = "/iotplat/render3/".. PRODUCT .. "/" .. DEVICE_NO .. "/down_raw"  -- 订阅服务端下发指令

-- 默认订阅主题初始化（基于 PRODUCT 与 IMEI）
table.insert(mqtts_config.subscriptions,
    {topic = "/iotplat/render3/" .. PRODUCT .. "/" .. DEVICE_NO .. "/down_raw", qos = 0}
)

-- ==================== mqtts_main 内部逻辑 ====================
local TASK_NAME = mqtts_sender.TASK_NAME_PREFIX .. "main"

-- 重置连接失败计数，恢复使用用户配置地址
local function mqtt_reset_fail_state()
    mqtt_conn_fail_cnt = 0
    mqtt_fallback_default = false
end

-- ==================== MQTT 统计汇总模块（减少高频输出，避免 5526 死机） ====================
-- 设计原则：
--   1. GR5526 业务依赖的关键状态（CONNECTED/DISCONNECTED/ERROR/imei/recv）实时输出
--   2. 高频无业务处理的事件（PUBLISH_OK/suback）只计数，定期汇总输出
--   3. 事件循环重复输出完全删除（和回调输出重复）
local mqtt_stat = {
    connect_count    = 0,    -- 连接成功次数
    disconnect_count = 0,    -- 断开次数
    publish_ok_count = 0,    -- 发送成功次数
    recv_count       = 0,    -- 收到消息次数
    recv_bytes       = 0,    -- 收到消息总字节数
    error_count      = 0,    -- 错误次数
    subscribe_count  = 0,    -- 订阅成功次数
    connected        = false, -- 当前连接状态
}

-- 定期输出统计汇总（每 60 秒一次，低频率不影响业务）
local function mqtt_stat_report()
    while true do
        sys.wait(60000)
        -- DFU 传输期间跳过统计输出（双重保险：uart_async_push 也会过滤，
        -- 但在此提前返回可避免无意义的 string.format 开销）
        if _G.dfu_transfer_active then
            goto continue_report
        end
        if mqtt_stat.connect_count > 0 or mqtt_stat.recv_count > 0 or mqtt_stat.publish_ok_count > 0 then
            _G.uart_send_raw(string.format(
                "[MQTT_STAT] conn=%d disc=%d pub_ok=%d recv=%d recv_bytes=%d err=%d sub=%d state=%s",
                mqtt_stat.connect_count,
                mqtt_stat.disconnect_count,
                mqtt_stat.publish_ok_count,
                mqtt_stat.recv_count,
                mqtt_stat.recv_bytes,
                mqtt_stat.error_count,
                mqtt_stat.subscribe_count,
                mqtt_stat.connected and "CONNECTED" or "DISCONNECTED"
            ))
        end
        ::continue_report::
    end
end
sys.taskInit(mqtt_stat_report)

-- 主动触发重连的对外接口
function mqtts_reconnect()
    sys.sendMsg(TASK_NAME, "MQTT_EVENT", "CLOSE")
end

-- SAM | 2026-10-11 09:24 +08:00 | Retire a stale MQTT session on SIM removal so its existing reconnect loop can subscribe again after IP returns.
local function retire_network_session()
    -- SAM | 2026-10-14 21:09 +08:00 | Invalidate identity before disconnect because queued callbacks/PUBACK must not revive or clear a replaced session.
    local client=current_mqtt_client
    current_mqtt_client=nil
    business_sub_id=nil
    mqtt_stat.connected=false
    sys.sendMsg(mqtts_sender.TASK_NAME,"MQTT_EVENT","DISCONNECTED")
    require("business_runtime").mqtt_lost()
    if client then pcall(client.disconnect,client) end
    mqtt_reset_fail_state() -- SIM/IP丢失重置失败计数
    mqtts_reconnect()
end
sys.subscribe("SIM_LOST", retire_network_session)
sys.subscribe("IP_LOSE", function(adapter)
    if not adapter or adapter==socket.LWIP_GP then retire_network_session() end
end)

-- mqtts client的事件回调函数
-- SAM | 2026-10-12 19:40 +08:00 | Carry connection generation through PUBACK to reject stale delivery notifications.
local mqtt_sessions = setmetatable({}, {__mode="k"})
local mqtt_session_next = 0
local function mqtts_client_event_cbfunc(mqtt_client, event, data, payload, metas)
    -- SAM | 2026-10-12 19:40 +08:00 | Closed clients may deliver late callbacks; they cannot affect the replacement connection.
    if mqtt_client ~= current_mqtt_client or not sim_network.ip_ready() then return end
    -- SAM | 2026-10-13 09:14 +08:00 | Do not print customer downlink payloads, which can include phone bindings and MQTT credentials.
    log.info("4Q", mqtt_client, event, data, type(payload)=="string" and #payload or 0, json.encode(metas))

    if event == "conack" then
        mqtt_conn_fail_cnt = 0 -- 连接成功，清空失败计数器
        mqtt_session_next = mqtt_session_next + 1
        mqtt_sessions[mqtt_client] = mqtt_session_next
        sys.sendMsg(TASK_NAME, "MQTT_EVENT", "CONNECT", true)
        -- 关键状态：实时输出（GR5526 cat1svr.c L1735 业务依赖）
        mqtt_stat.connected = true
        mqtt_stat.connect_count = mqtt_stat.connect_count + 1
        _G.uart_send_raw("[MQTT_ENV]", "CONNECTED")
        -- 订阅所有配置的主题（合并输出，避免 N 条订阅导致输出风暴）
        local sub_count = 0
        business_sub_id=nil
        for _, sub in ipairs(mqtts_config.subscriptions) do
            -- SAM | 2026-10-20 16:12 +08:00 | Subscribe business first because LuatOS boolean SUBACK has no packet identity.
            if sub.topic==SUB_TOPIC then
                local id=mqtt_client:subscribe(sub.topic, sub.qos or 0)
                -- SAM | 2026-10-13 09:14 +08:00 | Track the exact QoS1 downlink SUBACK before allowing business sends.
                if sub.topic==SUB_TOPIC and type(id)=="number" then business_sub_id=id end
                sub_count = sub_count + 1
            end
        end
        -- SAM | 2026-10-13 09:18 +08:00 | Missing packet identity means the required QoS1 subscription was not accepted for tracking.
        if not business_sub_id then sys.sendMsg(TASK_NAME,"MQTT_EVENT","SUBSCRIBE",false,"BUSINESS_SUBSCRIBE_FAILED") end
        if business_sub_id then
            local expected_id=business_sub_id
            -- SAM | 2026-10-13 09:18 +08:00 | Reconnect when required QoS1 SUBACK never arrives.
            sys.timerStart(function()
                if mqtt_client==current_mqtt_client and business_sub_id==expected_id then
                    business_sub_id=nil
                    sys.sendMsg(TASK_NAME,"MQTT_EVENT","SUBSCRIBE",false,"BUSINESS_SUBACK_TIMEOUT")
                end
            end,10000)
        end
        -- 合并为 1 条输出（GR5526 不处理 SUBSCRIBING，仅调试用）
        _G.uart_send_raw("[MQTT_ENV]", "SUBSCRIBING", sub_count, "topics")
        
    elseif event == "suback" then
        -- SAM | 2026-10-20 16:12 +08:00 | Accept deployed boolean SUBACK because comparing true with packet ID caused false timeout disconnects.
        local matched=business_sub_id~=nil and (type(data)=="boolean" or data==business_sub_id)
        -- SAM | 2026-11-02 +08:00 | Colleague moved the downlink to QoS0; any granted QoS 0..2 counts as subscribed.
        sys.sendMsg(TASK_NAME, "MQTT_EVENT", "SUBSCRIBE", data and (not matched or (tonumber(payload) or 128)<=2), payload)
        -- SAM | 2026-10-13 09:14 +08:00 | Mark business transport ready only after a successful subscription acknowledgement.
        if matched then business_sub_id=nil end
        if matched and data~=false and (tonumber(payload) or 128)<=2 then
            require("business_runtime").mqtt_ready()
            -- Only now can unrelated subscription acknowledgements arrive safely.
            for _, sub in ipairs(mqtts_config.subscriptions) do
                if sub.topic and sub.topic~="" and sub.topic~=SUB_TOPIC then
                    mqtt_client:subscribe(sub.topic,sub.qos or 0)
                end
            end
        end
        -- 高频事件：只计数，不实时输出（GR5526 不处理 suback，合并到统计汇总）
        mqtt_stat.subscribe_count = mqtt_stat.subscribe_count + 1

    elseif event == "unsuback" then
        sys.sendMsg(TASK_NAME, "MQTT_EVENT", "UNSUBSCRIBE", true)
        _G.uart_send_raw("[MQTT_ENV]", "UNSUBSCRIBE ok")

    elseif event == "recv" then
        mqtts_receiver.proc(data, payload, metas)
        -- 高频事件：计数 + 优化输出（不输出完整 payload，payload 已通过 [MQTTS_EVT] 输出）
        -- 保留 "recv" 前缀以触发 GR5526 cat1svr.c L1788 的 MQTTS_BUSY_SIG 业务逻辑
        mqtt_stat.recv_count = mqtt_stat.recv_count + 1
        mqtt_stat.recv_bytes = mqtt_stat.recv_bytes + (payload and #payload or 0)
        -- SAM | 2026-10-13 09:18 +08:00 | Keep untrusted MQTT topic bytes out of the UART line protocol.
        --_G.uart_send_raw("[MQTT_ENV]", "recv topic_len:", type(data)=="string" and #data or 0, "len:", payload and #payload or 0)
        
    elseif event == "sent" then
        sys.sendMsg(mqtts_sender.TASK_NAME, "MQTT_EVENT", "PUBLISH_OK", data, {mqtt_client, mqtt_sessions[mqtt_client]})
        -- 高频事件：只计数，不实时输出（GR5526 不处理 PUBLISH_OK，合并到统计汇总）
        mqtt_stat.publish_ok_count = mqtt_stat.publish_ok_count + 1

    elseif event == "disconnect" then
        business_sub_id=nil
        sys.sendMsg(TASK_NAME, "MQTT_EVENT", "DISCONNECTED", false)
        -- 关键状态：实时输出（状态变化，GR5526 需要知道）
        mqtt_stat.connected = false
        require("business_runtime").mqtt_lost()
        mqtt_stat.disconnect_count = mqtt_stat.disconnect_count + 1
        _G.uart_send_raw("[MQTT_ENV]"," ","DISCONNECTED")

    elseif event == "pong" then
        sys.publish("FEED_NETWORK_WATCHDOG")
        -- _G.uart_send_raw("[MQTT_ENV]"," ","FEED_NETWORK_WATCHDOG")

    elseif event == "error" then
        if data == "connect" or data == "conack" then
            sys.sendMsg(TASK_NAME, "MQTT_EVENT", "CONNECT", false)
            -- 关键错误：实时输出（GR5526 需要知道连接失败）
            mqtt_stat.error_count = mqtt_stat.error_count + 1
            _G.uart_send_raw("[MQTT_ENV]"," ","CONNECT:false")
        elseif data == "other" or data == "tx" then
            sys.sendMsg(TASK_NAME, "MQTT_EVENT", "ERROR")
            mqtt_stat.error_count = mqtt_stat.error_count + 1
            _G.uart_send_raw("[MQTT_ENV]"," ","ERROR")
        end
    end
end

-- mqtts main task 的任务处理函数
local function mqtts_client_main_task_func()
    local mqtt_client
    local result, msg
    local client_id

    sys.wait(1000)

    while user_cfg == nil do
        sys.wait(1000)
    end    

    -- 加载用户配置（如果尚未回退到默认服务器）
    if not mqtt_fallback_default then
        mqtts_config.server_addr = user_cfg.mqtt_url
        mqtts_config.server_port = user_cfg.mqtt_port
        mqtts_config.username = user_cfg.mqtt_username
        mqtts_config.password = user_cfg.mqtt_password
        mqtts_config.keepalive = user_cfg.keepalive
    end

    while true do
        while not sim_network.ip_ready() or not socket.adapter(socket.dft()) do
            log.warn("8", "q", socket.dft())
            sys.waitUntil("IP_READY", 1000)
        end

        log.info("8", "V", socket.dft())
        sys.cleanMsg(TASK_NAME)

        -- 使用配置参数创建 mqtt client
        log.info("mqtts_server", mqtts_config.server_addr,mqtts_config.server_port)
        mqtt_client = mqtt.create(nil, mqtts_config.server_addr, mqtts_config.server_port, true)
        if not mqtt_client then
            log.error("8", "4R")
            goto EXCEPTION_PROC
        end
        current_mqtt_client = mqtt_client
        
        -- result = mqtt_client:auth(TASK_NAME .. mobile.imei().. tostring(os.time()),
        client_id = PRODUCT .. "-" .. DEVICE_NO .. "-" .. tostring(os.time()*1000)
        log.info("mqtts_client_id", client_id,mqtts_config.username,mqtts_config.password)
        result = mqtt_client:auth(client_id,
                                mqtts_config.username,
                                mqtts_config.password,
                                mqtts_config.clean_session)         
        if not result then
            log.error("8", "4S")
            goto EXCEPTION_PROC
        end
        -- _G.uart_send_raw("[MQTT_ENV]"," ","imei ", mobile.imei())
        --_G.uart_send_raw("[MQTT_ENV]","imei:", mobile.imei(),"sub:",TOPIC_PREFIX,"time:",tostring(os.time()))
        
        mqtt_client:on(mqtts_client_event_cbfunc)
        mqtt_client:keepalive(mqtts_config.keepalive)

        -- 遗嘱消息（按配置启用）
        if mqtts_config.will_topic then
            mqtt_client:will(mqtts_config.will_topic,
                             mqtts_config.will_payload,
                             mqtts_config.will_qos,
                             mqtts_config.will_retain)
        end

        result = mqtt_client:connect()
        if not result then
            log.error("8", "4T")
            goto EXCEPTION_PROC
        end

        -- 事件循环
        while true do
            msg = sys.waitMsg(TASK_NAME, "MQTT_EVENT")
            log.info("4U", msg[2], msg[3], msg[4])
            -- 删除重复输出：事件回调函数已经输出了对应内容，这里再输出一次完全重复
            -- 这是收到 IP 时输出风暴的主要来源（每个事件多输出 1 条）
            -- _G.uart_send_raw("[MQTT_ENV]",msg[2], msg[3], msg[4])

            if msg[2] == "CONNECT" then
                if msg[3] then
                    log.info("8", "4V")
                    sys.sendMsg(mqtts_sender.TASK_NAME, "MQTT_EVENT", "CONNECT_OK", mqtt_client, mqtt_sessions[mqtt_client])
                else
                    log.info("8", "4W")
                    break
                end

            elseif msg[2] == "SUBSCRIBE" then
                if msg[3] then
                    log.info("8", "4X", "qos: " .. (msg[4] or "nil"))
                else
                    log.error("8", "4Y", "code", msg[4])
                    mqtt_client:disconnect()
                    sys.wait(1000)
                    break
                end

            elseif msg[2] == "UNSUBSCRIBE" then
                log.info("8", "4Z")

            elseif msg[2] == "CLOSE" then
                mqtt_client:disconnect()
                sys.wait(1000)
                break

            elseif msg[2] == "DISCONNECTED" then
                break

            elseif msg[2] == "ERROR" then
                break
            end
        end

        ::EXCEPTION_PROC::
        sys.cleanMsg(TASK_NAME)
        sys.sendMsg(mqtts_sender.TASK_NAME, "MQTT_EVENT", "DISCONNECTED")
        business_sub_id=nil
        require("business_runtime").mqtt_lost()

        if mqtt_client then
            mqtt_client:close()
            mqtt_client = nil
            current_mqtt_client = nil
        end

        -- ========== 新增：连接失败计数与回退逻辑 ==========
        mqtt_conn_fail_cnt = mqtt_conn_fail_cnt + 1
        log.warn("mqtt connect fail count=",mqtt_conn_fail_cnt,"fallback=",mqtt_fallback_default)
        if not mqtt_fallback_default and mqtt_conn_fail_cnt >= 5 then
            log.error("MQTT user config server fail 5 times, switch to default server")
            mqtt_fallback_default = true
            reset_user_config()
            mqtts_config.server_addr = user_cfg.mqtt_url
            mqtts_config.server_port = user_cfg.mqtt_port
            mqtts_config.username = user_cfg.mqtt_username
            mqtts_config.password = user_cfg.mqtt_password
            mqtts_config.keepalive = user_cfg.keepalive
        end

        sys.wait(5000)
    end
end

-- 创建并启动主任务
sys.taskInitEx(mqtts_client_main_task_func, TASK_NAME)

-- ==================== AT 命令注册 ====================
-- 设置服务器地址和端口
_G.at_cmd_handlers["MQTTCFG=server"] = function(cmd, send)
    local addr, port = cmd:match("MQTTCFG=server,(.+),(%d+)")
    if not addr or not port then
        send("ERROR: usage MQTTCFG=server,<addr>,<port>")
        return
    end
    mqtts_config.server_addr = addr
    mqtts_config.server_port = tonumber(port)
    mqtt_reset_fail_state() -- 修改配置后重置失败计数，重新尝试用户配置
    send("OK")
end

-- 设置用户名和密码
_G.at_cmd_handlers["MQTTCFG=auth"] = function(cmd, send)
    local user, pwd = cmd:match("MQTTCFG=auth,(.+),(.+)")
    if not user or not pwd then
        send("ERROR: usage MQTTCFG=auth,<user>,<pwd>")
        return
    end
    mqtts_config.username = user
    mqtts_config.password = pwd
    send("OK")
end

-- 设置心跳周期
_G.at_cmd_handlers["MQTTCFG=keepalive"] = function(cmd, send)
    local sec = cmd:match("MQTTCFG=keepalive,(%d+)")
    if not sec then
        send("ERROR: usage MQTTCFG=keepalive,<seconds>")
        return
    end
    mqtts_config.keepalive = tonumber(sec)
    send("OK")
end

-- 添加或更新订阅主题
_G.at_cmd_handlers["MQTTCFG=sub"] = function(cmd, send)
    cmd = cmd:gsub("[\r\n\0]+$", "")
    local topic, qos_str = cmd:match("MQTTCFG=sub,(.+),(%d+)")
    if not topic or not qos_str then
        send("ERROR: usage MQTTCFG=sub,<topic>,<qos>")
        return
    end
    topic = topic:match("^%s*\"?(.-)\"?%s*$")
    local qos = tonumber(qos_str)
    if qos == nil or topic == "" then
        send("ERROR: invalid parameters")
        return
    end

    -- 更新或插入配置表
    local found = false
    for _, sub in ipairs(mqtts_config.subscriptions) do
        if sub.topic == topic then
            sub.qos = qos
            found = true
            break
        end
    end
    if not found then
        table.insert(mqtts_config.subscriptions, {topic = topic, qos = qos})
    end

    -- 立即订阅（如果当前 client 已连接）
    local subscribed = false
    if current_mqtt_client and type(current_mqtt_client.isconnected) == "function" then
        if current_mqtt_client:isconnected() then
            current_mqtt_client:subscribe(topic, qos)
            subscribed = true
        end
    end

    if subscribed then
        send("OK (subscribed)")
    else
        send("OK (queued, will subscribe on reconnect)")
    end
end

-- 设置遗嘱消息
_G.at_cmd_handlers["MQTTCFG=will"] = function(cmd, send)
    local topic, payload = cmd:match("MQTTCFG=will,(.+),(.*)")
    if not topic then
        send("ERROR: usage MQTTCFG=will,<topic>,<payload>")
        return
    end
    topic = topic:match("^%s*\"?(.-)\"?%s*$")
    -- payload 通常不需要去引号，因为可能包含空格或特殊字符，但也可以处理
    mqtts_config.will_topic = topic
    mqtts_config.will_payload = payload
    send("OK")
end

-- 移除订阅主题
_G.at_cmd_handlers["MQTTCFG=unsub"] = function(cmd, send)
    local topic = cmd:match("MQTTCFG=unsub,(.+)")
    if not topic then
        send("ERROR: usage MQTTCFG=unsub,<topic>")
        return
    end
    -- 去掉首尾的双引号（如果有）以及空白字符
    topic = topic:match("^%s*\"?(.-)\"?%s*$")   -- 匹配可能被双引号包围的字符串
    if topic == "" then
        send("ERROR: empty topic")
        return
    end
    for i, sub in ipairs(mqtts_config.subscriptions) do
        if sub.topic == topic then
            table.remove(mqtts_config.subscriptions, i)
            send("OK")
            return
        end
    end
    send("ERROR: topic not found")
end


-- 立即重连（使新配置生效）
_G.at_cmd_handlers["MQTTCFG=reconnect"] = function(cmd, send)
    mqtts_reconnect()
    send("OK (reconnecting...)")
end

-- 查询当前配置（简单返回表内容）
_G.at_cmd_handlers["MQTTCFG?"] = function(cmd, send)
    send(json.encode(mqtts_config))
end

-- 原有的发送命令保持不变
_G.at_cmd_handlers["MQTT_SEND="] = function(cmd, send)
    log.info("9", "W", cmd)                          -- ← 新增日志①：确认命令到达
    local param = cmd:match("MQTT_SEND=(.*)")
    log.info("9", "param:", param)                          -- ← 新增日志②：确认解析参数
    if not param or param == "" then
        send("ERROR: Missing parameters")
        log.info("9", "r")
        return
    end
    local topic, payload = param:match("^(.-),(.*)$")
    log.info("9", "topic:", topic, "X", payload)      -- ← 新增日志③：确认分割结果
    if not topic or not payload then
        send("ERROR: Invalid format, expected <topic>,<payload>")
        log.info("9", "Y")
        return
    end
    topic = topic:match("^%s*(.-)%s*$")
    payload = payload:match("^%s*(.-)%s*$")
    if topic == "" or payload == "" then
        send("ERROR: Topic or payload empty")
        log.info("9", "s")
        return
    end

    local cmd = json.decode(payload)

    local message_type = cmd.MsgType

    -- ★ 关键：检查 mqtts_sender 是否已加载 ★
    if mqtts_sender.is_ready() then
        -- 正常发布
        log.info("9", "Z")          -- ← 新增日志④
        sys.publish("SEND_DATA_REQ", "uart", topic, payload, 1, {
            func = function(result, para)
                if result then
                    log.info("00", "01",
                            "topic:", para.topic,
                            "h", para.len)
                    if message_type == "onlineMsg" or  message_type == "offlineMsg" then      
                        send("MQTT_SEND_CB:" .. message_type .." OK")
                    end    
                else
                    log.info("00", "02",
                            "topic:", para.topic)
                    send("MQTT_SEND_CB" .. message_type .." ERROR")
                end
            end,
            para = {topic = topic, len = #payload}
        })
        log.info("9", "03", topic, "h", #payload)  -- ← 新增日志⑤
        send("OK")
    else
        -- mqtt_sender 未加载，缓存到本地，等重制定时器重试
        log.warn("9", "04")  -- ← 新增日志⑥
        table.insert(at_send_cache, {
            tag     = "uart",
            topic   = topic,
            payload = payload,
            qos     = 1
        })
        -- 仍然回复 OK，告知 AT 端命令已接收（数据后续会自动补发）
        log.info("9", "05", #at_send_cache)
        send("OK")
    end
end
_G.at_cmd_handlers["MQTT_SILENTSEND="] = function(cmd, send)
    log.info("a", "W", cmd)                          -- ← 新增日志①：确认命令到达
    local param = cmd:match("MQTT_SILENTSEND=(.*)")
    log.info("a", "param:", param)                          -- ← 新增日志②：确认解析参数
    if not param or param == "" then
        log.info("a", "r")
        return
    end
    local topic, payload = param:match("^(.-),(.*)$")
    log.info("a", "topic:", topic, "X", payload)      -- ← 新增日志③：确认分割结果
    if not topic or not payload then
        log.info("a", "Y")
        return
    end
    topic = topic:match("^%s*(.-)%s*$")
    payload = payload:match("^%s*(.-)%s*$")
    if topic == "" or payload == "" then
        log.info("a", "s")
        return
    end

    -- ★ 关键：检查 mqtts_sender 是否已加载 ★
    if mqtts_sender.is_ready() then
        -- 正常发布
        log.info("a", "Z")          -- ← 新增日志④
        sys.publish("SEND_DATA_REQ", "uart", topic, payload, 2, {
            func = function(result, para)
                if result then
                    log.info("06", "01",
                            "topic:", para.topic,
                            "h", para.len)
                else
                    log.info("06", "02",
                            "topic:", para.topic)
                end
            end,
            para = {topic = topic, len = #payload}
        })
        log.info("a", "03", topic, "h", #payload)  -- ← 新增日志⑤
    else
        -- mqtt_sender 未加载，缓存到本地，等重制定时器重试
        log.warn("a", "04")  -- ← 新增日志⑥
        table.insert(at_send_cache, {
            tag     = "uart",
            topic   = topic,
            payload = payload,
            qos     = 1
        })
        -- 仍然回复 OK，告知 AT 端命令已接收（数据后续会自动补发）
        log.info("a", "05", #at_send_cache)
    end
end

--------//test
function mqtt_client_send_data(topic,payload)
    sys.publish("SEND_DATA_REQ", "mqtt_main", topic, payload, 1)
end   


-- SAM | 2026-10-13 09:14 +08:00 | Export the configured MQTT device identity for exact business-topic routing without exposing credentials.
return {business_identity=function() return DEVICE_NO end}
