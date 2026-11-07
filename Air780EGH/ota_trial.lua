-- SAM | 2026-10-30 08:58 +08:00 | Controlled-trial profile check for the CAT1 native install (version range, core, build identity).
local M={}
local CORE='29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec'
local function hex(s)return type(s)=='string' and #s==64 and not s:find('[^0-9a-f]')end
function M.new(profile,observe)
 local function live()
  if type(profile)~='table' or profile.source~='1.5.7' or profile.target~='1.5.8' or
   profile.core_sha256~=CORE or not hex(profile.evidence_sha256) or type(observe)~='function' then return nil end
  local ok,v=pcall(observe)
  if ok and type(v)=='table' and v.model=='Air780EGH' and v.core=='V2052' and v.bits==64 and
   v.fs_bytes==524288 and v.version==profile.source then return v end
 end
 local self={}
 function self:network()return live()~=nil end
 function self:install(job,id)
  if not live() or type(job)~='table' or job.target~='CAT1' or job.source~=profile.source or job.version~=profile.target or
   not hex(job.hash) or type(job.size)~='number' or job.size%1~=0 or job.size<=0 or job.size>974848 or
   type(job.bundle)~='table' or not hex(job.bundle.manifest_sha256) or type(id)~='table' then return false end
  return id.core_sha256==CORE and id.build_kind=='SCRIPT_ONLY_SAME_CORE' and id.user_data_ranges_in_payload==false and
   id.package_sha256==job.hash and id.manifest_sha256==job.bundle.manifest_sha256
 end
 return self
end
return M
