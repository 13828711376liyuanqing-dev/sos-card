-- SAM | 2026-10-13 09:14 +08:00 | Keep alarm identity, call attempt, and platform acknowledgement separate because a call ending never cancels SOS.
local M = {}
local function uint(v)
    return type(v)=="number" and v%1==0 and v>=0 and v<=0xffffffff
end
local function valid_phone(v)
    return type(v)=="string" and #v>=3 and #v<=32 and v:match("^%+?%d+$")~=nil
end
local function valid_phone_list(list)
    if type(list)~="table" then return false end
    local count=0
    for k,v in pairs(list) do
        if type(k)~="number" or k%1~=0 or k<1 or k>5 or not valid_phone(v) then return false end
        count=count+1
    end
    if count~=#list or count>5 then return false end
    for i=1,count do if list[i]==nil then return false end end
    return true
end
local function copy(s)
    local out={}
    for k,v in pairs(s) do out[k]=v end
    return out
end
local function valid_state(s)
    if type(s)~="table" or not uint(s.next_id) or s.next_id<1 then return false end
    if type(s.alarm_active)~="boolean" or not uint(s.alarm_id) then return false end
    if s.alarm_acked~=nil and type(s.alarm_acked)~="boolean" then return false end
    if s.alarm_time~=nil and not uint(s.alarm_time) then return false end
    if s.call_attempted~=nil and type(s.call_attempted)~="boolean" then return false end
    if s.phone_seq~=nil and not uint(s.phone_seq) then return false end
    if s.low_seq~=nil and not uint(s.low_seq) then return false end
    if s.low_battery_reported~=nil and type(s.low_battery_reported)~="boolean" then return false end
    if s.low_battery_pending~=nil and (type(s.low_battery_pending)~="table" or not uint(s.low_battery_pending.level) or s.low_battery_pending.level>100 or not uint(s.low_battery_pending.seq)) then return false end
    if s.phone_reply~=nil and (type(s.phone_reply)~="table" or not uint(s.phone_reply.seq) or
        (s.phone_reply.CmdType~=0 and s.phone_reply.CmdType~=1) or type(s.phone_reply.Result)~="boolean") then return false end
    if s.alarm_active and s.alarm_id==0 then return false end
    if s.call_out~=nil and not valid_phone(s.call_out) then return false end
    if not valid_phone_list(s.call_in) then return false end
    return true
end

