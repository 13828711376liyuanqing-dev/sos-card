-- 默认配置（结构体默认值）
local default_user_cfg = {
    sip_url = "103.169.62.13",
    sip_port = 5060,
    username = "10003",
    password = "tk@2026",
    log_url = ""
}

-- 全局当前配置表
user_cfg = nil

local CFG_FILE = "/user_cfg.bin"

local function print_user_config()
    log.info("==== 当前用户配置 ====")
    log.info("sip_url :", user_cfg.sip_url)
    log.info("sip_port :", user_cfg.sip_port)
    log.info("username:", user_cfg.username)
    log.info("password:", user_cfg.password)
    log.info("log_url:", user_cfg.log_url)
    log.info("======================")
end

function init_user_config()
    -- 文件不存在，使用默认配置
    log.info("初始化配置文件")

    if not io.exists(CFG_FILE) then
        log.info("配置文件不存在，加载默认配置")
        user_cfg = json.decode(json.encode(default_user_cfg))
        return false
    end

    local f = io.open(CFG_FILE, "rb")
    if not f then
        log.info("打开配置文件失败，使用默认配置")
        user_cfg = json.decode(json.encode(default_user_cfg))
        return false
    end
    
    local data = f:read("*a")
    f:close()

    -- 解析json
    user_cfg = json.decode(data)
    if not user_cfg or type(user_cfg) ~= "table" then
        log.info("配置文件损坏，重置为默认配置")
        user_cfg = json.decode(json.encode(default_user_cfg))
        return false     
    end

    return true    
end

function set_user_cfg(key, val)
    if not user_cfg then
        log.info("配置未初始化")
        return false
    end
    if key == "sip_url"  then
        user_cfg[key] = tostring(val)
    elseif key == "sip_port" then
        user_cfg[key] = tonumber(val)
    elseif key == "username" then
        user_cfg[key] = tostring(val)
    elseif key == "password" then
        user_cfg[key] = tostring(val)   
    elseif key == "log_url" then
        user_cfg[key] = tostring(val)              
    else
        log.info("不存在的配置字段:", key)
        return false
    end
    log.info("修改配置", key, "=", val)
    
    return true
end

function save_user_config()

    local f = io.open(CFG_FILE, "wb")
    if not f then
        log.info("打开配置文件失败，无法保存")
        return false
    end
    -- 序列化table为字符串写入
    local str = json.encode(user_cfg)
    f:write(str)
    f:close()
    log.info("配置保存成功", CFG_FILE)

    return true 
end

function config_task()
    sys.wait(100)
    init_user_config()
    print_user_config()
end

sys.taskInit(config_task)