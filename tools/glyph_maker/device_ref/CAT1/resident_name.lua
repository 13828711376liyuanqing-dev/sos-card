--[[
SAM | 2026-11-02 +08:00 | Platform-pushed resident name + glyphs -> GR (F-021).
MQTT residentNameMsg -> structural checks -> BUS_EVT name_begin / glyph x n / name_end over the existing UART
sender -> GR validates CRC, stages in RAM, commits atomically and answers NAME_RES=.
Nothing is written to the CAT1 file system (OTA space); the last message is kept in RAM only so a GR reboot can be
served without the platform. GR "need" for glyphs we do not hold goes up as residentNameNeed.
]]
local M = {}

-- SAM | 2026-11-04 +08:00 | MAX_STORE 1000 -> 4000: GR keeps the set in two dedicated Flash pages now (user: 4 KB storage space).
local MAX_CHARS, MAX_GLYPHS, MAX_B64, MAX_FILE, MAX_STORE = 8, 28, 268, 8192, 4000   -- 28 = name 8x2 + campus 12x1 (16px)
local last_msg          -- last validated platform message (RAM only)
local txn = 0
local busy = false
-- GR answers name_end within a few ms, often before the sender starts waiting: keep results by id, not only as an event.
local results = {}

local function reply(t)
    local imei = mobile.imei()
    if not imei then return end
    t.Time = os.time()
    local ok, s = pcall(json.encode, t)
    if ok then sys.publish("SEND_DATA_REQ", "resident_name", "/iotplat/datapush3/notsos/WARNCARD3/" .. imei, s, 1) end
end

-- SAM | 2026-11-02 +08:00 | Same power lock as OTA: "[OTA_HOLD] 1" keeps GR from powering CAT1 off (idle low power) from the
-- start of a download/delivery until the platform reply is out. GR has one shared lock, so "0" is only sent while the OTA
-- job is IDLE (an OTA in flight owns the lock and refreshes it itself). Refreshed every 5 s so an OTA boot beacon cannot drop it.
local hold_n = 0
local function ota_idle()
    local ok, idle = pcall(function() return require("ota_runtime").instance():status().phase == "IDLE" end)
    return not ok or idle
end
local function send_hold(on)
    if _G.uart_send_raw then pcall(_G.uart_send_raw, "[OTA_HOLD] " .. (on and "1" or "0") .. "\r\n") end
end
local function hold(on)
    if on then
        hold_n = hold_n + 1
        if hold_n == 1 then
            send_hold(true)
            sys.taskInit(function()
                while hold_n > 0 do sys.wait(5000); if hold_n > 0 then send_hold(true) end end
            end)
        end
    elseif hold_n > 0 then
        hold_n = hold_n - 1
        if hold_n == 0 and ota_idle() then send_hold(false) end
    end
end
M.held = function() return hold_n > 0 end

-- SAM | 2026-11-03 +08:00 | English names use the built-in ASCII font: only non-ASCII characters (the ones that need pushed
-- glyphs) count toward the 8-character limit; the whole name is bounded by 63 UTF-8 bytes.
local function wide_chars(s)
    local n = 0
    for _ in s:gmatch("[\194-\244][\128-\191]*") do n = n + 1 end
    return n
end

