-- SAM | 2026-10-30 08:58 +08:00 | Signed whole-device ZIP: HTTP Range reads, manifest/signature checks, per-component ports, CAT1 proof.
local candidate_paths=require("ota_candidates")
local K_ZIP_TRUNCATED='ZIP_TRUNCATED'
local K_BUNDLE_PORT_ERROR='BUNDLE_PORT_ERROR'
local K_BUSINESS_PAUSED='BUSINESS_PAUSED'
local K_BUNDLE_ENTITY_CHANGED='BUNDLE_ENTITY_CHANGED'
local K_HASH_UPDATE_FAILED='HASH_UPDATE_FAILED'
local K_DIAGNOSTIC_ONLY='DIAGNOSTIC_ONLY'
local M={}
local crc32=require("ota_store").crc32
local LIMIT=16384
local GR_SLOT=442368
local GR_PAYLOAD=GR_SLOT-904
local allowed={['bundle.json']=8192,['signature.json']=2048,['signing_public.xml']=2048,
 ['CAT1/build.json']=16384,['GR5526/payload.bin']=GR_SLOT,['CAT1/payload.sota']=974848}
local function need(ok,code) if not ok then error(code,0) end end
local function safe(e,fallback)return type(e)=='string' and e:match('^[A-Z0-9_]+$') and e or fallback end
local function uint(n,lo,hi) return type(n)=='number' and n%1==0 and n>=lo and n<=hi end
local function hex(s,n) return type(s)=='string' and #s==n and s:match('^[0-9a-f]+$')~=nil end
local function u16(s,p) local a,b=s:byte(p,p+1);need(b~=nil,K_ZIP_TRUNCATED);return a+b*256 end
local function u32(s,p) return u16(s,p)+u16(s,p+2)*65536 end
local function field(t,name)
 local value
 for k,v in pairs(t or {}) do if type(k)=='string' and k:lower()==name then need(value==nil and type(v)=='string','HTTP_HEADERS');value=v end end
 return value
