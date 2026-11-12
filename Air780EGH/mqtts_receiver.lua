--[[
@module  mqtts_receiver
@summary mqtts cient数据接收处理应用功能模块 
@version 1.0
@date    2025.07.29
@author  马梦阳
@usage
本文件为mqtts client 数据接收应用功能模块，核心业务逻辑为：
处理接收到的publish数据，同时将数据发送给其他应用功能模块做进一步处理；

本文件的对外接口有2个：
1、mqtts_receiver.proc(topic, payload, metas)：publish数据处理入口，在mqtts_main.lua中调用；
2、sys.publish("RECV_DATA_FROM_SERVER", "recv from mqtt ssl server: ", topic, payload)：
   将接收到的publish中的topic和payload数据通过消息"RECV_DATA_FROM_SERVER"发布出去；
   需要处理数据的应用功能模块订阅处理此消息即可，本demo项目中uart_app.lua中订阅处理了本消息；
]]

local mqtts_receiver = {}
-- SAM | 2026-11-05 +08:00 | Bound metadata acceptance to one task while MQTT callbacks remain non-blocking.
local ota_receive_pending=false
-- SAM | 2026-11-02 +08:00 | Load at boot so GR's NAME_RES "need" after a GR reboot has a handler before any push.
require("resident_name")



--[[
处理接收到的publish数据

@api mqtts_receiver.proc(topic, payload, metas)

@param1 topic string
表示publish主题

@param2 payload string
表示publish数据负载

@param2 payload string
表示publish数据负载

@param3 metas table
表示publish报文的一些参数；格式如下：
{
    qos: number类型，取值范围0,1,2
    retain：number类型，取值范围0,1
    dup：number类型，取值范围0,1
    message_id: number类型
}

@return1 result nil

@usage

mqtts_receiver.proc(topic, payload, metas)
]]

local function reboot_timer_cbfunc()
    -- SAM | 2026-11-04 +08:00 | Never reboot while an OTA is pending or its state is unknown.
    if not require("ota_runtime").instance():reboot_allowed() then return end
    pm.reboot()
end 

function mqtts_receiver_test(topic,payload)
    -- SAM | 2026-11-02 +08:00 | A non-JSON downlink must not raise inside the MQTT callback.
    local ok, cmd = pcall(json.decode, payload)
    if not ok or type(cmd) ~= "table" then return end

    local message_type = cmd.MsgType

    if message_type == nil then 
        return 
    end    

    if message_type == "paraSetMsg" then
        local para = cmd.ParaData
        local cmd_type = cmd.CmdType
        local url = cmd.VoipAddr
        local usr_name = cmd.VoipUser
        local usr_psw = cmd.VoipPasswd
        local mqtt_url = cmd.MqttAddr
        local mqtt_usr = cmd.MqttUser
        local mqtt_psw = cmd.MqttPasswd
        local mqtt_keplive = cmd.MqttClientKeepAliveInterval
        local mqtt_changed = false

        --local str = "103.169.62.13:5060"
        if url then 
            local ip, port = url:match("^([^:]+):(%d+)$")
            if ip and port then

                log.info("parse", ip, port)
                set_user_cfg("sip_url",ip)
                set_user_cfg("sip_port",port)
                set_user_cfg("username",usr_name)
                set_user_cfg("password",usr_psw)

                save_user_config()                
            else
                log.warn("解析失败")
            end
        end

        if mqtt_url then 
            local m_ip, m_port = mqtt_url:match("^([^:]+):(%d+)$")
            if m_ip and m_port then
                if m_ip ~= user_cfg.mqtt_url then 
                    set_user_cfg("mqtt_url",m_ip)
                    mqtt_changed = true
                end     
                if tonumber(m_port) ~= user_cfg.mqtt_port then 
                    set_user_cfg("mqtt_port",m_port)
                    mqtt_changed = true
                end                 
                
                if mqtt_usr ~= user_cfg.mqtt_username then 
                    set_user_cfg("mqtt_username",mqtt_usr)
                    mqtt_changed = true
                end
                if mqtt_psw ~= user_cfg.mqtt_password then 
                    set_user_cfg("mqtt_password",mqtt_psw)
                    mqtt_changed = true
                end
                if mqtt_keplive ~= user_cfg.keepalive then 
                    set_user_cfg("keepalive",mqtt_keplive)
                    mqtt_changed = true
                end            

                if mqtt_changed then 
                    save_user_config()

                    local mqtts_main = require("mqtts_main")
                    if mqtts_main.mqtt_reset_fail_state then
                        mqtts_main.mqtt_reset_fail_state()
                    end
                    if mqtts_main.mqtts_reconnect then
                        mqtts_main.mqtts_reconnect()
                    end
                end 

            end       
        end        

    elseif message_type == "phoneBindMsg" then
        local callout = cmd.CallOut
        local callinlist = cmd.CallInList

        reply_data = {
            MsgType = "phoneBindReplyMsg",
            CmdType = 0,
            Time = os.time(),
            CallOut = callout,
            CallInList = callinlist,
            Result = true
        }

        local content = json.encode(reply_data)
        log.info("phoneBindReplyMsg",content)

        imei = mobile.imei()
        local topic_reply = "/iotplat/datapush3/notsos/WARNCARD3/" .. imei 
        mqtt_client_send_data(topic_reply,content) 
    elseif message_type == "personSearchMsg" then
        --sys.taskInit(test_device_find)
    elseif message_type == "rebootMsg" then
        local reboot = cmd.Cmd       

        if reboot == 1 then
            if not require("ota_runtime").instance():reboot_allowed() then 
                reply_data = {
                    MsgType = "rebootReplyMsg",
                    Status = "fail",
                    Time = os.time(),
                }

                local content = json.encode(reply_data)
                log.info("rebootReplyMsg",content)
                imei = mobile.imei()
                local topic_reply = "/iotplat/datapush3/notsos/WARNCARD3/" .. imei 
                mqtt_client_send_data(topic_reply,content)    

            end  
        end
    elseif message_type == "logMsg" then   
        local log_type = cmd.Cmd
        local logurl = cmd.Address  
         
        set_user_cfg("log_url",logurl)
        save_user_config()        

        if log_type == 2 then 
            create_upload_log_task()
        end    
    end  


