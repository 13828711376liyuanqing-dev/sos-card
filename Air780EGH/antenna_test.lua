-- SAM | 2026-10-10 16:51 +08:00 | Add bounded antenna sessions because PC needs acknowledged LTE/GNSS measurements.
-- API provenance: official LuatOS script/libs/exgnss.lua and components/mobile/luat_lib_mobile.c;
-- snapshots and local demo references are recorded in logs/cat1_antenna_20261010/lua-report.md.
local loaded, gnss = pcall(require, "exgnss")
if not loaded then gnss = nil end
local TAG = "antenna_test"
local running, mode, interval, seq = false, "ALL", 2, 0
local started, ttff, timer, owns_gnss, configured = nil, nil, nil, false, false

local function call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, ...)
    if ok then return value end
end
local function number(v, low, high)
    if type(v) ~= "number" or v ~= v or v < low or v > high then return "NA" end
    -- SAM | 2026-10-10 16:58 +08:00 | Emit integer fields without .0 because protocol counters parse as integers on the host.
    if v == math.floor(v) then return string.format("%.0f", v) end
    return tostring(v)
end
local function clock_ms()
    if not mcu or type(mcu.ticks2) ~= "function" then return nil end
    -- SAM | 2026-10-10 16:58 +08:00 | Recombine million-ms parts because ticks2(1) is not a binary high/low counter.
    local ok, high, low = pcall(mcu.ticks2, 1)
    if ok and type(high) == "number" and type(low) == "number" then return high * 1000000.0 + low end
end
local function elapsed()
    local now = clock_ms()
    if started and now and now >= started then return now - started end
end
local function emit(s)
    if type(_G.uart_send_raw) ~= "function" then return false end
    return _G.uart_send_raw("[ANT] v=1 " .. s) ~= false
end
local function ack(op, ok, extra)
    return emit("type=ACK op=" .. op .. " ok=" .. (ok and "1" or "0") .. (extra and " " .. extra or ""))
end
local function release()
    running = false
    if timer then sys.timerStop(timer); timer = nil end
    if owns_gnss then
        local ok = pcall(gnss.close, gnss.DEFAULT, {tag=TAG})
        if not ok or call(gnss.is_active, gnss.DEFAULT, {tag=TAG}) then return false end
        owns_gnss = false
    end
    return true
end
local function sample()
    if not running then return end
    if _G.dfu_transfer_active then release(); return end
    if mode == "ALL" or mode == "LTE" then
        seq = seq + 1
        local cell = call(mobile and mobile.scell)
        if type(cell) ~= "table" then cell = {} end
        -- Scalar signal APIs return zero on failure. Zero remains NA where ambiguous.
        local csq = call(mobile and mobile.csq)
        if csq == 99 then csq = "99" else csq = number(csq, 1, 31) end
        emit("type=LTE seq=" .. seq .. " csq=" .. csq ..
            " reg=" .. number(call(mobile and mobile.status), 0, 8) ..
            " rsrp=" .. number(call(mobile and mobile.rsrp), -140, -44) ..
            " rsrq=" .. number(call(mobile and mobile.rsrq), -20, -3) ..
            " snr=" .. number(call(mobile and mobile.snr), 1, 30) ..
            " rssi=" .. number(call(mobile and mobile.rssi), -114, -1) ..
            " cell=" .. number(cell.cid, 1, 268435455) .. " tac=" .. number(cell.tac, 1, 65535))
    end
    if mode == "ALL" or mode == "GNSS" then
        seq = seq + 1
        local fix = call(gnss and gnss.is_fix)
        local rmc = call(gnss and gnss.rmc, 2)
        local gsv = call(gnss and gnss.gsv)
        local gga = call(gnss and gnss.gga, 2)
        if type(rmc) ~= "table" then rmc = {} end
        if type(gsv) ~= "table" then gsv = {} end
        if type(gga) ~= "table" then gga = {} end
        -- SAM | 2026-10-10 16:53 +08:00 | Expose raw GSV SNR separately because its documented unit does not establish C/N0.
        local snr_max
        if type(gsv.sats) == "table" then
            for _, sat in ipairs(gsv.sats) do
                local snr = type(sat) == "table" and sat.snr or nil
                if type(snr) == "number" and snr > 0 and snr <= 99 then
                    snr_max = math.max(snr_max or snr, snr)
                end
            end
        end
        local ms = elapsed()
        if fix == true and not ttff then ttff = ms end
        emit("type=GNSS seq=" .. seq .. " fix=" .. (fix == true and "1" or fix == false and "0" or "NA") ..
            " sats_view=" .. number(gsv.total_sats, 0, 256) ..
            " sats_used=" .. (fix == true and number(gga.satellites_tracked, 0, 256) or "NA") ..
            " cn0_max=NA lat=" .. (fix == true and number(rmc.lat, -90, 90) or "NA") ..
            " lon=" .. (fix == true and number(rmc.lng, -180, 180) or "NA") ..
            " hdop=" .. (fix == true and number(gga.hdop, 0, 99.98) or "NA") ..
            " elapsed_ms=" .. number(ms, 0, 4294967295) .. " ttff_ms=" .. number(ttff, 0, 4294967295) ..
            " snr_max=" .. number(snr_max, 1, 99))
    end
