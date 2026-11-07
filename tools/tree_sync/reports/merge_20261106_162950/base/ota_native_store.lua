-- SAM | 2026-10-30 08:58 +08:00 | Two-slot journal for the native FOTA installer (yp001_cat_fota_0/1).
local M={}
local PATH={['/yp001_ota_state_0']='/yp001_cat_fota_0',
            ['/yp001_ota_state_1']='/yp001_cat_fota_1'}
function M.new(disk,codec)
    local store_module=require('ota_store')
    disk=disk or store_module.file_port()
    local journal=store_module.new({
        read=function(path,limit)
            if not PATH[path] then return nil,'PATH_DENIED' end
            return disk.read(PATH[path],limit)
        end,
        write=function(path,raw)
            if not PATH[path] then return false end
            return disk.write(PATH[path],raw)
        end,
    },codec or json)
    return {
        load=function()
            local value,err=journal:load()
            return value,err==nil
        end,
        save=function(value)return journal:save(value)end,
    }
end
return M
