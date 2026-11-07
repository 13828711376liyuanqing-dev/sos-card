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



-- ==================== 模块导出 ====================
return {
    initAudioDevice = initAudioDevice,
    deinitAudioDevice = deinitAudioDevice,
    getMultimediaId = getMultimediaId
}




