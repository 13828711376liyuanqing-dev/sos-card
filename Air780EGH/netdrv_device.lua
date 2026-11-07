--[[
@module netdrv_device
@summary Air780EGH SIM, registration and IP status for the YP001 UART link
]]

require "netdrv_4g"

-- SAM | 2026-10-14 21:09 +08:00 | Share logical SIM/IP readiness and generation because cached adapter/IMSI values cannot authorize a new session after removal.
local M = {}

-- SAM | 2026-10-11 09:24 +08:00 | Keep one SIM/network observer because duplicate IP reports hid recovery transitions.
local sim_state = "UNKNOWN"
local registration = nil
local signal_level = 0
local last_signal_level = 0
local system_info_send = false

local NW_SIGNAL_LEVEL_0     = 5
local NW_SIGNAL_LEVEL_1     = 9
local NW_SIGNAL_LEVEL_2     = 13
local NW_SIGNAL_LEVEL_3     = 17
local NW_SIGNAL_LEVEL_4     = 21
local NW_SIGNAL_LEVEL_FULL  = 25
local ip_ready, generation = false, 0
function M.status() return sim_state end
function M.ready() return sim_state == "RDY" end
function M.ip_ready() return M.ready() and ip_ready end
function M.generation() return generation end

local function send(kind, value)
    if type(_G.uart_send_raw) == "function" then
        _G.uart_send_raw("[" .. kind .. "]", value)
    end
end

local function read_mobile(fn)
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn)
    if ok then return value end
    return nil
end

-- SAM | 2026-10-20 16:36 +08:00 | Read the supported mobile.csq API because getCsq is absent on V2052; removed/locked SIMs and invalid results remain unknown.
function M.csq()
    if not M.ready() then return 99 end
    local value=read_mobile(mobile and mobile.csq)
    if type(value)=="number" and value==math.floor(value) and
       ((value>=0 and value<=31) or value==99) then return value end
    return 99
end

local function report_sim(status)
    if status == sim_state then return end
    sim_state = status
    registration, ip_ready = nil, false
    generation = generation + 1
    log.info("sim", "state", status)
    send("SIM_ENV", status)
    -- SAM | 2026-10-14 21:09 +08:00 | Publish one canonical state for live events and the boot snapshot; a locked card also invalidates sessions.
    sys.publish("SIM_STATE", status)
    if status == "NORDY" or status == "SIM_PIN" then
        registration = nil
        -- SAM | 2026-10-11 09:24 +08:00 | Clear the old registration immediately because mobile.status may still briefly report the removed SIM's value.
        send("NET_ENV", "REG=UNKNOWN")
        -- SAM | 2026-10-11 09:24 +08:00 | Notify services immediately so stale MQTT/SIP sessions are retired after card removal.
        sys.publish("SIM_LOST")
    end
end

local function report_registration()
    if not M.ready() then return end
    local status = read_mobile(mobile and mobile.status)
    if type(status) ~= "number" then return end
    if status ~= registration then
        registration = status
        send("NET_ENV", "REG=" .. tostring(status))
    end
end

-- 根据信号值返回等级0~4
local function get_signal_level(val)
    if val <= NW_SIGNAL_LEVEL_0 then
        return 0
    elseif val <= NW_SIGNAL_LEVEL_1 then
        return 1
    elseif val <= NW_SIGNAL_LEVEL_2 then
        return 2
    elseif val <= NW_SIGNAL_LEVEL_3 then
        return 3
    elseif val <= NW_SIGNAL_LEVEL_4 then
        return 4
    else
        return 4 -- 满格
    end
end

local function report_rssi_level()
    if sim_state == "NORDY" or sim_state == "SIM_PIN" then return end

    -- SAM | 2026-11-02 +08:00 | CSQ 99 means unknown, not full bars; M.csq() also returns 99 while the SIM is not ready.
    local csq = M.csq()
    signal_level = (csq == 99) and 0 or get_signal_level(csq)

    if signal_level ~= last_signal_level then
        last_signal_level = signal_level
        -- notify to app
        -- todo
        send("NET_ENV", "RSSIBAR=" .. tostring(last_signal_level))
    end
end

local function report_imei()

    if system_info_send == false then 

        local imei = mobile.imei() or "unknown"
        local imsi = mobile.imsi() or "unknown"
        
        log.info("IMEI", imei)

        send("NET_ENV", "IMEI=" .. imei)
        send("NET_ENV", "IMSI=" .. imsi)

        system_info_send = true

        report_cat1_poweron()
    end
end

function report_cat1_poweron()
    send("NET_ENV", "POWERON")
end    

sys.subscribe("SIM_IND", function(status, value)
    if status == "RDY" or status == "NORDY" or status == "SIM_PIN" then
        report_sim(status)
        report_registration()
    elseif status == "GET_NUMBER" or status == "SIM_WC" then
        log.info("sim", status, value)
    end
end)

sys.subscribe("IP_READY", function(ip, adapter)
    -- SAM | 2026-10-14 21:09 +08:00 | Accept only the cellular adapter after SIM readiness, never an old IP callback while no card is usable.
    if adapter and adapter ~= socket.LWIP_GP then return end
    if not M.ready() then return end
    if not ip_ready then generation = generation + 1 end
    ip_ready = true
    report_registration()
    local address = socket.localIP(socket.LWIP_GP) or ip or "UNKNOWN"
    send("NET_ENV", "IP_READY=" .. tostring(address))
end)

sys.subscribe("IP_LOSE", function(adapter)
    -- SAM | 2026-10-14 21:09 +08:00 | Advance generation on IP loss so SIP callbacks from the disconnected transport are stale too.
    if adapter and adapter ~= socket.LWIP_GP then return end
    if ip_ready then generation = generation + 1 end
    ip_ready = false
    send("NET_ENV", "IP_LOSE")
end)

-- SAM | 2026-10-11 09:24 +08:00 | Use the target firmware's SIM recovery facility without copying the old demo's unverified WAKEUP2 mapping.
sys.taskInit(function()
    sys.wait(500)
    if mobile and type(mobile.setAuto) == "function" then
        -- SAM | 2026-10-14 21:09 +08:00 | Configure once with the documented reserved nil argument; setAuto has no success return value.
        local ok, err = pcall(mobile.setAuto, 10000, 0, 5, nil, 60000)
        if not ok then log.error("sim", "5f", tostring(err)) end
    else
        log.warn("sim", "5g")
    end

    local imsi = read_mobile(mobile and mobile.imsi)
    -- SAM | 2026-10-14 21:09 +08:00 | Bootstrap only an unknown state because a cached IMSI must not override a newer NORDY/PIN event.
    if sim_state == "UNKNOWN" and type(imsi) == "string" and #imsi > 0 then
        report_sim("RDY")
    elseif sim_state == "UNKNOWN" then
        send("SIM_ENV", sim_state)
        sys.publish("SIM_STATE", sim_state)
    end
    report_registration()

    while true do
        sys.wait(5000)
        report_registration()
        report_rssi_level()
        report_imei()
    end
end)
return M
