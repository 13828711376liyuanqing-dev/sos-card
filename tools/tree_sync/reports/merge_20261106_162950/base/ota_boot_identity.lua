-- SAM | 2026-10-30 08:58 +08:00 | After reboot, verifies the running scripts match the signed CAT1 build record.
local M={}
local CRC='.airm2m_all_crc#.bin'
local function uint(n,lo,hi)return type(n)=='number' and n%1==0 and n>=lo and n<=hi end
local function hex(s)return type(s)=='string' and #s==64 and not s:find('[^0-9a-f]')end
local function version(s)
 if type(s)~='string' or #s>11 then return nil end
 local a,b,c=s:match('^(%d+)%.(%d+)%.(%d+)$');a,b,c=tonumber(a),tonumber(b),tonumber(c)
 if uint(a,0,999) and uint(b,0,999) and uint(c,0,999) then return a*1000000+b*1000+c end
end
local function identity(e)
 if type(e)~='table' or not uint(e.file_count,1,128) or type(e.files)~='table' or
  not hex(e.package_sha256) or not hex(e.manifest_sha256) or not hex(e.build_record_sha256) or not version(e.version) then return nil end
 local files,n={},0
 for name,digest in pairs(e.files)do
  if type(name)~='string' or #name>96 or not name:match('^[%w_][%w_.%-]*$') or name:find('..',1,true) or not hex(digest) then return nil end
  n=n+1;if n>128 then return nil end;files[name]=digest
 end
 if n~=e.file_count or not files['main.luac'] then return nil end
 return files
end
function M.matches(e,job)
 return identity(e)~=nil and type(job)=='table' and job.target=='CAT1' and e.package_sha256==job.hash and
  version(e.version)==version(job.version) and version(job.version)~=nil and
  type(job.bundle)=='table' and e.manifest_sha256==job.bundle.manifest_sha256
end
function M.new(expected,hash,api,can_read)
 local files=identity(expected)
 if not files then return nil,'BOOT_IDENTITY_INVALID' end
 api=api or io
 if not hash or type(hash.hash_begin)~='function' or type(hash.hash_update)~='function' or type(hash.hash_finish)~='function' then return nil,'BOOT_HASH_UNAVAILABLE' end
 local names={};for name in pairs(files)do names[#names+1]=name end;table.sort(names)
 local seen,list_offset,index,offset,total={},0,1,0,0
 local listed,context,length,terminal=false,nil,nil,nil
 local function need(ok,why)if not ok then error(why,0)end end
 local function use(name,action)
  local f=api.open('/luadb/'..name,'rb');need(f~=nil,'BOOT_READ_FAILED')
  local ok,result=pcall(action,f);local closed,value=pcall(f.close,f)
  need(ok and closed and value~=nil and value~=false,'BOOT_READ_FAILED');return result
 end
 local function step()
  if terminal then return terminal=='VERIFIED',terminal end
  if can_read and can_read()~=true then return false,'BUSINESS_PAUSED' end
  if not listed then
   local ok,page=api.lsdir('/luadb/',16,list_offset)
   need(ok==true and type(page)=='table' and #page<=16,'BOOT_LIST_FAILED')
   local count=0;for k in pairs(page)do count=count+1;need(uint(k,1,#page),'BOOT_LIST_FAILED')end
   need(count==#page,'BOOT_LIST_FAILED')
   for _,entry in ipairs(page)do
    need(type(entry)=='table' and entry.type==0 and type(entry.name)=='string','BOOT_FILE_SET')
    local name=entry.name;need((files[name]~=nil or name==CRC) and not seen[name],'BOOT_FILE_SET');seen[name]=true
   end
   list_offset=list_offset+#page;need(list_offset<=#names+1,'BOOT_FILE_SET')
   if #page<16 then
    need(list_offset==#names+1 and seen[CRC],'BOOT_FILE_SET')
    for _,name in ipairs(names)do need(seen[name],'BOOT_FILE_SET')end
    need(use(CRC,function(f)return f:seek('end')end)==16,'BOOT_FILE_SET');listed=true
   end
   return true,'CHECKING'
  end
  local name=names[index]
  local data=use(name,function(f)
   local size=f:seek('end');need(uint(size,0,524288),'BOOT_READ_FAILED')
   if length==nil then length=size;total=total+size;need(total<=524288,'BOOT_READ_FAILED')end
   need(size==length and f:seek('set',offset)==offset,'BOOT_READ_FAILED')
   local n=math.min(4096,length-offset)
   if n==0 then return '' end
   local chunk=f:read(n);need(type(chunk)=='string' and #chunk==n,'BOOT_READ_FAILED');return chunk
  end)
  if not context then context=hash.hash_begin('SHA256');need(context~=nil,'BOOT_HASH_FAILED')end
  need(hash.hash_update(context,data)==true,'BOOT_HASH_FAILED');offset=offset+#data
  if offset==length then
   need(hash.hash_finish(context)==files[name],'BOOT_CODE_MISMATCH')
   context,length,offset=nil,nil,0;index=index+1
   if index>#names then terminal='VERIFIED';return true,terminal end
  end
  return true,'CHECKING'
 end
 local self={}
 function self:step()
  local ok,a,b=pcall(step)
  if ok then return a,b end
  terminal=type(a)=='string' and a:match('^BOOT_[A-Z_]+$') and a or 'BOOT_READ_FAILED'
  return false,terminal
 end
 return self
end
return M
