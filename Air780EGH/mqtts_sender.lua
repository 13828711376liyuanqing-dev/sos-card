-- SAM | 2026-10-26 +08:00 | Decode packet/client/epoch within the four-field envelope; drop only three duplicate debug lines.
--[[
@module  mqtts_sender
@summary mqtts client数据发送应用功能模块 
@version 1.0
@date    2025.07.29
@author  马梦阳
@usage
本文件为mqtts client 数据发送应用功能模块，核心业务逻辑为：
1、sys.subscribe("SEND_DATA_REQ", send_data_req_proc_func)订阅"SEND_DATA_REQ"消息，将其他应用模块需要发送的数据存储到队列send_queue中；
2、mqtts sender task接收"CONNECT OK"、"PUBLISH_REQ"、"PUBLISH OK"三种类型的"MQTT_EVENT"消息，遍历队列send_queue，逐条发送数据到server；
3、mqtts sender task接收"DISCONNECTED"类型的"MQTT_EVENT"消息，丢弃掉队列send_queue中未发送的数据；
4、任何一条数据无论发送成功还是失败，只要这条数据有回调函数，都会通过回调函数通知数据发送方；

本文件的对外接口有1个：
1、sys.subscribe("SEND_DATA_REQ", send_data_req_proc_func)：订阅"SEND_DATA_REQ"消息；
   其他应用模块如果需要发送数据，直接sys.publish这个消息即可，将需要发送的topic，payload和qos以及回调函数和回调参数一起publish出去；
   本demo项目中uart_app.lua和timer_app.lua中publish了这个消息；
]]

local mqtts_sender = {}

--[[
数据发送队列，数据结构为：
{
    [1] = {topic="topic1", payload="payload1", qos=0, cb={func=callback_function1, para=callback_para1}},
    [2] = {topic="topic2", payload="payload2", qos=1, cb={func=callback_function2, para=callback_para2}},
    [3] = {topic="topic3", payload="payload3", qos=2, cb={func=callback_function3, para=callback_para3}},
}
topic的内容为publish的主题，string类型，必须存在；
payload的内容为publish的负载数据，string类型，必须存在；
qos的内容为publish的质量等级，number类型，取值范围0,1,2，可选，如果用户没有指定，默认为0；
cb.func的内容为数据发送结果的用户回调函数，可以不存在；
cb.para的内容为数据发送结果的用户回调函数的回调参数，可以不存在；
]]
local send_queue = {}

-- mqtts client的任务名前缀
mqtts_sender.TASK_NAME_PREFIX = "mqtts_"

-- mqtts_client_sender的任务名
mqtts_sender.TASK_NAME = mqtts_sender.TASK_NAME_PREFIX.."sender"

