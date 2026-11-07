--[[
audio_wav.lua  v3.8   音频自检：喇叭循环播放 + MIC 回环 + 只录音，基于 v3.6/v3.7
  v3.8 相对 v3.7（本次修复）：
   1) ★ 新增对称的停止接口：stop_speaker / stop_mic / stop_rec / stop_all
   2) ★ 修竞态：用 st.want(意图) + st.running(执行态) 双标志，
      start/stop 都在调用方上下文同步置位 —— "刚 start 就 stop" 也能立即生效
      （v3.7 里 st.running 要等 worker 唤醒才置 true，这段窗口内 stop 会被忽略）
   3) ★ 所有循环/等待都判 st.want，停止响应 ≤100ms（播放中途、录音中途都能停）
   4) ★ 无可用音源且 TTS 不可用时，不再空转：等 1s 重试，连续 3 次失败就退出并报错
   5) 保留 v3.6/3.7：音量默认 播放80/MIC70、回调直写文件不攒内存、空间打印、自动删文件、rec_ctx 守卫
接口（全部非阻塞，可在 AT/串口回调里安全调用）：
  M.start_speaker(opts) / M.stop_speaker()
  M.start_mic(opts)     / M.stop_mic()
  M.start_rec(opts)     / M.stop_rec()
  M.stop() == M.stop_all()
  M.set_vol(play, mic) / M.is_running() / M.is_speaker_running() / M.is_mic_running() / M.get_stats()
消息：WAV_START / WAV_STOP / WAV_STOPPED / WAV_DONE
]]
local exaudio = require "exaudio"
local M = {}

local CFG, st, rec_ctx
CFG = {
    mode        = "loop",            -- 由 start_xxx 设置，不要手改
    sec         = 5,                -- 录音秒数
    frames_per_cb = 1,               -- 每次回调帧数（1 帧 ≈ 20ms），不是秒
    stop_settle = 80,
    gap_ms      = 50,
    spk_gap_ms  = 400,               -- 喇叭循环两遍之间的间隔
    keep_file   = false,             -- false = 测完自动删文件
    min_free_kb = 400,
    -- ★ 音量（100 会削顶+啸叫，实际是增益过冲）
    play_vol    = 70,
    mic_vol     = 70,
    spk_file    = nil,               -- 指定喇叭测试音源；nil = 自动查找
    tts_text    = "音频自检，一二三四五",
    spk_candidates = {
        "/luadb/test.mp3", "/luadb/1.mp3", "/luadb/sample-6s.mp3",
        "/luadb/test.wav", "/ram/audio_hd.wav", "/sd/audio_hd.wav",
    },
    paths       = { "/ram/audio_hd.wav", "/sd/audio_hd.wav" },  -- 不碰内置 Flash
    rate        = 16000,

	require_v2  = false,             -- false = 新旧框架都跑；true = 只允许新框架
    time_slack  = 5,                 -- time 的安全冗余（秒），两套框架通用
}
-- ★ want = 业务意图（调用方同步置位）；running = worker 实际是否在执行
st = { want = false, running = false, mode = nil,
       rounds = 0, peak = 0, bytes = 0, path = nil, src = nil }

-- ================= 基础工具 =================
-- 分段等待：只看 st.want，被 stop 立刻返回 false
local function wait_ms(ms)
    local t0 = os.clock()
    while st.want do
        local el = (os.clock() - t0) * 1000
        if el >= ms then return true end
        local left = ms - el
        sys.wait(left > 100 and 100 or left)
    end
    return false
end

local function free_kb(path)
    local ok, total, used, bsz = io.fsstat(path)
    if not ok or not bsz then return nil end
    return math.floor((total - used) * bsz / 1024),
           math.floor(total * bsz / 1024),
           math.floor(used * bsz / 1024)
end

local function dump_space(tag, path)
    local free, total, used = free_kb(path)
    if free then
        log.info("wav", tag, path, "总量", total, "KB", "已用", used, "KB", "剩余", free, "KB")
    else
        log.warn("wav", tag, path, "fsstat 失败（可能未挂载）")
    end
    return free
end

local function le(v, n)
    local t = {}
    for i = 1, n do t[i] = string.char(v % 256); v = (v - v % 256) / 256 end
    return table.concat(t)
end
local function wav_header(data_len, rate, ch, bits)
    local block = math.floor(ch * bits / 8)
    return "RIFF" .. le(36 + data_len, 4) .. "WAVE"
        .. "fmt " .. le(16, 4) .. le(1, 2) .. le(ch, 2) .. le(rate, 4)
        .. le(rate * block, 4) .. le(block, 2) .. le(bits, 2)
        .. "data" .. le(data_len, 4)
