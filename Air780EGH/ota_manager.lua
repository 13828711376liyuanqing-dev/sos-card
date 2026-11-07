-- SAM | 2026-10-30 08:58 +08:00 | Durable OTA state machine (one task at a time). Every effect follows the persisted state in ota_store and an
-- answer from GR; nothing is authorised by RAM flags. Phases: IDLE -> WAIT_GR -> GR_GRANTED -> PREPARING/PAUSED -> PREPARED ->
-- WAIT_ACTIVATE -> (GR: GR installs | CAT1: RECOVERY_HOLD+io ARMED -> ACTIVATION_ISSUED -> INSTALLING) -> COMPLETE_PENDING -> IDLE.
-- A bundle has two components: GR5526 first, then CAT1 from the same release record. See README.md.
local candidate_paths=require("ota_candidates")
local M = {}
local K_STATE_INVALID='STATE_INVALID'
local K_STATE_CHANGED='STATE_CHANGED'
local K_COMPONENT_SPACE='COMPONENT_SPACE'
local K_CLEANUP_IDENTITY='CLEANUP_IDENTITY'
local K_RETRY_BACKOFF='RETRY_BACKOFF'
local K_GR_RECONCILE_REQUIRED='GR_RECONCILE_REQUIRED'
local K_NATIVE_RELEASE_PENDING='NATIVE_RELEASE_PENDING'
local K_RETRY_CLOCK_UNAVAILABLE='RETRY_CLOCK_UNAVAILABLE'
local K_RELEASE_NOT_VERIFIED='RELEASE_NOT_VERIFIED'
local K_FAILED_HASH_LIMIT='FAILED_HASH_LIMIT'
local K_COMPLETE_PENDING='COMPLETE_PENDING'
local function hex(s,n) return type(s)=="string" and #s==n and not s:find("[^%x]") end
local function text(s,n) return type(s)=="string" and #s>0 and #s<=n and not s:find("[%z\r\n]") end
local function set(...) local t={};for _,k in ipairs({...}) do t[k]=true end;return t end
-- Prepare outcomes that are progress, not failures (retry budget untouched).
local TRANSIENT=set('DOWNLOAD_PENDING','paused','BUSINESS_BUSY_OR_UNKNOWN','BUSINESS_PAUSED')
-- Transport failures that keep an ordinary bounded retry instead of a permanent hold.
local RETRYABLE=set('network_error','network_timeout','network_idle_timeout','network_eof','network_socket','HTTP_TIMEOUT','HTTP_IDLE_TIMEOUT',
    'HTTP_EOF','HTTP_SOCKET','http_status','NETWORK_ERROR','CAT_PROOF_TIMEOUT','GR_NACK_7')
