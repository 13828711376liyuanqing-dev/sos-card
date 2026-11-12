-- SAM | 2026-10-30 08:58 +08:00 | CAT1 native script FOTA (vendor fota.init/run/isDone/finish) with its own journal: start -> WRITING (4 KiB per
-- step) -> COMMITTED -> REBOOTING -> CONFIRMED after reboot. User-data snapshot before commit and after boot must match.
local M={}
local function call(p,k,...)
    local ok,a,b,c=pcall(function(...) return p[k](...) end,...)
    if not ok then return nil end
    return a,b,c
end
local function copy(v)
    if type(v)~='table' then return v end
    local out={};for k,x in pairs(v)do out[k]=copy(x)end;return out
end
local function same_job(a,b)
    if type(a)~='table' or type(b)~='table' then return false end
    for _,k in ipairs({'id','hash','target','size','source','version'})do if a[k]~=b[k] then return false end end
    return true
end
local function valid_release(t)
    local j=type(t)=='table' and t.job
    return type(j)=='table' and j.target=='CAT1' and type(j.id)=='string' and #j.id>0 and
        type(j.hash)=='string' and #j.hash==64 and not j.hash:find('[^0-9a-f]') and
        type(j.size)=='number' and j.size>0 and j.size%1==0 and j.size<=974848 and
        type(j.source)=='string' and type(j.version)=='string' and
        type(t.epoch)=='number' and t.epoch>0 and t.epoch<=0xffffffff and t.epoch%1==0 and
        type(t.version)=='string' and (t.version==j.source or t.version==j.version)
end
local function same_release(a,b)
    if not valid_release(a) or not valid_release(b) or a.epoch~=b.epoch or a.version~=b.version then return false end
    return same_job(a.job,b.job)
