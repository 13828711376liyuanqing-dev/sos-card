-- SAM | 2026-10-30 08:58 +08:00 | Two-slot CRC-protected journal file for the manager state (yp001_ota_state_0/1).
local M = {}
local LIMIT = 16384
local PATH = {"/yp001_ota_state_0", "/yp001_ota_state_1"}
local function crc32(s)
    local c = 0xffffffff
    for i = 1, #s do
        c = c ~ s:byte(i)
        for _ = 1, 8 do c = (c >> 1) ~ ((c & 1) ~= 0 and 0xedb88320 or 0) end
    end
    return (~c) & 0xffffffff
end
M.crc32 = crc32

function M.new(disk, codec)
    local self = {generation = 0, slot = 0, loaded = false, error = nil}
    local function decode(raw)
        if type(raw) ~= "string" or #raw > LIMIT then return nil end
        local seq, checksum, payload = raw:match("^YPOTA1\n(%d+)\n(%x%x%x%x%x%x%x%x)\n(.+)$")
        local encoded_seq=seq
        seq = tonumber(seq)
        if not seq or seq < 1 or seq > 0xffffffff or seq%1~=0 or tostring(seq)~=encoded_seq or crc32(tostring(seq).."\n"..payload) ~= tonumber(checksum,16) then return nil end
        local ok, value = pcall(codec.decode, payload)
        if not ok or type(value) ~= "table" then return nil end
        return {sequence=seq, value=value, raw=raw}
    end
    function self:load()
        if self.error then return nil, self.error end
        local records = {}
        for i, path in ipairs(PATH) do
            local ok, raw, err = pcall(disk.read, path, LIMIT+1)
            if not ok or (not raw and err ~= "missing") then
                self.error="STORE_READ_FAILED"; return nil,self.error
            end
            if raw then
                records[i] = decode(raw)
                if not records[i] then self.error="STORE_CORRUPT";return nil,self.error end
            end
        end
        local a,b=records[1],records[2]
        if a and b and (math.abs(a.sequence-b.sequence) > 1 or a.sequence==b.sequence) then
            self.error="STORE_GENERATION_CONFLICT";return nil,self.error
        end
        local index = b and (not a or b.sequence>a.sequence) and 2 or 1
        local best=records[index]
        self.loaded=true
        if not best then return nil end
        self.slot=index;self.generation=best.sequence
        return best.value
    end
    function self:save(value)
        if type(value)~="table" then return false,"STORE_VALUE_INVALID" end
        if not self.loaded then self:load() end
        if self.error then return false,self.error end
        if self.generation >= 0xffffffff then return false,"STORE_GENERATION_EXHAUSTED" end
        local ok,payload=pcall(codec.encode,value)
        if not ok or type(payload)~="string" then return false,"STORE_ENCODE_FAILED" end
        local decoded,roundtrip=pcall(codec.decode,payload)
        if not decoded or type(roundtrip)~="table" then return false,"STORE_ENCODE_FAILED" end
        local seq=self.generation+1
        local raw="YPOTA1\n"..seq.."\n"..string.format("%08x",crc32(seq.."\n"..payload)).."\n"..payload
        if #raw>LIMIT then return false,"STORE_FULL" end
        local target=self.slot==1 and 2 or 1
        local wrote,result=pcall(disk.write,PATH[target],raw)
        local read,check=pcall(disk.read,PATH[target],LIMIT+1)
        if not wrote or result~=true or not read or check~=raw then
            self.error="STORE_COMMIT_FAILED";return false,self.error
        end
        self.slot=target;self.generation=seq
        return true
    end
    return self
end

-- Close + readback is not a claim of hardware atomicity; activation still needs a verified persistence port.
function M.file_port()
    return {
        read=function(path,limit)
            if type(io.exists)~="function" then return nil,"EXISTENCE_API_UNAVAILABLE" end
            if not io.exists(path) then return nil,"missing" end
            local f=io.open(path,"rb");if not f then return nil,"open_failed" end
            local data=f:read(limit);f:close();return data
        end,
        write=function(path,data)
            local f=io.open(path,"wb");if not f then return false end
            local ok,result=pcall(f.write,f,data)
            local closed,close_result=pcall(f.close,f)
            return ok and result~=nil and result~=false and closed and close_result~=nil and close_result~=false
        end
    }
end
return M