end

local function fmt_of(rate)
    if rate == 8000  then return exaudio.PCM_8000  end
    if rate == 24000 then return exaudio.PCM_24000 end
    if rate == 32000 then return exaudio.PCM_32000 end
    if rate == 48000 then return exaudio.PCM_48000 end
    return exaudio.PCM_16000
end

local function peak16(s)
    local mx, i, n = 0, 1, #s
    while i + 1 <= n do
        local v = s:byte(i) + s:byte(i + 1) * 256
        if v >= 32768 then v = v - 65536 end
        if v < 0 then v = -v end
        if v > mx then mx = v end
        i = i + 16
    end
    return mx
end

local function pick_rec_path()
    for _, p in ipairs(CFG.paths) do
        local fp = io.open(p, "wb")
        if fp then fp:close() log.info("wav", "录音路径 =", p) return p end
        log.warn("wav", "不可写", p)
    end
    return nil
end

local function resolve_src()
    if CFG.spk_file and io.exists(CFG.spk_file) then return CFG.spk_file end
    for _, p in ipairs(CFG.spk_candidates) do
        if io.exists(p) then return p end
    end
    return nil
end

-- ================= 录音（回调直写文件，不攒内存） =================
local function on_mic_data(buff, size)
    local ctx = rec_ctx
    if not ctx then return end
    local d
    if type(buff) == "string" then d = buff
    elseif buff and buff.query then d = buff:query(0, size or buff:used()) end
    if not d or #d == 0 then return end
    if ctx.fp then ctx.fp:write(d) end
    ctx.bytes  = ctx.bytes + #d
    ctx.frames = ctx.frames + 1
    local p = peak16(d)
    if p > ctx.peak then ctx.peak = p end
end

local function record_once(path)
    local need_kb = math.floor(CFG.sec * CFG.rate * 2 / 1024) + 8
    local free = dump_space("开录前", "/ram")
    if free and free < math.max(CFG.min_free_kb, need_kb) then
        log.error("wav", "空间不足：需要", need_kb, "KB 剩余", free, "KB")
        return nil
    end

    local fp = io.open(path, "wb")
    if not fp then log.error("wav", "打不开", path) return nil end
    fp:write(string.rep("\0", 44))              -- 占位头，最后回填

    local ctx = { fp = fp, peak = 0, bytes = 0, frames = 0 }
    rec_ctx = ctx

    local ok = exaudio.record_start({
        format = fmt_of(CFG.rate),
        time   = math.ceil(CFG.sec) + CFG.time_slack,   -- ★ 安全上限，不是目标时长
        path   = on_mic_data,
    })
    log.info("wav", "record_start =", ok, "sec =", CFG.sec,
             "time上限 =", math.ceil(CFG.sec) + CFG.time_slack,
             "mic_vol =", CFG.mic_vol, "框架 =", exaudio.is_audio_v2() and "new" or "old")
    if not ok then
        rec_ctx = nil pcall(function() fp:close() end)
        return nil
    end

    local full = wait_ms(CFG.sec * 1000)        -- ★ 可被 stop 打断
    if not full then log.warn("wav", "录制被提前停止") end

    pcall(exaudio.record_stop)
    if CFG.stop_settle > 0 then wait_ms(CFG.stop_settle) end
    rec_ctx = nil                               -- ★ 守卫
    pcall(function() fp:close() end)

    local data_len = ctx.bytes
    local hfp = io.open(path, "r+b") or io.open(path, "r+")
    if hfp then
        hfp:seek("set", 0)
        hfp:write(wav_header(data_len, CFG.rate, 1, 16))
        hfp:close()
    else
        log.error("wav", "回填 WAV 头失败")
    end

    st.peak, st.bytes = ctx.peak, data_len
    log.info("wav", "录完", data_len, "字节 峰值 =", ctx.peak, "帧 =", ctx.frames,
             "期望 =", math.floor(CFG.sec * CFG.rate * 2),
             "文件 =", (io.fileSize and io.fileSize(path)) or -1, "字节")
    dump_space("录完后", "/ram")
    return data_len
end

-- ================= 播放 =================
local function on_play_done(ev)
    if ev == exaudio.PLAY_DONE then sys.publish("WAV_DONE") end
end

