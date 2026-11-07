-- SAM | 2026-10-30 08:58 +08:00 | Fallback for servers without HTTP Range: reads the bundle ZIP sequentially from offset 0.
local M={}
local B=require('ota_bundle')
local function need(v,e)if not v then error(e,0)end end
local profile,u16,u32,safe=B.stream_profile()
local function open(p,input,diag)
 local live,pos
 local function close()if live then pcall(live.close);live=nil end;return true end
 local function guarded()need(p.can_read()==true,'BUSINESS_PAUSED')end
 local function start()
  close();guarded();local why
  live,why=p.open_stream(input.url);need(live,why or 'NETWORK_ERROR');need(live.status==200,'HTTP_STREAM_STATUS');pos=0
 end
 local function exact(n)
  local parts,left={},n
  while left>0 do
   guarded();local count=math.min(left,16384);local s,e=live.read(count);need(type(s)=='string' and #s>0 and #s<=count,e or 'HTTP_EOF')
   parts[#parts+1]=s;left=left-#s;pos=pos+#s;need(pos<=2097152,'ARCHIVE_LIMIT')
  end
  return table.concat(parts)
 end
 local ok,result,reason=pcall(function()
  need(type(input.md5)=='string' and #input.md5==32,'ARCHIVE_MD5_REQUIRED')
  start()
  local md,sha=p.hash_begin('MD5'),p.hash_begin('SHA256')
  need(md and sha,'HASH_BEGIN_FAILED')
  local function hash(s)need(p.hash_update(md,s)==true and p.hash_update(sha,s)==true,'HASH_UPDATE_FAILED');return s end
  local function take(n)return hash(exact(n))end
  local cache,components,seen={}, {}, {}
  local bytes,manifest_hash=0
  local function keep(at,s)bytes=bytes+#s;need(bytes<=35000,'METADATA_LIMIT');cache[#cache+1]={at=at,data=s}end
  for _=1,6 do
   local at=pos;local h=take(30)
   need(u32(h,1)==0x04034b50,'ZIP_LOCAL_HEADER')
   local flags,n,sz=u16(h,7),u16(h,27),u32(h,19)
   need((flags==0 or flags==0x800) and u16(h,9)==0 and u16(h,29)==0 and n>0 and n<=64 and sz==u32(h,23),'ZIP_STORE_REQUIRED')
   local name=take(n);need(profile[name] and not seen[name] and sz>0 and sz<=profile[name],'ZIP_MEMBER');seen[name]=true
   keep(at,h..name)
   if name=='GR5526/payload.bin' or name=='CAT1/payload.sota' then
    components[#components+1]={first=pos,last=pos+sz}
    local left=sz;while left>0 do local k=math.min(left,16384);take(k);left=left-k end
   else local at=pos;local data=take(sz);keep(at,data);if name=='bundle.json' then manifest_hash=p.sha256(data)end end
  end
  local tail_at=pos;local tail={}
  while true do
   guarded();local s,e=live.read(1024);need(type(s)=='string',e or 'NETWORK_ERROR')
   if #s==0 then break end
   pos=pos+#s;need(pos-tail_at<=4118,'ZIP_DIRECTORY');need(pos<=2097152,'ARCHIVE_LIMIT')
   tail[#tail+1]=hash(s)
  end
  keep(tail_at,table.concat(tail));close()
  local size,digest=pos,p.hash_finish(md)
  need(digest==input.md5:lower(),'ARCHIVE_MD5_MISMATCH')
  local identity={size=size,sha256=p.hash_finish(sha)}
  local q=setmetatable({},{__index=p})
  q.transport_mode='SEQUENTIAL_200';q.network_restart_from_zero=true;q.metadata_bytes=bytes
  q.close_transport=close
  q.preflight_snapshot=function(m,n,mh)
   guarded();return m==digest and n==size and mh==manifest_hash
  end
  q.read_at=function(_,first,count)
   local yes,value=pcall(function()
    guarded()
    for _,s in ipairs(cache)do if first>=s.at and first+count<=s.at+#s.data then return s.data:sub(first-s.at+1,first-s.at+count)end end
    local component
    for _,c in ipairs(components)do if first>=c.first and first+count<=c.last then component=c end end
    need(component,'BYTE_SOURCE_BOUNDS')
    if not live or first<pos then start()end
    while pos<first do exact(math.min(first-pos,16384))end
    local data=exact(count);if pos==component.last then close()end;return data
   end)
   if not yes then close();return nil,safe(value,'STREAM_ERROR')end
   return value,identity
  end
  return (diag and B.open_diagnostic or B.open)(q,input)
 end)
 if not ok then reason=safe(result,'STREAM_ERROR');result=nil end
 if not result then close()end
 return result,reason
end
function M.open(p,i)return open(p,i,false)end
function M.open_diagnostic(p,i)return open(p,i,true)end
return M