function M.new(port)
    local self={}
    local stored,err=port.store:load()
    local valid=not stored or valid_state(stored)
    local state=valid and (stored or {next_id=1,alarm_active=false,alarm_id=0,call_out=nil,call_in={}})
        or {next_id=1,alarm_active=false,alarm_id=0,call_out=nil,call_in={}}
    local store_error=err or (not valid and "STATE_INVALID" or nil)
    local battery, battery_known, network=nil,false,"offline"
    local mqtt_ready=false
    local call_state="unknown"
    local inflight=false
    local next_send=0
    local attempts=state.alarm_acked and 4 or 0
    local went_offline=false
    local online_sent,online_pending,online_next=false,false,0
    local phone_pending,phone_next=false,0
    local low_pending,low_next=false,0
    local online_session=0

    local function emit(value) port.emit(value) end
    local function notice(code) emit({op="notice",code=code}) end
    local function save(next_state)
        if store_error then return false,store_error end
        local ok,why=port.store:save(next_state)
        if not ok then store_error=why or "STORE_FAILED"; return false,store_error end
        state=next_state
        return true
    end
    local function alarm_state() emit({op="alarm_state",active=state.alarm_active,id=state.alarm_id}) end
    local function epoch()
        if not port.time_valid() then return nil end
        local n=port.time()
        if type(n)=="number" and n%1==0 and n>1700000000 and n<4102444800 then return n end
        return nil
    end
    local function send_alarm()
        if not state.alarm_active or not mqtt_ready or inflight or attempts>=4 then return end
        if attempts>0 and port.millis()<next_send then return end
        local now=epoch()
        if not now then next_send=port.millis()+60000; notice("TIME_UNKNOWN"); return end
        local initial=state.alarm_time
        if not initial then
            local new=copy(state); new.alarm_time=now
            local ok=save(new)
            if not ok then notice("STORE_FAILED"); return end
            initial=now
        end
        attempts=attempts+1
        local flight=attempts
        local id=state.alarm_id
        inflight=true
        next_send=port.millis()+60000
        port.publish("sos", {MsgType="sosMsg",Data=1,RelatedValue=initial+300,Time=initial}, function(ok)
            if state.alarm_id~=id or attempts~=flight then return end
            inflight=false
            if not ok then notice("SOS_PUBACK_FAILED") end
        end)
    end
    -- SAM | 2026-10-13 09:14 +08:00 | Use an explicit empty Beacon list when no position exists; the platform sees no fabricated coordinates.
    local function send_online()
        if not mqtt_ready or online_sent or online_pending or not battery_known or not epoch() then return end
        if port.millis()<online_next then return end
        local version=port.version()
        if type(version)~="string" or version=="" then notice("VERSION_UNKNOWN"); return end
        online_pending=true
        local session=online_session
        online_next=port.millis()+60000
        port.publish("notsos",{MsgType="onlineMsg",Version=version,Battery=battery,
            Position={PositionType="Bluetooth",Beacon={}},Time=epoch()},function(ok)
            if session~=online_session then return end
            online_pending=false
            online_sent=ok and true or false
            if not ok then notice("ONLINE_PUBACK_FAILED") end
        end)
    end
    -- SAM | 2026-10-13 09:14 +08:00 | Keep phone-bind reply pending until QoS1 delivery because it reports the durable current binding.
    local function send_phone_reply()
        if not mqtt_ready or phone_pending or not state.phone_reply or not epoch() or port.millis()<phone_next then return end
        phone_pending=true; phone_next=port.millis()+60000
        local reply=state.phone_reply
        port.publish("notsos",{MsgType="phoneBindReplyMsg",CmdType=reply.CmdType,
            Result=reply.Result,CallOut=state.call_out or "",CallInList=state.call_in,Time=epoch()},function(ok)
            phone_pending=false
            if ok and state.phone_reply and state.phone_reply.seq==reply.seq then
                local next_state=copy(state); next_state.phone_reply=nil
                local saved=save(next_state)
                if not saved then notice("PHONE_REPLY_STORE_FAILED") end
            elseif not ok then notice("PHONE_REPLY_PUBACK_FAILED") end
        end)
    end
    -- SAM | 2026-10-13 09:14 +08:00 | Retain the below-25% report until PUBACK; C-07 still needs platform field confirmation.
    local function send_low_battery()
        if not mqtt_ready or low_pending or not state.low_battery_pending or not epoch() or port.millis()<low_next then return end
        low_pending=true; low_next=port.millis()+60000
        local event=state.low_battery_pending
        port.publish("notsos",{MsgType="lowBatteryMsg",Battery=event.level,Status="lowBattery",Time=epoch()},function(ok)
            low_pending=false
            if ok and state.low_battery_pending and state.low_battery_pending.seq==event.seq then
                local next_state=copy(state); next_state.low_battery_pending=nil
                local saved=save(next_state)
                if not saved then notice("LOW_BATTERY_STORE_FAILED") end
            elseif not ok then notice("LOW_BATTERY_PUBACK_FAILED") end
        end)
    end

    function self:hello()
        if store_error then notice(store_error); return end
        local imei=port.imei()
        if type(imei)=="string" and imei:match("^%d%d%d%d%d%d%d%d%d%d%d%d%d%d%d$") then
            -- SAM | 2026-10-23 20:18 +08:00 | Internal UART hello carries actual compiled identities; absent metadata remains unknown, never a package-label fallback.
            local hello={op="hello",imei=imei,alarm_active=state.alarm_active,alarm_id=state.alarm_id}
            if type(port.product_version)=="function" and type(port.build)=="function" then
                hello.component_version=port.version();hello.product_build_version=port.product_version();hello.build=port.build()
            end
            emit(hello)
        else notice("IMEI_UNKNOWN") end
        alarm_state()
        -- SAM | 2026-10-25 +08:00 | Replay only the current durable acknowledgement after link recovery; never acknowledge a cancelled alarm.
        if state.alarm_active and state.alarm_acked then emit({op="alarm_ack",id=state.alarm_id}) end
        emit({op="network",state=network})
        -- SAM | 2026-10-13 09:14 +08:00 | Recover display call state after UART loss without pretending an unknown SIP session has ended.
        emit({op="call",state=call_state})
        local t=epoch(); if t then emit({op="time",epoch=t}) end
        local csq=port.csq(); if uint(csq) and (csq<=31 or csq==99) then emit({op="signal",csq=csq}) end
    end
    function self:command(c)
        if type(c)~="table" or type(c.op)~="string" then notice("BAD_COMMAND"); return end
        if c.op=="hello" then self:hello(); return end
        if c.op=="battery" then
            if type(c.known)~="boolean" or (c.known and (not uint(c.battery) or c.battery>100)) then notice("BAD_BATTERY"); return end
            battery_known=c.known; battery=c.known and c.battery or nil
            if battery_known and not store_error then
                if battery<25 and not state.low_battery_reported then
                    local next_state=copy(state)
                    if (state.low_seq or 0)>=0xffffffff then notice("LOW_BATTERY_ID_EXHAUSTED"); return end
                    next_state.low_seq=(state.low_seq or 0)+1
                    next_state.low_battery_reported=true; next_state.low_battery_pending={level=battery,seq=next_state.low_seq}
                    local saved,why=save(next_state)
                    if not saved then notice(why) end
                elseif battery>=25 and state.low_battery_reported then
                    local next_state=copy(state); next_state.low_battery_reported=false
                    local saved,why=save(next_state)
                    if not saved then notice(why) end
                end
            end
            send_online()
            send_low_battery()
            return
        end
        if c.op=="alarm" then
            -- SAM | 2026-11-04 +08:00 | dial=false synchronizes QP-owned SOS without creating a second call; legacy callers keep their behavior.
            if c.dial~=nil and type(c.dial)~="boolean" then notice("BAD_DIAL_OWNER"); return end
            if not uint(c.id) then notice("BAD_ALARM_ID"); alarm_state(); return end
            if store_error then notice(store_error); return end
            if state.alarm_active then alarm_state(); return end
            -- SAM | 2026-10-13 09:14 +08:00 | Only id=0 creates a new event; replayed old IDs after cancellation must not redial.
            if c.id~=0 then notice("STALE_ALARM_ID"); alarm_state(); return end
            local new=copy(state)
            local id=state.next_id
            if id>=new.next_id then
                if id==0xffffffff then notice("ID_EXHAUSTED"); alarm_state(); return end
                new.next_id=id+1
            end
            new.alarm_active=true; new.alarm_id=id; new.alarm_time=nil; new.alarm_acked=false; new.call_attempted=false
            local ok,why=save(new)
            if not ok then notice(why); return end
            attempts=0; next_send=0; inflight=false
            alarm_state()
            -- The durable call_attempted marker must be committed before any non-idempotent dial.
            if c.dial~=false and state.call_out then
                local dial=copy(state); dial.call_attempted=true
                local saved=save(dial)
                if saved then
                    local started=port.dial(state.call_out)
                    if started then call_state="dialing"; emit({op="call",state="dialing"})
                    else notice("CALL_START_FAILED"); self:call("failed") end
                else notice("CALL_STORE_FAILED"); self:call("failed") end
            elseif c.dial~=false then notice("CALLOUT_UNBOUND") end
            send_alarm()
            return
        end
        if c.op=="cancel" then
            if store_error then notice(store_error); return end
            if not state.alarm_active then alarm_state(); return end
            if c.id~=nil and (not uint(c.id) or (c.id~=0 and c.id~=state.alarm_id)) then notice("ALARM_ID_MISMATCH"); alarm_state(); return end
            local new=copy(state); new.alarm_active=false
            local ok,why=save(new)
            if not ok then notice(why); return end
            alarm_state(); return
        end
        if c.op=="accept" or c.op=="hangup" then
            local ok=port.call_control(c.op)
            if not ok then notice("CALL_CONTROL_FAILED") end
            return
        end
        if c.op=="search" then notice("SEARCH_ACK_UNDEFINED"); return end
        notice("UNKNOWN_COMMAND")
    end
    function self:network(value)
        -- SAM | 2026-10-14 20:53 +08:00 | Keep SIM loss authoritative until RDY starts registration because late IP/MQTT callbacks can revive a removed card.
        if network=="no_sim" and value~="no_sim" and value~="registering" then return end
        local was_ready=mqtt_ready
        network=value
        mqtt_ready=value=="mqtt"
        if not mqtt_ready then
            if was_ready then went_offline=true end
            online_session=online_session+1
            online_sent=false; online_pending=false; online_next=0
        elseif went_offline then
            -- SAM | 2026-10-13 09:14 +08:00 | Start a new bounded retry round only on real reconnection, preserving the persisted SOS identity.
            if state.alarm_active and not state.alarm_acked and attempts>=4 then attempts=0; next_send=0 end
            went_offline=false
        end
        emit({op="network",state=value})
        if mqtt_ready then send_alarm(); send_online(); send_phone_reply(); send_low_battery() else inflight=false end
    end
    function self:signal(value)
        if uint(value) and (value<=31 or value==99) then emit({op="signal",csq=value}) end
    end
    function self:time()
        local now=epoch(); if now then emit({op="time",epoch=now}); send_alarm(); send_online(); send_phone_reply(); send_low_battery() end
    end
    function self:call(value)
        if value=="unknown" or value=="dialing" or value=="incoming" or value=="connected" or value=="ended" or value=="failed" then
            call_state=value; emit({op="call",state=value})
        end
    end
    -- SAM | 2026-10-23 20:12 +08:00 | Consume actual SIP readiness because boot-time unknown otherwise blocks GR OTA forever; a late ready cannot hide an active call.
    function self:call_ready()
        if call_state=="unknown" or call_state=="ended" or call_state=="failed" or call_state=="idle" then
            call_state="idle";emit({op="call",state=call_state})
        end
    end
    -- SAM | 2026-10-23 20:12 +08:00 | Export only a copied business gate; battery/charging/stillness and GR installation authority remain separate.
    function self:ota_status()
        local known=store_error==nil and call_state~="unknown"
        return {known=known,alarm=state.alarm_active,call=call_state,network=network,
            idle=known and not state.alarm_active and mqtt_ready and network=="mqtt" and
                (call_state=="idle" or call_state=="ended")}
    end
    -- SAM | 2026-10-13 09:14 +08:00 | Enforce the persisted incoming whitelist at the event boundary before presenting a call for acceptance.
    function self:incoming(number)
        -- SAM | 2026-10-13 09:18 +08:00 | Unknown durable whitelist is never equivalent to a verified empty whitelist.
        if store_error then port.call_control("hangup"); notice(store_error); return end
        if #state.call_in>0 then
            local allowed=false
            for _,v in ipairs(state.call_in) do if v==number then allowed=true; break end end
            if not allowed then port.call_control("hangup"); notice("CALLER_NOT_ALLOWED"); return end
        end
        self:call("incoming")
    end
    function self:downlink(message)
        if type(message)~="table" then return false end
        if message.MsgType=="sosReplyMsg" then
            local now=epoch()
            if message.Status=="success" and state.alarm_active and attempts>0 and state.alarm_time and now and
                type(message.Time)=="number" and message.Time>=state.alarm_time and message.Time<=now+300 then
                local next_state=copy(state); next_state.alarm_acked=true
                local ok=save(next_state)
                if ok then emit({op="alarm_ack",id=state.alarm_id}); attempts=4 else notice("ACK_STORE_FAILED") end
            end
            return true
        end
        if message.MsgType=="phoneBindMsg" then
            if store_error then notice(store_error); return true end
            if message.CmdType~=0 and message.CmdType~=1 then notice("PHONE_COMMAND_INVALID"); return true end
            local next_state=copy(state)
            local result=true
            if message.CmdType==0 then
                if not valid_phone(message.CallOut) or not valid_phone_list(message.CallInList) then result=false
                else
                    if result then next_state.call_out=message.CallOut; next_state.call_in=message.CallInList end
                end
            else next_state.call_out=nil; next_state.call_in={} end
            if not result then notice("PHONE_DATA_INVALID") end
            if (state.phone_seq or 0)>=0xffffffff then notice("PHONE_REPLY_ID_EXHAUSTED"); return true end
            next_state.phone_seq=(state.phone_seq or 0)+1
            next_state.phone_reply={CmdType=message.CmdType,Result=result,seq=next_state.phone_seq}
            local ok,why=save(next_state); if not ok then notice(why) end
            if ok then send_phone_reply() end
            return true
        end
        if message.MsgType=="paraSetMsg" then notice("PARAMETERS_NOT_READY"); return true end
        if message.MsgType=="personSearchMsg" then notice("SEARCH_ACK_UNDEFINED"); return true end
        return false
    end
    function self:tick()
        if state.alarm_active and mqtt_ready and not inflight and attempts<4 and port.millis()>=next_send then send_alarm() end
        send_online()
        send_phone_reply()
        send_low_battery()
    end
    function self:state() return state end
    return self
end
return M