-- Network-class download causes keep the trial ticket (GR has not been written yet).
local function net_reason(r) return type(r)=='string' and (r:find('^network_')~=nil or r=='NETWORK_ERROR' or r=='HTTP_TIMEOUT' or r=='HTTP_IDLE_TIMEOUT' or r=='HTTP_EOF' or r=='HTTP_SOCKET') end
local function uint(v) return type(v)=="number" and v>=0 and v<=0xffffffff and v%1==0 end
-- SAM | 2026-11-04 +08:00 | Multi-OTA growth: retries[] (per release manifest and component hash) and failures[] were never removed,
-- so the journal grew ~170 B per release (x2 copies). Both maps are now capped (oldest retries / lowest keys go first, the entries
-- of the job in hand are kept) and a completed release clears its own entries plus every non-permanent retry (see finish below).
local HISTORY_MAX=8
local function trim(map,keep)
    local keys,count={},0
    for k in pairs(map) do count=count+1;if not keep[k] then keys[#keys+1]=k end end
    table.sort(keys,function(a,b)
        local x,y=type(map[a])=='table' and map[a].next_retry or 0,type(map[b])=='table' and map[b].next_retry or 0
        if x~=y then return x<y end
        return a<b
    end)
    for i=1,#keys do if count<=HISTORY_MAX then break end;map[keys[i]]=nil;count=count-1 end
end
local function trial_job(j)return type(j)=='table' and type(j.bundle)=='table' and _G.OTA_TRIAL_MD5~=nil and j.bundle.md5==_G.OTA_TRIAL_MD5 and j.version==_G.OTA_TRIAL_TARGET end
local function io_get(s)local r=s.io2;if type(r)=='table' and s.job and r.id==s.job.id then return r.v end end
local function io_n(s)local r=s.io2;return type(r)=='table' and s.job and r.id==s.job.id and r.n or 0 end
local function io_set(n,v,rearm)if not (type(n.io2)=='table' and n.io2.id==n.job.id) then n.io2={id=n.job.id,n=0} end;n.io2.v=v;if rearm then n.io2.n=n.io2.n+1 end end
-- Spend the live install-only state. The trial ticket is spent only before GR is done; afterwards GR's side is final and the CAT1 component
-- is bounded by its own retries/re-arms (round 1: a CAT1-side fault spent the ticket and stranded the CAT1 component).
local function spend(n)local v=io_get(n);if v=='ARMED' or v=='RUNNING' then io_set(n,'SPENT') end
    if n.trial and n.trial.status=='RUNNING' and not (n.release and n.release.gr_done) then n.trial.status='SPENT' end end
local function call(port,name,...)
    if type(port[name])~="function" then return nil,"CAPABILITY_"..name end
    local ok,a,b=pcall(port[name],...)
    if not ok then return nil,"PORT_"..name end
    return a,b
end
function M.new(store,port,codec)
    local state,err=store:load()
    local function clone(v) return (codec.decode((codec.encode(v)))) end
    if not state then state={schema=1,phase="IDLE",outbox={},next_id=1,failures={},retries={}} end
    if type(state)=="table" and state.retries==nil then state.retries={} end
    local phases={IDLE=true,WAIT_GR=true,GR_GRANTED=true,PREPARING=true,PAUSED=true,PREPARED=true,
        WAIT_ACTIVATE=true,ACTIVATION_ISSUED=true,INSTALLING=true,RECOVERY_HOLD=true,COMPLETE_PENDING=true}
    local function valid_job(j)
        return type(j)=="table" and hex(j.id,64) and hex(j.hash,64) and
          (j.target=="CAT1" or j.target=="GR5526") and text(j.version,63) and text(j.source,63)
    end
    local function checkpoint_valid(d,j)
        if type(d)~="table" or not valid_job(j) or not uint(j.size) or j.size<1 or j.size>16777216 or
          not hex(j.md5,32) or d.sha256~=j.hash:lower() or d.md5~=j.md5:lower() or d.size~=j.size or
          (d.path~=candidate_paths.path(j.hash) and d.path~="/ota_candidate_"..j.hash:lower()..".part") or not uint(d.offset) or d.offset>d.size then return false end
        local tag=d.etag
        return (d.offset==0 and tag==nil) or (type(tag)=="string" and #tag>=2 and #tag<=256 and tag:match('^"[^"%c]*"$')~=nil)
    end
    local function valid_result(r,j)
        return type(r)=="table" and type(r.success)=="boolean" and text(r.version,63) and
          (not j or r.version==(r.success and j.version or j.source))
    end
    local function valid_proof(p,r)
        return type(p)=="table" and p.md5==r.command.Md5:lower() and p.manifest==r.manifest and
            uint(p.size) and p.size>=22 and p.size<=2097152 and type(p.etag)=="string" and
            #p.etag>=2 and #p.etag<=128 and p.etag:match('^"[^"%c]*"$')~=nil
    end
    local function valid_release(r)
        if type(r)~="table" or not hex(r.manifest,64) or not hex(r.gr_hash,64) or type(r.command)~="table" then return false end
        local c=r.command
        if c.MsgType~="otaMsg" or not text(c.CurrentVersion,64) or not text(c.TargetVersion,64) or
           not text(c.Address,1024) or not c.Address:match("^https?://") or not hex(c.Md5,32) or not uint(c.Time) or
           c.Force~=nil or c.OtaBatteryThreshold~=nil then return false end
        for _,k in ipairs({"gr_finished","gr_done","gr_cleaned","cat_finished","cat_done","cat_cleaned"}) do
            if type(r[k])~="boolean" then return false end
        end
        if (r.gr_done or r.gr_cleaned) and not r.gr_finished then return false end
        if r.cat_hash~=nil and (not hex(r.cat_hash,64) or not r.gr_done or not r.gr_cleaned) then return false end
        if (r.cat_finished or r.cat_done or r.cat_cleaned) and not r.cat_hash then return false end
        if (r.cat_done or r.cat_cleaned) and not r.cat_finished then return false end
        if r.cleanup_target~=nil and r.cleanup_target~="GR5526" and r.cleanup_target~="CAT1" then return false end
        if r.cleanup_target=="GR5526" and (not r.gr_finished or r.gr_cleaned) then return false end
        if r.cleanup_target=="CAT1" and (not r.cat_finished or r.cat_cleaned) then return false end
        if r.archive_proof~=nil and not valid_proof(r.archive_proof,r) then return false end
        return true
    end
    local function same_release(r,j)
        local c=r and r.command
        return c and type(j.bundle)=="table" and r.manifest==j.bundle.manifest_sha256 and
            c.CurrentVersion==j.source and c.TargetVersion==j.version and c.Address==j.url and
            c.Md5:lower()==j.bundle.md5
    end
    local function valid_state(v)
        if type(v)~="table" or v.schema~=1 or not phases[v.phase] or type(v.outbox)~="table" or
          type(v.failures)~="table" or type(v.retries)~="table" or not uint(v.next_id) or v.next_id<1 then return false end
        local v_phase,v_job,v_release,v_trial,v_download,v_epoch,v_retries,v_outbox=v.phase,v.job,v.release,v.trial,v.download,v.epoch,v.retries,v.outbox
        if v_phase=="IDLE" then
            if v_job~=nil or v_epoch~=nil or v_download~=nil then return false end
        else
            if not valid_job(v_job) then return false end
            if v_phase=="WAIT_GR" then if v_epoch~=nil then return false end
            elseif not uint(v_epoch) or v_epoch<1 then return false end
        end
        -- SAM | 2026-11-06 +08:00 | Keep the safety-wait budget bound to this durable GR owner; corrupt retry records fail closed.
        local a=v.activation_retry
        if a~=nil and (type(a)~='table' or not v_job or v_job.target~='GR5526' or a.id~=v_job.id or
            a.hash~=v_job.hash or a.version~=v_job.version or a.epoch~=v_epoch or not uint(a.count) or a.count>3 or
            not uint(a.next_retry) or type(a.waiting)~='boolean') then return false end
        if v.prepared_ack~=nil and type(v.prepared_ack)~="boolean" then return false end
        if v_release~=nil and not valid_release(v_release) then return false end
        if v_release and v_release.cleanup_target and v_phase~="IDLE" then return false end
        if v_job and v_job.bundle~=nil then
            if not same_release(v_release,v_job) or
               v_job.hash~=(v_job.target=="GR5526" and v_release.gr_hash or v_release.cat_hash) then return false end
        end
        if v.reason~=nil and not text(v.reason,256) then return false end
        if v_trial~=nil then
            local t=v_trial
            if type(t)~='table' or not hex(t.id,64) or not hex(t.hash,64) or not uint(t.epoch) or t.epoch==0 or
                not hex(t.md5,32) or (t.status~='ARMED' and t.status~='RUNNING' and t.status~='SPENT') then return false end
        end
        local r=v.io2
        if r~=nil and (type(r)~='table' or not hex(r.id,64) or not uint(r.n) or r.n>3 or
            (r.v~='ARMED' and r.v~='RUNNING' and r.v~='SPENT' and r.v~='FINISHED')) then return false end
        if v.result~=nil and not valid_result(v.result,v_job) then return false end
        if v_phase==K_COMPLETE_PENDING and not valid_result(v.result,v_job) then return false end
        if v_download~=nil and not checkpoint_valid(v_download,v_job) then return false end
        if v.native_release~=nil then
            local t=v.native_release
            if v_phase~="IDLE" or type(t)~="table" or not valid_job(t.job) or t.job.target~="CAT1" or
                not uint(t.epoch) or t.epoch<1 or not text(t.version,63) or
                (t.version~=t.job.source and t.version~=t.job.version) then return false end
        end
        for hash,count in pairs(v.failures) do if not hex(hash,64) or not uint(count) or count>3 then return false end end
        for hash,r in pairs(v_retries) do
            if not hex(hash,64) or type(r)~="table" or not uint(r.count) or r.count<1 or r.count>3 or
              not uint(r.next_retry) or type(r.permanent)~="boolean" then return false end
        end
        local length=0
        for k in pairs(v_outbox) do if not uint(k) or k<1 or k>8 then return false end;length=length+1 end
        local previous=0
        for i=1,length do
            local q=v_outbox[i]
            if type(q)~="table" or not uint(q.id) or q.id<=previous or q.id>=v.next_id or type(q.payload)~="table" then return false end
            previous=q.id;local p=q.payload
            if not uint(p.Time) then return false end
            if p.MsgType=="otaReplyMsg" then if p.otaReply~="success" and p.otaReply~="fail" then return false end
            elseif p.MsgType=="otaResultMsg" then
                if (p.Status~="success" and p.Status~="fail") or not text(p.Version,63) then return false end
            else return false end
        end
        return true
    end
    if not valid_state(state) then err=K_STATE_INVALID end
    local self={error=err}
    local install_armed_live=false -- install-only path armed in this boot (a reboot spends an ARMED state)
    local activate_wait=0
    -- SAM | 2026-11-06 +08:00 | A persisted wait is not a fresh QUERY response; never carry safety authorization across restart.
    local activation_query=false
    local activation_query_at
    local activation_safe_at
    local accepting=false
    local reconciled=state.phase=="IDLE" or state.phase=="WAIT_GR"
    local function commit(next)
        if self.error then return false,self.error end
        if not valid_state(next) then self.error=K_STATE_INVALID;return false,self.error end
        local ok,why=store:save(next)
        if not ok then self.error=why or "STORE_FAILED";return false,self.error end
        state=next;return true
    end
    local function append(next,payload)
        if #next.outbox>=8 or next.next_id>=0xffffffff then return false end
        next.outbox[#next.outbox+1]={id=next.next_id,payload=payload}
        next.next_id=next.next_id+1;return true
    end
    local function now() return call(port,"now") or 0 end
    local function send(op)
        if not state.job then return false end
        return call(port,"send_gr",{op=op,job=state.job.id,target=state.job.target,
          hash=state.job.hash,epoch=state.epoch or 0,phase=state.phase,version=op=="COMPLETE" and state.result.version or state.job.version,
          outcome=op=="COMPLETE" and (state.result.success and "success" or "fail") or nil,
          size=op=="REQUEST" and state.job.size or nil})
    end
    -- SAM | 2026-11-06 +08:00 | Only a known pre-install safety wait may retry; persist reservations before UART effects.
    local function activation_clock()
        local t=call(port,'now');if uint(t) and t>0 and t<=0xffffffff-30 then return t end
    end
    local function activation_query_send()
        local t=activation_clock()
        if activation_query and activation_query_at and t and t>=activation_query_at and t-activation_query_at<5 then return true end
        activation_safe_at=nil;activation_query=true;activation_query_at=t
        local ok,why=send('QUERY');if ok~=true then activation_query=false end;return ok,why
    end
    local function activation_due()
        local r=state.activation_retry
        if r.count>=3 then return false,'ACTIVATION_RETRY_LIMIT' end
        local t=activation_clock();if not t then return false,K_RETRY_CLOCK_UNAVAILABLE end
        if r.next_retry==0 then
            local n=clone(state);n.activation_retry.next_retry=t+30
            local ok,why=commit(n);return false,ok and K_RETRY_BACKOFF or why
        end
        if t<r.next_retry then return false,K_RETRY_BACKOFF end
        return true
    end
    local function reply_failure(reason)
        if self.error then return false,self.error end
        if accepting==true then return false,reason end
        if state.release and state.release.gr_done and not state.release.cat_finished then return false,reason end
        local n=clone(state)
        if not append(n,{MsgType="otaReplyMsg",otaReply="fail",Time=now()}) then return false,"OUTBOX_FULL" end
        local ok,why=commit(n);return false,ok and reason or why
    end
    function self:status()
        if self.error then return {error=self.error,phase="RECOVERY_HOLD"} end
        local s=clone(state)
        s.io=io_get(state);s.io_n=io_n(state)
        return s
    end
    -- Arms the CAT1 install-only path: the runtime rebuilds bundle/proof and a local receipt before asking GR; a commit-safe
    -- STATUS INSTALL_PENDING then starts the native install. At most 3 re-arms per job (io2.n), only from a stop.
    function self:arm_io()
        local j,r=state.job,state.release;local v,used=io_get(state),io_n(state)
        local stuck=state.phase=='INSTALLING' and v=='RUNNING' and used<3 and j and j.target=='CAT1' and call(port,'io_clear',clone(j))==true
        local g='';for _,x in ipairs({not self.error,v==nil or (v=='SPENT' and used<3) or stuck,state.phase=='RECOVERY_HOLD' or stuck,
            j and j.target=='CAT1' and j.bundle~=nil,r and r.gr_done and r.gr_cleaned,r and j and r.cat_hash==j.hash,call(port,'idle')==true}) do g=g..(x and 1 or 0) end
        if g~='1111111' then return false,'IO_SCOPE_'..g end
        local n=clone(state);n.phase='RECOVERY_HOLD';io_set(n,'ARMED',v~=nil)
        local ok,why=commit(n);if not ok then return false,why end
        install_armed_live=true;return self:reconcile()
    end
    function self:transport_fault(reason,hold)
        if self.error or not text(reason,256) then return false end
        if not hold and state.trial and state.trial.status=='SPENT' then return true end
        local n=clone(state);n.reason=reason
        spend(n)
        if hold then n.phase='RECOVERY_HOLD' elseif n.phase=='GR_GRANTED' or n.phase=='PREPARING' then n.phase='PAUSED' end
        return commit(n)
    end
    -- History keys from round 1 (R4/R6/t151 recovery). Nothing reads them; they only cost journal space (OTA_PRUNE).
    local legacy={'retired','r6_handoff','gr_recovery','gr_r4','gr_r5','gr_r6','gr_r7','cancelled','trial_prior',
        't151','t151_prior','t151r','t151n','t151i','t151k','t151kn','t151k2','t151k_reason','t151c'}
    function self:prune_history(dry)
        if self.error then return false,self.error end
        local old,n,any={},clone(state),false
        for _,k in ipairs(legacy) do if n[k]~=nil then old[k]=n[k];n[k]=nil;any=true end end
        if not any then if dry then return true,'' end;local ok,why=commit(n);if not ok then return false,why end;return true,'' end
        local text=(codec.encode(old));if type(text)~='string' then return false,'ENCODE' end
        if dry then return true,text end
        local ok,why=commit(n);if not ok then return false,why end
        return true,text
    end
    function self:component_complete(target,manifest)
        local r=state.release
        if self.error or not r or r.manifest~=manifest then return false end
        if target=="GR5526" then return r.gr_done end
        return target=="CAT1" and r.cat_done or false
    end
    function self:owns_bundle(manifest)
        local j,r=state.job,state.release
        local phase=state.phase
        return not self.error and reconciled and j~=nil and r~=nil and r.manifest==manifest and
            same_release(r,j) and uint(state.epoch) and state.epoch>0 and
            (phase=="GR_GRANTED" or phase=="PREPARING" or phase=="PAUSED" or phase=="PREPARED" or phase=="WAIT_ACTIVATE" or
            phase=="RECOVERY_HOLD" and j.target=='CAT1' and io_get(state)=='ARMED')
    end
    function self:owns_component(target,epoch,manifest)
        return self:owns_bundle(manifest) and state.job.target==target and state.epoch==epoch
    end
    function self:archive_verified(md5,size,etag,manifest)
        if not self:owns_bundle(manifest) then return false end
        local p=state.release.archive_proof
        return p~=nil and p.md5==md5 and p.size==size and p.etag==etag and p.manifest==manifest
    end
    function self:save_archive_proof(md5,size,etag,manifest)
        if not self:owns_bundle(manifest) then return false,"GR_OWNERSHIP_REQUIRED" end
        local proof={md5=md5,size=size,etag=etag,manifest=manifest}
        if not valid_proof(proof,state.release) then return false,"ARCHIVE_PROOF_INVALID" end
        if self:archive_verified(md5,size,etag,manifest) then return true end
        local n=clone(state);n.release.archive_proof=proof;return commit(n)
    end
    function self:pending_cleanup()
        if self.error or state.phase~="IDLE" or not state.release then return nil end
        local r=state.release
        if r.gr_finished and not r.gr_cleaned then return {target="GR5526",hash=r.gr_hash} end
        if r.cat_finished and not r.cat_cleaned then return {target="CAT1",hash=r.cat_hash} end
    end
    function self:pending_native_release()
        if not self.error and state.native_release then return clone(state.native_release) end
    end
    function self:native_release_done(token)
        local t=state.native_release
        if self.error or not t or type(token)~="table" or type(token.job)~="table" or
            t.epoch~=token.epoch or t.version~=token.version then return false,"RELEASE_IDENTITY" end
        for _,key in ipairs({"id","hash","target","size","source","version"}) do
            if t.job[key]~=token.job[key] then return false,"RELEASE_IDENTITY" end
        end
        local n=clone(state);n.native_release=nil;return commit(n)
    end
    function self:reserve_cleanup(target,hash)
        if state.native_release then return false,K_NATIVE_RELEASE_PENDING end
        local c=self:pending_cleanup()
        if not c or c.target~=target or c.hash~=hash then return false,K_CLEANUP_IDENTITY end
        if state.release.cleanup_target==target then return true end
        local n=clone(state);n.release.cleanup_target=target;return commit(n)
    end
    function self:cleanup_done(target,hash)
        local c=self:pending_cleanup()
        if not c or c.target~=target or c.hash~=hash or state.release.cleanup_target~=target then return false,K_CLEANUP_IDENTITY end
        local n=clone(state);n.release[target=="GR5526" and "gr_cleaned" or "cat_cleaned"]=true
        n.release.cleanup_target=nil;return commit(n)
    end
    function self:next_command()
        local r=state.release
        if not self.error and state.phase=="IDLE" and r and r.gr_done and r.gr_cleaned and not r.cat_finished and not r.cleanup_target then
            return clone(r.command)
        end
    end
    function self:reboot_allowed()
        return not self.error and state.phase=="IDLE"
    end
    local function accept(cmd)
        if self.error then return false,self.error end
        if state.phase~="IDLE" then return false,"BUSY" end
        if state.native_release then return false,K_NATIVE_RELEASE_PENDING end
        if self:pending_cleanup() then return false,"RELEASE_CLEANUP_PENDING" end
        if #state.outbox>5 then return false,"OUTBOX_FULL" end
        if type(cmd)~="table" or cmd.MsgType~="otaMsg" or not text(cmd.CurrentVersion,64) or
           not text(cmd.TargetVersion,64) or not text(cmd.Address,1024) or not cmd.Address:match("^https?://") or
           not hex(cmd.Md5,32) or not uint(cmd.Time) or cmd.Force~=nil or cmd.OtaBatteryThreshold~=nil then
            return reply_failure("COMMAND_INVALID")
        end
        local release=state.release
        if release and release.gr_done and not release.cat_finished then
            local c=release.command
            if c.CurrentVersion~=cmd.CurrentVersion or c.TargetVersion~=cmd.TargetVersion or c.Address~=cmd.Address or c.Md5:lower()~=cmd.Md5:lower() then
                return false,"BUNDLE_SEQUENCE_BUSY"
            end
            local clock=call(port,"now");local retry=state.retries[release.manifest]
            if not uint(clock) or clock<1 or clock>0xffffffff-120 then return false,K_RETRY_CLOCK_UNAVAILABLE end
            if retry and (retry.permanent or retry.count>=3) then return false,K_FAILED_HASH_LIMIT end
            if retry and clock<retry.next_retry then return false,K_RETRY_BACKOFF end
            local n=clone(state);local count=retry and retry.count+1 or 1
            n.retries[release.manifest]={count=count,next_retry=clock+30*2^(count-1),permanent=false}
            trim(n.retries,{[release.manifest]=true})
            local ok,why=commit(n);if not ok then return false,why end
        end
        local job,why=call(port,"resolve",clone(cmd))
        if not valid_job(job) then return reply_failure(why or "RELEASE_MAPPING_UNAVAILABLE") end
        job=clone(job);job.hash=job.hash:lower();job.id=job.id:lower()
        -- Resolve/validate are trusted release ports, never fields supplied by the untrusted OTA command.
        local ok,reason=call(port,"validate",job,cmd)
        if ok~=true then return reply_failure(reason or K_RELEASE_NOT_VERIFIED) end
        local compared=call(port,"compare",job.version,job.source)
        if type(compared)~="number" or compared<=0 then return reply_failure("VERSION_NOT_NEWER") end
        if (state.failures[job.hash] or 0)>=3 then return reply_failure(K_FAILED_HASH_LIMIT) end
        local retry=state.retries[job.hash]
        if retry and (retry.permanent or retry.count>=3) then return reply_failure(K_FAILED_HASH_LIMIT) end
        local n=clone(state);n.job=clone(job);n.phase="WAIT_GR";n.epoch=nil;n.result=nil;n.download=nil;n.prepared_ack=nil
        if job.bundle~=nil then
            if type(job.bundle)~="table" or not hex(job.bundle.manifest_sha256,64) or not hex(job.bundle.md5,32) or
               job.bundle.md5~=cmd.Md5:lower() or job.source~=cmd.CurrentVersion or job.version~=cmd.TargetVersion or job.url~=cmd.Address then
                return reply_failure("BUNDLE_JOB_INVALID")
            end
            local prior=state.release
            if prior and prior.gr_done and not prior.cat_finished and not same_release(prior,job) then return false,"BUNDLE_SEQUENCE_BUSY" end
            if prior and prior.gr_done and not prior.cat_finished and same_release(prior,job) and job.target=="GR5526" then return false,"GR_ALREADY_COMPLETE" end
            if prior and prior.cat_done and same_release(prior,job) then return false,"RELEASE_ALREADY_COMPLETE" end
            if job.target=="CAT1" then
                if not same_release(prior,job) or not prior.gr_done or not prior.gr_cleaned or
                   (prior.cat_hash and prior.cat_hash~=job.hash) then return false,"GR_COMPLETION_REQUIRED" end
                n.release.cat_hash=job.hash;n.release.cat_finished=false;n.release.cat_done=false;n.release.cat_cleaned=false
            else
                n.release={manifest=job.bundle.manifest_sha256,command={MsgType="otaMsg",CurrentVersion=cmd.CurrentVersion,
                    TargetVersion=cmd.TargetVersion,Address=cmd.Address,Md5=cmd.Md5,Time=cmd.Time},gr_hash=job.hash,
                    gr_finished=false,gr_done=false,gr_cleaned=false,cat_finished=false,cat_done=false,cat_cleaned=false}
            end
        elseif state.release and state.release.gr_done and not state.release.cat_finished then
            return false,"BUNDLE_SEQUENCE_BUSY"
        end
        ok,why=commit(n);if not ok then return false,why end
        send("REQUEST");return true,"PENDING_GR"
    end
    function self:accept(cmd,automatic)
        if accepting then return false,"BUSY" end
        accepting=automatic or 1
        local returned,ok,why=pcall(accept,cmd)
        if not returned then accepting=false;self.error="ACCEPT_FAILED";return false,self.error end
        accepting=false
        return ok,why
    end
    function self:prepare()
        if self.error then return false,self.error end
        if state.phase~="GR_GRANTED" and state.phase~="PAUSED" then return false,"PHASE" end
        if state.trial and state.trial.status=='SPENT' then return false,'TRIAL_SPENT' end
        if not reconciled then send("QUERY");return false,K_GR_RECONCILE_REQUIRED end
        if call(port,"idle")~=true then return false,"BUSINESS_BUSY_OR_UNKNOWN" end
        if call(port,"validate",state.job)~=true then return false,K_RELEASE_NOT_VERIFIED end
        local trial=state.trial
        if trial then
            if trial.status=='SPENT' then return false,'TRIAL_SPENT' end
            local j=state.job
            local same=j.id==trial.id and j.hash==trial.hash and state.epoch==trial.epoch
            local nextcat=j.target=='CAT1' and j.bundle and j.bundle.md5==trial.md5 and state.release and
                state.release.gr_hash==trial.hash and state.release.gr_done and state.release.gr_cleaned and trial.status=='RUNNING'
            if not same and not nextcat then return false,'TRIAL_SCOPE' end
        end
        if type(port.space)=='function' then
            local ok,why=call(port,'space',clone(state.job));if ok~=true then return false,why or K_COMPONENT_SPACE end
        end
        local hash=state.job.hash
        local prior=state.retries[hash]
        local clock=call(port,"now")
        local clock_valid=uint(clock) and clock>0 and clock<=0xffffffff-120
        if prior then
            if prior.count>=3 then return false,K_FAILED_HASH_LIMIT end
            if prior.permanent then
                if state.reason=='GR_NACK_7' and state.job.target=='GR5526' then
                    local n=clone(state);n.retries[hash].permanent=false
                    local ok,why=commit(n);return false,ok and 'GR_PERMISSION_RETRY_ARMED' or why
                end
                return false,K_FAILED_HASH_LIMIT
            end
            if not clock_valid then return false,K_RETRY_CLOCK_UNAVAILABLE end
            if prior.next_retry==0 then
                local n=clone(state);n.retries[hash].next_retry=clock+30*2^(prior.count-1)
                local ok,why=commit(n);return false,ok and K_RETRY_BACKOFF or why
            end
            if clock<prior.next_retry then return false,K_RETRY_BACKOFF end
        end
        local n=clone(state);n.phase="PREPARING"
        if n.trial then n.trial.status="RUNNING" end
        local count=(prior and prior.count or 0)+1
        n.retries[hash]={count=count,next_retry=(clock_valid and clock+30*2^(count-1) or 0),permanent=false}
        trim(n.retries,{[hash]=true})
        local ok,why=commit(n);if not ok then return false,why end
        local prepared,reason=call(port,"prepare",clone(state.job))
        local idle=call(port,"idle")==true
        local verified=prepared==true and idle and call(port,"verify_candidate",state.job)==true
        if self.error or state.phase~="PREPARING" or state.job.hash~=hash then return false,self.error or K_STATE_CHANGED end
        n=clone(state)
        if not verified then
            if prepared==true then reason=idle and "CANDIDATE_VERIFICATION_FAILED" or "BUSINESS_BUSY_OR_UNKNOWN"
            elseif reason==nil and not idle then reason="BUSINESS_BUSY_OR_UNKNOWN" end
            reason=reason or "PREPARE_NOT_VERIFIED"
            n.phase="PAUSED";n.reason=reason
            if TRANSIENT[reason] then n.retries[hash]=prior
            elseif not RETRYABLE[reason] then n.retries[hash].permanent=true end
            if n.trial and not TRANSIENT[reason] and not net_reason(reason) and not (n.release and n.release.gr_done) then n.trial.status='SPENT' end
            ok,why=commit(n);return false,ok and reason or why
        end
        n.retries[hash]=prior
        n.phase="PREPARED";n.reason=nil;n.prepared_ack=false
        ok,why=commit(n);if ok then send("PREPARED") end;return ok,why
    end
    function self:save_download(checkpoint)
        if self.error then return false,self.error end
        if state.phase~="PREPARING" then return false,"PHASE" end
        if not checkpoint_valid(checkpoint,state.job) then return false,"CHECKPOINT_INVALID" end
        local old=state.download
        if old and (checkpoint.offset<old.offset or checkpoint.offset-old.offset>16384 or
          (old.etag~=nil and checkpoint.etag~=old.etag)) then return false,"CHECKPOINT_REGRESSION" end
        if not old and checkpoint.offset>16384 then return false,"CHECKPOINT_GAP" end
        local n=clone(state);n.download=clone(checkpoint);return commit(n)
    end
    function self:request_activation()
        if self.error then return false,self.error end
        if state.phase~="PREPARED" then return false,"PHASE" end
        -- SAM | 2026-11-06 +08:00 | Retrying needs a new matching safe STATUS plus the runtime's fresh local safety gate.
        local r=state.activation_retry
        if r then
            if not r.waiting then return false,'ACTIVATION_RECONCILE_REQUIRED' end
            if state.trial and state.trial.status=='SPENT' then return false,'TRIAL_SPENT' end
            local due,why=activation_due();if not due then return false,why end
            local t=activation_clock()
            if not reconciled or not activation_safe_at or not t or t<activation_safe_at or t-activation_safe_at>=3 then
                activation_query_send();return false,K_GR_RECONCILE_REQUIRED
            end
        end
        if not reconciled then send("QUERY");return false,K_GR_RECONCILE_REQUIRED end
        if state.prepared_ack~=true then send("PREPARED");return false,"PREPARED_NOT_ACKNOWLEDGED" end
        -- The matching GR PREPARED receipt retains the verified candidate; do not restart download/restore here.
        local original=state
        local safe=call(port,"safe")==true
        if self.error or state~=original then return false,self.error or K_STATE_CHANGED end
        if not safe then return false,"UNSAFE_OR_UNKNOWN" end
        if r then
            local t=activation_clock()
            if not t or not activation_safe_at or t<activation_safe_at or t-activation_safe_at>=3 then
                activation_query_send();return false,K_GR_RECONCILE_REQUIRED
            end
        end
        local n=clone(state);n.phase="WAIT_ACTIVATE"
        if r then n.activation_retry.count=r.count+1;n.activation_retry.waiting=false end
        local ok,why=commit(n)
        if ok then activation_query=false;activation_safe_at=nil;send("ACTIVATE") end;return ok,why
    end
    function self:on_gr(msg)
        if self.error then return false,self.error end
        local j=state.job
        if type(msg)~="table" or not j or msg.job~=j.id or msg.hash~=j.hash or msg.target~=j.target or
          not uint(msg.epoch) then return false,"IDENTITY" end
        if (msg.op=="GRANT" or msg.op=="STATUS") and state.phase=="WAIT_GR" and msg.phase=="DOWNLOADING" and msg.epoch>0 and msg.version==j.version then
            local n=clone(state);n.epoch=msg.epoch;n.phase="GR_GRANTED"
            if j.target=='GR5526' and trial_job(j) and not (n.trial and n.trial.id==j.id and n.trial.epoch==msg.epoch) then
                n.trial_prior=n.trial_prior or n.trial;n.trial={id=j.id,hash=j.hash,epoch=msg.epoch,md5=j.bundle.md5,status='ARMED'}
            end
            if not (j.bundle and j.target=="CAT1") and
               not append(n,{MsgType="otaReplyMsg",otaReply="success",Time=now()}) then return false,"OUTBOX_FULL" end
            local ok,why=commit(n);if ok then reconciled=true end;return ok,why
        end
        if msg.op=="DENY" and state.phase=="WAIT_GR" then
            -- A deny is not proof of no durable owner after a lost GRANT. Query before clearing the job.
            local n=clone(state);n.reason=text(msg.reason,256) and msg.reason or "GR_DENIED"
            local ok,why=commit(n);if ok then send("QUERY") end;return ok,why
        end
        if msg.epoch~=state.epoch then return false,"EPOCH" end
        if msg.op=='DENY' and state.phase=='WAIT_ACTIVATE' and msg.version==j.version and
            (msg.phase=='PREPARED' or msg.phase=='INSTALL_PENDING') and text(msg.reason,256) then
            -- SAM | 2026-11-06 +08:00 | This explicit PREPARED denial proves no install was committed; other denials still spend/hold.
            if j.target=='GR5526' and msg.phase=='PREPARED' and msg.reason=='activation_safe_wait' and
                io_get(state)==nil and not (state.trial and state.trial.status=='SPENT') then
                local prior=state.activation_retry
                if prior and prior.waiting then return true end
                local t=activation_clock();local n=clone(state);n.reason=msg.reason
                n.activation_retry={id=j.id,hash=j.hash,version=j.version,epoch=state.epoch,
                    count=prior and prior.count or 0,next_retry=t and t+30 or 0,waiting=true}
                local ok,why=commit(n);if not ok then return false,why end
                activation_query=false;activation_safe_at=nil;reconciled=false
                if n.activation_retry.count<3 then activation_query_send() end
                return true
            end
            -- GR 1.5.1 can deny its own commit (stale motion sample after the Boot journal write) while B is complete.
            -- Its INSTALL_PENDING resume commits without that write, so one re-ACTIVATE is armed; reconcile sends it.
            if j.target=='GR5526' and not state.activation_retry and msg.reason=='boot_commit_failed' and msg.phase=='INSTALL_PENDING' and io_get(state)==nil then
                local n=clone(state);n.reason=msg.reason;io_set(n,'ARMED');activate_wait=0;return commit(n)
            end
            return self:transport_fault(msg.reason,true)
        end
        if msg.op=="STATUS" and msg.phase~="COMPLETE" then
            if msg.version~=j.version then return false,"VERSION" end
            -- SAM | 2026-11-06 +08:00 | A late PREPARED reply after a reserved retry is ambiguous, never permission to activate again.
            local retry=state.activation_retry
            if retry and (msg.phase~='PREPARED' or msg.reason~='ok' or msg.commit_safe~=true) then activation_safe_at=nil end
            if retry and msg.phase=='PREPARED' and (state.phase=='WAIT_ACTIVATE' or state.phase=='PREPARED') then
                if not retry.waiting then return self:transport_fault('ACTIVATION_STATUS_REQUIRES_RECOVERY',true) end
                if retry.count>=3 then return true end
                if not activation_query or msg.reason~='ok' or msg.commit_safe~=true then return true end
                local n=clone(state);n.phase='PREPARED';n.prepared_ack=true
                local ok,why=commit(n)
                if ok then reconciled=true;activation_safe_at=activation_clock();activation_query=false end
                return ok,why
            end
            if state.phase=='WAIT_ACTIVATE' and io_get(state)=='RUNNING' and
                (msg.phase=='PREPARED' or msg.phase=='DOWNLOADING') then
                return self:transport_fault('INSTALL_RECOVERY_STALE_STATUS',true)
            end
            if msg.phase=="INSTALL_PENDING" then
                if state.phase=='RECOVERY_HOLD' and io_get(state)=='ARMED' and install_armed_live then
                    if j.target=='CAT1' and call(port,'install_recovery_ready',clone(j),state.epoch)~=true then reconciled=true;return true end
                    -- GR not commit-safe yet: wait (the runtime keeps querying, bounded by IO_TIMEOUT).
                    if msg.reason~='ok' or msg.commit_safe~=true then reconciled=true;return true end
                    local g=''
                    for _,v in ipairs({msg.reason=='ok',msg.commit_safe==true,call(port,'idle')==true,
                        call(port,'install_recovery_ready',clone(j),state.epoch)==true,call(port,'safe')==true}) do g=g..(v and 1 or 0) end
                    if g~='11111' then
                        self:transport_fault('INSTALL_RECOVERY_GATE_'..g,true);return false,'IO_GATE'
                    end
                    if j.target=='CAT1' then
                        local n=clone(state);n.phase='ACTIVATION_ISSUED';io_set(n,'RUNNING')
                        local ok,why=commit(n);if not ok then return false,why end
                        reconciled=true
                        local started,reason=call(port,'activate',clone(j),state.epoch)
                        if self.error or state.phase~='ACTIVATION_ISSUED' then return false,self.error or K_STATE_CHANGED end
                        n=clone(state);n.phase=started==true and 'INSTALLING' or 'RECOVERY_HOLD'
                        n.reason=nil;if started~=true then n.reason=reason or 'INSTALL_STATE_UNKNOWN' end
                        if started~=true then io_set(n,'SPENT') end
                        return commit(n)
                    end
                    return false,'IO_GATE'
                end
                -- Inside a re-ACTIVATE wait a STATUS is a late reply to an earlier QUERY, not a lost activation (board 10-29 22:44).
                if state.phase=='WAIT_ACTIVATE' and (io_get(state)=='RUNNING' or io_get(state)=='ARMED') and msg.op=='STATUS' then return true end
                -- The single re-ACTIVATE of a GR job that never got it (held, or rebooted while armed).
                if j.target=='GR5526' and not state.activation_retry and state.phase=='RECOVERY_HOLD' and io_n(state)==0 and io_get(state)~='RUNNING' and io_get(state)~='FINISHED' and
                    msg.op=='STATUS' and msg.reason=='ok' and msg.commit_safe==true and (state.reason=='ACTIVATION_STATUS_REQUIRES_RECOVERY' or
                    state.reason=='INSTALL_RECOVERY_INTERRUPTED' or state.reason=='boot_commit_failed') then
                    local n=clone(state);n.phase='WAIT_ACTIVATE';io_set(n,'RUNNING',true);activate_wait=0
                    local ok,why=commit(n);if ok then reconciled=true;send('ACTIVATE') end;return ok,why
                end
                if state.phase==K_COMPLETE_PENDING then return send("COMPLETE") end
                if state.phase=="INSTALLING" or state.phase=="ACTIVATION_ISSUED" or state.phase=="RECOVERY_HOLD" then return true end
                local n=clone(state);n.phase="RECOVERY_HOLD";n.reason="ACTIVATION_STATUS_REQUIRES_RECOVERY"
                if io_get(n)=='RUNNING' then spend(n) end
                return commit(n)
            end
            if msg.phase=="DOWNLOADING" then
                if state.phase=="GR_GRANTED" or state.phase=="PAUSED" then reconciled=true;return true end
                if state.phase=="PREPARING" and not reconciled then
                    local n=clone(state);n.phase="PAUSED"
                    local ok,why=commit(n);if ok then reconciled=true end;return ok,why
                end
                if state.phase=="PREPARED" or state.phase=="WAIT_ACTIVATE" then
                    if call(port,"validate",j)~=true or call(port,"verify_candidate",j)~=true then return false,K_RELEASE_NOT_VERIFIED end
                    return send("PREPARED")
                end
            elseif msg.phase=="PREPARED" and (state.phase=="PREPARED" or state.phase=="WAIT_ACTIVATE") then
                local n=clone(state);n.phase="PREPARED";n.prepared_ack=true
                local ok,why=commit(n);if ok then reconciled=true end;return ok,why
            end
            return false,"STATUS_PHASE"
        end
        if msg.op=="GRANT" and msg.phase=="INSTALL_PENDING" and state.phase=="WAIT_ACTIVATE" then
            if msg.version~=j.version then return false,"VERSION" end
            -- CAT1: GR now owns the CAT1 install and never grants it twice; its GRANT commit_safe is unreliable on GR 1.5.1,
            -- so the install goes through the install-only path instead of starting here.
            if j.target=='CAT1' and j.bundle then
                local n=clone(state);n.phase='RECOVERY_HOLD';n.reason='CAT1_INSTALL_ARMED';io_set(n,'ARMED')
                local ok,why=commit(n);if not ok then return false,why end
                install_armed_live=true;reconciled=true;return true
            end
            local original=state;local n=clone(state)
            local verified=call(port,"safe")==true and call(port,"validate",j)==true and call(port,"verify_candidate",j)==true
            if self.error or state~=original then return false,self.error or K_STATE_CHANGED end
            if not verified then
                n.phase="RECOVERY_HOLD";n.reason="ACTIVATION_RECHECK_FAILED"
                if io_get(n)=='RUNNING' then spend(n) end
                commit(n);return false,n.reason
            end
            -- Persist before any call that may install or reboot; after a crash never repeat blindly.
            n.phase="ACTIVATION_ISSUED"
            local ok,why=commit(n);if not ok then return false,why end
            local started,reason=call(port,"activate",clone(j),state.epoch)
            if self.error or state.phase~="ACTIVATION_ISSUED" then return false,self.error or K_STATE_CHANGED end
            n=clone(state);n.phase=started==true and "INSTALLING" or "RECOVERY_HOLD"
            n.reason=nil;if started~=true then n.reason=reason or "INSTALL_STATE_UNKNOWN" end
            return commit(n)
        end
        if j.target=="GR5526" and (msg.op=="RELEASED" or msg.op=="STATUS") and msg.phase=="COMPLETE" and
            (state.phase=="WAIT_ACTIVATE" or state.phase=="ACTIVATION_ISSUED" or state.phase=="INSTALLING" or state.phase=="RECOVERY_HOLD") then
            local success=msg.outcome=="success"
            if (not success and msg.outcome~="fail") or msg.version~=(success and j.version or j.source) then return false,"RESULT_IDENTITY" end
            local n=clone(state)
            if not (j.bundle and success) and
               not append(n,{MsgType="otaResultMsg",Status=msg.outcome,Version=msg.version,Time=now()}) then return false,"OUTBOX_FULL" end
            if not success then n.failures[j.hash]=math.min(3,(n.failures[j.hash] or 0)+1);trim(n.failures,{[j.hash]=true}) end
            local v=io_get(n)
            if v and (v=='RUNNING' or (success and v=='SPENT')) then
                io_set(n,success and 'FINISHED' or 'SPENT')
                if n.trial then n.trial.status=success and 'RUNNING' or 'SPENT' end
            end
            n.result={version=msg.version,success=success};n.phase=K_COMPLETE_PENDING
            local ok,why=commit(n);if not ok then return false,why end
        end
        if (msg.op=="RELEASED" or msg.op=="STATUS") and msg.phase=="COMPLETE" and state.phase==K_COMPLETE_PENDING then
            if msg.version~=state.result.version or msg.outcome~=(state.result.success and "success" or "fail") then return false,"RESULT_IDENTITY" end
            -- SAM | 2026-11-06 +08:00 | Retire safety-wait metadata only after this owner's durable terminal result.
            local n=clone(state);n.phase="IDLE";n.job=nil;n.epoch=nil;n.reason=nil;n.download=nil;n.result=nil;n.prepared_ack=nil;n.activation_retry=nil
            if j.target=="CAT1" then
                n.native_release={job=clone(j),epoch=state.epoch,version=state.result.version}
            end
            if j.bundle then
                local prefix=j.target=="GR5526" and "gr" or "cat"
                n.release[prefix.."_finished"]=true;n.release[prefix.."_done"]=state.result.success
                -- SAM | 2026-11-04 +08:00 | Whole release done (CAT1 after GR): its retry/failure entries have no further use, nor has any
                -- non-permanent retry (only a backoff for a job no longer in hand). Permanent ones (known-bad packages) stay, capped.
                if prefix=="cat" and state.result.success then
                    local r=n.release
                    for _,k in ipairs({r.manifest,r.gr_hash,r.cat_hash}) do n.retries[k]=nil;n.failures[k]=nil end
                    for k,v in pairs(n.retries) do if not v.permanent then n.retries[k]=nil end end
                    trim(n.retries,{});trim(n.failures,{})
                end
            end
            return commit(n)
        end
        return false,"PHASE"
    end
    function self:finish(info)
        if self.error then return false,self.error end
        if state.phase~="INSTALLING" and state.phase~="ACTIVATION_ISSUED" and state.phase~="RECOVERY_HOLD" then return false,"PHASE" end
        if type(info)~="table" or info.healthy~=true or info.installation_verified~=true or info.data_ok~=true or
          not text(info.version,63) then return false,"NOT_CONFIRMED" end
        local success=info.version==state.job.version
        if not success and info.version~=state.job.source then return false,"VERSION_UNKNOWN" end
        local n=clone(state)
        if not (state.job.bundle and state.job.target=="GR5526" and success) and
           not append(n,{MsgType="otaResultMsg",Status=success and "success" or "fail",Version=info.version,Time=now()}) then
            return false,"OUTBOX_FULL"
        end
        if not success then n.failures[n.job.hash]=(n.failures[n.job.hash] or 0)+1;trim(n.failures,{[n.job.hash]=true}) end
        n.result={version=info.version,success=success};n.phase=K_COMPLETE_PENDING
        local ok,why=commit(n);if ok then send("COMPLETE") end;return ok,why
    end
    function self:ack(id,broker_confirmed)
        if self.error or broker_confirmed~=true then return false,"NOT_DELIVERED" end
        if not state.outbox[1] or state.outbox[1].id~=id then return false,"OUTBOX_ID" end
        local n=clone(state);table.remove(n.outbox,1);return commit(n)
    end
    function self:reconcile()
        if self.error then return false,self.error end
        -- SAM | 2026-11-06 +08:00 | Known safety waits query only after backoff; exhausted budgets stay held without a send loop.
        local retry=state.activation_retry
        if retry and retry.waiting and (state.phase=='WAIT_ACTIVATE' or state.phase=='PREPARED') then
            local due,why=activation_due()
            if not due then return not self.error,why end
            return activation_query_send()
        end
        -- Armed GR re-ACTIVATE: sent ~5 ticks after the DENY. While RUNNING no QUERY is sent (GR is validating/leasing),
        -- bounded to ~180 ticks.
        if state.phase=='WAIT_ACTIVATE' and io_get(state)=='ARMED' then
            activate_wait=activate_wait+1;if activate_wait<5 then return true end
            local n=clone(state);io_set(n,'RUNNING');activate_wait=0
            local ok,why=commit(n);if ok then send('ACTIVATE') end;return ok,why
        end
        if state.phase=='WAIT_ACTIVATE' and io_get(state)=='RUNNING' then
            activate_wait=activate_wait+1
            if activate_wait<=180 then return true end
            activate_wait=0;return self:transport_fault('INSTALL_RECOVERY_ACTIVATE_TIMEOUT',true)
        end
        if state.phase=="WAIT_GR" then return send("REQUEST") end
        if state.phase==K_COMPLETE_PENDING then return send("COMPLETE") end
        if state.job then return send("QUERY") end
        return true
    end
    -- Boot rules: an armed or in-flight install-only state never survives a reboot; a GR-phase trial interrupted by a reboot is
    -- spent; an interrupted PREPARING resumes as PAUSED.
    if not err and (io_get(state)=='ARMED' or (io_get(state)=='RUNNING' and state.phase=='WAIT_ACTIVATE')) then
        local n=clone(state);spend(n)
        n.phase='RECOVERY_HOLD';n.reason='INSTALL_RECOVERY_INTERRUPTED';commit(n)
    end
    if not err and state.trial and state.trial.status=='RUNNING' and not (state.release and state.release.gr_done) and
        (state.phase=='PREPARING' or state.phase=='PAUSED' or state.phase=='GR_GRANTED') then
        local n=clone(state);n.trial.status='SPENT';commit(n)
    end
    -- Crash in PREPARING has no native activation permission. Keep the owner and re-verify candidate on resume.
    if not err and state.phase=="PREPARING" then
        local n=clone(state);n.phase="PAUSED"
        commit(n)
    end
    return self
end
return M
