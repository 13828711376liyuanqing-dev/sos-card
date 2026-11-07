--[[
@module  audio_drv
@summary 音频设备管理模块，负责音频设备的初始化和控制（仅使用exaudio扩展库）
@version 2.1
@date    2025.10.23
@author  陈媛媛
@usage
本模块提供以下功能：
1、定义所有硬件引脚常量
2、使用exaudio扩展库初始化音频设备
3、支持幂等初始化/反初始化，避免重复配置硬件
]]

-- [FIX v2.1] 用 pcall 包裹 require，避免 exaudio 不存在时导致 Lua VM 崩溃退出
-- 当前固件 (LuatOS V2034 Air780EGH) 未内置 exaudio 扩展库
local exaudio = nil
local _exaudio_ok, _exaudio_err = pcall(function() exaudio = require "exaudio" end)


if not _exaudio_ok or not exaudio then
    log.warn("3", "0c" .. tostring(_exaudio_err) .. "0d")
    exaudio = {
        setup = function() return false end,
        vol = function() end,
        mic_vol = function() end,
        play_stop = function() end,
    }
end
local sys = require "sys"

-- ==================== 电源控制 GPIO ====================
local GPIO_PA_POWER = 24      -- PA供电脚
local GPIO_CODEC_POWER = 20   -- 编解码芯片供电脚（ES8311）

-- 内部上电函数
local function powerOn()
    gpio.setup(GPIO_CODEC_POWER, 1, gpio.PULLUP)  -- 8311供电上拉
    gpio.setup(GPIO_PA_POWER, 1, gpio.PULLUP)     -- PA供电上拉
    log.info("3", "0e")
end

-- 内部下电函数
local function powerOff()
    gpio.setup(GPIO_CODEC_POWER, 0) -- 8311供电下拉
    gpio.setup(GPIO_PA_POWER, 0)    -- PA供电下拉
    log.info("3", "0f")
end

-- ==================== 幂等状态标志 ====================
local is_initialized = false    -- 是否已初始化
local is_deinitialized = false  -- 是否已反初始化（可选，用于严格逻辑）

-- ==================== dac_delay 自适应 ====================
local set_dac_delay = 0
local version = rtos.version()
local version_num = 0
if version then
    local num_str = version:match("V(%d+)")
    if num_str then
        version_num = tonumber(num_str)
    end
end

if version_num and version_num >= 2026 then
    set_dac_delay = 6     -- 单位100ms
else
    set_dac_delay = 600   -- 单位1ms
end

-- exaudio配置参数
local audio_configs = {
    model = "es8311",
    i2c_id = 1,
    pa_ctrl = 1,            -- PA使能脚（注意与PA供电脚不同）
    dac_ctrl = 0xff,         -- 音频编解码芯片电源控制（实际用GPIO20，此处占位）
    dac_delay = set_dac_delay,
    pa_delay = 100,
    dac_time_delay = 100,
    bits_per_sample = 16,
    pa_on_level = 1
}

-- ==================== 对外接口（幂等） ====================
-- 初始化：仅第一次执行硬件上电和exaudio.setup
function initAudioDevice()
    if is_initialized then
        log.info("3", "0g")
        return true
    end

    powerOn()
    -- sys.wait(50)   -- 等待电源稳定

    log.info("3", "0h")
    if exaudio.setup(audio_configs) then
        exaudio.vol(73)        -- 喇叭音量（默认）
        exaudio.mic_vol(80)    -- 麦克风音量
        is_initialized = true
        is_deinitialized = false
        log.info("3", "0i")
        return true
    else
        log.error("3", "0j")
        -- 初始化失败时，也尝试下电（可根据需要决定是否下电）
        powerOff()
        return false
    end
end

-- 反初始化：停止所有播放、下电（幂等，多次调用只生效一次）
function deinitAudioDevice()
    if not is_initialized or is_deinitialized then
        log.info("3", "0k")
        return true
    end

    -- 停止所有可能的播放（type 0 和 type 1）
    exaudio.play_stop({type = 0})
    exaudio.play_stop({type = 1})
    -- sys.wait(20)   -- 等待播放彻底停止

    powerOff()
    is_initialized = false
    is_deinitialized = true
    log.info("3", "0l")
    return true
end

-- 获取多媒体通道ID（兼容性接口，始终返回0）
function getMultimediaId()
    return 0
end



local function play_audio_test()
    log.info("0m")
    audio_path = "/luadb/sample-6s.mp3"
    exaudio.play_start({type= 0, content = audio_path,cbfnc = play_end,priority = 1})
end

-- ==================== 全局电源控制函数（AT命令和其他模块调用） ====================
-- 音频上电：初始化音频设备（幂等，多次调用只生效一次）
function audio_power_on()
    log.info("3", "0n")
    return initAudioDevice()
end

-- 音频下电：反初始化音频设备（幂等，多次调用只生效一次）
function audio_power_off()
    log.info("3", "0o")
    return deinitAudioDevice()
end

-- 注册到全局表（确保 _G.audio_power_on / _G.audio_power_off 可用）
_G.audio_power_on = audio_power_on
_G.audio_power_off = audio_power_off

_G.at_cmd_handlers["AUDIO_POWER_ON"] = function(cmd, uart_send)
    _G.audio_power_on()
    uart_send("OK")