-- "SEND_DATA_REQ"消息的处理函数
local function send_data_req_proc_func(tag, topic, payload, qos, cb)
    -- 将原始数据增加前缀，然后插入到发送队列send_queue中
    -- table.insert(send_queue, {topic=topic, payload="send from "..tag..": "..payload, qos=qos or 0, cb=cb})
    table.insert(send_queue, {topic=topic, payload=payload, qos=qos or 0, cb=cb})
    -- 发送消息通知 mqtts sender task，有新数据等待发送
    -- SAM | 2026-10-13 09:14 +08:00 | Log length only because business payloads can include bound phone numbers or parameter credentials.
    log.info("51", "topic:", topic, "h", #payload)
    sys.sendMsg(mqtts_sender.TASK_NAME, "MQTT_EVENT", "PUBLISH_REQ")
end

-- 按照顺序发送send_queue中的数据
-- 如果调用publish接口成功，则返回当前正在发送的数据项
-- 如果调用publish接口失败，通知回调函数发送失败后，继续发送下一条数据
local function publish_item(mqtt_client, session)
    local item
    -- 如果发送队列中有数据等待发送
    while #send_queue>0 do
        -- 取出来第一条数据赋值给item
        -- 同时从队列send_queue中删除这一条数据
        item = table.remove(send_queue, 1)

        -- publish数据
        -- result表示调用publish接口的同步结果，返回值有以下几种：
        -- 如果失败，返回nil
        -- 如果成功，number类型，qos为0时直接返回0；qos为1或者2时返回publish报文的message id
        -- SAM | 2026-10-12 19:40 +08:00 | Bind completion to packet and connection so stale ACK cannot remove OTA results.
        local result = mqtt_client:publish(item.topic, item.payload, item.qos)

        -- publish接口调用成功
        if result then
            item.packet_id = result
            item.client = mqtt_client
            item.session = session
            return item
        -- publish接口调用失败
        else
            -- 如果当前发送的数据有用户回调函数，则执行用户回调函数
            if item.cb and item.cb.func then
                item.cb.func(false, item.cb.para)
            end
        end
    end
end


local function publish_item_cbfunc(item, result)
    if item then
        -- 如果当前发送的数据有用户回调函数，则执行用户回调函数
        if item.cb and item.cb.func then
            item.cb.func(result, item.cb.para)
        end
    end
end

-- mqtts client sender的任务处理函数
local function mqtts_client_sender_task_func() 

    local mqtt_client
    local session
    local send_item
    local result, msg

    while true do
        -- 等待"MQTT_EVENT"消息
        -- sys.waitMsg(task_name, msg_type, timeout)
        -- 超时500ms以便继续循环检查
        msg = sys.waitMsg(mqtts_sender.TASK_NAME, "MQTT_EVENT", 500)

	while msg do
            log.info("52", msg[2], msg[3], msg[4])
        -- mqtt连接成功
        -- msg[3]表示mqtt client对象
        if msg[2] == "CONNECT_OK" then
            -- SAM | 2026-10-12 19:40 +08:00 | A new session invalidates unconfirmed in-flight delivery.
            if send_item then publish_item_cbfunc(send_item, false); send_item = nil end
            mqtt_client = msg[3]
            session = msg[4]
	    log.info("53", mqtt_client)
                -- 如果没有正在等待发送结果的发送数据项，发送send_queue中的数据
            if not send_item and #send_queue > 0 then
                log.info("54", #send_queue, "55")
            send_item = publish_item(mqtt_client, session)
	    end
        -- mqtt publish数据请求
        elseif msg[2] == "PUBLISH_REQ" then
            -- 如果mqtt client对象存在，并且没有正在等待发送结果的发送数据项
            if mqtt_client and not send_item then
                -- 发送send_queue中的数据
                send_item = publish_item(mqtt_client, session)
	    else
                    if not mqtt_client then
                        log.info("5b")
                    else
                        log.info("5c")
                    end
            end
        -- mqtt publish数据成功
        elseif msg[2] == "PUBLISH_OK" then
            local context=msg[4]
            if send_item and type(context)=='table' and msg[3] == send_item.packet_id and context[1] == send_item.client and
               context[2] == send_item.session then
            -- publish成功，执行回调函数通知发送方
            publish_item_cbfunc(send_item, true)
            -- publish成功，通知网络环境检测看门狗功能模块进行喂狗
            sys.publish("FEED_NETWORK_WATCHDOG")
            -- 发送send_queue中的数据
            send_item = publish_item(mqtt_client, session)
            end
        -- mqtt断开连接
        elseif msg[2] == "DISCONNECTED" then
            -- 清空mqtt client对象
            mqtt_client = nil
            -- 如果存在正在等待发送结果的发送项，执行回调函数通知发送方失败
            publish_item_cbfunc(send_item, false)
            -- 如果发送队列中有数据等待发送
            while #send_queue>0 do
                -- 取出来第一条数据赋值给send_item
                -- 同时从队列send_queue中删除这一条数据
                send_item = table.remove(send_queue,1)
                -- 执行回调函数通知发送方失败
                publish_item_cbfunc(send_item, false)
            end
            -- 当前没有正在等待发送结果的发送项
            send_item = nil
        end
	-- 继续取出下一条消息
            msg = sys.waitMsg(mqtts_sender.TASK_NAME, "MQTT_EVENT", 0)
        end
    end
end



-- 订阅"SEND_DATA_REQ"消息；
-- 其他应用模块如果需要发送数据，直接sys.publish这个消息即可，将需要发送的数据以及回调函数和回调参数一起publish出去；
-- 本demo项目中uart_app.lua和timer_app.lua中publish了这个消息；
sys.subscribe("SEND_DATA_REQ", send_data_req_proc_func)


--创建并且启动一个task
--运行这个task的处理函数mqtts_client_sender_task_func
sys.taskInitEx(mqtts_client_sender_task_func, mqtts_sender.TASK_NAME)
-- 对外接口：判断 mqtts_sender 是否已就绪
function mqtts_sender.is_ready()
    return true  -- 能执行到这里说明模块已加载完毕
end
return mqtts_sender
