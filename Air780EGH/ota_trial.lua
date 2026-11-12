-- SAM | 2026-10-30 08:58 +08:00 | Controlled-trial profile check for the CAT1 native install (version range, core, build identity).
-- SAM | 2026-11-10 +08:00 | Production gate (user baseline 2026-11-10: every shipped device accepts any higher signed version, no per-package
-- receiver). The device identity (model, core, width, file system, core hash) is still checked; the SOURCE is the version the device is
-- running now and the TARGET only has to be higher. Which package may be installed is decided by the signed manifest and the signed
-- authorization (GR authority), no longer by a version range or an MD5 written into this script.
local M={}
local CORE='29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec'
local function hex(s)return type(s)=='string' and #s==64 and not s:find('[^0-9a-f]')end
-- x.y.z -> number (same encoding as the GR descriptor: major*1e6+minor*1e3+patch); nil when the text is not a version
local function num(v)
 if type(v)~='string' then return nil end
 local a,b,c=v:match('^(%d+)%.(%d+)%.(%d+)$')
 if not a or #a>3 or #b>3 or #c>3 then return nil end
 return tonumber(a)*1000000+tonumber(b)*1000+tonumber(c)
end
function M.new(profile,observe)
 local function live()
  if type(profile)~='table' or profile.core_sha256~=CORE or not hex(profile.evidence_sha256) or type(observe)~='function' then return nil end
  local ok,v=pcall(observe)
  if ok and type(v)=='table' and v.model=='Air780EGH' and v.core=='V2052' and v.bits==64 and
   v.fs_bytes==524288 and num(v.version) then return v end
 end
 local self={}
 function self:network()return live()~=nil end
 -- An upgrade of what the device runs now: source is the running version, target is strictly higher.
 function self:eligible(job)
  local v=live()
  return v~=nil and type(job)=='table' and job.source==v.version and num(job.version)~=nil and num(job.version)>num(v.version)
 end
 -- SAM | 2026-11-10 | The unverified-KV data scope belongs to the job, before AND after the install reboot: device identity is checked, the job must
 -- be a well-formed upgrade, and the running version is the source (before the reboot) or the target (after it). (Using eligible() here broke the
 -- post-reboot data comparison: the device then runs the target, so source~=running and the install stayed in RECOVERY_HOLD DATA_EVIDENCE_UNAVAILABLE.)
 function self:scoped(job)
  local v=live()
  return v~=nil and type(job)=='table' and num(job.source)~=nil and num(job.version)~=nil and num(job.version)>num(job.source) and
   (v.version==job.source or v.version==job.version)
 end
 function self:install(job,id)
  if not self:eligible(job) or job.target~='CAT1' or
   not hex(job.hash) or type(job.size)~='number' or job.size%1~=0 or job.size<=0 or job.size>974848 or
   type(job.bundle)~='table' or not hex(job.bundle.manifest_sha256) or type(id)~='table' then return false end
  return id.core_sha256==CORE and id.build_kind=='SCRIPT_ONLY_SAME_CORE' and id.user_data_ranges_in_payload==false and
   id.package_sha256==job.hash and id.manifest_sha256==job.bundle.manifest_sha256
 end
 return self
end
return M
