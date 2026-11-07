-- SAM | 2026-10-24 +08:00 | Maintenance baseline holds the exact failed S2 task; no automatic resume or old-bundle reinstall before an empty-download cancellation receipt.
local M={}
local OLD='d31713e0fb1af1bcb4eb026a201b2a39'
function M.new(options)
 local active=require('ota_runtime').new(options)
 local function held()
  local s=active:status();local j=s.job
  return j and j.bundle and j.bundle.md5==OLD and s.phase~='CANCELLING'
 end
 local self={}
 function self:tick()if held() then return false,'S2_REPAIR_HELD' end;return active:tick()end
 function self:pump_gr()if held() then return false end;return active:pump_gr()end
 function self:on_gr_line(line)if held() then return false,'S2_REPAIR_HELD' end;return active:on_gr_line(line)end
 function self:accept(cmd)
  if type(cmd)=='table' and cmd.Md5==OLD then return false,'OLD_BUNDLE_RETIRED' end
  if held() then return false,'S2_REPAIR_HELD' end
  return active:accept(cmd)
 end
 return setmetatable(self,{__index=function(_,key)
  local value=active[key]
  if type(value)=='function' then return function(_,...)return value(active,...)end end
  return value
 end})
end
return M