end

-- Record the first observed fix event, independent of the reporting interval.
sys.subscribe("GNSS_STATE", function(event)
    if running and mode ~= "LTE" and event == "FIXED" and not ttff then ttff = elapsed() end
end)

_G.at_cmd_handlers = _G.at_cmd_handlers or {}
_G.at_cmd_handlers["AT+ANTSTART"] = function(cmd)
    if _G.dfu_transfer_active then ack("START", false, "error=DFU_BUSY"); return end
    local requested, seconds = cmd:match("^AT%+ANTSTART=(%u+),(%d+)$")
    seconds = tonumber(seconds)
    if (requested ~= "ALL" and requested ~= "LTE" and requested ~= "GNSS") or not seconds or seconds < 1 or seconds > 60 then
        ack("START", false, "error=BAD_ARGS"); return
    end
    if running and requested == mode and seconds == interval then
        ack("START", true, "mode=" .. mode .. " interval=" .. interval); return
    end
    if not release() then ack("START", false, "error=GNSS_CLOSE"); return end
    started = clock_ms()
    if requested ~= "LTE" then
        if not gnss or type(gnss.open) ~= "function" or type(gnss.close) ~= "function" or type(gnss.is_active) ~= "function" then
            ack("START", false, "error=GNSS_UNAVAILABLE"); return
        end
        local ok = pcall(function()
            -- Preserve a legacy client's setup, including its board-specific options.
            if not configured then
                if type(gnss.opts) ~= "table" then gnss.setup({gnssmode=1, agps_enable=true, debug=false}) end
                configured=true
            end
            owns_gnss = true
            gnss.open(gnss.DEFAULT, {tag=TAG})
            assert(gnss.is_active(gnss.DEFAULT, {tag=TAG}), "GNSS inactive")
        end)
        if not ok then release(); ack("START", false, "error=GNSS_OPEN"); return end
    end
    mode, interval, seq, ttff = requested, seconds, 0, nil
    if requested ~= "LTE" and call(gnss.is_fix) == true then ttff = elapsed() end
    local ok, id = pcall(sys.timerLoopStart, sample, interval * 1000)
    if not ok or not id then release(); ack("START", false, "error=TIMER_FAILED"); return end
    timer, running = id, true
    if not ack("START", true, "mode=" .. mode .. " interval=" .. interval) then release() end
end
_G.at_cmd_handlers["AT+ANTSTOP"] = function(cmd)
    if cmd ~= "AT+ANTSTOP" then ack("STOP", false, "error=BAD_ARGS"); return end
    if release() then ack("STOP", true, "running=0") else ack("STOP", false, "error=GNSS_CLOSE") end
end
_G.at_cmd_handlers["AT+ANTSTATUS"] = function(cmd)
    if cmd ~= "AT+ANTSTATUS" then ack("STATUS", false, "error=BAD_ARGS"); return end
    ack("STATUS", true, "running=" .. (running and "1" or "0") .. " mode=" .. mode .. " interval=" .. interval)
end
_G.antenna_test_stop = release
return {stop=release}
