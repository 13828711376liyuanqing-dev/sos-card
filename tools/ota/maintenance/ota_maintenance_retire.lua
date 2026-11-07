-- SAM | 2026-11-07 +08:00 | Explicit wired-maintenance profile retires one failed GR task; never installed in production automatically.
-- This writes only the manager journal through ota_store.save/readback. It neither clears candidate files nor authorizes hardware maintenance.
local M={}
local function uint(v)return type(v)=='number' and v>=0 and v<=0xffffffff and v%1==0 end
local function hex(v)return type(v)=='string' and #v==64 and not v:find('[^0-9a-f]')end
local function text(v,n)return type(v)=='string' and #v>0 and #v<=n and not v:find('[%z\r\n]')end
local function profile_valid(p)
    return type(p)=='table' and text(p.tag,96) and hex(p.job_id) and hex(p.hash) and uint(p.epoch) and p.epoch>0 and
        text(p.source_version,63) and text(p.target_version,63) and p.source_version~=p.target_version and
        p.reason=='activation_validation_failed' and p.baseline_version==p.target_version
end
local function audit_matches(a,p)
    if type(a)~='table' or a.reason~='wired_maintenance_retired' or a.failure_reason~=p.reason then return false end
    for _,k in ipairs({'tag','job_id','hash','epoch','source_version','target_version','baseline_version'})do
        if a[k]~=p[k] then return false end
    end
    return true
end
local function native_inactive(s)
    if s==nil then return true end
    if type(s)~='table' or s.schema~=1 or s.active==true then return false end
    if s.phase=='IDLE' then
        return s.job==nil and s.path==nil and s.epoch==nil and s.result==nil and s.native_activation_possible~=true and
            (s.recovery_phase==nil or s.recovery_phase=='IDLE')
    end
    return s.phase=='CONFIRMED' and (s.recovery_phase==nil or s.recovery_phase=='CONFIRMED') and
        type(s.result)=='table' and s.result.installation_verified==true and s.result.data_ok==true
end
local function run(store,native_store,codec,p,actual_version,now)
    if not profile_valid(p) then return false,'PROFILE_INVALID' end
    local function clone(v)return codec.decode(codec.encode(v))end
    local state,err=store:load()
    if err or type(state)~='table' then return false,err or 'MANAGER_STATE_MISSING' end
    -- SAM | 2026-11-07 +08:00 | Validate through the real manager using a private memory copy; boot normalization cannot alter the device journal.
    local memory=clone(state)
    local manager=require('ota_manager').new({load=function()return memory end,save=function(v)memory=clone(v);return true end},{},codec)
    if manager:status().error then return false,'MANAGER_STATE_INVALID' end
    -- A matching durable audit wins before later task/native/version checks: subsequent boots must leave a new OTA entirely untouched.
    if audit_matches(state.cancelled,p) then return true,'ALREADY_RETIRED' end
    if state.cancelled~=nil then return false,'AUDIT_MISMATCH' end
    local j,t,r=state.job,state.trial,state.release
    if state.phase~='RECOVERY_HOLD' or state.reason~=p.reason or type(j)~='table' or j.target~='GR5526' or
        j.id~=p.job_id or j.hash~=p.hash or state.epoch~=p.epoch or j.source~=p.source_version or j.version~=p.target_version then
        return false,'TASK_IDENTITY_OR_STATE'
    end
    if type(t)~='table' or t.status~='SPENT' or t.id~=p.job_id or t.hash~=p.hash or t.epoch~=p.epoch then
        return false,'TRIAL_IDENTITY_OR_STATE'
    end
    -- SAM | 2026-11-07 +08:00 | io2 is keyed by job ID; retain unrelated history because the manager never activates it for this GR job.
    if state.native_release~=nil or (state.io2~=nil and state.io2.id==j.id) then return false,'INSTALL_ONLY_STATE_PRESENT' end
    -- SAM | 2026-11-07 +08:00 | Retain only the matched failed bundle so existing IDLE cleanup can reclaim its exact OTA candidate later.
    if type(r)~='table' or r.gr_hash~=p.hash or type(r.command)~='table' or
        r.command.CurrentVersion~=p.source_version or r.command.TargetVersion~=p.target_version then return false,'RELEASE_IDENTITY' end
    if r.gr_done~=false or r.gr_finished~=false or r.gr_cleaned~=false or r.cat_hash~=nil or
        (r.cat_started~=nil and r.cat_started~=false) or r.cat_finished~=false or r.cat_done~=false or r.cat_cleaned~=false or r.cleanup_target~=nil then
        return false,'COMPONENT_PROGRESS_PRESENT'
    end
    if actual_version~=p.baseline_version then return false,'BASELINE_VERSION_MISMATCH' end
    if not uint(now) or now==0 then return false,'CLOCK_UNAVAILABLE' end
    local native,verified=native_store:load()
    if verified~=true or not native_inactive(native) then return false,'NATIVE_STATE_UNSAFE' end
    if #state.outbox>=8 or state.next_id>=0xffffffff then return false,'OUTBOX_FULL' end
    -- SAM | 2026-11-07 +08:00 | Persist one original-protocol failure and spent quota with the audit before releasing only OTA metadata.
    local next=clone(state)
    next.outbox[#next.outbox+1]={id=next.next_id,payload={MsgType='otaResultMsg',Status='fail',Version=actual_version,Time=now}}
    next.next_id=next.next_id+1
    next.failures[p.hash]=math.min(3,(next.failures[p.hash] or 0)+1)
    next.cancelled={tag=p.tag,job_id=p.job_id,hash=p.hash,epoch=p.epoch,source_version=p.source_version,
        target_version=p.target_version,baseline_version=p.baseline_version,failure_reason=p.reason,reason='wired_maintenance_retired'}
    for _,k in ipairs({'job','epoch','download','result','prepared_ack','native_release','activation_retry'})do next[k]=nil end
    next.release.gr_finished=true;next.release.gr_done=false;next.release.gr_cleaned=false
    next.phase='IDLE';next.reason='WIRED_MAINTENANCE_RETIRED'
    local ok,why=store:save(next)
    if ok~=true then return false,why or 'STORE_COMMIT_FAILED' end
    return true,'RETIRED'
end
function M.run(store,native_store,codec,profile,actual_version,now)
    local ok,result,why=pcall(run,store,native_store,codec,profile,actual_version,now)
    if not ok then return false,'MAINTENANCE_EXCEPTION' end
    return result,why
end
return M
