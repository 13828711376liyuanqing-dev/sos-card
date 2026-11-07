-- SAM | 2026-10-13 09:14 +08:00 | Bind the pure business state machine to the existing UART, MQTT, SIP and network events without changing OTA routing.
local M={}
local codec={encode=json.encode,decode=json.decode}
-- SAM | 2026-10-15 +08:00 | Keep one require per line because Luatools merging otherwise treats the intervening expression as part of a filename.
local store_module=require("business_store")
local store=store_module.new(store_module.file_port(),codec)
local main=require("mqtts_main")
-- SAM | 2026-10-14 21:09 +08:00 | Use the shared logical SIM/IP observer so bootstrap and locked-card states reach the same business gate.
local sim_network=require("netdrv_device")
local core=require("business_core")
local time_synced=false
-- SAM | 2026-10-24 +08:00 | MQTT readiness must re-observe a stopped SIP instance after the asynchronous SIM/IP snapshot retires the boot-time call state.
local accept_stopped_sip
local clock_ok=mcu and type(mcu.ticks)=="function"
-- SAM | 2026-10-13 09:14 +08:00 | Extend the module tick counter across uint32 wrap so 60-second retry deadlines remain monotonic.
local tick_last,tick_elapsed=nil,0
local function monotonic_ms()
    if not clock_ok then return 0 end
    local ok,raw=pcall(mcu.ticks)
    if not ok or type(raw)~="number" then clock_ok=false; return 0 end
    if tick_last then
        local delta=raw-tick_last
        if delta<0 then delta=delta+0x100000000 end
        tick_elapsed=tick_elapsed+delta
    end
    tick_last=raw
    return tick_elapsed
end
local function identity()
    return main.business_identity and main.business_identity() or nil
end
-- SAM | 2026-10-25 +08:00 | Retain rejected UART business events in a bounded FIFO; pressure immediately revokes OTA consent.
local uart_pending,uart_pending_bytes,uart_overflow={},0,false
_G.business_uart_backlog=function()return uart_overflow or #uart_pending>0 end
local function flush_uart()
    if #uart_pending>0 and _G.uart_send_raw and _G.uart_send_raw(uart_pending[1].line)==true then
        uart_pending_bytes=uart_pending_bytes-#uart_pending[1].line;table.remove(uart_pending,1)
    end