-- 等播放完成：只看 st.want，被 stop 立刻返回 false（≤100ms）
local function wait_play_done(timeout_ms)
    local t0 = os.clock()
    while st.want do
        if sys.waitUntil("WAV_DONE", 100) then return true end
        if (os.clock() - t0) * 1000 >= timeout_ms then return false end
    end
    return false
end

local function play_file_once(path, timeout_ms)
    sys.waitUntil("WAV_DONE", 1)                -- 清残留完成消息
    local ok = exaudio.play_start({
        type = 0, content = path, cbfnc = on_play_done, priority = 0,
    })
    log.info("wav", "play_start(0) =", ok, "vol =", CFG.play_vol)
    if not ok then return false end
    local done = wait_play_done(timeout_ms or 30000)
    pcall(exaudio.play_stop, { type = 0 })
    return done
end

local function play_tts_once(timeout_ms)
    sys.waitUntil("WAV_DONE", 1)
    local ok = exaudio.play_start({
        type = 1, content = CFG.tts_text, cbfnc = on_play_done, priority = 0,
    })
    log.info("wav", "play_start(1) TTS =", ok)
    if not ok then return false end
    local done = wait_play_done(timeout_ms or 20000)
    pcall(exaudio.play_stop, { type = 1 })
    return done
end

-- ================= 三条业务流程 =================
-- ① 喇叭循环播放
local function run_speaker()
    local src = resolve_src()
    st.src = src
    log.info("wav", "喇叭测试音源 =", src or "TTS(内置)", "音量 =", CFG.play_vol)
    local fail = 0
    while st.want do
        local ok
        if src then ok = play_file_once(src, 60000)
        else        ok = play_tts_once(20000) end
        if not st.want then break end          -- ★ 停止：立刻退出

        if not ok then
            fail = fail + 1
            log.warn("wav", "喇叭播放失败", fail, "次", src or "TTS")
            if fail >= 3 then
                log.error("wav", "连续3次失败：无可用音源或TTS不可用，退出喇叭测试")
                return false, "NO_SOURCE"
            end
            wait_ms(1000)                      -- ★ 不再空转
        else
            fail = 0
        end
        wait_ms(CFG.spk_gap_ms)
        st.rounds = st.rounds + 1
        log.info("wav", "喇叭第", st.rounds, "遍完成")
    end
    return true
end

-- ② 只录音
local function run_rec()
    local path = pick_rec_path()
    if not path then return false, "NO_FS" end
    st.path = path
    while st.want do
        record_once(path)
        st.rounds = st.rounds + 1
        log.info("wav", "录音第", st.rounds, "轮 峰值 =", st.peak)
    end
    return true
end

-- ③ MIC -> 喇叭 回环
local function run_loopback()
    local path = pick_rec_path()
    if not path then return false, "NO_FS" end
    st.path = path
    while st.want do
        local t0 = os.clock()
        local n = record_once(path)
        if not st.want then break end
        if n and n > 0 then
            local dur = math.floor(n / (CFG.rate * 2) * 1000)
            log.info("wav", "WAV 时长", dur, "ms 开始回放")
            play_file_once(path, dur + 5000)
            wait_ms(CFG.gap_ms)
        end
        st.rounds = st.rounds + 1
        log.info("wav", "回环第", st.rounds, "轮 峰值 =", st.peak,
                 "周期 =", math.floor((os.clock() - t0) * 1000), "ms")
    end
    return true
end

-- ================= 常驻 worker（全工程只建一次） =================
local function worker()
    while true do
        sys.waitUntil("WAV_START")
        if not st.want then                    -- start 后立刻 stop：什么都不做
            log.info("wav", "启动请求已被取消")
            sys.publish("WAV_STOPPED")
        else
            st.running = true
            local ok, err = pcall(function()
                if st.mode == "spk"  then return run_speaker()  end
                if st.mode == "rec"  then return run_rec()      end
                if st.mode == "loop" then return run_loopback() end
                return false, "BAD_MODE"
            end)

            rec_ctx = nil
            pcall(exaudio.record_stop)
            pcall(exaudio.play_stop, { type = 0 })
            pcall(exaudio.play_stop, { type = 1 })

            if not CFG.keep_file and st.path then
                local fsz = (io.fileSize and io.fileSize(st.path)) or -1
                local r = os.remove(st.path)
                log.info("wav", "已删除", st.path, "结果 =", r, "原大小 =", fsz, "字节")
                st.path = nil
            end
            dump_space("清理后", "/ram")
            collectgarbage("collect")
            log.info("wav", "内存 =", math.floor(collectgarbage("count")), "KB")

            st.running, st.want = false, false
            sys.publish("WAV_STOPPED")
            if not ok then log.error("wav", "会话异常", err) end
            if err  then log.error("wav", "会话失败原因", err) end
        end
    end
