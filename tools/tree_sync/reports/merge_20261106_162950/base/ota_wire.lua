-- SAM | 2026-10-30 08:58 +08:00 | OTA2 binary frame encode/decode (CRC16 over the header, CRC32 over the whole frame).
local M = {}
local function integer(v, max)
    return type(v)=='number' and v>=0 and v<=max and v%1==0
end
local function crc16(s)
    local c=0xffff
    for i=1,#s do
        c=c ~ (s:byte(i)<<8)
        for _=1,8 do c=((c<<1) ~ ((c&0x8000)~=0 and 0x1021 or 0))&0xffff end
    end
    return c
end
local function crc32(s)
    local c=0xffffffff
    for i=1,#s do
        c=c ~ s:byte(i)
        for _=1,8 do c=(c>>1) ~ ((c&1)~=0 and 0xedb88320 or 0) end
    end
    return (~c)&0xffffffff
end
local function header(s)
    if #s<24 or s:sub(1,4)~='OTA2' then return nil end
    local version,kind,flags,session,sequence,offset,length,check=string.unpack('<BBI2I4I4I4I2I2',s,5)
    if version~=2 or flags~=0 or length>512 or crc16(s:sub(1,22))~=check then return nil end
    return {type=kind,session=session,sequence=sequence,offset=offset,length=length}
end
function M.encode(kind,session,sequence,offset,payload)
    if not integer(kind,255) or not integer(session,0xffffffff) or
       not integer(sequence,0xffffffff) or not integer(offset,0xffffffff) or
       type(payload)~='string' or #payload>512 then return nil end
    local h='OTA2'..string.pack('<BBI2I4I4I4I2',2,kind,0,session,sequence,offset,#payload)
    local body=h..string.pack('<I2',crc16(h))..payload
    return body..string.pack('<I4',crc32(body))
end
function M.decode(s)
    if type(s)~='string' or #s<28 or #s>540 then return nil end
    local h=header(s)
    if not h or #s~=28+h.length or crc32(s:sub(1,-5))~=string.unpack('<I4',s,#s-3) then return nil end
    h.payload=s:sub(25,-5)
    return h
end
function M.parser(sink)
    assert(type(sink)=='function')
    local buffer,expected='',nil
    return {
        reset=function() buffer,expected='',nil end,
        buffered=function() return #buffer end,
        feed=function(_,data)
            assert(type(data)=='string')
            -- Consume incrementally: caller chunk size cannot grow our retained storage.
            for i=1,#data do
                buffer=buffer..data:sub(i,i)
                while #buffer>0 do
                    if buffer:sub(1,math.min(4,#buffer))~= ('OTA2'):sub(1,math.min(4,#buffer)) then
                        buffer,expected=buffer:sub(2),nil
                    elseif #buffer<24 then break
                    else
                        if not expected then
                            local h=header(buffer)
                            if h then expected=28+h.length end
                        end
                        if not expected then buffer=buffer:sub(2)
                        elseif #buffer<expected then break
                        else
                            local frame=M.decode(buffer:sub(1,expected))
                            if frame then
                                buffer,expected=buffer:sub(expected+1),nil
                                sink(frame)
                            else buffer,expected=buffer:sub(2),nil end
                        end
                    end
                end
            end
        end
    }
end
function M.mux(text,sink)
    local mode,prefix,last=0,'',nil
    local delivered=false
    local parser=M.parser(function(frame) delivered=true;sink(frame) end)
    local self={}
    function self:lost() mode,prefix=3,'';parser:reset() end
    function self:feed(data,now)
        for i=1,#data do
            local c=data:sub(i,i)
            if (mode==2 or (mode==0 and #prefix>0)) and last and
                (type(now)~='number' or (now-last)%0x100000000>2000) then self:lost() end
            last=now
            if mode==3 then
                if c=='\n' then mode=0 end
            elseif mode==2 then
                delivered=false;parser:feed(c)
                if delivered and parser:buffered()==0 then mode=0 end
            else
                if mode==0 then
                    if c==('OTA2'):sub(#prefix+1,#prefix+1) then
                        prefix=prefix..c
                        if #prefix==4 then
                            if type(now)~='number' then self:lost()
                            else mode=2;parser:feed(prefix);prefix='' end
                        end
                    else
                        if #prefix>0 then text(prefix);prefix='' end
                        mode=1;text(c)
                        if c=='\n' then mode=0 end
                    end
                else
                    text(c);if c=='\n' then mode=0 end
                end
            end
        end
    end
    return self
end
return M