local function valid(cmd)
    if type(cmd.Name) ~= "string" or cmd.Name == "" or wide_chars(cmd.Name) > MAX_CHARS or #cmd.Name > 63 then return false, "name" end
    if type(cmd.Room or "") ~= "string" or #(cmd.Room or "") > 63 then return false, "room" end
    if type(cmd.Campus or "") ~= "string" or #(cmd.Campus or "") > 95 then return false, "campus" end
    if type(cmd.Seq) ~= "number" or cmd.Seq < 0 or cmd.Seq % 1 ~= 0 then return false, "seq" end
    local g = cmd.Glyphs
    -- SAM | 2026-11-03 +08:00 | 0 glyphs is fine even for a Chinese name: characters the device font already has are not pushed.
    if type(g) ~= "table" or #g > MAX_GLYPHS then return false, "glyphs" end
    -- GR record: 20 B header + 16 B per glyph + bitmaps, refused above 4000 B (same rule as yp_name_glyphs.c).
    local store = 20 + 16 * #g
    for _, v in ipairs(g) do
        if type(v) ~= "table" or type(v.U) ~= "string" or not v.U:match("^%x%x%x%x?%x?%x?$") or
           (v.S ~= 16 and v.S ~= 32) or type(v.W) ~= "number" or type(v.H) ~= "number" or
           v.W < 1 or v.W > 40 or v.H < 1 or v.H > 40 or type(v.X) ~= "number" or type(v.Y) ~= "number" or
           type(v.A) ~= "number" or type(v.D) ~= "string" or #v.D > MAX_B64 or not v.D:match("^[%w%+/=]+$") or
           type(v.C) ~= "string" or not v.C:match("^%x%x%x%x$") then
            return false, "glyph"
        end
        store = store + math.ceil(v.W / 8) * v.H
    end
    if store > MAX_STORE then return false, "store" end
    return true
end