end
local function version(s)
 need(type(s)=='string' and #s<=11,'VERSION_FORMAT')
 local a,b,c=s:match('^(%d+)%.(%d+)%.(%d+)$')
 if not a then a,b=s:match('^(%d+)%.(%d+)$');c='0' end
 a,b,c=tonumber(a),tonumber(b),tonumber(c)
 need(uint(a,0,999) and uint(b,0,999) and uint(c,0,999),'VERSION_FORMAT');return a*1000000+b*1000+c
end
local function copy(t) local r={};for k,v in pairs(t) do r[k]=v end;return r end
local function inspect(port,input,diagnostic)
 need(type(port)=='table' and type(input)=='table','BUNDLE_ARGUMENT')
 local function call(name,...)
  need(type(port[name])=='function','CAPABILITY_'..name:upper())
  local ok,value,reason=pcall(port[name],...);need(ok,K_BUNDLE_PORT_ERROR);return value,reason
 end
 local url=input.url
 local archive_md5=type(input.md5)=='string' and input.md5:lower() or nil
 need(type(url)=='string' and #url<=2048 and url:match('^https?://[^/%?#]+') and not url:find('[%c%s#]'),'BUNDLE_URL')
 need(hex(port.trusted_key_id,64),'TRUSTED_KEY_MISSING')
 local size,entity
 local function read(first,count)
  need(uint(first,0,2097151) and uint(count,1,LIMIT),'RANGE_BOUNDS')
  need(not size or first+count<=size,'RANGE_BOUNDS');need(call('can_read')==true,K_BUSINESS_PAUSED)
  if type(port.read_at)=='function' then
   need(port.transport_mode=='SEQUENTIAL_200','BYTE_SOURCE_MODE')
   local body,id=call('read_at',url,first,count)
   if body==nil then error(safe(id,'BYTE_SOURCE'),0)end
   need(type(body)=='string' and #body==count and type(id)=='table' and uint(id.size,22,2097152) and hex(id.sha256,64),'BYTE_SOURCE')
   local object='"sha256-'..id.sha256..'"'
   need(first+count<=id.size and (not size or (size==id.size and entity==object)),K_BUNDLE_ENTITY_CHANGED)
   size,entity=id.size,object
   need(call('can_read')==true,K_BUSINESS_PAUSED);return body
  end
  local h={Range='bytes='..first..'-'..(first+count-1)};if entity then h['If-Range']=entity end
  local r,why=call('http_get',url,h,count)
  if r==nil then
   if why=='HTTP_TIMEOUT' or why=='HTTP_CONNECT' or why=='HTTP_SOCKET' or why=='HTTP_EOF' or why=='HTTP_SEND' then error('NETWORK_ERROR',0) end
   if why==K_BUSINESS_PAUSED or why=='HTTP_BUSY' then error(K_BUSINESS_PAUSED,0) end
  end
  need(type(r)=='table' and r.status==206,'HTTP_RANGE_REQUIRED')
  need(r.final_url==nil or r.final_url==url,'HTTP_REDIRECT')
  need(type(r.headers)=='table' and type(r.body)=='string' and #r.body==count,'HTTP_LENGTH')
  local range=field(r.headers,'content-range');local a,b,n
  if range then a,b,n=range:match('^bytes (%d+)%-(%d+)/(%d+)$') end
  a,b,n=tonumber(a),tonumber(b),tonumber(n)
  need(a==first and b==first+count-1 and uint(n,22,2097152),'HTTP_CONTENT_RANGE')
  need(tonumber(field(r.headers,'content-length'))==count,'HTTP_LENGTH')
  local tag=field(r.headers,'etag')
  need(type(tag)=='string' and #tag>=2 and #tag<=128 and tag:match('^"[^"%c]*"$'),'HTTP_ETAG')
  need(not size or (size==n and entity==tag),K_BUNDLE_ENTITY_CHANGED)
  size,entity=n,tag;need(call('can_read')==true,K_BUSINESS_PAUSED);return r.body
 end
 read(0,1)
 local tail=read(size-22,22)
 need(u32(tail,1)==0x06054b50 and u16(tail,5)==0 and u16(tail,7)==0 and u16(tail,9)==6 and u16(tail,11)==6 and u16(tail,21)==0,'ZIP_EOCD')
 local cd_size,cd_start=u32(tail,13),u32(tail,17)
 need(cd_size<=4096 and cd_start+cd_size==size-22 and cd_start>0,'ZIP_DIRECTORY')
 local central=read(cd_start,cd_size);local pos,entries,ordered=1,{},{}
 for _=1,6 do
  need(pos+45<=#central and u32(central,pos)==0x02014b50,'ZIP_DIRECTORY')
  local flags,method=u16(central,pos+8),u16(central,pos+10)
  need((flags==0 or flags==0x800) and method==0,'ZIP_STORE_REQUIRED')
  local checksum,packed,raw=u32(central,pos+16),u32(central,pos+20),u32(central,pos+24)
  local name_len,extra_len,comment_len=u16(central,pos+28),u16(central,pos+30),u16(central,pos+32)
  need(name_len>0 and name_len<=64 and extra_len==0 and comment_len==0 and u16(central,pos+34)==0,'ZIP_PROFILE')
  need(pos+45+name_len<=#central,K_ZIP_TRUNCATED)
  local name=central:sub(pos+46,pos+45+name_len)
  need(allowed[name] and not entries[name] and packed==raw and uint(raw,1,allowed[name]),'ZIP_MEMBER')
  local e={name=name,size=raw,crc=checksum,flags=flags,local_offset=u32(central,pos+42)}
  entries[name]=e;ordered[#ordered+1]=e;pos=pos+46+name_len
 end
 need(pos==#central+1,'ZIP_DIRECTORY')
 table.sort(ordered,function(a,b)return a.local_offset<b.local_offset end)
 local next_offset=0
 for _,e in ipairs(ordered) do
  need(e.local_offset==next_offset and e.local_offset+30<=cd_start,'ZIP_OVERLAP')
  local h=read(e.local_offset,30)
  need(u32(h,1)==0x04034b50 and u16(h,7)==e.flags and u16(h,9)==0 and u32(h,15)==e.crc and u32(h,19)==e.size and u32(h,23)==e.size,'ZIP_LOCAL_HEADER')
  local name_len=u16(h,27);need(name_len==#e.name and u16(h,29)==0,'ZIP_LOCAL_HEADER')
  need(read(e.local_offset+30,name_len)==e.name,'ZIP_LOCAL_NAME')
  e.offset=e.local_offset+30+name_len;next_offset=e.offset+e.size;need(next_offset<=cd_start,'ZIP_OVERLAP')
 end
 need(next_offset==cd_start,'ZIP_OVERLAP')
 local function meta(name)
  local e=entries[name];local body=read(e.offset,e.size);need(crc32(body)==e.crc,'ZIP_META_CRC');return body
 end
 local raw_manifest,raw_signature,public_xml=meta('bundle.json'),meta('signature.json'),meta('signing_public.xml')
 local signature=call('decode',raw_signature)
 need(type(signature)=='table' and signature.schema==1 and signature.domain=='YP001_BUNDLE_LOCAL_TEST_RSA_V1' and signature.algorithm=='RSA-2048-SHA256-PKCS1v1.5','SIGNATURE_PROFILE')
 need(signature.key_id==port.trusted_key_id and call('sha256',public_xml)==port.trusted_key_id,'SIGNATURE_KEY')
 need(call('verify_manifest',raw_manifest,raw_signature)==true,'SIGNATURE_INVALID')
 local doc=call('decode',raw_manifest)
 need(type(doc)=='table' and doc.schema==6 and doc.product=='YP001' and doc.distribution=='CAT1_RANGE_ZIP_STORED_SERIAL','MANIFEST_PROFILE')
 need(doc.signing_key_id==port.trusted_key_id and doc.signing_domain==signature.domain and doc.preserve_user_data==true,'MANIFEST_TRUST')
 need(doc.gr_slot_bytes==GR_SLOT and doc.gr_signature_reserve==904 and doc.reserve_bytes==16384 and doc.cat_core_required=='LuatOS-SoC_V2052_Air780EGH_113.soc','LAYOUT_PROFILE')
 local current=call('current_version');need(version(current)==version(doc.source_version),'SOURCE_VERSION_MISMATCH')
 need(version(doc.target_version)>version(current),'VERSION_NOT_NEWER')
 if input.source_version then need(version(input.source_version)==version(current),'SOURCE_VERSION_MISMATCH') end
 if input.target_version then need(version(input.target_version)==version(doc.target_version),'TARGET_VERSION_MISMATCH') end
 local raw_build=meta('CAT1/build.json');need(call('sha256',raw_build)==doc.cat_build_record_sha256,'BUILD_RECORD_HASH')
 local components,paths={}, {GR5526='GR5526/payload.bin',CAT1='CAT1/payload.sota'}
 need(type(doc.components)=='table' and #doc.components==2,'COMPONENT_COUNT')
 for _,c in ipairs(doc.components) do
  need(type(c)=='table' and paths[c.target] and c.path==paths[c.target] and not components[c.target],'COMPONENT_ID')
  local e=entries[c.path]
  need(c.bytes==e.size and hex(c.sha256,64) and hex(c.md5,32) and version(c.version)==version(doc.target_version),'COMPONENT_MANIFEST')
  local native_gr=false
  if c.target=='GR5526' then
   if c.format=='YP001_GR_PROJECT_PSS_V1' then
    need(c.native_verified==true and uint(c.payload_bytes,8,GR_PAYLOAD) and c.bytes==c.payload_bytes+904 and
      hex(doc.gr_layout_contract_sha256,64) and hex(doc.gr_data_contract_sha256,64),'GR_NATIVE_PROFILE')
    native_gr=true
   else
    need(c.format=='RAW_A_ADDRESS_BIN' and c.native_verified==false and c.bytes<=GR_PAYLOAD,'GR_NATIVE_PROFILE')
   end
  else need(c.format=='LUATOS_EC7XX_SCRIPT_SOTA' and c.native_verified==true,'CAT_NATIVE_PROFILE') end
  components[c.target]={target=c.target,size=c.bytes,sha256=c.sha256,md5=c.md5,version=c.version,url=url,offset=e.offset,etag=entity,bundle_size=size,crc=e.crc,native_gr=native_gr}
 end
 local build=call('decode',raw_build)
 need(type(build)=='table' and build.schema=='YP001_CAT1_SCRIPT_SOTA_V1' and build.sha256==components.CAT1.sha256 and build.package_bytes==components.CAT1.size and version(build.version)==version(components.CAT1.version),'BUILD_RECORD_PROFILE')
 need(uint(build.file_count,1,128) and type(build.compiled_sha256)=='table','BUILD_CODE_IDENTITY')
 local code_files,code_count={},0
 for name,digest in pairs(build.compiled_sha256) do
  need(type(name)=='string' and #name<=96 and name:match('^[%w_][%w_.%-]*$') and
    not name:find('..',1,true) and hex(digest,64),'BUILD_CODE_IDENTITY')
  code_count=code_count+1;need(code_count<=128,'BUILD_CODE_IDENTITY');code_files[name]=digest
 end
 need(code_count==build.file_count and code_files['main.luac']~=nil,'BUILD_CODE_IDENTITY')
 need(doc.cat_actual_script_version==components.CAT1.version and uint(doc.gr_compiled_build,1,65535),'COMPONENT_MANIFEST')
 local manifest_hash=call('sha256',raw_manifest);need(hex(manifest_hash,64),'MANIFEST_HASH')
 local self={}
 local cat_proof=build.gr_cat_proof_hex
 if cat_proof~=nil then need(hex(cat_proof,1808),'CAT_PROOF_FORMAT') end
 function self:cat_proof()return cat_proof end
 -- This is an expected identity, not a health/installation result. Every caller receives its own map.
 function self:cat_identity()
  return {files=copy(code_files),file_count=code_count,version=build.version,
    core_sha256=build.soc_sha256,build_kind=build.build_kind,user_data_ranges_in_payload=build.user_data_ranges_in_payload,
    build_record_sha256=doc.cat_build_record_sha256,manifest_sha256=manifest_hash,
    package_sha256=components.CAT1.sha256,cat_proof=build.gr_cat_proof_hex}
 end
 local scan_offset,scan_context,scan_state=0,nil,'PENDING'
 function self:preflight_status() return {offset=scan_offset,size=size,state=scan_state,etag=entity} end
 local function preflight_step()
  need(hex(archive_md5,32),'ARCHIVE_MD5_REQUIRED')
  need(diagnostic==true or call('owns_bundle',manifest_hash)==true,'GR_BUNDLE_OWNERSHIP_REQUIRED')
  if diagnostic==true then
   need(call('can_read')==true,K_BUSINESS_PAUSED)
   if scan_state=='VERIFIED' then return true,'VERIFIED' end
  elseif call('archive_verified',archive_md5,size,entity,manifest_hash)==true then scan_offset,scan_state=size,'VERIFIED';return true,'VERIFIED' end
  if type(port.preflight_snapshot)=='function' then
   need(call('preflight_snapshot',archive_md5,size,manifest_hash)==true,'STREAM_PREFLIGHT_REQUIRED')
   scan_offset=size
  else
   if not scan_context then scan_context=call('hash_begin','MD5');need(scan_context~=nil,'HASH_BEGIN_FAILED');scan_offset=0 end
   scan_state='VERIFYING'
   -- Diagnostic reads remain bounded at 16KiB; production Range keeps its 4KiB progress steps.
   -- SAM | 2026-11-04 +08:00 | unless the device port sets scan_bytes (OTA speed-up A, 16KiB on the device).
   local scan=uint(port.scan_bytes,1,LIMIT) and port.scan_bytes or 4096
   local n=math.min(diagnostic==true and LIMIT or scan,size-scan_offset);need(n>0,'HASH_STATE')
   local chunk=read(scan_offset,n);need(diagnostic==true or call('owns_bundle',manifest_hash)==true,'GR_BUNDLE_OWNERSHIP_REQUIRED')
   if call('hash_update',scan_context,chunk)~=true then scan_context,scan_offset=nil,0;error(K_HASH_UPDATE_FAILED,0) end
   scan_offset=scan_offset+n
   if scan_offset<size then return true,'VERIFYING' end
   local digest=call('hash_finish',scan_context);scan_context=nil
   if digest~=archive_md5 then scan_offset,scan_state=0,'REJECTED';error('ARCHIVE_MD5_MISMATCH',0) end
  end
  if diagnostic~=true then
   need(call('save_archive_proof',archive_md5,size,entity,manifest_hash)==true,'ARCHIVE_PROOF_SAVE')
   need(call('archive_verified',archive_md5,size,entity,manifest_hash)==true,'ARCHIVE_PROOF_READBACK')
  end
  scan_state='VERIFIED';return true,'VERIFIED'
 end
 function self:preflight_step()
  local ok,result,why=pcall(preflight_step)
  if ok then return result,why end
  return false,safe(result,K_BUNDLE_PORT_ERROR)
 end
 function self:summary() return {size=size,etag=entity,manifest_sha256=manifest_hash,source_version=doc.source_version,target_version=doc.target_version,transport_mode=port.transport_mode or 'HTTP_RANGE',network_restart_from_zero=port.network_restart_from_zero==true,metadata_bytes=port.metadata_bytes,diagnostic_only=diagnostic==true,device_installable=diagnostic~=true and doc.device_installable==true and components.GR5526.native_gr==true and doc.gr_layout_approved==true} end
 function self:close()if type(port.close_transport)=='function' then return call('close_transport')==true end;return true end
 function self:component(target) return components[target] and copy(components[target]) or nil end
 local diag_index,diag_offset,diag_sha,diag_md,diag_rejected=1,0,nil,nil,false
 local function diagnostic_step()
  need(diagnostic==true,K_DIAGNOSTIC_ONLY)
  need(not diag_rejected,'DIAGNOSTIC_REJECTED')
  need(scan_state=='VERIFIED','ARCHIVE_MD5_UNVERIFIED')
  need(call('can_read')==true,K_BUSINESS_PAUSED)
  if diag_index>2 then return true,{stage='COMPLETE',gr_verified=true,cat_verified=true,install_enabled=false} end
  local target=diag_index==1 and 'GR5526' or 'CAT1'
  local c=components[target]
  if not diag_sha then
   diag_sha=call('hash_begin','SHA256');diag_md=call('hash_begin','MD5')
   need(diag_sha~=nil and diag_md~=nil,'HASH_BEGIN_FAILED')
  end
  local n=math.min(LIMIT,c.size-diag_offset)
  local body=read(c.offset+diag_offset,n)
  need(call('hash_update',diag_sha,body)==true and call('hash_update',diag_md,body)==true,K_HASH_UPDATE_FAILED)
  diag_offset=diag_offset+n
  local offset=diag_offset
  local stage='COMPONENT_READING'
  if diag_offset==c.size then
   local sha,md=call('hash_finish',diag_sha),call('hash_finish',diag_md)
   diag_sha,diag_md=nil,nil
   need(sha==c.sha256 and md==c.md5,'COMPONENT_DIGEST')
   diag_index=diag_index+1;diag_offset=0;stage=diag_index>2 and 'COMPLETE' or 'COMPONENT_VERIFIED'
  end
  return true,{stage=stage,target=target,offset=offset,size=c.size,gr_verified=diag_index>1,cat_verified=diag_index>2,install_enabled=false}
 end
 function self:diagnostic_step()
  local ok,result,info=pcall(diagnostic_step)
  if ok then return result,info end
  local why=safe(result,K_BUNDLE_PORT_ERROR)
  if why~=K_BUSINESS_PAUSED and why~='ARCHIVE_MD5_UNVERIFIED' and why~=K_DIAGNOSTIC_ONLY then diag_rejected=true end
  return false,why
 end
 local function component_port(target,epoch,base)
  if diagnostic==true then return nil,K_DIAGNOSTIC_ONLY end
  if not components[target] or not uint(epoch,1,0xffffffff) or type(base)~='table' then return nil,'COMPONENT_ARGUMENT' end
  local component=components[target]
  local function owned()
   if call('owns',target,epoch,manifest_hash)~=true then return false end
   if target=='CAT1' and call('completed','GR5526',manifest_hash)~=true then return false end
   return call('completed',target,manifest_hash)==false
  end
  if not owned() then return nil,'GR_OWNERSHIP_REQUIRED' end
  if not hex(archive_md5,32) or call('archive_verified',archive_md5,size,entity,manifest_hash)~=true then return nil,'ARCHIVE_MD5_UNVERIFIED' end
  local existing=0
  if type(base.size)=='function' then
   existing=base.size(candidate_paths.path(component.sha256))
   if not uint(existing,0,component.size) then return nil,'COMPONENT_FILE_SIZE' end
  end
  local free=call('free_bytes');local budget=component.size-existing+(target=='GR5526' and not component.native_gr and 904 or 0)+16384
  if not uint(free,0,524288) or budget>free then return nil,'COMPONENT_SPACE' end
  local result=copy(base)
  result.http_get=function(request_url,headers,count)
   need(owned(),'GR_OWNERSHIP_LOST');need(request_url==url and type(headers)=='table','COMPONENT_HTTP')
   local a,b=(headers.Range or ''):match('^bytes=(%d+)%-(%d+)$');a,b=tonumber(a),tonumber(b)
   need(uint(a,0,component.size-1) and uint(b,a,component.size-1) and b-a+1==count and count<=LIMIT,'COMPONENT_RANGE')
   need(headers['If-Range']==nil or headers['If-Range']==entity,K_BUNDLE_ENTITY_CHANGED)
   local body=read(component.offset+a,count);need(owned(),'GR_OWNERSHIP_LOST')
   return {status=206,body=body,headers={['Content-Range']='bytes '..a..'-'..b..'/'..component.size,['Content-Length']=tostring(count),ETag=entity}}
  end
  for _,name in ipairs({'write','truncate','checkpoint','verify_file'}) do
   local method=base[name]
   result[name]=function(...)
    if not owned() or call('can_read')~=true or type(method)~='function' then return false end
    local value=method(...)
    if not owned() or call('can_read')~=true then return false end
    if name=='verify_file' and type(value)=='table' and value.content_hash_only==true then
     value=copy(value)
     value.signature_valid=value.size==component.size and value.sha256==component.sha256 and value.md5==component.md5
    end
    return value
   end
  end
  return result
 end
 function self:component_port(target,epoch,base)
  local ok,result,why=pcall(component_port,target,epoch,base)
  if ok then return result,why end
  return nil,safe(result,K_BUNDLE_PORT_ERROR)
 end
 return self
end
function M.stream_profile()return copy(allowed),u16,u32,safe end
local function protected_open(port,input,diagnostic)
 local ok,result=pcall(inspect,port,input,diagnostic)
 if ok then return result end
 return nil,safe(result,'BUNDLE_PARSE_FAILED')
end
function M.open(port,input)return protected_open(port,input,false)end
function M.open_diagnostic(port,input)return protected_open(port,input,true)end
return M
