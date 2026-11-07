--[[
@module libfota2
@summary fota升级v2
@version 1.1
@date    2024.11.22
@author  wendal/HH
@demo    fota2
@usage
--用法实例
local libfota2 = require("libfota2")

-- 功能:获取fota的回调函数
-- 参数:
-- result:number类型
--   0表示成功
--   1表示连接失败
--   2表示url错误
--   3表示服务器断开
--   4表示接收报文错误
--   5表示使用iot平台VERSION需要使用 xxx.yyy.zzz形式
function libfota_cb(result)
    log.info("fota", "result", result)
    -- fota成功
    if result == 0 then
        rtos.reboot()   --如果还有其他事情要做,自行决定reboot的时机
    end
end

--下方示例为合宙iot平台,地址:http://iot.openluat.com
libfota2.request(libfota_cb)

--如使用自建服务器,自行更换url
-- 对自定义服务器的要求是:
-- 若需要升级, 响应http 200, body为升级文件的内容
-- 若不需要升级, 响应300或以上的代码,务必注意
local opts = {url="http://xxxxxx.com/xxx/upgrade"}
-- opts的详细说明, 看后面的函数API文档
libfota2.request(libfota_cb, opts)

-- 若需要定时升级
-- 合宙iot平台
sys.timerLoopStart(libfota2.request, 4*3600*1000, libfota_cb)
-- 自建平台
sys.timerLoopStart(libfota2.request, 4*3600*1000, libfota_cb, opts)

-- 版本更新说明
-- 版本号：202607021200
-- 1、更新时间：2026-07-02 12:00
-- 2、更新内容
--    新增libfota2.version()接口
--    支持libfota2库文件版本号管理功能，版本号的格式为：yyyymmddhhmm，表示yyyy年mm月dd日hh时mm分发布的版本
]]

local libfota2 = {}

-- 单独判断下服务器下发的数据是不是"{"开头"}"结尾的字符串
local function isjson(str)
    local start, _ = string.find(str, "^%{")
    local _, end_ = string.find(str, "%}$")
    return start == 1 and end_ == #str and string.sub(str, 2, #str - 1):find("%B{") == nil
end

-- 根据模组型号自动获取设备标识查询串
local function get_device_query()
    local model = hmeta.model()

    -- 4G模组走IMEI
    if model:find("^Air780E")         -- Air780Exx 系列模组
        or model:find("^Air8000")     -- Air8000 系列模组
        or model:find("^Air700") then -- Air700 系列模组
        return "imei=" .. mobile.imei()

        -- WiFi/MCU模组走MAC地址
    elseif model:find("^Air8101") then -- Air8101 系列模组
        return "mac=" .. wlan.getMac()

        -- 部分模组需要使用 mcu.unique_id()
    elseif model:find("^Air1601")      -- Air1601 系列模组
        or model:find("^Air1602")      -- Air1602 系列模组
        or model:find("^Air1780") then -- Air1780 系列模组
        return "mac=" .. mcu.unique_id():toHex()
    end
end

local function fota_task(cbFnc, opts)
    local ret = 0
    local url = opts.url
    local code, headers, body = http.request(opts.method, opts.url, opts.headers, opts.body, opts, opts.server_cert,
                                    opts.client_cert, opts.client_key, opts.client_password).wait()
    -- log.info("http fota", code, headers, body)
    if code == 200 or code == 206 then
        if body == 0 then
            ret = 4
        else
            ret = 0
        end
    elseif code == -4 then
        ret = 1
    elseif code == -5 then
        ret = 3
    else
        log.info("l", code, body)
        ret = 4
        local hziot = "iot.openluat.com"
        local msg, json_body, result
        if string.find(url, hziot) then
            log.info("4o")
            json_body, result = json.decode(body)
            -- 如果json解析失败，证明服务器下发的不是json
            if result == 1 and isjson(body) then
                code = json_body["code"]
            else
                -- 这个值随便取的，只要不和其他定义重复就行
                code = 1111111111111
            end
            if code == 43 then
                log.info("4p",
                    "4q")
            elseif code == 3 then
                log.info("4r", "4s")
            elseif code == 17 then
                log.info("4t",
                    "4u")
            elseif code == 21 then
                log.info("4v", "4w")
            elseif code == 25 then
                log.info("4x",
                    "4y")
            elseif code == 26 then
                log.info("4z",
                    "4A")
            elseif code == 27 then
                log.info("4B",
                    "4C")
            elseif code == 40 then
                log.info("4D",
                    "4E")
            elseif code == 1111111111111 then
                log.info("4F", "4G", type(body), body)
            else
                log.info("4H", code)
            end
        end
    end

    cbFnc(ret)