local function lines_for(cmd, id)
    local out = {}
    out[1] = json.encode({op = "name_begin", id = id, seq = cmd.Seq, g = #cmd.Glyphs, name = cmd.Name,
                          room = cmd.Room or "", campus = cmd.Campus or ""})
    for i, v in ipairs(cmd.Glyphs) do
        out[#out + 1] = json.encode({op = "glyph", id = id, i = i - 1, u = v.U, s = v.S, w = v.W, h = v.H,
                                     x = v.X, y = v.Y, a = v.A, d = v.D, c = v.C})
    end
    out[#out + 1] = json.encode({op = "name_end", id = id, g = #cmd.Glyphs})
    return out
end

-- Send one whole transaction; up to 3 attempts, each waits 3 s for GR's NAME_RES result.
local deliver
function deliver(cmd)
    if busy then return end
    busy = true
    hold(true)
    sys.taskInit(function()
        local res
        for _ = 1, 3 do
            txn = txn % 100000 + 1
            local id = txn
            for _, l in ipairs(lines_for(cmd, id)) do
                if not (_G.uart_send_raw and _G.uart_send_raw("BUS_EVT=" .. l)) then res = {ok = false, err = "uart"} break end
                sys.wait(40)     -- pace: GR parses one line at a time
            end
            if not res then
                for _ = 1, 7 do                     -- about 3 s in 500 ms slices
                    if results[id] then res = results[id] break end
                    sys.waitUntil("RESIDENT_NAME_RES", 500)
                end
                results = {}
            end
            if res and res.ok then break end
            res = nil
            sys.wait(500)
        end
        busy = false
        log.info("resident_name", "result", res and res.ok, res and res.err)
        reply({MsgType = "residentNameReply", Seq = cmd.Seq,
               Result = res and res.ok and "ok" or "fail", Err = res and res.err or "timeout"})
        if last_msg ~= cmd then deliver(last_msg) end   -- a newer message arrived while busy
        sys.wait(3000)                                   -- let the MQTT reply leave before power may be cut
        hold(false)
    end)
end

function M.on_platform(cmd)
    local ok, why = valid(cmd)
    if not ok then
        log.warn("resident_name", "rejected", why)
        reply({MsgType = "residentNameReply", Seq = type(cmd.Seq) == "number" and cmd.Seq or 0, Result = "bad", Err = why})
        return
    end
    if last_msg and cmd.Seq < last_msg.Seq then
        reply({MsgType = "residentNameReply", Seq = cmd.Seq, Result = "stale"})
        return
    end
    last_msg = cmd
    deliver(cmd)
end

-- SAM | 2026-11-03 +08:00 | One-file delivery like OTA, JSON only (zip support removed by user decision): the platform
-- (or the bench via `cat_at NAME_URL=`) gives a URL of residentNameMsg_<name>.json; CAT1 downloads it into RAM (never the file system), checks the optional MD5, then delivers.
-- SAM | 2026-11-03 +08:00 | User rule: a download command first clears the CAT1 logs (fs_log's /log/app.log and its
-- rollover .bak, up to 2 x 128 KB) so the file system has room. /log/ble.ini is business data awaiting upload: kept.
-- Skipped while an OTA job is in flight. Returns the bytes freed.
local LOG_FILES = {"/log/app.log", "/log/app.log.bak"}
function M.clear_logs()
    if not ota_idle() then return 0 end
    local freed = 0
    for _, f in ipairs(LOG_FILES) do
        local n = io.fileSize and io.fileSize(f) or 0
        if n and n > 0 and os.remove(f) then freed = freed + n end
    end
    log.info("resident_name", "logs cleared", freed)
    return freed
end

local fetching = false
function M.fetch(url, md5, report)
    report = report or function() end
    if fetching then report("BUSY") return false end
    if type(url) ~= "string" or not url:match("^https?://") or #url > 512 then report("BAD_URL") return false end
    md5 = (md5 and md5 ~= "") and md5 or url:match("[?&]md5=(%x+)")      -- platform URLs carry md5= like the OTA ones
    fetching = true
    hold(true)
    sys.taskInit(function()
        report("LOG_CLEARED " .. M.clear_logs() .. "B")
        local ok, code, _, body = pcall(function() return http.request("GET", url, nil, nil, {timeout = 30000}).wait() end)
        fetching = false
        local why
        if not ok then why = "HTTP_ERROR"
        elseif code ~= 200 or type(body) ~= "string" then why = "HTTP_" .. tostring(code)
        elseif #body == 0 or #body > MAX_FILE then why = "SIZE_" .. #body
        elseif md5 and md5 ~= "" and crypto.md5(body):lower() ~= md5:lower() then why = "MD5"
        end
        local cmd
        if not why then
            local jok, v = pcall(json.decode, body)
            if jok and type(v) == "table" and v.MsgType == "residentNameMsg" then cmd = v else why = "NOT_RESIDENT_NAME_JSON" end
        end
        if why then
            log.warn("resident_name", "fetch", why)
            report("FAIL " .. why)
            reply({MsgType = "residentNameReply", Seq = 0, Result = "download", Err = why})
            sys.wait(3000)
            hold(false)
            return
        end
        report("OK " .. #body .. "B seq=" .. tostring(cmd.Seq))
        M.on_platform(cmd)                               -- delivery takes its own hold before this one is dropped
        hold(false)
    end)
    return true
end

-- Bench: GR CLI `cat_at NAME_URL=<url>[,<md5>]`; progress comes back as [NAME_URL=] lines on the GR console.
_G.at_cmd_handlers["NAME_URL="] = function(frame, uart_send)
    local arg = frame:sub(10)
    local url, md5 = arg:match("^(.-),(%x+)$")
    if not url or #md5 ~= 32 then url, md5 = arg, nil end
    if M.fetch(url, md5, function(s) uart_send(s) end) then uart_send("DOWNLOADING") end
end

-- GR -> CAT1: NAME_RES={"op":"result",...} or NAME_RES={"op":"need","u":"5F20,79C0"}
_G.at_cmd_handlers["NAME_RES="] = function(frame)
    local ok, v = pcall(json.decode, frame:sub(10))
    if not ok or type(v) ~= "table" then return end
    if v.op == "result" then
        if type(v.id) == "number" then results[math.tointeger(v.id) or v.id] = v end
        sys.publish("RESIDENT_NAME_RES", v)
    elseif v.op == "need" and type(v.u) == "string" then
        local have = {}
        for _, g in ipairs(last_msg and last_msg.Glyphs or {}) do have[g.U:upper()] = true end
        local miss = {}
        for u in v.u:gmatch("%x+") do if not have[u:upper()] then miss[#miss + 1] = u:upper() end end
        if last_msg and #miss == 0 then
            deliver(last_msg)                       -- GR rebooted, CAT1 still holds the glyphs
        else
            reply({MsgType = "residentNameNeed", Missing = miss})
        end
    end
end

return M
