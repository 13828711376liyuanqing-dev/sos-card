local exgnss = require("exgnss")

local GPS_LOCATE_TIMEOUT = 45
local GNSS_POWER_PIN = 21      -- GPS电源控制
local gnssUartId = 2
local gps_locate_success = false
local wifi_scan_timer_id = nil
local wifi_scan_timer_out = false
local wifi_scan_done = false
local wifi_s_time
local cell_s_time
local test_online_msg = false
local test_sos_pos_msg = false
local test_offline_msg = false
local test_finddevice_msg = false


local function gnss_state(event, ticks)
    log.info("exgnss", "state", event)
    if event == "FIXED" then
        local rmc_data = exgnss.rmc(0)
        local gga2 = exgnss.gga(2)
        if rmc_data then
            log.info("nmea", "rmc", json.encode(rmc_data, "5f"))
            local lat = rmc_data.lat or 0
            local lng = rmc_data.lng or 0
            --sys.publish("UART_SEND_DATA", string.format("GNSS定位成功: lat=%.5f, lng=%.5f", lat, lng))
            local str = string.format("%s|%s|%s", lng, lat, gga2.hdop)

            local json_data = {
                PositionType = "2",
                Body = {
                    {
                        accesstype = 2,
                        ctime = tostring(os.time()),
                        imei = mobile.imei(),
                        gps = str
                    }
                }
            }      
            local content = json.encode(json_data)

            gps_locate_success = true
            
            _G.uart_send_raw("[GPS_RESULT] ", content)
        end
    elseif event == "LOSE" then
        log.info("exgnss", "定位丢失")
        sys.publish("UART_SEND_DATA", "GNSS定位丢失")
    elseif event == "CLOSE" then
        log.info("exgnss", "CLOSE")
        if not gps_locate_success then
            _G.uart_send_raw("[GPS_RESULT] ", "FAILED")
        end    
    end
end

local function gnss_fnc()
    log.info("gnss_app", "开始初始化GNSS")

    local gnssotps = {
        gnssmode = 1,
        agps_enable = true,
        debug = false,
    }

    exgnss.setup(gnssotps)

    exgnss.open(exgnss.TIMERORSUC, {tag = "main_gnss",val=GPS_LOCATE_TIMEOUT, cb = function(tag)
        log.info("GNSS回调", tag)
        local rmc_data = exgnss.rmc(2)
        if rmc_data then
            log.info("nmea", "rmc", json.encode(rmc_data))
        end
    end})
    gps_locate_success = false
    log.info("gnss_app", "GNSS初始化完成")
end

local function gnss_test_fnc()
    log.info("gnss_app", "开始初始化GNSS")

    local gnssotps = {
        gnssmode = 1,
        agps_enable = true,
        debug = true,
        uart = gnssUartId,
        uartbaud = 115200,
        bind = uart.VUART_0,
        auto_open = true,
        gnss_volgpio = GNSS_POWER_PIN        
    }

    exgnss.setup(gnssotps)

    exgnss.open(exgnss.DEFAULT, {tag = "main_gnss", cb = function(tag)
        log.info("GNSS回调", tag)
        local rmc_data = exgnss.rmc(2)
        if rmc_data then
            log.info("nmea", "rmc", json.encode(rmc_data))
        end
    end})

    sys.timerStart(uart.write, 500, gnssUartId, "$CFGTP,1000000,500000,7,0,800,0*7D\r\n")

    log.info("gnss_app", "GNSS初始化完成")
end

local function mac_format(mac_raw)
    if type(mac_raw) ~= "string" or #mac_raw ~= 12 then
        return mac_raw or ""
    end
    local parts = {}
    for i = 1, 12, 2 do
        table.insert(parts, mac_raw:sub(i, i+1))
    end
    return table.concat(parts, ":")
end

local function build_macs_str(wifi_list)
    local arr = {}
    local cnt = 0
    for k,v in pairs(wifi_list) do
        if cnt > 8 then 
            break
        end    
        log.info("scan", v["ssid"], v["rssi"], mac_format(v["bssid"]:toHex()))
        local item = string.format("%s,%d", mac_format(v["bssid"]:toHex()), v["rssi"])
        table.insert(arr, item)    
        cnt = cnt + 1    
    end

    return table.concat(arr, "|")
