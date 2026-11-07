-- SAM | 2026-10-30 08:58 +08:00 | Read-only user-data snapshot (root files, initialized KV) used to prove an install preserved data.
local candidate_paths=require("ota_candidates")
local M={}
local function need(ok,why)if not ok then error(why,0)end end
local function uint(n,max)return type(n)=='number' and n>=0 and n<=max and n%1==0 end
local function field(s)return tostring(#s)..':'..s end
-- Type-tagged, sorted encoding avoids JSON table ordering and string/number collisions.
local function canonical(v,depth,seen)
 need(depth<=8,'KV_VALUE_UNSUPPORTED')
 local t=type(v)
 if t=='string' then need(#v<=4096,'KV_VALUE_UNSUPPORTED');return 's'..field(v) end
 if t=='boolean' then return v and 'b1' or 'b0' end
 if t=='number' then
  need(v==v and v~=math.huge and v~=-math.huge,'KV_VALUE_UNSUPPORTED')
  return 'n'..field(string.format('%.17g',v))
 end
 need(t=='table' and not seen[v],'KV_VALUE_UNSUPPORTED');seen[v]=true
 local parts,n,bytes={},0,0
 for k,x in pairs(v)do
  need(type(k)=='string' or type(k)=='number','KV_VALUE_UNSUPPORTED')
  n=n+1;need(n<=256,'KV_VALUE_UNSUPPORTED')
  local part=field(canonical(k,depth+1,seen))..field(canonical(x,depth+1,seen))
  bytes=bytes+#part;need(bytes<=8191,'KV_VALUE_UNSUPPORTED');parts[n]=part
 end
 table.sort(parts);seen[v]=nil
 local s='t'..table.concat(parts);need(#s<=8192,'KV_VALUE_UNSUPPORTED');return s
end
function M.capture(p)
 local stage='PORT_CHECK'
 local function run()
  local api,kv,h=p.io,p.kv,p.hash
  need(api and kv and h,'CAPABILITY_UNAVAILABLE')
  local function step()
   stage='IDLE_CHECK'
   need(type(p.can_read)=='function' and p.can_read()==true,'BUSY')
   if p.yield then p.yield() end
   need(p.can_read()==true,'BUSY')
  end
  local function finish(c)
   stage='HASH_FINISH'
   local s=h.hash_finish(c)
   need(type(s)=='string' and #s==64 and not s:find('[^0-9a-f]'),'HASH_FAILED');return s
  end
  local function digest(s)
   stage='HASH_BEGIN'
   local c=h.hash_begin('SHA256');need(c~=nil,'HASH_FAILED')
   stage='HASH_UPDATE';need(h.hash_update(c,s)==true,'HASH_FAILED');return finish(c)
  end
  local function scan()
   stage='IDLE_CHECK'
   need(type(p.can_read)=='function' and p.can_read()==true,'BUSY')
   local files,keys,seen,offset,total={},{},{},0,0
   while true do
    stage='FILE_LIST'
    local ok,page=api.lsdir('/',100,offset)
    local d={o=offset,n=type(page)=='table' and #page or -1,k=ok==true};M.ld=d
    need(ok==true and type(page)=='table','FILE_LIST_FAILED');need(#page<100,'FILE_LIMIT')
    local n=0;for k in pairs(page)do n=n+1;need(uint(k,#page) and k>0,'FILE_LIST_FAILED')end
    need(n==#page,'FILE_LIST_FAILED')
    for i,e in ipairs(page)do
     d.i=i;d.l=type(e)=='table' and type(e.name)=='string' and #e.name or -1;d.d=d.l>0 and seen[e.name]==true
     need(type(e)=='table' and type(e.name)=='string' and #e.name>0 and #e.name<=128 and
      not e.name:find('[/\\%z]') and e.name~='.' and e.name~='..' and not seen[e.name],'FILE_LIST_FAILED')
     seen[e.name]=true
     -- LuaDB is signed code, checked separately. Unknown directories are not silently omitted.
     -- SAM | 2026-11-02 +08:00 | /log and /ble are fs_log.lua's debug-log and beacon-upload buffers (appended every 30 s), not user data;
     -- hashing them would make every scan differ, so only these two named directories are skipped. Other directories still fail.
     -- SAM | 2026-11-02 +08:00 | exgnss rewrites its GNSS caches (hxxt*) whenever positioning runs, so they are not user data either.
     if not (e.name=='luadb' and e.type==1) and not ((e.name=='log' or e.name=='ble') and e.type==1) and
      not ((e.name=='hxxt.dat' or e.name=='hxxt_tm' or e.name=='hxxtloc') and e.type==0) and
      not (p.excluded and p.excluded['/'..e.name]==true and e.type==0) then
      need(e.type==0,'DIRECTORY_UNVERIFIED');need(uint(e.size,524288),'FILE_SIZE_INVALID')
      total=total+e.size;need(total<=524288,'FILE_LIMIT')
      files[#files+1]={path='/'..e.name,size=e.size}
     end
    end
    break
   end
   table.sort(files,function(a,b)return a.path<b.path end)
   for _,entry in ipairs(files)do
    stage='FILE_OPEN'
    need(p.can_read()==true,'BUSY')
    local f=api.open(entry.path,'rb');need(f~=nil,'FILE_READ_FAILED')
    local ok,why=pcall(function()
     stage='FILE_SEEK'
     need(f:seek('end')==entry.size and f:seek('set',0)==0,'FILE_READ_FAILED')
     stage='HASH_BEGIN';local c=h.hash_begin('SHA256');need(c~=nil,'HASH_FAILED')
     local left=entry.size
     while left>0 do
      stage='FILE_READ';local count=math.min(left,4096);local s=f:read(count)
      need(type(s)=='string' and #s==count,'FILE_READ_FAILED')
      stage='HASH_UPDATE';need(h.hash_update(c,s)==true,'HASH_FAILED');left=left-count
      if left>0 then step() end
     end
     stage='FILE_SEEK';need(f:seek('end')==entry.size,'FILE_READ_FAILED');entry.sha256=finish(c)
    end)
    local failed_stage=stage
    stage='FILE_CLOSE';local closed,value=pcall(f.close,f)
    if not ok then stage=failed_stage;error(why,0)end
    need(closed and value~=nil and value~=false,'FILE_READ_FAILED')
   end
   -- Never call kv.init(): an unreadable/uninitialized database is UNKNOWN, not empty.
   stage='KV_STATUS';local status_ok,used,capacity,count=pcall(kv.status)
   local unavailable=not status_ok or not (uint(capacity,1048576) and capacity>0 and uint(used,capacity) and uint(count,256))
   local kv_unverified=p.allow_unavailable_kv==true and unavailable
   if not kv_unverified then
   need(uint(capacity,1048576) and capacity>0 and uint(used,capacity) and uint(count,256),'KV_UNAVAILABLE')
   stage='KV_ITER';local it=kv.iter();need(it~=nil,'KV_UNAVAILABLE')
   local names={}
   for i=1,count do
    if i%8==0 then step() end
    need(p.can_read()==true,'BUSY')
    stage='KV_NEXT';local k=kv.next(it);need(type(k)=='string' and #k>0 and #k<=255 and not names[k],'KV_COUNT_CHANGED')
    names[k]=true;stage='KV_GET';local value=kv.get(k);need(value~=nil,'KV_READ_FAILED')
    keys[i]={key_sha256=digest(k),value_sha256=digest(canonical(value,0,{})),value_type=type(value)}
   end
   stage='KV_NEXT';need(kv.next(it)==nil,'KV_COUNT_CHANGED')
   stage='KV_STATUS';local u,c,n=kv.status();need(u==used and c==capacity and n==count,'KV_COUNT_CHANGED')
   table.sort(keys,function(a,b)return a.key_sha256<b.key_sha256 end)
   end
   local scope=kv_unverified and 'root_files_kv_unverified' or 'root_files_and_initialized_kv'
   local lines={}
   if kv_unverified then lines[#lines+1]='scope:'..scope end
   for _,e in ipairs(files)do lines[#lines+1]='f'..field(e.path)..':'..e.size..':'..e.sha256 end
   for _,e in ipairs(keys)do lines[#lines+1]='k'..e.key_sha256..':'..e.value_type..':'..e.value_sha256 end
   return {files=files,kv=keys,digest=digest(table.concat(lines,'\n')),scope=scope,kv_unverified=kv_unverified}
  end
  local first=scan();step();local second=scan()
  need(first.digest==second.digest and first.scope==second.scope,'SCAN_CHANGED')
  second.schema=1;second.complete=true;second.data_ok=false
  second.atomic=false
  return second
 end
 local ok,result=pcall(run)
 if ok then return result end
 local allowed={BUSY=true,CAPABILITY_UNAVAILABLE=true,KV_VALUE_UNSUPPORTED=true,HASH_FAILED=true,
  FILE_LIST_FAILED=true,DIRECTORY_UNVERIFIED=true,FILE_SIZE_INVALID=true,FILE_LIMIT=true,
  FILE_READ_FAILED=true,KV_UNAVAILABLE=true,KV_COUNT_CHANGED=true,KV_READ_FAILED=true,SCAN_CHANGED=true}
 local token=type(result)=='string' and result:match('([A-Z_]+)$') or nil
 local why=allowed[token] and token or 'READ_FAILED'
 local kind
 if why=='READ_FAILED' and type(result)=='string' then
  if result:find('attempt to call',1,true) then kind='CALL_FAILED'
  elseif result:find('attempt to index',1,true) then kind='INDEX_FAILED'
  elseif result:find('stack overflow',1,true) then kind='STACK_FAILED'
  else kind='NATIVE_EXCEPTION' end
 end
 return {schema=1,complete=false,data_ok=false,error=why,stage=stage,exception_kind=kind,atomic=false}
end
function M.device_port(can_read)
 return {io=io,kv=fskv,can_read=can_read,yield=function()sys.wait(1)end,
  hash={hash_begin=function()return crypto.hash_init('SHA256')end,
   hash_update=function(c,s)local ok,r=pcall(crypto.hash_update,c,s);return ok and r~=false end,
   hash_finish=function(c)local s=crypto.hash_finish(c);return type(s)=='string' and s:lower() or nil end}}
end
function M.transaction_snapshot(job,path,can_read,boot,allow_unavailable_kv)
 if type(job)~='table' or type(job.hash)~='string' or #job.hash~=64 or job.hash:find('[^0-9a-f]') or
  path~=candidate_paths.path(job.hash) then return nil end
 local p=M.device_port(can_read)
 p.allow_unavailable_kv=allow_unavailable_kv==true
 p.excluded={['/yp001_ota_state_0']=true,['/yp001_ota_state_1']=true,
  ['/yp001_cat_fota_0']=true,['/yp001_cat_fota_1']=true,[path]=true}
 -- Called before sys.run/business initialization: do not yield into business writers.
 if boot then p.yield=nil end
 local r=M.capture(p)
 if not r.complete then return nil,r.error end
 return {schema=1,complete=true,scope=r.scope,kv_unverified=r.kv_unverified,digest=r.digest,files=#r.files,keys=#r.kv}
end
return M
