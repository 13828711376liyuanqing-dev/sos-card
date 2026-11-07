local LOG_DIR  = "/log"      -- 写片内 FS 就用 "/log"
local LOG_FILE = LOG_DIR .. "/app.log"
local BLE_DIR  = "/ble"      -- 写片内 FS 就用 "/log"
local BLE_FILE = LOG_DIR .. "/ble.ini"
-- SAM | 2026-11-03 +08:00 | 128 KB x2 could fill the CAT1 file system and stop a whole-device OTA (COMPONENT_SPACE); 16 KB x2 as in the 11-02 slim plan.
local LOG_MAX  = 16 * 1024      -- 单文件上限，超过就滚动
local BUF_MAX  = 10 * 1024           -- 缓冲阈值，攒够再落盘
local buf, buf_len = {}, 0

httpplus = require("httpplus")

if not io.dexist(LOG_DIR) then
    local ok, err = io.mkdir(LOG_DIR)
    log.info("fs", "mkdir", LOG_DIR, ok, err)   -- 失败会返回 false, 负数错误码
end

if not io.dexist(BLE_DIR) then
    local ok, err = io.mkdir(BLE_DIR)
    log.info("fs", "mkdir", BLE_DIR, ok, err)   -- 失败会返回 false, 负数错误码
end

-- SAM | 2026-11-04 +08:00 | While an OTA job is in flight (update.lua ota_log_paused) log files are not written, so they cannot use
-- the space the OTA reserved; the buffer is dropped and writing resumes when the job is back to IDLE.
local function ota_paused() return _G.ota_log_paused ~= nil and _G.ota_log_paused() == true end
local function log_flush()
    if ota_paused() then buf, buf_len = {}, 0; return true end
    if buf_len == 0 then return true end
    local fd = io.open(LOG_FILE, "ab")      -- ★ "ab" 追加，绝不能是 "w"
    if not fd then return false end
    local ok = fd:write(table.concat(buf))
    fd:close()                               -- ★ 必须 close，否则丢数据
    buf, buf_len = {}, 0
    return ok
end

