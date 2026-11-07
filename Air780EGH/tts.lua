--[[
@module  tts_at_cmd
@summary 文字转语音(TTS) AT命令封装（协程任务版）
@version 3.0
@date    2025.09.08
@author  陈媛媛

功能：
- 提供AT命令控制TTS，所有播放操作在独立协程中执行
- 提供Lua API供其他模块调用（如SIP来电播报）
- 支持音量、音色、优先级控制
]]

local exaudio = require "exaudio"
local audio_dev = require "audio_drv"

local TASK_NAME = "tts_task"

-- ==================== 配置参数 ====================
local voice_table = {
    "[m51]",   -- 许久
    "[m52]",   -- 许多
    "[m53]",   -- 晓萍
    "[m54]",   -- 唐老鸭
    "[m55]",   -- 许宝宝
}
local current_voice_idx = 1
local default_text = "支付宝到账,1千万元"

local g_tts_vol = 73
local g_tts_priority = 1
local g_task_running = false
local g_initialized = false   -- 音频硬件是否已初始化

-- ==================== 内部函数（协程中执行） ====================
local function init_audio()
    if g_initialized then
        return true
    end
    local ret = audio_dev.initAudioDevice()
    if ret then
        exaudio.vol(g_tts_vol)
        g_initialized = true
        log.info("TTS", "v")
        return true
    else
        log.error("TTS", "62")
        return false
    end
end

local function deinit_audio()
    if not g_initialized then
        return true
    end
    exaudio.play_stop({type = 1})
    if audio_dev.deinitAudioDevice then
        audio_dev.deinitAudioDevice()
    end
    g_initialized = false
    log.info("TTS", "63")
    return true
end

local function play_tts(content, priority)
    if not g_initialized then
        log.error("TTS", "64")
        return false
    end
    if not content or content == "" then
        content = default_text
    end
    if not content:match("%[m%d+%]") then
        content = voice_table[current_voice_idx] .. content
    end
    local prio = priority or g_tts_priority
    local play_param = {
        type = 1,
        content = content,
        priority = prio,
        cbfnc = function(event)
            if event == exaudio.PLAY_DONE then
                log.info("TTS", "u")
                _G.uart_send_raw("+TTS: PLAY_DONE\r\n")   -- 新增：通知 GR5526
            end
        end
    }
    exaudio.play_start(play_param)
    log.info("TTS", "播放", content, "65", prio)
    return true
end

local function stop_tts()
    if not g_initialized then
        return false
    end
    exaudio.play_stop({type = 1})
    log.info("TTS", "66")
    return true
end

local function set_volume(vol)
    vol = tonumber(vol)
    if vol and vol >= 0 and vol <= 100 then
        g_tts_vol = vol
        if g_initialized then
            exaudio.vol(vol)
        end
        log.info("TTS", "67", vol)
        return true
    end
    return false
end

local function set_voice_by_index(idx)
    idx = tonumber(idx)
    if idx and idx >= 1 and idx <= #voice_table then
        current_voice_idx = idx
        log.info("TTS", "68", voice_table[current_voice_idx])
        return true
    end
    return false
end

local function get_status()
    if not g_initialized then
        return "uninit"
    end
    return (not exaudio.is_end()) and "playing" or "stopped"
end

-- ==================== 主任务（协程） ====================
local function tts_main_task()
    -- 初始化音频硬件（在协程中执行，可安全使用 sys.wait）
    init_audio()

    while true do
        local msg = sys.waitMsg(TASK_NAME)
        if not msg then
            break
        end
        local _, event, para = msg[1], msg[2], msg[3]
        log.info("0a", "event", event, para)

        if event == "MSG_STOP" then
            break
        elseif event == "MSG_PLAY" then
            play_tts(para.content, para.priority)
        elseif event == "MSG_STOP_PLAY" then
            stop_tts()
        elseif event == "MSG_VOLUME" then
            set_volume(para)
        elseif event == "MSG_VOICE" then
            set_voice_by_index(para)
        elseif event == "MSG_STATUS" then
            -- 状态查询需要返回结果，但这里无法直接 uart_send，由 AT 命令处理
            -- 保留原函数供外部直接调用
        end
    end

    deinit_audio()
    g_task_running = false
    log.info("0a", "69")
end

-- ==================== 任务启停控制 ====================
local function start_task()
    if g_task_running then
        return true
    end
    g_task_running = true
    sys.taskInitEx(tts_main_task, TASK_NAME)
    log.info("TTS", "08")
    return true
end

local function stop_task_async()
    if not g_task_running then
        return
    end
    sys.sendMsg(TASK_NAME, "cmd", "MSG_STOP")
    log.info("TTS", "09")
end

-- ==================== AT命令注册 ====================
_G.at_cmd_handlers = _G.at_cmd_handlers or {}