end

local function build_wifi_scan_result(results)
    if #results < 2 then 
        _G.uart_send_raw("[WIFI_RESULT] ", "FAILED")
    else 
        local imei = mobile.imei() or "unknown"
        local imsi = mobile.imsi() or "unknown"
        local network = "LTE"

        local ctime = tostring(os.time())
        local wifi_e_time = os.time() * 1000
        local cdma = 0
        local macs_str = build_macs_str(results)

        local json_data = {
            PositionType = "1",
            Body = {
                {
                    accesstype = 1,
                    ctime = ctime,
                    imei = imei,
                    imsi = imsi,
                    macs = macs_str,
                    network = network,
                    wifi_e_time = wifi_e_time,
                    wifi_s_time = wifi_s_time,
                    cdma = cdma
                }
            }
        }       
        
        local content = json.encode(json_data)
        --log.info("wifijson",content)

        if test_online_msg == true then 
            mqtt_test_send_online_msg(content)
            test_online_msg = false
        end    

        if test_offline_msg == true then 
            mqtt_test_send_offline_msg(content)
            test_offline_msg = false
        end            

        if test_sos_pos_msg == true then 
            mqtt_test_send_sos_pos_msg(content)
            test_sos_pos_msg = false
        end   
        
        if test_finddevice_msg == true then 
            mqtt_test_send_find_devide_msg(content)
            test_finddevice_msg = false
        end         

        

        _G.uart_send_raw("[WIFI_RESULT] ", content)
    end    
end    

