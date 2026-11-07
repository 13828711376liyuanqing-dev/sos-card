-- SAM | 2026-10-30 08:58 +08:00 | Post-boot health observation of the new CAT1 build (business up, version, code identity, data).
local M={}
local function call(p,k,...)
 local f=p[k];if type(f)~='function' then return nil end
 local ok,a,b,c=pcall(f,...);if ok then return a,b,c end
end
local function uint(n,hi)return type(n)=='number' and n>=0 and n<=hi and n%1==0 end
local function hex(s)return type(s)=='string' and #s==64 and not s:find('[^0-9a-f]')end
local function number(s)
 if type(s)~='string' or #s>11 then return nil end
 local a,b,c=s:match('^(%d+)%.(%d+)%.(%d+)$');a,b,c=tonumber(a),tonumber(b),tonumber(c)
 if uint(a,999) and uint(b,999) and uint(c,999) then return a*1000000+b*1000+c end
end
function M.new(p)
 local first,last,key,elapsed=nil,nil,nil,0
 local reason='NOT_OBSERVED'
 local self={}
 local function deny(why,reset)
  if reset then first,last,key,elapsed=nil,nil,nil,0 end
  reason=why;return nil,why
 end
 function self:status()return {reason=reason,observed_ms=elapsed,required_ms=120000}end
 function self:reset(why)return deny(why or 'NOT_OBSERVED',true)end
 function self:check(job,epoch)
  if type(job)~='table' or job.target~='CAT1' or not hex(job.id) or not hex(job.hash) or
   not number(job.version) or not uint(epoch,0xffffffff) or epoch<1 then return deny('HEALTH_IDENTITY',true)end
  local native=call(p,'native_status')
  if type(native)~='table' or (native.phase~='RECOVERY_HOLD' and native.phase~='CONFIRMED') or
   (native.recovery_phase~='COMMITTING' and native.recovery_phase~='COMMITTED' and native.recovery_phase~='REBOOTING' and native.recovery_phase~='CONFIRMED') then
   return deny('REBOOT_EVIDENCE_REQUIRED',true)
  end
  if native.epoch~=epoch or type(native.job)~='table' then return deny('HEALTH_IDENTITY',true)end
  for _,k in ipairs({'id','hash','target','version','source','size'})do
   if native.job[k]~=job[k] then return deny('HEALTH_IDENTITY',true)end
  end
  if native.code_identity_required~=true or call(p,'code_identity')~='VERIFIED' then return deny('BOOT_IDENTITY_REQUIRED',true)end
  local component,product,build=call(p,'version')
  if number(component)~=number(job.version) or number(product)~=number(job.version) or not uint(build,65535) or build<1 then
   return deny('RUNNING_VERSION_MISMATCH',true)
  end
  local business=call(p,'business')
  if type(business)~='table' or business.known~=true or business.idle~=true or business.alarm~=false or
   business.network~='mqtt' or (business.call~='idle' and business.call~='ended') then return deny('BUSINESS_NOT_HEALTHY',true)end
  local now=call(p,'now')
  if not uint(now,0xffffffff) then return deny('HEALTH_CLOCK',true)end
  local identity=job.id..job.hash..tostring(epoch)..job.version
  if key~=identity or not last or now<last or now-last>3000 then first=now;key=identity end
  last=now;elapsed=now-first
  if elapsed<120000 then return deny('HEALTH_OBSERVING',false)end
  local data_scope,kv_acceptance
  for _,v in ipairs({{'data_evidence','data_ok','DATA'}})do
   local e=call(p,v[1],job,epoch)
   if type(e)~='table' then return deny(v[3]..'_EVIDENCE_UNAVAILABLE',false)end
   if e.job~=job.id or e.hash~=job.hash or e.epoch~=epoch or number(e.version)~=number(job.version) or e[v[2]]~=true then
    return deny(v[3]..'_EVIDENCE_MISMATCH',false)
   end
   if not uint(e.observed_ms,0xffffffff) or e.observed_ms>now or now-e.observed_ms>3000 then return deny(v[3]..'_EVIDENCE_STALE',false)end
   data_scope=e.data_scope;kv_acceptance=e.kv_acceptance
  end
  reason='VERIFIED'
  return {job=job.id,hash=job.hash,epoch=epoch,version=job.version,healthy=true,installation_verified=true,data_ok=true,health_observed_ms=elapsed,
   data_scope=data_scope,kv_acceptance=kv_acceptance}
 end
 return self
end
return M