end    


function mqtts_receiver.proc(topic, payload, metas)

    --log.info("50", topic, payload:len(), json.encode(metas))
    log.info("51", topic, payload:len(), payload)

    -- 接收到数据，通知网络环境检测看门狗功能模块进行喂狗
    sys.publish("FEED_NETWORK_WATCHDOG") 

    -- SAM | 2026-10-12 19:41 +08:00 | OTA commands enter durable orchestration; never echo to legacy handling.
    if type(payload) == "string" and #payload <= 4096 then
        local ok, command = pcall(json.decode, payload)
        if ok and type(command) == "table" and command.MsgType == "otaMsg" then
            -- SAM | 2026-11-05 +08:00 | Match the working active entry: HTTP/sys.wait must execute in a task, never in the MQTT callback.
            if ota_receive_pending then
                if _G.ota_diag then pcall(_G.ota_diag,"[OTA_RX] REJECTED BUSY") end
                return
            end
            ota_receive_pending=true
            sys.taskInit(function()
                local engine=require("ota_runtime").instance()
                local ran, accepted, reason=pcall(engine.receive,engine,topic,command,metas)
                ota_receive_pending=false
                if _G.ota_diag then
                    local code=ran and type(reason)=="string" and #reason<=64 and reason:match("^[A-Z0-9_]+$") and reason or (ran and "UNKNOWN" or "EXCEPTION")
                    pcall(_G.ota_diag,ran and accepted and "[OTA_RX] ACCEPTED" or "[OTA_RX] REJECTED "..code)
                end
            end)
            return
        end
        -- SAM | 2026-10-13 09:14 +08:00 | Consume recognized customer business downlinks once so legacy UART echo cannot double process them.
        -- SAM | 2026-11-02 +08:00 | Resident name + glyph push (F-021) goes to GR via resident_name; never echoed.
        if ok and type(command)=="table" and command.MsgType=="residentNameMsg" then
            require("resident_name").on_platform(command)
            return
        end
        if ok and type(command)=="table" and command.MsgType=="residentNameUrl" then
            require("resident_name").fetch(command.Url, command.Md5)
            return
        end
        --if ok and type(command)=="table" and require("business_runtime").downlink(topic,command,payload) then return end
    end

    -- 将topic和payload通过"RECV_DATA_FROM_SERVER"消息publish出去，给其他应用模块处理
    sys.publish("RECV_DATA_FROM_SERVER", "[MQTTS_EVT] ", topic, payload)

    -- 也可以直接在此处编写代码，处理topic和payload   
    mqtts_receiver_test(topic,payload)
end

return mqtts_receiver