-- wifi扫描成功后, 会有WLAN_SCAN_DONE消息, 读取即可
sys.subscribe("WLAN_SCAN_DONE", function ()
    if wifi_scan_timer_out then return end

    local results = wlan.scanResult()
    log.info("scan", "results", #results)
    
    --for k,v in pairs(results) do
       -- log.info("scan", v["ssid"], v["rssi"], mac_format(v["bssid"]:toHex()))
    --end

    build_wifi_scan_result(results)

    wifi_scan_done = true
    if not wifi_scan_timer_id then
        sys.timerStop(wifi_scan_timer_id)
    end    
end)


local function wifi_scan_timer_cbfunc()
    wifi_scan_timer_out = true

    if wifi_scan_done == false then 
        _G.uart_send_raw("[WIFI_RESULT] ", "FAILED")
    end    
end    

local function wifi_scan_excute()
    log.info("gnss_app", "WIFI 扫描开始")
    wlan.init()
    wlan.scan()
    wifi_s_time = os.time()*1000 --扫描开始时间
    wifi_scan_timer_out = false
    wifi_scan_done = false
    wifi_scan_timer_id = sys.timerStart(wifi_scan_timer_cbfunc, 15000, "wifi_scan")
end

local function start_wifi_scan()
    sys.taskInit(wifi_scan_excute)

end

local function build_nearbts_str()
    local arr = {}
    local cells = mobile.getCellInfo()
    local scell_info = mobile.scell()

    log.info("scell_scan", json.encode(scell_info))    
    log.info("cell_scan", json.encode(cells))
    log.info("cell_scan", "results", #cells)

    if scell_info and cells then
        log.info("cell_scan", "not none")
        for _, c in ipairs(cells) do
            log.info("CID", scell_info.cid,"NCID",c.cid)

            if c.cid == scell_info.cid then
                --ingore
            else
                local item = string.format("%d,%d,%d,%d,%d", c.mcc,c.mnc,c.tac,c.cid,c.rsrp)
                table.insert(arr, item)    
            end
        end
    end

    return table.concat(arr, "|")
end

local function build_cell_scan_result()

    local imei = mobile.imei() or "unknown"
    local imsi = mobile.imsi() or "unknown"
    local network = "LTE"

    local ctime = tostring(os.time())
    local wifi_e_time = os.time() * 1000
    local cdma = 0
    local scell_info = mobile.scell()
    local scell_item = string.format("%d,%d,%d,%d,%d", scell_info.mcc,scell_info.mnc,scell_info.tac,scell_info.cid,scell_info.rssi)

    local nearbts_str = build_nearbts_str()

    local json_data = {
        PositionType = "0",
        Body = {
            {
                accesstype = 0,
                ctime = ctime,
                imei = imei,
                imsi = imsi,
                bts = scell_item,
                nearbts = nearbts_str,
                network = network,
                bts_time = cell_s_time,
                cdma = cdma
            }
        }
    }       
    
    local content = json.encode(json_data)
    log.info("lbsjson",content)

    _G.uart_send_raw("[LBS_RESULT] ", content)
 
end  

function cell_scan_excute()
    log.info("gnss_app", "LBS 扫描开始")
    cell_s_time = os.time()*1000
    mobile.reqCellInfo(15)
    sys.waitUntil("CELL_INFO_UPDATE", 15000)
    --log.info("cell_scan", json.encode(mobile.getCellInfo()))
    build_cell_scan_result()
end

local function start_cell_scan()
    sys.taskInit(cell_scan_excute)

end

-- 订阅
--ys.subscribe("CELL_INFO_UPDATE", cell_info)

-- 定期轮训式
--sys.taskInit(cellinfo_handle_task)

-- =================== 增量代码开始 ===================
-- =================== GNSS AT 命令注册 ===================
_G.at_cmd_handlers = _G.at_cmd_handlers or {}

-- SAM | 2026-10-10 16:51 +08:00 | Acknowledge completed initialization because exgnss APIs return nil, not a success flag.
local gnss_subscribed = false
local function run_gnss_init(fn, send)
    sys.taskInit(function()
        local ok, err = pcall(fn)
        if ok then send("OK") else send("ERROR"); log.error("gnss_app", tostring(err)) end
    end)
end

-- 1. 初始化 GNSS
_G.at_cmd_handlers["GNSSINIT"] = function(cmd, uart_send)
    if not gnss_subscribed then sys.subscribe("GNSS_STATE", gnss_state); gnss_subscribed = true end
    run_gnss_init(gnss_fnc, uart_send)
end
-- gps test
_G.at_cmd_handlers["GPSTEST"] = function(cmd, uart_send)
    run_gnss_init(gnss_test_fnc, uart_send)
end

-- WIFI test
_G.at_cmd_handlers["WIFITEST"] = function(cmd, uart_send)
    start_wifi_scan()
end

-- LBS test
_G.at_cmd_handlers["LBSTEST"] = function(cmd, uart_send)
    start_cell_scan()
end

_G.at_cmd_handlers["TESTONLINEMSG"] = function(cmd, uart_send)
    start_wifi_scan()
    test_online_msg = true
end

_G.at_cmd_handlers["TESTOFFLINEMSG"] = function(cmd, uart_send)
    start_wifi_scan()
    test_offline_msg = true
end

_G.at_cmd_handlers["TESTSOS_POS_MSG"] = function(cmd, uart_send)
    start_wifi_scan()
    test_sos_pos_msg = true
end

_G.at_cmd_handlers["TESTFINDDEVICE"] = function(cmd, uart_send)
    start_wifi_scan()
    test_finddevice_msg = true
end

function test_device_find()
    start_wifi_scan()
    test_finddevice_msg = true
end    

-- 2. 查询定位数据
_G.at_cmd_handlers["GNSSINFO"] = function(cmd, uart_send)
    local rmc = exgnss.rmc(0)
    if rmc and rmc.lat and rmc.lng then
        uart_send("+GNSS: " .. string.format("lat=%.5f lng=%.5f", rmc.lat, rmc.lng))
    else
        uart_send("+GNSS: no fix")
    end
end

-- 3. 重启 GNSS
_G.at_cmd_handlers["GNSSRST"] = function(cmd, uart_send)
    -- SAM | 2026-10-10 16:51 +08:00 | Restart only the legacy tag because antenna and other GNSS clients share ownership.
    run_gnss_init(function()
        exgnss.close(exgnss.TIMERORSUC, {tag="main_gnss"})
        exgnss.close(exgnss.DEFAULT, {tag="main_gnss"})
        exgnss.open(exgnss.DEFAULT, {tag="main_gnss"})
        assert(exgnss.is_active(exgnss.DEFAULT, {tag="main_gnss"}), "GNSS inactive")
    end, uart_send)
end