end

_G.at_cmd_handlers["AUDIO_POWER_OFF"] = function(cmd, uart_send)
    _G.audio_power_off()
    uart_send("OK")
end




-- 播放完成回调
local function play_end(event)
    if event == exaudio.PLAY_DONE then
        log.info("u",exaudio.is_end())
    end
end 




-- ============ 配置 ============
local RECORD_PATH  = "/record.pcm"   -- 注意：不要写到 /luadb/（脚本区可能只读）
local RECORD_SEC   = 5               -- 录音时长(秒)
local RECORD_VOL   = 70              -- MIC 增益(0~100)
local PLAY_VOL     = 70              -- 喇叭音量(0~100)
local SAMPLE_RATE  = 16000           -- 采样率，录/放必须一致
local SAMPLE_DEPTH = 16              -- 位深


local is_recording, is_playing = false, false
local taskName = "audio_rec"

-- ============ 录音完成回调 ============
local function record_end_cb(event)
    if event == exaudio.RECORD_DONE then
        is_recording = false
        local size = io.fileSize(RECORD_PATH) or 0
        log.info("0p", "0q", size, "字节",
                 "0r", SAMPLE_RATE * SAMPLE_DEPTH / 8 * RECORD_SEC)
        -- 录完自动回放
        sys.sendMsg(taskName, "PLAY")
    end
end

-- ============ 回放（PCM 必须流式） ============
local function play_record(cb)
    if not io.exists(RECORD_PATH) then
        log.error("0s", RECORD_PATH)
        return false
    end
    is_playing = true
    local ok = exaudio.play_start({
        type = 2,                         -- 2=流式播放
        sampling_rate      = SAMPLE_RATE,
        sampling_depth     = SAMPLE_DEPTH,
        signed_or_unsigned = true,        -- exaudio 录出来的是有符号 PCM
        cbfnc = function(e)
            if e == exaudio.PLAY_DONE then
                is_playing = false
                log.info("0t")
                if io.exists(RECORD_PATH) then os.remove(RECORD_PATH) end
                if cb then cb() end
            end
        end,
    })
    if not ok then is_playing = false return false end

    -- 边读边喂数据
    sys.taskInit(function()
        local fp = io.open(RECORD_PATH, "rb")
        if not fp then is_playing = false return end
        local buf = exaudio.get_stream_buffer_size() or 4096
        log.info("0u", buf)
        while is_playing do
            local data = fp:read(buf)
            if not data then break end
            if #data < buf then                    -- 尾包补静音，避免节奏抖动
                data = data .. string.rep("\0", buf - #data)
            end
            exaudio.play_stream_write(data)
            sys.wait(20)                           -- 必须让出时间片
        end
        fp:close()
        exaudio.finish()                            -- ★ 关键：告知没有更多数据
        log.info("0v")
    end)
    return true
end

-- ============ 开始录音 ============
local function start_record()
    if is_recording then log.info("0w") return end
    if is_playing then exaudio.play_stop({type = 2}) is_playing = false end

    if io.exists(RECORD_PATH) then os.remove(RECORD_PATH) end   -- 清旧文件

    exaudio.mic_vol(RECORD_VOL)      -- MIC 增益，录不到/太小就调这个
    exaudio.vol(PLAY_VOL)            -- 回放音量

    local ok = exaudio.record_start({
        format = exaudio.PCM_16000,  -- 16kHz PCM（=3）
        time   = RECORD_SEC,         -- 到点自动停；填0则无限录，需手动record_stop
        path   = RECORD_PATH,        -- ① 直接写文件（最简单）
        cbfnc  = record_end_cb,
    })
    log.info("0x", ok)
    if ok then
        is_recording = true
        log.info("0y", RECORD_SEC, "0z")
    end
end

local function audio_test_task()
	--sys.wait(10000)
	audio_power_on()
	log.info("v", "0A", exaudio.get_audio_mode(),
             "v2:", exaudio.is_audio_v2())
    sys.sendMsg(taskName, "REC")
	while true do
		local msg = sys.waitMsg(taskName)
		if msg and msg[1] == "REC" then
			start_record()
		elseif msg and msg[1] == "PLAY" then
			play_record()
		end
	end

end

local function speaker_audio_test()
    log.info("0B")
    sys.wait(1000)
    audio_power_on()
    audio_path = "/luadb/sample-6s.mp3"

    exaudio.play_start({type= 0, content = audio_path,cbfnc = play_end,priority = 1})
end


_G.at_cmd_handlers["AUDIO_TEST_SPEAKER"] = function(cmd, uart_send)
    _G.audio_power_on()
    uart_send("OK")
    play_audio_test()
end

_G.at_cmd_handlers["AUDIO_TEST_MIC"] = function(cmd, uart_send)
    _G.audio_power_on()
    uart_send("OK")
    sys.taskInitEx(audio_test_task,taskName)
end


--sys.taskInit(speaker_audio_test)
--sys.taskInitEx(audio_test_task,taskName)




-- ==================== 模块导出 ====================
return {
    initAudioDevice = initAudioDevice,
    deinitAudioDevice = deinitAudioDevice,
    getMultimediaId = getMultimediaId
}




