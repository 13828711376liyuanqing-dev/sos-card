-- SAM | 2026-10-30 08:58 +08:00 | Builds the runtime options for the real device (file system, HTTP, native FOTA port).
local M={}
local function integer(n,max)
    return type(n)=="number" and n>=0 and n%1==0 and n<=max
end
function M.new(first_trial_profile)
    local base=require("ota_platform").default()
    local function idle() return base.idle()==true end
    local trial=require('ota_trial').new(first_trial_profile,function()
        local ok,total,used,block=io.fsstat('/')
        if ok~=true or not integer(total,0xffffffff) or not integer(block,0x100000) then return nil end
        return {model=hmeta.model(),core=rtos.version(),bits=string.packsize('j')*8,
            fs_bytes=total*block,version=_G.PRODUCT_VERSION}
    end)
    local bundle={
        can_read=idle,
        current_version=function() return _G.PRODUCT_VERSION end,
        free_bytes=function()
            local success,ok,total,used,block=pcall(function()return io.fsstat("/")end)
            if not success or ok~=true or not integer(total,0xffffffff) or
                not integer(used,total) or not integer(block,0x100000) or block==0 then return nil end
            -- The package profile is explicitly the 512 KiB user filesystem.
            if total*block~=524288 then return nil end
            return (total-used)*block
        end,
    }
    -- SAM | 2026-11-04 +08:00 | OTA speed-up on the device: 16KiB steps, up to 3 s of steps per 1 s tick (see ota_runtime).
    return {download_tuning={chunk_size=16384,scan_bytes=16384,burst_ms=3000},bundle_port=bundle,native_fota_port={
        native=fota,
        first_trial=trial,
        require_code_identity=true,
        require_data_identity=true,
        allow_unavailable_kv=true,
        native_contract_verified=function() return false end,
        now=function() return mcu.ticks()/1000 end,
    },http_native={
        socket=socket,zbuff=zbuff,
        -- Native V2052 receive-limit behavior has not been checked on the module.
        -- Do not promote a PC transport test or API presence to device evidence.
        native_rx_limit_verified=trial:network(),
        now_ms=function()return mcu.ticks()end,
        wait=function(ms)return sys.wait(ms)end,
        can_read=idle,
    }}
end
return M