end
sys.taskInit(worker)

-- ================= 对外接口（全部非阻塞） =================
local function apply_vol()
    local v1 = exaudio.vol(CFG.play_vol)
    local v2 = exaudio.mic_vol(CFG.mic_vol)
    log.info("wav", "音量 播放 =", CFG.play_vol, "→", v1,
             " MIC =", CFG.mic_vol, "→", v2)
    return v1, v2
end

-- ★ start 在调用方上下文同步置 st.want，杜绝"刚 start 就 stop"的窗口
local function start_with(mode, opts)
    if st.want or st.running then return false, "BUSY" end
    if opts then for k, v in pairs(opts) do CFG[k] = v end end
		
	local is_v2 = exaudio.is_audio_v2()
    if CFG.require_v2 and not is_v2 then
        return false, "NOT_AUDIO_V2"                -- ★ 默认不拦，只有显式要求时才拦
    end
    log.info("wav", "音频框架 =", is_v2 and "new(audio_v2)" or "old(audio)",
             "require_v2 =", CFG.require_v2)
    st.mode = mode
    st.rounds, st.peak, st.bytes, st.src = 0, 0, 0, nil
    apply_vol()
    st.want = true                             -- ★ 先置意图，再发消息
    sys.publish("WAV_START")
    return true
end

-- ★ stop 同样同步置位，即使 worker 还没被唤醒也能取消
local function stop_any()
    if not st.want and not st.running then return false, "NOT_RUNNING" end
    st.want = false                            -- ★ 立刻生效
    sys.publish("WAV_STOP")
    return true
end

function M.start_speaker(opts) return start_with("spk",  opts) end   -- ① 喇叭测试
function M.start_rec(opts)     return start_with("rec",  opts) end   -- ② 只录音
function M.start_mic(opts)     return start_with("loop", opts) end   -- ③ 回环

function M.start(opts)
    local mode = (opts and opts.mode) or "loop"
    return start_with(mode, opts)
end

function M.stop_speaker() return stop_any() end      -- ★ 随时停喇叭
function M.stop_mic()     return stop_any() end      -- ★ 随时停回环
function M.stop_rec()     return stop_any() end      -- ★ 随时停录音
function M.stop()         return stop_any() end
function M.stop_all()     return stop_any() end

function M.set_vol(play, mic)
    if play then CFG.play_vol = play end
    if mic  then CFG.mic_vol  = mic  end
    return apply_vol()
end

function M.is_running()         return st.want or st.running end
function M.is_speaker_running() return (st.want or st.running) and st.mode == "spk"  end
function M.is_mic_running()     return (st.want or st.running) and st.mode == "loop" end
function M.is_rec_running()     return (st.want or st.running) and st.mode == "rec"  end
function M.get_stats()
    return { mode = st.mode, running = st.running, want = st.want,
             rounds = st.rounds, peak = st.peak, bytes = st.bytes,
             path = st.path, src = st.src,
             play_vol = CFG.play_vol, mic_vol = CFG.mic_vol }
end

_G.at_cmd_handlers["SPEAKER_TEST_START"] = function(cmd, uart_send)
    sys.taskInit(function()
    	_G.audio_power_on()
        local ok = M.start_speaker()
        uart_send(ok and "OK" or "ERROR")
    end)
end

_G.at_cmd_handlers["SPEAKER_TEST_STOP"] = function(cmd, uart_send)
    sys.taskInit(function()
        local ok = M.stop_speaker()
        sys.waitUntil("WAV_STOPPED")
    	_G.audio_power_off()
        uart_send(ok and "OK" or "ERROR")
    end)
end



_G.at_cmd_handlers["MIC_TEST_START"] = function(cmd, uart_send)
    sys.taskInit(function()
    	_G.audio_power_on()
        local ok = M.start_mic()
        uart_send(ok and "OK" or "ERROR")
    end)
end

_G.at_cmd_handlers["MIC_TEST_STOP"] = function(cmd, uart_send)
    sys.taskInit(function()
        local ok = M.stop_mic()
        sys.waitUntil("WAV_STOPPED")
    	_G.audio_power_off()
        uart_send(ok and "OK" or "ERROR")
    end)
end


return M
