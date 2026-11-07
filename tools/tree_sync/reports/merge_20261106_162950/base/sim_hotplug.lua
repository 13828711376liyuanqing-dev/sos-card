-- ===== SIM 热插拔：检测脚 =====
local DET_PIN = gpio.USIM_DET or gpio.WAKEUP2   -- Air780Exx 固定 PIN79
local last_present = nil
local switching    = false
local pending      = nil
local SIM_TARGET   = 0            -- 单卡：0；双卡：按需切 0/1

gpio.debounce(DET_PIN, 500)       -- 官方 500ms 防抖

-- 中断回调：只记录 + 通知任务，绝不做耗时动作
local function sim_det_cb(val)
    local present = (val == 0)     -- 0 = 卡在位
    if present == last_present then return end   -- ★ 状态没变就不理
    last_present = present
    pending = present
    sys.publish("SIM_DET_CHANGE")
end
gpio.setup(DET_PIN, sim_det_cb)

local function on_sim_change(present)
    switching = true
    if present then
        log.info("sim", "插卡 → 重新驻网")
        mobile.flymode(0, true)
        sys.wait(500)              -- 给底层一点时间真正断开射频
        -- 双卡：切换前必须确保不在飞行模式，否则 simid 会失败
        -- mobile.flymode(0, false); sys.wait(500); mobile.simid(SIM_TARGET)
        mobile.flymode(0, false)
        -- 等待注册：status 1/5 才算成功，2 是正常中间态
        local t = 0
        while t < 30000 do         -- 最多等 30 秒
            if mobile.status() == 1 or mobile.status() == 5 then break end
            sys.wait(1000); t = t + 1000
        end
        log.info("sim", "注册结果 status =", mobile.status())
    else
        log.info("sim", "拔卡 → 进飞行模式")
        mobile.flymode(0, true)
    end
    switching = false
end

local function sim_task()
    while true do
        sys.waitUntil("SIM_DET_CHANGE", 60000)
        log.info("sim", "get SIM_DET_CHANGE event or timeout")
        if pending ~= nil and not switching then
            local p = pending; pending = nil
            on_sim_change(p)
        end
    end
end


local function mobileinfo_task()
	log.info("status", mobile.status())
    sys.wait(2000)
    while 1 do
        log.info("imei", mobile.imei())
        log.info("imsi", mobile.imsi())
        log.info("apn", mobile.apn()) -- 获取当前APN
        log.info("status", mobile.status())
        log.info("iccid", mobile.iccid())
        log.info("csq", mobile.csq()) -- 4G模块的CSQ并不能完全代表强度
        log.info("rssi", mobile.rssi()) -- 需要综合rssi/rsrq/rsrp/snr一起判断
        log.info("rsrq", mobile.rsrq())
        log.info("rsrp", mobile.rsrp())
        log.info("snr", mobile.snr())
        log.info("simid", mobile.simid()) -- 这里是获取当前SIM卡槽
        -- log.info("apn", mobile.apn(0,1))
        -- sys内存
        log.info("lua", rtos.meminfo())
        log.info("sys", rtos.meminfo("sys"))
        sys.wait(15000)
    end
end

--sys.taskInit(mobileinfo_task)

sys.taskInit(sim_task)