-- SAM | 2026-10-30 08:58 +08:00 | Candidate file paths (/o<base32 of the hash>.p: V2052 rejects names over 63 bytes) and the download file port.
local M={}
function M.path(hash)
 if type(hash)~='string' or #hash~=64 or hash:find('[^%x]') then return nil end
 local alphabet='abcdefghijklmnopqrstuvwxyz234567'
 local out,acc,bits={},0,0
 for i=1,64 do
  acc=(acc<<4)|tonumber(hash:sub(i,i),16);bits=bits+4
  if bits>=5 then
   bits=bits-5;local n=(acc>>bits)&31;out[#out+1]=alphabet:sub(n+1,n+1)
   acc=acc&((1<<bits)-1)
  end
 end
 if bits>0 then local n=acc<<(5-bits);out[#out+1]=alphabet:sub(n+1,n+1) end
 return '/o'..table.concat(out)..'.p'
end
function M.allowed(path)
 return type(path)=='string' and #path==56 and path:match('^/o[a-z2-7]+%.p$')~=nil and
  (path:sub(-3,-3)=='a' or path:sub(-3,-3)=='q')
end
function M.new(hash,api)
 api=api or io
 -- SAM | 2026-11-04 +08:00 | io_limit: one read/write call may carry up to 16KiB (OTA speed-up download chunks); the file system is
-- still accessed in the board-verified 4KiB pieces. 11-04 board: a 16KiB chunk hit the old 4KiB limit -> write_readback_failed.
local p={chunk_size=4096,io_limit=16384,max_size=479232}
local PIECE=4096
 local active,visible
 local function uint(v,max) return type(v)=='number' and v>=0 and v%1==0 and v<=max end
 local function allowed(path)
  return M.allowed(path)
 end
 local function exists(path)
  if type(api.exists)~='function' then return nil end
  local ok,value=pcall(api.exists,path)
  if not ok or type(value)~='boolean' then return nil end
  return value
 end
 local function use(path,mode,action)
  if not allowed(path) then return nil end
  local ok,f=pcall(api.open,path,mode)
  if not ok or not f then return nil end
  local success,result=pcall(action,f)
  local closed,value=pcall(f.close,f)
  if not success or not closed or value==nil or value==false then return nil end
  return result
 end
 local function physical(path)
  if not allowed(path) then return nil end
  local found=exists(path)
  if found==false then return 0 end
  if found~=true then return nil end
  local n=use(path,'rb',function(f)return f:seek('end')end)
  return uint(n,p.max_size) and n or nil
 end
 function p.size(path)
  local n=physical(path)
  if n and path==active and visible~=nil then return n>=visible and visible or nil end
  return n
 end
 function p.truncate(path,n)
  local size=physical(path)
  if not uint(n,p.max_size) or not size or n>size then return false end
  active,visible=path,n
  return true
 end
 function p.read(path,offset,n)
  local size=p.size(path)
  if not size or not uint(offset,size) or not uint(n,p.io_limit) or offset+n>size then return nil end
  return use(path,'rb',function(f)
   if f:seek('set',offset)~=offset then return nil end
   local parts,left={},n
   while left>0 do
    local k=math.min(PIECE,left);local data=f:read(k)
    if type(data)~='string' or #data~=k then return nil end
    parts[#parts+1]=data;left=left-k
   end
   return table.concat(parts)
  end)
 end
 function p.write(path,offset,data)
  local size=p.size(path)
  if not size or offset~=size or type(data)~='string' or #data<1 or #data>p.io_limit or offset+#data>p.max_size then return false end
  local found=exists(path);if found==nil then return false end
  local wrote=use(path,found and 'r+b' or 'wb',function(f)
   if f:seek('set',offset)~=offset then return false end
   for at=1,#data,PIECE do
    local result=f:write(data:sub(at,at+PIECE-1));if result==nil or result==false then return false end
   end
   return true
  end)
  if wrote~=true then return false end
  active,visible=path,offset+#data
  return p.read(path,offset,#data)==data
 end
 function p.remove(path)
  if not allowed(path) then return false end
  local found=exists(path)
  if found==false then return true end
  if found~=true then return false end
  local fetched,remove=pcall(function()return api.remove end)
  if not fetched then remove=nil end
  if type(remove)~='function' and api==io and os then
   local ok,value=pcall(function()return os.remove end)
   if ok then remove=value end
  end
  if type(remove)~='function' then return false end
  local ok=pcall(remove,path)
  if not ok or exists(path)~=false then return false end
  if active==path then active,visible=nil,nil end
  return true
 end
 function p.verify_file(path,job)
  if type(job)~='table' or not uint(job.size,p.max_size) or job.size<1 or
    physical(path)~=job.size or p.size(path)~=job.size then return nil end
  local sha,md5=hash.hash_begin('SHA256'),hash.hash_begin('MD5')
  if not sha or not md5 then return nil end
  for offset=0,job.size-1,4096 do
   local bytes=p.read(path,offset,math.min(4096,job.size-offset))
   if not bytes or hash.hash_update(sha,bytes)~=true or hash.hash_update(md5,bytes)~=true then return nil end
   if sys and type(sys.wait)=='function' then sys.wait(1) end
  end
  if physical(path)~=job.size then return nil end
  return {size=job.size,sha256=hash.hash_finish(sha),md5=hash.hash_finish(md5),signature_valid=false,content_hash_only=true}
 end
 return p
end
return M
