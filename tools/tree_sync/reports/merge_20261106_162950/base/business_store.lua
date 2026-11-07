-- SAM | 2026-10-13 09:14 +08:00 | Isolate alarm and phone records from OTA/user files because retries must survive a CAT reset without erasing other data.
local M = {}
local paths = {"/yp001_business_0", "/yp001_business_1"}
local crc32 = require("ota_store").crc32
local limit = 8192

function M.new(disk, codec)
    local self = {generation=0, slot=0, error=nil}
    local function parse(raw)
        if type(raw) ~= "string" or #raw > limit then return nil end
        local seq, checksum, body = raw:match("^YPBUS1\n(%d+)\n(%x%x%x%x%x%x%x%x)\n(.+)$")
        seq = tonumber(seq)
        if not seq or seq < 1 or seq > 0xffffffff or crc32(tostring(seq).."\n"..body) ~= tonumber(checksum,16) then return nil end
        local ok, value = pcall(codec.decode, body)
        if not ok or type(value) ~= "table" then return nil end
        return {seq=seq,value=value}
    end
    function self:load()
        local records = {}
        for i,path in ipairs(paths) do
            local ok, raw, err = pcall(disk.read, path, limit+1)
            if not ok or (not raw and err ~= "missing") then self.error="STORE_READ_FAILED"; return nil,self.error end
            if raw then
                records[i] = parse(raw)
                if not records[i] then self.error="STORE_CORRUPT"; return nil,self.error end
            end
        end
        local a,b=records[1],records[2]
        if a and b and (a.seq==b.seq or math.abs(a.seq-b.seq)>1) then self.error="STORE_CONFLICT"; return nil,self.error end
        local index = b and (not a or b.seq>a.seq) and 2 or 1
        local best = records[index]
        if best then self.generation=best.seq; self.slot=index; return best.value end
        return nil
    end
    function self:save(value)
        if self.error then return false,self.error end
        if self.generation >= 0xffffffff then return false,"STORE_EXHAUSTED" end
        local ok,body=pcall(codec.encode,value)
        if not ok or type(body)~="string" then return false,"STORE_ENCODE_FAILED" end
        local seq=self.generation+1
        local raw="YPBUS1\n"..seq.."\n"..string.format("%08x",crc32(tostring(seq).."\n"..body)).."\n"..body
        if #raw>limit then return false,"STORE_FULL" end
        local target=self.slot==1 and 2 or 1
        local wrote,result=pcall(disk.write,paths[target],raw)
        local read,check=pcall(disk.read,paths[target],limit+1)
        if not wrote or result~=true or not read or check~=raw then self.error="STORE_COMMIT_FAILED"; return false,self.error end
        self.generation=seq; self.slot=target
        return true
    end
    return self
end

M.file_port = require("ota_store").file_port
return M
