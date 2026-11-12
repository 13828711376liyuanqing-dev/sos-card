-- SAM | 2026-11-07 +08:00 | One exact empty 21->22 GR grant returns to WAIT_GR so the ordinary GR reply can mint its frozen ticket.
-- Preserves the old ticket and journals; no native calls, candidate cleanup, GR writes or activation authority.
local M = {}
local busy = false
local profile_fields = {'tag','job_id','hash','epoch','source_version','target_version','manifest_sha256','package_md5','size'}
local profile_keys = {}
for _, key in ipairs(profile_fields) do profile_keys[key] = true end

local function uint(value)
    return type(value) == 'number' and value >= 0 and value <= 0xffffffff and value % 1 == 0
end
local function hex(value, length)
    return type(value) == 'string' and #value == length and not value:find('[^0-9a-f]')
end
local function valid_profile(p)
    if type(p) ~= 'table' or type(p.tag) ~= 'string' or #p.tag < 1 or #p.tag > 96 or p.tag:find('[%z\r\n]') or
        not hex(p.job_id,64) or not hex(p.hash,64) or not uint(p.epoch) or p.epoch == 0 or
        p.source_version ~= '1.5.21' or p.target_version ~= '1.5.22' or p.size ~= 382184 or
        not hex(p.manifest_sha256,64) or not hex(p.package_md5,32) then return false end
    for key in pairs(p) do if not profile_keys[key] then return false end end
    return true
end
local function same_profile(a, b)
    if not valid_profile(a) then return false end
    for _, key in ipairs(profile_fields) do if a[key] ~= b[key] then return false end end
    return true
end
local function equal(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= 'table' then return a == b end
    for key, value in pairs(a) do if not equal(value,b[key]) then return false end end
    for key in pairs(b) do if a[key] == nil then return false end end
    return true
end
local function native_idle(s)
    if s == nil then return true end
    return type(s) == 'table' and s.schema == 1 and s.phase == 'IDLE' and s.job == nil and
        s.path == nil and s.epoch == nil and s.result == nil and s.active ~= true and
        s.native_activation_possible ~= true and (s.recovery_phase == nil or s.recovery_phase == 'IDLE')
end

local function run(store, native_store, codec, profile, actual_version, now)
    if not valid_profile(profile) then return false,'PROFILE_INVALID' end
    local function clone(value) return codec.decode(codec.encode(value)) end
    local function manager_valid(value)
        local memory = clone(value)
        local private = {load=function() return memory end,
            save=function(_, next_value) memory=clone(next_value);return true end}
        return not require('ota_manager').new(private,{},codec):status().error
    end
    local state, err = store:load()
    if err or type(state) ~= 'table' then return false,err or 'MANAGER_STATE_MISSING' end
    local audit = state.trial_scope_resume
    if audit ~= nil then
        if type(audit) == 'table' and audit.schema == 1 and same_profile(audit.profile,profile) then
            return true,'ALREADY_MIGRATED'
        end
        return false,'AUDIT_MISMATCH'
    end
    if actual_version ~= profile.source_version then return false,'SOURCE_VERSION_MISMATCH' end
    if _G.OTA_TRIAL_MD5 ~= profile.package_md5 or _G.OTA_TRIAL_SOURCE ~= profile.source_version or
        _G.OTA_TRIAL_TARGET ~= profile.target_version then return false,'RECEIVER_RANGE_OR_MD5' end
    if not uint(now) or now == 0 then return false,'CLOCK_UNAVAILABLE' end
    if not manager_valid(state) then return false,'MANAGER_STATE_INVALID' end
    local generation = store.generation
    if not uint(generation) or generation == 0 then return false,'JOURNAL_GENERATION_UNAVAILABLE' end
    local job, release, trial = state.job, state.release, state.trial
    if state.phase ~= 'GR_GRANTED' or state.epoch ~= profile.epoch or type(job) ~= 'table' or
        job.target ~= 'GR5526' or job.id ~= profile.job_id or job.hash ~= profile.hash or
        job.source ~= profile.source_version or job.version ~= profile.target_version or job.size ~= profile.size or
        type(job.bundle) ~= 'table' or job.bundle.manifest_sha256 ~= profile.manifest_sha256 or
        job.bundle.md5 ~= profile.package_md5 then return false,'TASK_IDENTITY_OR_STATE' end
    if type(trial) ~= 'table' or trial.status ~= 'RUNNING' or trial.id == job.id then
        return false,'LEGACY_TRIAL_REQUIRED'
    end
    if state.download ~= nil or state.result ~= nil or state.activation_retry ~= nil or
        state.prepared_ack ~= nil or state.native_release ~= nil or
        (state.io2 ~= nil and state.io2.id == job.id) then return false,'PROGRESS_PRESENT' end
    if type(release) ~= 'table' or release.manifest ~= profile.manifest_sha256 or release.gr_hash ~= profile.hash or
        type(release.command) ~= 'table' or release.command.CurrentVersion ~= profile.source_version or
        release.command.TargetVersion ~= profile.target_version or release.command.Md5:lower() ~= profile.package_md5 or
        release.command.Address ~= job.url then return false,'RELEASE_IDENTITY' end
    for _, key in ipairs({'gr_finished','gr_done','gr_cleaned','cat_finished','cat_done','cat_cleaned'}) do
        if release[key] ~= false then return false,'COMPONENT_PROGRESS_PRESENT' end
    end
    if release.cat_hash ~= nil or release.cleanup_target ~= nil or release.archive_proof ~= nil or
        (release.cat_started ~= nil and release.cat_started ~= false) then return false,'COMPONENT_PROGRESS_PRESENT' end
    if #state.outbox >= 8 or state.next_id >= 0xffffffff then return false,'OUTBOX_FULL' end
    local native, verified = native_store:load()
    if verified ~= true or not native_idle(native) then return false,'NATIVE_STATE_UNSAFE' end

    local next_state = clone(state)
    next_state.trial_scope_resume = {schema=1,profile=clone(profile),applied_at=now,
        original_epoch=state.epoch,original_trial=clone(trial),journal_generation=generation,
        state_crc32=require('ota_store').crc32(codec.encode(state))}
    next_state.phase = 'WAIT_GR'
    next_state.epoch = nil
    if not manager_valid(next_state) then return false,'MIGRATED_STATE_INVALID' end
    local ok, why = store:save(next_state)
    if ok ~= true then return false,why or 'STORE_COMMIT_FAILED' end
    local readback, read_error = store:load()
    if read_error or not equal(readback,next_state) or not manager_valid(readback) then
        return false,read_error or 'RESUME_READBACK_FAILED'
    end
    return true,'WAIT_GR_RESTORED'
end

function M.run(store, native_store, codec, profile, actual_version, now)
    if busy then return false,'RESUME_BUSY' end
    busy = true
    local ok, result, reason = pcall(run,store,native_store,codec,profile,actual_version,now)
    busy = false
    if not ok then return false,'RESUME_EXCEPTION' end
    return result,reason
end
return M