function log_write(level, tag, ...)
    if ota_paused() then return end
    local t = string.format("%s[%s][%s]", os.date("%Y-%m-%d %H:%M:%S"), level, tag)
    for i = 1, select("#", ...) do
        t = t .. " " .. tostring((select(i, ...)))
    end
    buf[#buf + 1] = t .. "\r\n"
    buf_len = buf_len + #t + 2

    if buf_len >= BUF_MAX then
        -- 滚动：超限就把旧文件改名/删掉
        if io.fileSize and (io.fileSize(LOG_FILE) or 0) > LOG_MAX then
            os.remove(LOG_FILE .. ".bak")
            os.rename(LOG_FILE, LOG_FILE .. ".bak")
            buf, buf_len = {}, 0
        end
        log_flush()
    end
end

-- 挂个定时 flush，防止缓存长期不落盘
sys.timerLoopStart(log_flush, 30000)


function uploadLogFile()
    local recFilePath = LOG_FILE 
    local imei = mobile.imei()

    local file_name = string.format("%s-%s.log", imei, os.date("%Y%m%d_%H%M%S"))

    log.info("文件路径", recFilePath)
    log.info("文件名称", file_name)

    local formParams = {
        fileName = file_name,
    }

    local fileParams = {
        file = recFilePath
    }

    local opts = {
        url = "http://tkaiot-iotplatform500.tkhealthcare.com/centerservice/iotmngserver/otaFirmware/upload",
        --url = user_cfg.http_url,
        method = "POST",
        forms = formParams,
        files = fileParams,
        --timeout = HTTP_TIMEOUT,
        debug = true, -- 开启完整HTTP收发日志，抓包看上传内容
    }

    local code, response = httpplus.request(opts)

    log.info("httpplus.request", code==200 and "success" or "error", code)
    if code==200 then
        log.info("文件上传成功")
        log.info("httpplus.request headers", json.encode(response.headers or {}))
        local body = response.body:query()
        log.info("httpplus.request body", body and (body:len()>512 and body:len() or body) or "nil")         
    else
        log.info("文件上传失败")
   
    end
end

function create_upload_log()
    uploadLogFile()
end    

-- SAM | 2026-11-02 +08:00 | Global because mqtts_receiver logMsg calls it; as a local it was nil there.
function create_upload_log_task()
    sys.taskInit(create_upload_log)

end

local function ble_write_to_file(data)
    local fd = io.open(BLE_FILE, "ab")      -- ★ "ab" 追加，绝不能是 "w"
    if not fd then return false end
    local ok = fd:write(data)
    fd:close()                               -- ★ 必须 close，否则丢数据

    return ok
end

local function uploadBleFile()
    --local body_data = io.readFile(BLE_FILE)          -- 位置数据一般很小，整读没问题
    --if not body_data then return false end

    local size = io.fileSize(BLE_FILE)
    if not size or size == 0 then
        log.error("uploadBleFile", "file missing or empty", BLE_FILE)
        return false
    end
    log.info("uploadBleFile", "size", size)

    local body_data = io.readFile(BLE_FILE) 

    local boundary = "----LuatOSBoundary" .. tostring(os.time()) .. tostring(math.random(1000, 9999))
    
    local imei = mobile.imei()
    local file_name = string.format("%s-%s.json", imei, os.date("%Y%m%d_%H%M%S"))


    local json_str = json.encode({
        requestId = "98633c6229fff6c29128f3ded98522d1",
        --businessCode = "3ndcard_his_rail",
        --encryptionData = "H645irtEbusinessCode+secretKey",
        --time = tostring(os.time()),
        fileName = file_name,
        deviceId = imei,
    })

    local build_body_data = "[" .. body_data .. "]"

    local head = table.concat({
        "--", boundary, "\r\n",
        'Content-Disposition: form-data; name="data"\r\n',
        "Content-Type: application/json\r\n\r\n",
        json_str, "\r\n",
        "--", boundary, "\r\n",
        --'Content-Disposition: form-data; name="zipData"; filename="file_name"', "\r\n",
        "Content-Disposition: form-data; name=\"zipData\"; filename=\""..file_name.."\"", "\r\n",
        "Content-Type: application/octet-stream\r\n\r\n", 
    })
    local tail = "\r\n--" .. boundary .. "--\r\n"

    --log.info("uploadBleFile", "body", head .. build_body_data .. tail)

    local code, resp = httpplus.request({
        url     = "http://tkaiot-iotplatform500.tkhealthcare.com/warncard3httpdev/device-msg-parse/api/device/uploadLocation",
        method  = "POST",
        headers = {["Content-Type"] = "multipart/form-data; boundary=" .. boundary},  -- 这里必须自己带全 boundary
        body    = head .. build_body_data .. tail,
        timeout = 30,
        debug = true, 
    })
    log.info("up", "code", code, code == 200 and resp.body and resp.body:query() or tostring(resp))
  

    os.remove(BLE_FILE)
end

function create_upload_ble_file()
    uploadBleFile()
end    

local function create_upload_ble_task()
    sys.taskInit(create_upload_ble_file)

end

_G.at_cmd_handlers["LOG_UPLOAD"] = function(cmd, uart_send)
    create_upload_log_task()
end

_G.at_cmd_handlers["BEACON_DATA="] = function(cmd, send)
    --log.info("BEACON_DATA", "收到命令:", cmd)                          -- ← 新增日志①：确认命令到达
    
    local param = cmd:match("BEACON_DATA=(.*)")
    --log.info("BEACON_DATA", "param:", param)                          -- ← 新增日志②：确认解析参数
    if not param or param == "" then
        --send("ERROR: Missing parameters")
        log.info("BEACON_DATA", "ERROR: Missing parameters")
        return
    end
    local topic, payload = param:match("^(.-),(.*)$")
    log.info("BEACON_DATA", "topic:", topic, "payload", payload)      -- ← 新增日志③：确认分割结果
    if not topic or not payload then
        --send("ERROR: Invalid format, expected <topic>,<payload>")
        log.info("BEACON_DATA", "ERROR: Invalid format")
        return
    end
    topic = topic:match("^%s*(.-)%s*$")
    payload = payload:match("^%s*(.-)%s*$")
    if topic == "" or payload == "" then
        --send("ERROR: Topic or payload empty")
        log.info("BEACON_DATA", "ERROR: Topic or payload empty")
        return
    end

    if topic == "FIRST" then 
        local first_data = payload .. ","
        ble_write_to_file(first_data)
    elseif topic == "LAST" then 
        local last_data = payload
        ble_write_to_file(last_data)
        create_upload_ble_task()
    else 
        local continue_data = payload .. ","
        ble_write_to_file(continue_data)
    end    
end

_G.at_cmd_handlers["BEACON_UPLOAD"] = function(cmd, uart_send)
    create_upload_ble_task()
end

-- 使用
--log_write("I", "app", "启动", rtos.version())