-- TTSINIT：启动 TTS 任务（协程）
_G.at_cmd_handlers["TTSINIT"] = function(cmd, uart_send)
    if g_task_running then
        uart_send("OK")
        return
    end
    start_task()
    uart_send("OK")
end

-- TTSDEINIT：停止 TTS 任务并反初始化音频
_G.at_cmd_handlers["TTSDEINIT"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("OK")
        return
    end
    sys.taskInit(function()
        stop_task_async()
        local timeout = 0
        while g_task_running and timeout < 30 do
            sys.wait(100)
            timeout = timeout + 1
        end
        uart_send("OK")
    end)
end

-- TTSPLAY：发送播放消息
_G.at_cmd_handlers["TTSPLAY"] = function(cmd, uart_send)
    
    if not g_task_running then
        start_task()
    end
    local param = (cmd or ""):gsub("^TTSPLAY=", "")
    local parts = {}
    for part in param:gmatch("([^,]+)") do
        table.insert(parts, part)
    end
    local content = parts[1] or ""
    local priority = parts[2] and tonumber(parts[2])
    local voice_idx = parts[3] and tonumber(parts[3])
    local lang = parts[4]  -- 语言参数

    -- 1. 处理语言标记（放在最前面）
    if lang and lang ~= "" then
        local lang_tag = ""
        if lang:match("^%d$") then
            lang_tag = "[g" .. lang .. "]"
        elseif lang:match("^[Gg]%d$") then
            lang_tag = "[" .. lang .. "]"
        elseif lang == "auto" then
            lang_tag = "[g0]"
        elseif lang == "chinese" or lang == "cn" then
            lang_tag = "[g1]"
        elseif lang == "english" or lang == "en" then
            lang_tag = "[g2]"
        end
        if lang_tag ~= "" and not content:match("%[g%d%]") then
            content = lang_tag .. content
        end
    end

    -- 2. 处理音色标记（如果内容中没有音色标记则添加）
    if voice_idx and voice_idx >= 1 and voice_idx <= 5 then
        local voice_tag = voice_table[voice_idx]
        if not content:match("%[m%d+%]") then
            content = voice_tag .. content
        end
    end

    sys.sendMsg(TASK_NAME, "at", "MSG_PLAY", {content = content, priority = priority})
    uart_send("OK")
end

-- TTSSTOP：发送停止消息
_G.at_cmd_handlers["TTSSTOP"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: NOT INIT")
        return
    end
    sys.sendMsg(TASK_NAME, "at", "MSG_STOP_PLAY")
    uart_send("OK")
end

-- TTSVOL：设置音量（直接调用，因为不涉及 yield）
_G.at_cmd_handlers["TTSVOL"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: NOT INIT")
        return
    end
    if set_volume(cmd) then
        uart_send("OK")
    else
        uart_send("ERROR")
    end
end

-- TTSVOICE：切换音色（直接调用）
_G.at_cmd_handlers["TTSVOICE"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: NOT INIT")
        return
    end
    local success = false
    if cmd and #cmd > 0 then
        local idx = tonumber(cmd)
        if idx then
            success = set_voice_by_index(idx)
        end
    end
    uart_send(success and "OK" or "ERROR")
end

-- TTSSTATUS：查询状态（直接调用）
_G.at_cmd_handlers["TTSSTATUS"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("+TTS: uninit")
        return
    end
    uart_send("+TTS: " .. get_status())
end

-- TTSPRIORITY：设置优先级（直接调用）
_G.at_cmd_handlers["TTSPRIORITY"] = function(cmd, uart_send)
    if not g_task_running then
        uart_send("ERROR: NOT INIT")
        return
    end
    local prio = tonumber(cmd)
    if prio then
        g_tts_priority = prio
        uart_send("OK")
    else
        uart_send("ERROR")
    end
end

-- TTSLANG：预留
_G.at_cmd_handlers["TTSLANG"] = function(cmd, uart_send)
    log.info("TTS", "6a", cmd)
    uart_send("OK")
end

-- ==================== 导出Lua API（供其他模块调用） ====================
-- 这些 API 同样通过消息队列与任务交互，确保线程安全
local tts_api = {
    init = function()
        if not g_task_running then
            start_task()
        end
        return true
    end,
    deinit = function()
        if g_task_running then
            stop_task_async()
        end
        return true
    end,
    play = function(content, priority)
        if not g_task_running then
            log.error("TTS", "6b")
            return false
        end
        sys.sendMsg(TASK_NAME, "api", "MSG_PLAY", {content = content, priority = priority})
        return true
    end,
    stop = function()
        if not g_task_running then
            return false
        end
        sys.sendMsg(TASK_NAME, "api", "MSG_STOP_PLAY")
        return true
    end,
    setVolume = set_volume,
    setVoice = set_voice_by_index,
    getStatus = get_status,
}
return tts_api