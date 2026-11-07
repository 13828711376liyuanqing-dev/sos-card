-- SAM | 2026-10-26 +08:00 | Specialize permanently disabled private DFU callback and omit unused fixed constants; public behavior remains equivalent.
-- SAM | 2026-10-26 +08:00 | Build-only private-function reachability elimination; all public DFU queries/callbacks/rejections are retained.
--[[
@module  dfu_transfer
@summary GR5526 DFU Host (Cat1 side) — UART Normal Mode firmware transfer
@version 1.0
@date    2026-08-31

功能：
- HTTP 下载 GR5526 固件到 Cat1 LFS 文件系统
- 作为 DFU 主机，通过 UART1 向 GR5526 发送固件（GR5xx DFU Normal Mode）
- 6 个 AT 命令：DFU_DL / DFU_INFO / DFU_START / DFU_STATUS / DFU_ABORT / DFU_ERASE
- 二进制接收模式：升级期间切换 UART 接收为二进制帧解析

DFU 帧格式 (GR5xx Protocol):
  Header(2B=0x4744 "GD") + Type(2B LE) + Length(2B LE) + Data(N) + CRC(2B LE)
  CRC = sum of all bytes in (Type + Length + Data), low 16 bits, little-endian

命令集：
  0x01 Get Info          — 验证连接
  0x41 DFU Mode Set      — 设置双区模式 (0x01)，无响应
  0x23 Program Start     — 发送 Image Info (48B) + upgrade type
  0x24 Program Flash     — 发送固件数据块 (max 1024B data per frame)
  0x25 Program End       — 发送结束 + 32-bit checksum
]]

-- LuatOS 核心库 (sys/http/io/os/uart) 已由固件加载到全局环境，无需 require
-- 仅用户自定义模块需要 require

-- ==================== 常量配置 ====================

local FW_PATH        = "/gr5526_fw.bin"  -- 直接用根目录，避免 /ldata/ 子目录不存在




-- ========================================================================
--  Flash Layout (must match GR5526 upgrade.h — 两端必须一致!)
--  Total Flash: 1MB
-- ========================================================================



-- DFU 命令码








log.info("DFU", "0C", FW_PATH)

-- ==================== DFU 传输独占标志 ====================
-- 传输期间为 true，uart_app.lua 的 uart_async_push() 会检查此标志，
-- 只允许 "+DFU:" 开头的控制文本通过 UART1 发送到 GR5526，
-- 其他所有业务文本（[MQTT_STAT]/[NET_ENV]/[SIM_ENV]/[TTS] 等）全部静默丢弃，
-- 确保 DFU 二进制传输期间 UART 通道干净，避免文本数据污染 dfu_port 状态机。
_G.dfu_transfer_active = false

-- ==================== 工具函数 ====================

--- 16-bit累加和 CRC (Type + Length + Data 所有字节相加，取低16位)


--- 封装 DFU 帧
-- @param cmd_type number 命令码 (0-65535)
-- @param data string 数据负载 (可选，默认空)
-- @return string 完整帧二进制


--- 从二进制缓冲区中解析一帧 DFU 响应
-- @param buffer string 接收缓冲区
-- @return frame table|nil 解析出的帧 {cmd_type, data}
-- @return remaining string 剩余缓冲区


--- 发送完成回调标志（用于确认 uart.write() 的数据是否真的上了物理线）
local function dfu_uart_sent_cb(id) return end

--- 发送 DFU 帧并等待 ACK
-- @param cmd_type number 要发送的命令码
-- @param data string 数据负载
-- @param expected_cmd number|nil 期望的响应命令码 (默认同 cmd_type)
-- @return boolean 是否成功
-- @return table|nil 响应帧


-- ==================== HTTP 下载 ====================

--- 从 URL 下载固件到 LFS 文件
-- @param url string HTTP URL
-- @return boolean 是否成功
-- @return number|string 成功返回文件大小，失败返回错误码