end

--[[
fota升级
@api libfota2.request(cbFnc, opts)
@function cbFnc 用户回调函数，回调函数的调用形式为：cbFnc(result) , 必须传
@table fota参数, 后面有详细描述
@return nil 无返回值
@usaga

-- opts参数说明, 所有参数都是可选的
-- 1. opts.url string 升级所需要的URL, 若使用合宙iot平台,则不需要填
-- 2. opts.version string 版本号, 默认是 BSP版本号.x.z格式
-- 3. opts.timeout int 请求超时时间, 默认300000毫秒,单位毫秒
-- 4. opts.project_key string 合宙IOT平台的项目key, 默认取全局变量PRODUCT_KEY. 自建服务器不用填
-- 5. opts.imei string 设备识别码, 默认取IMEI(Cat.1模块)或WLAN MAC地址(wifi模块)或MCU唯一ID
-- 6. opts.firmware_name string 固件名称,默认是 _G.PROJECT.. "_LuatOS-SoC_" .. rtos.bsp()
-- 7. opts.server_cert string 服务器证书, 默认不使用
-- 8. opts.client_cert string 客户端证书, 默认不使用
-- 9. opts.client_key string 客户端私钥, 默认不使用
-- 10. opts.client_password string 客户端私钥口令, 默认不使用
-- 11. opts.method string 请求方法, 默认是GET
-- 12. opts.headers table 额外添加的请求头,默认不需要
-- 13. opts.body string 额外添加的请求body,默认不需要
]]
function libfota2.request(cbFnc, opts)
    if not opts then
        opts = {}
    end
    if fota then
        opts.fota = true
    else
        os.remove("/update.bin")
        opts.dst = "/update.bin"
    end
    if not cbFnc then
        cbFnc = function(ret)
        end
    end
    -- 处理URL
    if not opts.url then
        opts.url = "http://iot.openluat.com/api/site/firmware_upgrade?"
    end
    local query = ""
    if opts.url:sub(1, 3) ~= "###" and not opts.url_done then
        -- 补齐project_key函数
        if not opts.project_key then
            opts.project_key = _G.PRODUCT_KEY
            if not opts.project_key then
                log.error("l", "4I")
                cbFnc(5)
                return
            end
        end
        -- 补齐version参数
        if not opts.version then
            local x, y, z = string.match(_G.VERSION, "(%d+).(%d+).(%d+)")
            opts.version = rtos.version():sub(2) .. "." .. x .. "." .. z
        end
        -- 补齐firmware_name参数
        if not opts.firmware_name then
            local bsp = rtos.bsp()
            -- 如bsp包含'-', 就截取'-'前面的部分, 例如"air105-evb"就取"air105"
            if bsp:find("-") then
                bsp = bsp:sub(1, bsp:find("-") - 1)
            end
            opts.firmware_name = _G.PROJECT .. "_LuatOS-SoC_" .. bsp
        end
        -- 补齐imei参数
        if not opts.imei then
            query = get_device_query()
        end

        -- 然后拼接到最终的url里
        if not opts.imei then
            opts.url = string.format("%s%s&project_key=%s&firmware_name=%s&version=%s", opts.url, query, opts.project_key, opts.firmware_name, opts.version)
        else
            opts.url = string.format("%simei=%s&project_key=%s&firmware_name=%s&version=%s", opts.url, opts.imei, opts.project_key, opts.firmware_name, opts.version)
        end
    else
        if opts.url:sub(1,3)=="###" then
            opts.url = opts.url:sub(4)
        end
    end
    opts.url_done = true
    -- 处理method
    if not opts.method then
        opts.method = "GET"
    end
    log.info("4J", opts.method, opts.url)
    log.info("4K", query)
    log.info("4L", opts.project_key)
    log.info("4M", opts.firmware_name)
    log.info("4N", opts.version)
    sys.taskInit(fota_task, cbFnc, opts)
end

--[[
获取库版本信息
@return string 年月日时分，例如： "202606300102"
@usage
libfota2.version()
]]
function libfota2.version()
    return "202607021200"
end

log.debug("l", "g" .. libfota2.version())

return libfota2