end
function M.new(port)
    local p=port or {}
    local old,loaded=call(p,'load')
    local state={phase=(loaded==true and old==nil) and 'IDLE' or 'RECOVERY_HOLD'}
    if loaded==true and type(old)=='table' then
        state=copy(old)
        state.recovery_phase=old.recovery_phase or old.phase
        state.phase='RECOVERY_HOLD'
        if old.schema==1 and old.phase=='IDLE' and valid_release(old.retired) and
            old.job==nil and old.path==nil and old.epoch==nil and old.result==nil then state.phase='IDLE' end
    end
    local native=p.native or {}
    local active=false
    local next_write_at=0
    local self={}
    local boot_data_ok,boot_data_observed=false,false
    local function data_required()return p.require_data_identity==true or state.data_identity_required==true end
    local function valid_data(d)
        return type(d)=='table' and d.schema==1 and d.complete==true and
            (d.scope=='root_files_and_initialized_kv' or (p.allow_unavailable_kv==true and d.scope=='root_files_kv_unverified' and d.kv_unverified==true and d.keys==0 and
            type(p.first_trial)=='table' and p.first_trial:scoped(state.job))) and type(d.digest)=='string' and #d.digest==64 and not d.digest:find('[^0-9a-f]') and
            type(d.files)=='number' and d.files>=0 and d.files<=128 and d.files%1==0 and
            type(d.keys)=='number' and d.keys>=0 and d.keys<=256 and d.keys%1==0
    end
    local function matches_data(d)
        local b=state.data_baseline
        return valid_data(b) and valid_data(d) and b.scope==d.scope and b.digest==d.digest and b.files==d.files and b.keys==d.keys
    end
    function self:observe_boot_data()
        if boot_data_observed then return boot_data_ok end
        boot_data_observed=true
        if not data_required() then return false,'DATA_NOT_REQUIRED' end
        if active or state.phase~='RECOVERY_HOLD' or not valid_data(state.data_baseline) then return false,'DATA_BASELINE_MISSING' end
        local code_ok=false
        for _=1,512 do
            local ok,why=self:verify_running_identity()
            if ok then code_ok=true;break end
            if why~='BOOT_IDENTITY_CHECKING' then return false,why end
        end
        if not code_ok then return false,'BOOT_IDENTITY_CHECKING' end
        if state.recovery_phase=='CONFIRMED' then
            -- A previously confirmed installation is a historical result. Later lawful business writes must not be compared with its old pre-upgrade snapshot.
            boot_data_ok=type(state.result)=='table' and state.result.data_ok==true and
                state.result.data_digest==state.data_baseline.digest and state.result.installation_verified==true
            return boot_data_ok
        end
        if state.recovery_phase~='COMMITTING' and state.recovery_phase~='COMMITTED' and state.recovery_phase~='REBOOTING' then
            return false,'DATA_BOOT_PHASE'
        end
        local receipt=state.boot_data_receipt
        if type(receipt)=='table' and receipt.job==state.job.id and receipt.hash==state.job.hash and receipt.epoch==state.epoch and
            receipt.version==state.job.version and receipt.digest==state.data_baseline.digest then
            boot_data_ok=true;return true
        end
        if not matches_data(call(p,'data_snapshot',copy(state.job),state.path,true)) then return false,'DATA_BOOT_MISMATCH_OR_UNAVAILABLE' end
        -- Persist before business starts. A reset during probation must not compare legitimate later writes with the old snapshot.
        local next=copy(state)
        next.boot_data_receipt={job=state.job.id,hash=state.job.hash,epoch=state.epoch,version=state.job.version,digest=state.data_baseline.digest}
        if call(p,'save',next)~=true then return false,'DATA_BOOT_RECEIPT_FAILED' end
        state=next;boot_data_ok=true
        return boot_data_ok,boot_data_ok and nil or 'DATA_BOOT_MISMATCH_OR_UNAVAILABLE'
    end
    function self:data_evidence(job,epoch,now_ms)
        if not boot_data_ok or not valid_data(state.data_baseline) or type(job)~='table' or type(state.job)~='table' or epoch~=state.epoch then return nil end
        if not same_job(job,state.job) then return nil end
        if type(now_ms)~='number' or now_ms<0 or now_ms>0xffffffff or now_ms%1~=0 then return nil end
        return {job=job.id,hash=job.hash,epoch=epoch,version=job.version,observed_ms=now_ms,data_ok=true,
            evidence_kind='PREBUSINESS_BOOT_COMPARISON',data_digest=state.data_baseline.digest,
            data_scope=state.data_baseline.scope,kv_acceptance=state.data_baseline.kv_unverified==true and 'UNVERIFIED' or 'READABLE_KEYS_COMPARED'}
    end
    local function persist(phase,reason)
        local next=copy(state);next.phase=phase;next.reason=reason
        if call(p,'save',next)~=true then return false end
        state=next;return true
    end
    local function gate()
        return call(p,'safe')==true and call(p,'owner',copy(state.job),state.epoch)==true
    end
    local function stop(reason)
        -- Cancellation is best effort, never evidence that a vendor pending flag is clear.
        if active and state.native_activation_possible~=true then call(native,'finish',false) end
        active=false
        if not persist('HOLD',reason) then state.phase='HOLD';state.reason='JOURNAL_FAILED' end
        return false,reason
    end
    function self:status() return copy(state) end
    local function identity_required()return p.require_code_identity==true or state.code_identity_required==true end
    function self:verify_running_identity()
        if not identity_required() then return true,'NOT_REQUIRED' end
        if active or (state.phase~='RECOVERY_HOLD' and state.phase~='CONFIRMED') then return false,'REBOOT_EVIDENCE_REQUIRED' end
        if not require('ota_boot_identity').matches(state.expected_identity,state.job) then return false,'BOOT_IDENTITY_REQUIRED' end
        local ok,why=call(p,'code_identity',copy(state.expected_identity))
        if ok~=true then return false,why or 'BOOT_IDENTITY_UNAVAILABLE' end
        return true
    end
    function self:reboot(job,epoch)
        if active or state.phase~='COMMITTED' or type(job)~='table' or type(state.job)~='table' or
            epoch~=state.epoch then return false,'REBOOT_IDENTITY' end
        if not same_job(job,state.job) then return false,'REBOOT_IDENTITY' end
        if not gate() or type(p.reboot)~='function' then return false,'REBOOT_NOT_AUTHORIZED' end
        if data_required() and not matches_data(call(p,'data_snapshot',copy(job),state.path,false)) then return false,'DATA_CHANGED_BEFORE_REBOOT' end
        if not persist('REBOOTING') then return false,'JOURNAL_FAILED' end
        if not gate() then return false,'REBOOT_AUTHORITY_LOST' end
        if call(p,'reboot')~=true then return false,'REBOOT_RESULT_UNKNOWN' end
        return true
    end
    function self:clear_unwritten(job)
        if not active and state.phase=='IDLE' and state.job==nil then return true end -- already cleared (idempotent if the arm's other checks failed)
        if active or state.phase~='RECOVERY_HOLD' or state.recovery_phase~='HOLD' or state.reason~='AUTHORITY_LOST' or state.offset~=0 or
            state.native_activation_possible==true or type(job)~='table' or type(state.job)~='table' or not same_job(job,state.job) then return false end
        local next={schema=1,phase='IDLE'};if call(p,'save',next)~=true then return false end
        state=next;return true
    end
    function self:retire(token)
        if active or not valid_release(token) then return false,'RELEASE_IDENTITY' end
        if state.phase=='IDLE' and same_release(state.retired,token) then return true end
        if data_required() and not boot_data_ok then return false,'DATA_BOOT_EVIDENCE_REQUIRED' end
        if (state.phase~='CONFIRMED' and not (state.phase=='RECOVERY_HOLD' and state.recovery_phase=='CONFIRMED')) or
            type(state.result)~='table' or state.result.healthy~=true or state.result.installation_verified~=true or state.result.data_ok~=true or
            (identity_required() and state.result.code_identity~=true) or
            not same_release({job=state.job,epoch=state.epoch,version=state.result.version},token) then return false,'NOT_CONFIRMED' end
        local next={schema=1,phase='IDLE',retired=copy(token)}
        if call(p,'save',next)~=true then return false,'JOURNAL_FAILED' end
        state=next;return true
    end
    function self:confirm(job,epoch,info)
        if active or (state.phase~='RECOVERY_HOLD' and state.phase~='CONFIRMED') then return false,'REBOOT_EVIDENCE_REQUIRED' end
        if type(job)~='table' or type(state.job)~='table' or type(info)~='table' then return false,'RESULT_IDENTITY' end
        if not same_job(job,state.job) then return false,'RESULT_IDENTITY' end
        if job.target~='CAT1' or type(job.id)~='string' or type(job.hash)~='string' or
            type(epoch)~='number' or epoch<=0 or epoch%1~=0 or epoch~=state.epoch or
            info.job~=job.id or info.hash~=job.hash or info.epoch~=epoch then return false,'RESULT_IDENTITY' end
        if info.healthy~=true or info.installation_verified~=true or info.data_ok~=true or
            type(info.version)~='string' or (info.version~=job.version and info.version~=job.source) then return false,'NOT_CONFIRMED' end
        if data_required() and not boot_data_ok then return false,'DATA_BOOT_EVIDENCE_REQUIRED' end
        local phase=state.recovery_phase
        if phase~='INTENT' and phase~='HOLD' and phase~='COMMITTING' and phase~='COMMITTED' and phase~='REBOOTING' and phase~='CONFIRMED' then
            return false,'NATIVE_PHASE_UNKNOWN'
        end
        if info.version==job.version and phase~='COMMITTING' and phase~='COMMITTED' and phase~='REBOOTING' and phase~='CONFIRMED' then
            return false,'NO_COMMIT_EVIDENCE'
        end
        local identity_ok,identity_reason=self:verify_running_identity()
        if not identity_ok then return false,identity_reason end
        local result={version=info.version,healthy=true,installation_verified=true,data_ok=true,
            data_digest=data_required() and state.data_baseline.digest or nil,
            data_scope=data_required() and state.data_baseline.scope or nil,
            kv_acceptance=data_required() and (state.data_baseline.kv_unverified==true and 'UNVERIFIED' or 'READABLE_KEYS_COMPARED') or nil,
            code_identity=identity_required() and true or nil,health_observed_ms=info.health_observed_ms}
        if state.result then
            if phase~='CONFIRMED' or type(state.result)~='table' or state.result.version~=info.version or
                state.result.healthy~=true or state.result.installation_verified~=true or state.result.data_ok~=true or
                (identity_required() and state.result.code_identity~=true) then
                return false,'RESULT_CONFLICT'
            end
            return true,copy(state.result)
        end
        local next=copy(state);next.phase='CONFIRMED';next.recovery_phase='CONFIRMED';next.result=result
        if call(p,'save',next)~=true then return false,'JOURNAL_FAILED' end
        state=next;return true,copy(result)
    end
    function self:completion_report(job,epoch)
        if data_required() and not boot_data_ok then return nil,'DATA_BOOT_EVIDENCE_REQUIRED' end
        local r=state.result;local expected=state.expected_identity
        if active or not identity_required() or (state.phase~='CONFIRMED' and
            not(state.phase=='RECOVERY_HOLD' and state.recovery_phase=='CONFIRMED')) or
            type(job)~='table' or type(state.job)~='table' or epoch~=state.epoch or type(r)~='table' or
            r.version~=job.version or r.healthy~=true or r.installation_verified~=true or r.data_ok~=true or r.code_identity~=true or
            type(r.health_observed_ms)~='number' or r.health_observed_ms%1~=0 or r.health_observed_ms<120000 or
            r.health_observed_ms>0xffffffff then return nil,'NATIVE_CONFIRMATION_REQUIRED' end
        if not same_job(job,state.job) then return nil,'RESULT_IDENTITY' end
        if type(expected)~='table' or type(expected.cat_proof)~='string' or #expected.cat_proof~=1808 or
            expected.cat_proof:find('[^0-9a-f]') then return nil,'CAT_PROOF_REQUIRED' end
        local ok,why=self:verify_running_identity();if not ok then return nil,why end
        return {actual_version=r.version,native_phase='CONFIRMED',code_identity=true,installation_verified=true,data_ok=true,
            durable_result=true,health_ms=r.health_observed_ms,proof=expected.cat_proof}
    end
    function self:start(job,path,epoch)
        if state.phase~='IDLE' then return false,'RECOVERY_REQUIRED' end
        if type(job)~='table' or job.target~='CAT1' or type(job.id)~='string' or
           type(job.hash)~='string' or #job.hash~=64 or job.hash:find('[^0-9a-f]') or
           type(job.size)~='number' or job.size<=0 or job.size%1~=0 or
           type(path)~='string' or #path==0 or type(epoch)~='number' or epoch<=0 or epoch%1~=0 then
            return false,'IDENTITY'
        end
        if call(p,'native_contract_verified',copy(job))~=true then return false,'NATIVE_CONTRACT_UNVERIFIED' end
        local expected
        if p.require_code_identity==true then
            expected=call(p,'expected_identity',copy(job))
            if not require('ota_boot_identity').matches(expected,job) then return false,'BOOT_IDENTITY_REQUIRED' end
        end
        for _,name in ipairs({'init','wait','run','isDone','finish'})do
            local ok,fn=pcall(function()return native[name]end)
            if not ok or type(fn)~='function' then return false,'NATIVE_API_UNAVAILABLE' end
        end
        state.job=copy(job);state.path=path;state.epoch=epoch;state.offset=0
        if not gate() or call(p,'verify',copy(job),path)~=true or not gate() then return false,'NOT_AUTHORIZED' end
        local now=call(p,'now')
        if type(now)~='number' or now~=now or now<0 or now==math.huge then return false,'CLOCK' end
        state.started=now;state.last_clock=now
        state.retired=nil;state.recovery_phase=nil;state.result=nil
        state.boot_data_receipt=nil
        boot_data_ok=false;boot_data_observed=false
        next_write_at=0
        state.code_identity_required=p.require_code_identity==true
        state.expected_identity=copy(expected)
        state.data_identity_required=p.require_data_identity==true
        if data_required() then
            local d=call(p,'data_snapshot',copy(job),path,false)
            if not valid_data(d) or not gate() then return false,'DATA_BASELINE_UNAVAILABLE' end
            state.data_baseline=copy(d)
        end
        if not persist('INTENT') then state.phase='HOLD';return false,'JOURNAL_FAILED' end
        if not gate() then return stop('AUTHORITY_LOST') end
        -- init may have side effects even when it throws; retain intent and cancel conservatively.
        active=true
        if call(native,'init')~=true then return stop('INIT_FAILED') end
        state.phase='WRITING'
        return true
    end
    function self:step()
        if not active or state.phase~='WRITING' then return false,'RECOVERY_REQUIRED' end
        if not gate() then return stop('AUTHORITY_LOST') end
        local now=call(p,'now')
        if type(now)~='number' or now~=now or now<state.last_clock or now-state.started>120 then return stop('TIMEOUT_OR_CLOCK') end
        state.last_clock=now
        if now<next_write_at then return true,'WAIT_CACHE' end
        local ready=call(native,'wait')
        if ready==false then return true,'WAIT' end
        if ready~=true then return stop('WAIT_FAILED') end
        if state.offset<state.job.size then
            local count=math.min(4096,state.job.size-state.offset)
            local data=call(p,'read',state.path,state.offset,count)
            if type(data)~='string' or #data~=count then return stop('READ_FAILED') end
            if not gate() then return stop('AUTHORITY_LOST') end
            if state.offset+count==state.job.size then
                if call(p,'verify',copy(state.job),state.path)~=true or not gate() then return stop('COMMIT_RECHECK_FAILED') end
                if data_required() and not matches_data(call(p,'data_snapshot',copy(state.job),state.path,false)) then return stop('DATA_CHANGED_BEFORE_COMMIT') end
                if not gate() then return stop('AUTHORITY_LOST') end
                local intent=copy(state)
                intent.phase='COMMITTING';intent.recovery_phase='COMMITTING';intent.native_activation_possible=true
                if call(p,'save',intent)~=true then return stop('JOURNAL_FAILED') end
                state=intent;state.phase='WRITING'
                if not gate() then return stop('AUTHORITY_LOST') end
            end
            local ok,done,cache=call(native,'run',data)
            if ok~=true or type(done)~='boolean' or type(cache)~='number' or cache<0 or cache%1~=0 or cache>0x7fffffff then return stop('WRITE_FAILED') end
            state.offset=state.offset+count
            if done and state.offset~=state.job.size then
                state.native_activation_possible=true;state.recovery_phase='COMMITTING'
                return stop('EARLY_DONE')
            end
            if cache>65536 then next_write_at=now+0.1;return true,'WAIT_CACHE' end
            return true,'PROGRESS'
        end
        local ok,done=call(native,'isDone')
        if ok~=true then return stop('VERIFY_FAILED') end
        if done~=true then return true,'WAIT' end
        if call(p,'verify',copy(state.job),state.path)~=true or not gate() then return stop('COMMIT_RECHECK_FAILED') end
        if data_required() and not matches_data(call(p,'data_snapshot',copy(state.job),state.path,false)) then return stop('DATA_CHANGED_BEFORE_COMMIT') end
        if not persist('COMMITTING') then return stop('JOURNAL_FAILED') end
        if not gate() then return stop('AUTHORITY_LOST') end
        if call(native,'finish',true)~=true then return stop('FINISH_UNKNOWN') end
        active=false
        if not persist('COMMITTED') then state.phase='RECOVERY_HOLD';return false,'COMMIT_RESULT_UNKNOWN' end
        -- No automatic reboot or fabricated health result. GR must authorize the
        -- reboot and real boot/version/data evidence must close the transaction.
        return true,'COMMITTED'
    end
    return self
end
return M
