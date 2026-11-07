-- SAM | 2026-10-30 08:56 +08:00 | OTA entry points of the CAT1 receiver: starts the runtime, registers the GR-forwarded
-- commands (cat_at <CMD>) and the plain-text USB diagnostics. Revision history: doc/2026-10-29_*OTA*.md.
local runtime = require("ota_runtime")
local instance = runtime.start()
_G.cat1_fota_active = false

-- SAM | 2026-11-04 +08:00 | Long-term space: a new OTA command (bench OTA_TRIAL or platform otaMsg) first deletes the CAT1 app logs
-- (the name-glyph download clears app.log only; the OTA also clears /log/ble.ini, the temporary BLE location cache), and fs_log stops writing log files
-- while a job is in flight, so logs cannot eat the component space during the download (diagnostics stay on the VUART).
-- SAM | 2026-11-06 +08:00 | /log/ble.ini (temporary BLE location cache awaiting upload, 74 KB after a few offline hours on the bench) is cleared too: it
-- filled the file system and made the GR component fail with COMPONENT_SPACE. The name-glyph download still keeps it.
local LOG_FILES = {'/log/app.log', '/log/app.log.bak', '/log/ble.ini'}
local log_paused = instance:status().phase ~= 'IDLE'
_G.ota_log_paused = function() return log_paused end
local function clear_logs()
    if instance:status().phase ~= 'IDLE' then return end
    local freed = 0
    for _, f in ipairs(LOG_FILES) do
        local n = io.fileSize and io.fileSize(f) or 0
        if n and n > 0 and os.remove(f) then freed = freed + n end
    end
    if _G.ota_diag then pcall(_G.ota_diag, '[OTA] LOG_CLEARED '..freed) end
end
-- SAM | 2026-11-05 +08:00 | Platform metadata reads need the same early rail hold as the working active entry.
local ota_hold
for _, name in ipairs({'accept', 'receive'}) do
    local f = instance[name]
    instance[name] = function(self, ...)
        if name=='receive' then ota_hold(true) end
        pcall(clear_logs)
        local a, b = f(self, ...)
        log_paused = instance:status().phase ~= 'IDLE'
        return a, b
    end
end

local function word(s) return type(s)=='string' and #s<=64 and s:match('^[%w_]+$') end