end
local function emit(v)
    local ok,payload=pcall(json.encode,v)
    if not ok or type(payload)~='string' then return false end
    local line='BUS_EVT='..payload
    -- SAM | 2026-10-26 +08:00 | Atomic resync delimiter; cache this synchronous callback lookup to fit the unchanged partition.
    if v.op=='hello' then line='\r\n'..line end
    local send=_G.uart_send_raw
    if #uart_pending==0 and send and send(line)==true then return true end
    sys.publish('OTA_BUSINESS_BUSY')
    -- SAM | 2026-10-25 +08:00 | BUS_EVT carries current state; supersede only an unsent snapshot of the same op, then append in observation order.
    for i=#uart_pending,1,-1 do
        if uart_pending[i].op==v.op then
            uart_pending_bytes=uart_pending_bytes-#uart_pending[i].line;table.remove(uart_pending,i)
        end
    end
    if #uart_pending>=64 or uart_pending_bytes+#line>32768 then
        uart_overflow=true;sys.publish('OTA_UART_FAULT','BUSINESS_RETRY_QUEUE_FULL');return false
    end
    uart_pending[#uart_pending+1]={op=v.op,line=line};uart_pending_bytes=uart_pending_bytes+#line;return false
end
local service
service=core.new({
    store=store, emit=emit,
    imei=function() return mobile.imei() end,
    version=function() return _G.VERSION end,
    -- SAM | 2026-10-23 20:18 +08:00 | Report compiled CAT1 identity over the existing hello so GR can measure the CAT source independently.
    product_version=function() return _G.PRODUCT_VERSION end,
    build=function() return _G.FW_RELEASE_BUILD end,
    -- SAM | 2026-10-20 16:36 +08:00 | Share the measured SIM-gated signal with diagnostics because the obsolete getCsq API always yielded 99.
    csq=sim_network.csq,
    time=function() return os.time() end,
    time_valid=function() return time_synced end,
    millis=monotonic_ms,
    publish=function(kind,value,cb)
        if not clock_ok then cb(false); emit({op="notice",code="CLOCK_UNAVAILABLE"}); return end
        local id=identity()
        if type(id)~="string" or id=="" then cb(false); emit({op="notice",code="DEVICE_ID_UNBOUND"}); return end
        local topic="/iotplat/datapush3/"..kind.."/WARNCARD3/"..id
        sys.publish("SEND_DATA_REQ","business",topic,json.encode(value),1,{func=function(ok) cb(ok) end})
    end,
    dial=function(number)
        -- SAM | 2026-10-14 21:09 +08:00 | A missing/locked SIM cannot accept a new network call; the core preserves its single-attempt alarm record.
        if not sim_network.ip_ready() then return false end
        local handler=_G.at_cmd_handlers and _G.at_cmd_handlers["SIP_CALL"]
        if not handler then return false end
        -- A single invocation is allowed only after the call_attempted record is committed.
        local returned,failed=false,false
        local ok=pcall(handler,"SIP_CALL="..number,function(result)
            if type(result)=="string" and result:find("ERROR",1,true) then
                if returned then service:call("failed") else failed=true end
            end
        end)
        returned=true
        return ok and not failed
    end,
    call_control=function(op)
        -- SAM | 2026-10-14 21:09 +08:00 | Reject network acceptance without IP, while still allowing local hangup cleanup.
        if op=="accept" and not sim_network.ip_ready() then return false end
        local key=op=="accept" and "SIP_ACCEPT" or "SIP_HANGUP"
        local handler=_G.at_cmd_handlers and _G.at_cmd_handlers[key]
        if not handler then return false end
        -- SAM | 2026-10-13 13:24 +08:00 | Surface SIP command rejection because
        -- pcall only proves the handler did not throw, not that it accepted the action.
        local returned,failed=false,false
        local ok=pcall(handler,key,function(result)
            if type(result)=="string" and result:find("ERROR",1,true) then
                if returned then emit({op="notice",code="CALL_CONTROL_FAILED"})
                else failed=true end
            end
        end)
        returned=true
        return ok and not failed
    end
})

function M.command(payload)
    if type(payload)~="string" or #payload>1024 then emit({op="notice",code="BAD_COMMAND"}); return end
    local ok,value=pcall(json.decode,payload)
    if not ok or type(value)~="table" then emit({op="notice",code="BAD_COMMAND"}); return end
    service:command(value)
end
function M.downlink(topic,value,raw)
    local id=identity()
    if not id or topic~="/iotplat/render3/WARNCARD3/"..id.."/down_raw" then return false end
    -- SAM | 2026-10-13 09:14 +08:00 | Reject a JSON object masquerading as an empty whitelist; Lua tables alone lose the [] vs {} distinction.
    if type(value)=="table" and value.MsgType=="phoneBindMsg" and value.CmdType==0 then
        local count=0
        if type(raw)=="string" then local ignored; ignored,count=raw:gsub('"CallInList"%s*:',"") end
        if count~=1 or raw:find("\\",1,true) or not raw:find('"CallInList"%s*:%s*%[') then
            emit({op="notice",code="PHONE_DATA_INVALID"}); return true
        end
    end
    return service:downlink(value)
end
-- SAM | 2026-10-14 21:09 +08:00 | Gate MQTT readiness on the observer and consume boot/live/PIN states through the same path.
function M.mqtt_ready()
    if sim_network.ip_ready() then
        service:network("mqtt")
        if accept_stopped_sip then accept_stopped_sip() end
    end
end
function M.mqtt_lost() service:network("offline") end
-- SAM | 2026-10-23 20:12 +08:00 | Default OTA startup reads the existing service lazily; missing clock or current cellular readiness must deny transfer.
-- SAM | 2026-10-24 +08:00 | Bind a live SIP snapshot; a stopped on-demand service is provably idle, while absent/initializing/active snapshots cannot grant OTA readiness.
local sip_status_provider
local function sip_snapshot()
    if not sip_status_provider then return nil end
    local ok,s=pcall(sip_status_provider)
    if ok and type(s)=='table' and type(s.task_running)=='boolean' and type(s.state)=='string' then return s end
end
accept_stopped_sip=function()
    local s=sip_snapshot()
    if s and s.task_running==false and s.state=='STATE_IDLE' then
        service:call_ready();return true
    end
    return false
end
function M.bind_sip_status(provider)
    sip_status_provider=type(provider)=='function' and provider or nil
    return accept_stopped_sip()
end
function M.ota_status()
    local status=service:ota_status()
    if not clock_ok or not sim_network.ip_ready() then status.known=false;status.idle=false end
    if sip_status_provider then
        local s=sip_snapshot()
        if not s or not ((s.task_running==false and s.state=='STATE_IDLE') or
            (s.task_running==true and s.state=='STATE_READY')) then status.known=false;status.idle=false end
    end
    return status
end
-- SAM | 2026-10-23 20:12 +08:00 | Repeated network-loss notices need not duplicate an already-unknown call event on the shared UART.
local function retire_call()
    if service:ota_status().call~="unknown" then service:call("unknown") end
end

-- SAM | 2026-10-23 20:12 +08:00 | A retired SIP session cannot retain an old idle/ended state through SIM or IP recovery.
sys.subscribe("SIM_LOST",function() time_synced=false;retire_call();service:network("no_sim") end)
local function sim_changed(status)
    if status=="RDY" then retire_call();service:network("registering")
    elseif status=="NORDY" or status=="SIM_PIN" then
        time_synced=false;retire_call();service:network("no_sim")
        if status=="SIM_PIN" then emit({op="notice",code="SIM_PIN_REQUIRED"}) end
    elseif status=="UNKNOWN" then retire_call();service:network("unknown") end
end
-- SIM_STATE includes the observer's boot snapshot, unlike raw SIM_IND alone.
sys.subscribe("SIM_STATE",sim_changed)
sim_changed(sim_network.status())
-- SAM | 2026-10-13 09:14 +08:00 | Request fresh time on every IP recovery; this asynchronous request cannot delay alarm dialing.
sys.subscribe("IP_READY",function(_,adapter)
    -- SAM | 2026-10-14 21:09 +08:00 | Cellular readiness gates IP/time/call events so an unrelated adapter or stale callback cannot restore business.
    if (adapter and adapter~=socket.LWIP_GP) or not sim_network.ip_ready() then return end
    time_synced=false
    -- SAM | 2026-10-25 +08:00 | Duplicate IP_READY cannot downgrade a live MQTT session; real loss already retires that state.
    if service:ota_status().network~="mqtt" then service:network("ip") end
    if socket and type(socket.sntp)=="function" then pcall(socket.sntp) end
end)
sys.subscribe("IP_LOSE",function(adapter)
    if adapter and adapter~=socket.LWIP_GP then return end
    time_synced=false;retire_call();service:network("offline")
end)
sys.subscribe("NTP_UPDATE",function()
    if sim_network.ip_ready() then time_synced=true; service:time() end
end)
sys.subscribe("SIP_APP_MAIN_INCOMING",function(number)
    if sim_network.ip_ready() then service:incoming(number) end
end)
sys.subscribe("SIP_APP_MAIN_CONNECTED",function()
    if sim_network.ip_ready() then service:call("connected") end
end)
-- SAM | 2026-10-23 20:12 +08:00 | Forward the actual ready event to GR instead of leaving its OTA call gate permanently unknown.
sys.subscribe("SIP_APP_MAIN_READY",function()
    if sim_network.ip_ready() then service:call_ready() end
end)
-- SAM | 2026-10-23 20:18 +08:00 | Ignore a delayed end notification after SIM/IP retirement; it cannot replace unknown with idle eligibility on recovery.
sys.subscribe("SIP_APP_MAIN_DISCONNECTED",function()
    if sim_network.ip_ready() then service:call("ended") end
end)
sys.subscribe("SIP_APP_MAIN_LOSE",function() retire_call() end)
-- SAM | 2026-10-24 +08:00 | Starting invalidates old permission; stopped events cannot override a newer live session or an active business call.
sys.subscribe("SIP_APP_MAIN_STARTING",retire_call)
sys.subscribe("SIP_APP_MAIN_STOPPED",accept_stopped_sip)
sys.taskInit(function()
    local last_csq=nil
    while true do
        sys.wait(1000)
        service:tick()
        -- SAM | 2026-10-13 09:14 +08:00 | Report measured signal changes while online without flooding the shared UART.
        -- SAM | 2026-10-20 16:36 +08:00 | Use the same validated live signal as hello/status reporting.
        local csq=sim_network.csq()
        if csq~=last_csq then last_csq=csq; service:signal(csq) end
    end
end)
-- SAM | 2026-10-25 +08:00 | Retry one retained event per tick; never burst through a Flash hold.
sys.taskInit(function()while true do flush_uart();sys.wait(10)end end)
return M
