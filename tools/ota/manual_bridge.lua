-- SAM | 2026-10-24 +08:00 | Baseline-only bridge retires the exact unsent JSON-bug task after fresh GR IDLE; never clear user data or release a live owner.
local M={}
local OLD='3d6719bf8646044f8e428162283e3f06'
local NEW='353e60cc1d9c1a3adf059769b2f28d15'
function M.new(options)
 local runtime=require('ota_runtime')
 local active=runtime.new(options)
 local pending,fault
 local self={}
 local function ticks()local n=mcu.ticks();if type(n)=='number' and n>=0 and n%1==0 then return n end end
 local function legacy(s)
  local j=s.job
  return s.phase=='WAIT_GR' and type(j)=='table' and j.target=='GR5526' and j.source=='1.0.2' and j.version=='1.5.0' and type(j.bundle)=='table' and j.bundle.md5==OLD
 end
 local function emit(s)
  if type(_G.uart_send_raw)=='function' then _G.uart_send_raw('OTA_LOCAL='..s)end
 end
 function self:tick()
  if fault or legacy(active:status()) then return false,fault or 'LEGACY_TASK_HELD' end
  return active:tick()
 end
 function self:accept(cmd)
  if fault then return false,fault end
  local s=active:status()
  if not legacy(s) then return active:accept(cmd) end
  local t=ticks()
  if pending and t and t>=pending.at and t-pending.at<3000 then return false,'QUERY_PENDING' end
  pending=nil
  if s.error or s.epoch~=nil or type(cmd)~='table' or cmd.MsgType~='otaMsg' or cmd.Md5~=NEW or cmd.CurrentVersion~='1.0.2' or cmd.TargetVersion~='1.5.0' or not t then return false,'REPLACEMENT_REFUSED' end
  local ok,copy=pcall(function()return json.decode(json.encode(cmd))end)
  if not ok then return false,'COMMAND_INVALID' end
  pending={at=t,id=s.job.id,hash=s.job.hash,command=copy}
  if require('ota_platform').default().send_gr({op='QUERY'})~=true then pending=nil;return false,'QUERY_SEND_FAILED' end
  return true,'GR_IDLE_QUERY_PENDING'
 end
 function self:on_gr_line(line)
  if not pending then return active:on_gr_line(line) end
  local t=ticks();local query=pending
  if not t or t<query.at or t-query.at>=3000 then pending=nil;return false,'QUERY_EXPIRED' end
  if type(line)~='string' or #line>1024 or line:sub(1,7)~='OTA_GR=' then return false,'FRAME' end
  local ok,msg=pcall(function()return json.decode(line:sub(8))end)
  if not ok or type(msg)~='table' then return false,'JSON' end
  pending=nil
  if msg.op~='STATUS' or msg.reason~='ok' or msg.phase~='IDLE' or msg.job~='' or msg.hash~='' or msg.target~='' or type(msg.epoch)~='number' or msg.epoch<0 or msg.epoch>0xffffffff or msg.epoch%1~=0 then emit('GR_NOT_IDLE');return false,'GR_NOT_IDLE' end
  local store=require('ota_store');local disk=store.new(store.file_port(),json)
  local state,why=disk:load()
  if not state or not legacy(state) or state.epoch~=nil or state.job.id~=query.id or state.job.hash~=query.hash or state.download~=nil or type(state.release)~='table' or state.release.gr_done or state.release.gr_finished or state.release.cat_done or state.release.cat_finished then return false,why or 'WAITING_TASK_CHANGED' end
  state.retired_waiting={id=query.id,hash=query.hash,md5=OLD,reason='JSON_NATIVE_TRANSPORT_FIX'}
  state.phase='IDLE';state.job=nil;state.epoch=nil;state.release=nil;state.reason=nil;state.result=nil;state.download=nil;state.prepared_ack=nil
  local saved,reason=disk:save(state)
  if not saved then fault='RETIRE_SAVE_FAILED';return false,reason or fault end
  active=runtime.new(options)
  if active:status().error then fault='RELOAD_FAILED';return false,fault end
  emit('OLD_WAIT_RETIRED_GR_IDLE')
  local scheduled=pcall(sys.taskInit,function()
   local success,accepted,result=pcall(function()return active:accept(query.command)end)
   local code=success and type(result)=='string' and result:match('^[A-Z0-9_]+$') and result or 'ACCEPT_FAILED'
   emit((success and accepted==true and 'ACCEPTED_' or 'REJECTED_')..code)
  end)
  if not scheduled then return false,'TASK_START_FAILED' end
  return true,'OLD_WAIT_RETIRED'
 end
 return setmetatable(self,{__index=function(_,key)
  local value=active[key]
  if type(value)=='function' then return function(_,...)return active[key](active,...)end end
  return value
 end})
end
return M