-- cat_at FOTA_STATUS: phase, outbox, reason, progress, last tick step, install-only state and trial ticket.
_G.at_cmd_handlers.FOTA_STATUS = function(cmd, send)
    local state = instance:status()
    send(state.error or state.phase)
    if state.outbox then send('OTA_OUTBOX='..#state.outbox) end
    if word(state.reason) then send('OTA_REASON='..state.reason) end
    local p = state.progress
    if p then send('OTA_PROGRESS='..p.target..':'..p.committed..'/'..p.total) end
    if word(instance.last_tick_reason) then send('OTA_STEP='..instance.last_tick_reason) end
    send('OTA_IO='..tostring(state.io)..'/'..tostring(state.io_n)..' TRIAL='..tostring(state.trial and state.trial.status))
end

-- Plain-text diagnostics on the USB virtual serial (uart.VUART_0, read by tools/ota/cat1_vuart_log.py).
-- ota_diag also mirrors the line to GR, where it lands in the GR RX ring (readable by J-Link).
local vu = uart.VUART_0
pcall(uart.setup, vu, 115200)
_G.ota_diag = function(x)
    pcall(uart.write, vu, x..'\r\n')
    if _G.uart_send_raw then pcall(_G.uart_send_raw, x) end
end
-- OTA power hold: tell GR to keep CAT1 powered from the OTA command until the OTA ends ("[OTA_HOLD] 1/0" text line, GR keeps it alive 45 min per refresh).
-- SAM | 2026-11-01 +08:00 | Start as held so the first IDLE beacon after a reboot releases any hold left in GR by the previous run.
local held = true
local hold_t = -600000
ota_hold = function(on)
    if on == held and not on then return end
    if on and not held then hold_t = mcu.ticks() end
    held = on
    if _G.uart_send_raw then pcall(_G.uart_send_raw, '[OTA_HOLD] '..(on and '1' or '0')..'\r\n') end
end
-- Beacon every 10 s: [OTA] B <phase> <io>/<re-arms> <ticket> <reason> N <native journal> S <tick step> P <progress>
-- SAM | 2026-11-04 +08:00 | P = V|D|G<bytes>/<total> (archive scan, component download, transfer to GR) or none.
sys.taskInit(function()
    while true do
        sys.wait(10000)
        local s = instance:status()
        log_paused = s.phase ~= 'IDLE'
        -- SAM | 2026-11-01 +08:00 | A failed OTA UART window cannot progress until reboot: drop the hold so GR's low-power logic can power-cycle CAT1 and the job resumes.
        -- SAM | 2026-11-01 +08:00 | Keep the lock for the whole OTA. A dead UART window (needs reboot) reboots CAT1 while GR keeps power;
        -- only a job that can no longer run by itself (PAUSED with a SPENT ticket) releases the lock so low power is not blocked forever.
        local stuck = s.phase=='PAUSED' and s.trial and s.trial.status=='SPENT'
        local dead = _G.ota_window_blocked and _G.ota_window_blocked()
        ota_hold(not stuck and (s.phase~='IDLE' or (held and mcu.ticks()-hold_t<60000)))
        if dead and not stuck and s.phase~='IDLE' and rtos and rtos.reboot then pcall(log.warn,'OTA_DIAG','WINDOW_DEAD_REBOOT');sys.wait(1000);rtos.reboot() end
        pcall(uart.write, vu, '[OTA] B '..tostring(s.phase)..' '..tostring(s.io)..'/'..tostring(s.io_n)..' '..
            tostring(s.trial and s.trial.status)..' '..tostring(s.reason)..' N '..
            tostring(instance.native_diag and instance:native_diag())..' S '..tostring(instance.last_tick_reason)..
            ' P '..tostring(instance.transfer_progress and instance:transfer_progress())..'\r\n')
    end
end)

-- SAM | 2026-11-04 +08:00 | cat_at OTA_GR_CANCEL_EMPTY: bench recovery for a GR owner left DOWNLOADING by a failed download whose CAT1
-- journal was wiped (receiver clean block). Only while this CAT1 has no job: QUERY GR, and if GR reports a GR5526
-- DOWNLOADING owner, echo its exact identity in CANCEL_EMPTY. GR alone decides: it cancels only an empty owner (no durable
-- progress, B all FF, no Boot activity) and persists COMPLETE/cancel; anything else is denied and nothing changes.
local cancel_wait
do
    local prior = _G.at_cmd_handlers.OTA_GR
    _G.at_cmd_handlers.OTA_GR = function(line, ...)
        if cancel_wait then pcall(cancel_wait, line) end
        if prior then return prior(line, ...) end
    end
end
local function gr_reply(want, ms)
    local got
    cancel_wait = function(line)
        if type(line) ~= 'string' or line:sub(1, 7) ~= 'OTA_GR=' then return end
        local ok, m = pcall(json.decode, line:sub(8))
        if ok and type(m) == 'table' and (m.op == want or m.op == 'DENY' or m.op == 'CANCELLED') then got = m end
    end
    for _ = 1, ms / 100 do if got then break end; sys.wait(100) end
    cancel_wait = nil
    return got
end
local cancel_busy = false
_G.at_cmd_handlers.OTA_GR_CANCEL_EMPTY = function(cmd, send)
    local s = instance:status()
    if cancel_busy or s.error or s.phase ~= 'IDLE' or not _G.uart_send_raw then
        send('OTA_GR_CANCEL_EMPTY=REFUSED '..tostring(s.phase)); return
    end
    cancel_busy = true
    sys.taskInit(function()
        local function done(x) send('OTA_GR_CANCEL_EMPTY='..x); if _G.ota_diag then _G.ota_diag('[OTA] GR_CANCEL_EMPTY '..x) end; cancel_busy = false end
        _G.uart_send_raw('OTA_CTL='..json.encode({op='QUERY'}))
        local q = gr_reply('STATUS', 5000)
        if not q or q.op ~= 'STATUS' then done('NO_STATUS'); return end
        if q.phase ~= 'DOWNLOADING' or q.target ~= 'GR5526' then done('NOT_NEEDED '..tostring(q.phase)..' '..tostring(q.target)); return end
        _G.uart_send_raw('OTA_CTL='..json.encode({op='CANCEL_EMPTY', job=q.job, hash=q.hash, target=q.target,
            version=q.version, epoch=q.epoch}))
        local r = gr_reply('CANCELLED', 8000)
        if not r then done('NO_REPLY'); return end
        done(tostring(r.op)..' '..tostring(r.reason)..' '..tostring(r.phase))
    end)
end

-- cat_at FOTA_PROBE: bench rehearsal. Times fota.init and fota.wait, then fota.finish(false); never writes or reboots.
-- Only while IDLE with an empty native journal. The UART idle check runs in the task: this command's own reply is queued.
local probe_busy = false
_G.at_cmd_handlers.FOTA_PROBE = function(cmd, send)
    local s = instance:status()
    local n = instance.native_diag and instance:native_diag() or 'none'
    if probe_busy or s.error or s.phase~='IDLE' or fota==nil or not (n=='none' or n:sub(1,5)=='IDLE ') then
        send('FOTA_PROBE=REFUSED '..tostring(s.phase)..' '..n..' F'..type(fota))
        return
    end
    probe_busy = true
    sys.taskInit(function()
        local idle = false
        for _=1,25 do
            idle = _G.ota_uart_idle and _G.ota_uart_idle()
            if idle then break end
            sys.wait(200)
        end
        if not idle then send('FOTA_PROBE=REFUSED UART_BUSY'); probe_busy = false; return end
        local t0 = mcu.ticks()
        local ok, init = pcall(fota.init); if not ok then init = 'ERR' end
        local t1 = mcu.ticks()
        local ready, polls
        for x=1,100 do
            polls = x
            local c, v = pcall(fota.wait)
            if c then ready = v else ready = 'ERR' end
            if ready ~= false then break end
            sys.wait(100)
        end
        local t2 = mcu.ticks()
        local c3, fin = pcall(fota.finish, false); if not c3 then fin = 'ERR' end
        local t3 = mcu.ticks()
        local line = 'FOTA_PROBE init='..tostring(init)..'/'..(t1-t0)..'ms wait='..tostring(ready)..'/'..(t2-t1)..'ms/'..polls..
            ' finish0='..tostring(fin)..'/'..(t3-t2)..'ms'
        if _G.ota_diag then _G.ota_diag('[OTA] '..line) end
        send(line)
        probe_busy = false
    end)
end

-- cat_at OTA_FS: read-only filesystem usage and root listing (the GR component needs its size + 16 KiB free).
-- SAM | 2026-11-06 +08:00 | Optional directory: cat_at OTA_FS=/log lists that directory (read-only), to see what fills the space.
_G.at_cmd_handlers.OTA_FS = function(cmd, send)
    local _, _, total, used, block = pcall(io.fsstat, '/')
    send('OTA_FS total='..tostring(total)..' used='..tostring(used)..' block='..tostring(block))
    local dir = type(cmd)=='string' and cmd:match('^OTA_FS=(/[%w_%.%-/]*)$') or '/'
    if #dir > 1 and dir:sub(-1) == '/' then dir = dir:sub(1, -2) end
    local c, ok, list = pcall(io.lsdir, dir, 100, 0)
    if not (c and ok and type(list)=='table') then send('OTA_FS lsdir='..tostring(ok)); return end
    for i, e in ipairs(list) do
        if i > 40 then send('OTA_FS more'); break end
        send('F '..tostring(e.name)..' '..tostring(e.size)..' '..tostring(e.type))
    end
end

-- cat_at OTA_PRUNE: drop obsolete history keys from the OTA journal (see manager prune_history). The removed JSON is
-- streamed to the VUART first so the PC log keeps an archive. With nothing left it rewrites the journal once.
_G.at_cmd_handlers.OTA_PRUNE = function(cmd, send)
    local ok, text = instance:prune_history(true)
    if not ok then send('OTA_PRUNE=REFUSED '..tostring(text)); return end
    for i=1,#text,180 do pcall(uart.write, vu, '[OTA] PRUNE_ARCHIVE '..i..' '..text:sub(i,i+179)..'\r\n') end
    pcall(uart.write, vu, '[OTA] PRUNE_ARCHIVE_END '..#text..'\r\n')
    local done, why = instance:prune_history(false)
    send('OTA_PRUNE='..(done and ('DONE '..#text) or tostring(why)))
end

-- cat_at OTA_TRIAL=<url>: local start (no platform push yet). Only the bundle frozen in main.lua (OTA_TRIAL_MD5, also
-- required in the URL), only from OTA_TRIAL_SOURCE. accept() still verifies the signed bundle and needs GR authority.
_G.at_cmd_handlers.OTA_TRIAL = function(cmd, send)
    local md5, url = _G.OTA_TRIAL_MD5, cmd:match('^OTA_TRIAL=(https?://%S+)$')
    if not md5 or md5:find('^0+$') or not url or #url>1024 or not url:find('md5='..md5, 1, true) or
        _G.PRODUCT_VERSION~=_G.OTA_TRIAL_SOURCE then
        send('OTA_TRIAL=REFUSED')
        return
    end
    ota_hold(true)
    sys.taskInit(function()
        local c, ok, why = pcall(instance.accept, instance, {MsgType='otaMsg', CurrentVersion=_G.OTA_TRIAL_SOURCE,
            TargetVersion=_G.OTA_TRIAL_TARGET, Address=url, Md5=md5, Time=os.time()})
        send('OTA_TRIAL='..(c and ok and 'WAIT_GR' or tostring(why)))
    end)
end

return runtime