-- ==================== 固件信息读取 ====================

--- 读取固件文件信息 (大小 + Image Info + 32-bit checksum)
-- @return table|nil 固件信息
local function dfu_get_fw_info()
    local f = io.open(FW_PATH, "rb")
    if not f then return nil end

    local size = f:seek("end")
    if size < 48 then
        f:close()
        return nil
    end

    -- 读取最后 48 字节 Image Info
    f:seek("set", size - 48)
    local img_info = f:read(48)
    f:close()

    -- 验证 Image Info pattern (前2字节应为 0x4744 "GD")
    local pattern = img_info:byte(1) + img_info:byte(2) * 256
    if pattern ~= 0x4744 then
        log.warn("DFU", "0U" .. string.format("%04X", pattern),
                 "0V")
    end

    -- 计算固件 32-bit 累加和 checksum (分块读取，避免大文件占内存)
    f = io.open(FW_PATH, "rb")
    local checksum = 0
    local chunk_size = 4096
    f:seek("set", 0)
    while true do
        local chunk = f:read(chunk_size)
        if not chunk or #chunk == 0 then break end
        for i = 1, #chunk do
            checksum = checksum + chunk:byte(i)
        end
    end
    f:close()
    checksum = checksum % 4294967296  -- 2^32

    return {
        size     = size,
        img_info = img_info,
        checksum = checksum,
    }
end

-- ==================== DFU 主机传输主流程（内部实现） ====================



-- ==================== DFU 主机传输包装器（统一管理 UART 独占标志） ====================
-- 不管 dfu_host_transfer_impl() 从哪个路径 return（成功/失败/中止），
-- 包装器都会在最后清除 _G.dfu_transfer_active，确保 UART 通道被释放。


-- ==================== 二进制接收接口 (供 uart_app.lua 调用) ====================

--- UART 二进制接收回调
-- 在 uart_app.lua 的接收回调中，当 false == true 时调用此函数
-- @param data string 接收到的二进制数据
function dfu_binary_recv(data) return end

--- 查询是否处于二进制接收模式
-- @return boolean
local function dfu_is_binary_mode()
    return false
end

-- ==================== AT 命令注册 ====================
_G.at_cmd_handlers = _G.at_cmd_handlers or {}

--- DFU_INFO — 查询本地固件信息
_G.at_cmd_handlers["DFU_INFO"] = function(cmd, uart_send)
    local fw_info = dfu_get_fw_info()
    if fw_info then
        uart_send("+DFU: INFO size=" .. fw_info.size ..
                  " crc=" .. string.format("0x%08X", fw_info.checksum))
    else
        uart_send("+DFU: INFO no_firmware")
    end
end

--- DFU_STATUS — 查询 DFU 状态
_G.at_cmd_handlers["DFU_STATUS"] = function(cmd, uart_send)
    uart_send("+DFU: STATE " .. "idle" .. " progress=" .. 0)
end

-- SAM | 2026-10-25 +08:00 | Remove overwritten mutating handler bodies to fit the safety repair; final rejection handlers and read-only queries are unchanged.
-- ==================== 模块导出 ====================
-- SAM | 2026-10-12 19:41 +08:00 | Legacy mutating commands bypass signatures, durable GR ownership and layout checks.
for _, name in ipairs({"DFU_DL", "DFU_START", "DFU_ERASE", "DFU_ABORT"}) do
    _G.at_cmd_handlers[name] = function(cmd, uart_send)
        uart_send("+DFU: REJECTED REQUIRE_VERIFIED_OTA_TRANSACTION")
    end
end
local dfu_transfer = {
    on_sent        = dfu_uart_sent_cb,
    binary_recv    = dfu_binary_recv,
    is_binary_mode = dfu_is_binary_mode,
    get_state      = function() return "idle" end,
    get_progress   = function() return 0 end,
}

log.info("DFU", "1y")
return dfu_transfer
