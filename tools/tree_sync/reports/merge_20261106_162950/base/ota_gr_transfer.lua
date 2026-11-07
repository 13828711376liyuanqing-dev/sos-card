-- SAM | 2026-10-30 08:58 +08:00 | Streams a staged GR candidate to GR over the OTA2 binary UART protocol (ota_wire).
local wire = require("ota_wire")
local M={}
local function uint(v,max) return type(v)=='number' and v>=0 and v<=max and v%1==0 end
local function hex(v) return type(v)=='string' and #v==64 and not v:find('[^0-9a-f]') end
local function call(p,k,...)
    if type(p[k])~='function' then return nil end
    local ok,a=pcall(p[k],...);if ok then return a end
end
function M.new(p)
    assert(type(p)=='table')
    local phase,job,path,epoch,pending='IDLE'
    local offset,durable,sequence,attempts=0,0,0,0
    local error,paused
    local self={}
    local function fail(why) phase,error,pending='FAILED',why,nil;return false,why end
    local function same(j,e)
        return job and type(j)=='table' and j.target=='GR5526' and job.id==j.id and job.hash==j.hash and job.size==j.size and
            job.version==j.version and epoch==e
    end
    function self:start(j,file,e)
        if type(j)~='table' or j.target~='GR5526' or not hex(j.id) or not hex(j.hash) or
            not uint(j.size,442368) or j.size<912 or type(j.version)~='string' or
            not uint(e,0xffffffff) or e==0 or type(file)~='string' or #file>256 or #file==0 or file:find('%c') then
            return false,'GR_JOB_INVALID'
        end
        if same(j,e) then
            if file~=path then return false,'GR_PATH_CHANGED' end
            return phase~='FAILED',error
        end
        job={id=j.id,hash=j.hash,size=j.size,version=j.version};path,epoch=file,e
        phase,error,pending,offset,durable,sequence,attempts,paused='HELLO',nil,nil,0,0,0,0,false
        return true
    end
    function self:on_frame(f)
        local q=pending
        if not q or type(f)~='table' or f.session~=epoch or f.sequence~=q.sequence or
            f.offset~=q.offset or type(f.payload)~='string' or #f.payload~=16 then return false end
        if (q.kind==1 and f.type~=2) or (q.kind~=1 and f.type~=128 and f.type~=129) then return false end
        if q.response then return false end
        q.response=f;return true
    end
    local function matches(f)
        return pending and type(f)=='table' and f.session==epoch and f.sequence==pending.sequence and
            f.offset==pending.offset and f.type==pending.kind
    end
    function self:on_tx_sent(f)
        if not matches(f) or not pending.queued then return false end
        pending.queued=false;pending.sent_at=call(p,'now')
        pending.attempts=pending.attempts+1;attempts=pending.attempts;return true
    end
    function self:on_tx_failed(f)
        if not matches(f) then return false end
        return fail('GR_UART_TX_FAILED')
    end
    function self:ready(j,e) return phase=='VERIFIED' and same(j,e) end
    function self:pause()
        call(p,'cancel')
        pending,error,offset,durable,attempts=nil,nil,0,0,0
        phase=job and 'HELLO' or 'IDLE';paused=true
    end
    function self:status()
        return {phase=phase,reason=error,offset=offset,durable=durable,attempts=attempts}
    end
    local function response(q)
        local f=q.response
        if q.kind==1 then
            local chunk,sector,slot,features,open=string.unpack('<I2I2I4I4I4',f.payload)
            if chunk~=512 or sector~=4096 or slot<job.size or slot>442368 or features~=0 or open>1 then return fail('GR_CAPS_INVALID') end
            if open~=1 then return fail('GR_PORT_UNBOUND') end
            phase='BEGIN';return false,'DOWNLOAD_PENDING'
        end
        local kind,reason,flags,accepted,checkpoint,total=string.unpack('<BBI2I4I4I4',f.payload)
        if kind~=q.kind then return fail('GR_ACK_INVALID') end
        if f.type==129 then
            if reason==7 and q.attempts<3 then
                q.response=nil;q.sent_at=call(p,'now');pending=q
                return false,'DOWNLOAD_PENDING'
            end
            return fail('GR_NACK_'..tostring(reason))
        end
        if reason~=0 or flags>3 or (flags&1)==0 or total~=job.size or accepted>total or checkpoint>accepted or
            (checkpoint~=total and checkpoint%4096~=0) then return fail('GR_ACK_INVALID') end
        if q.kind==3 then
            -- A reboot/reconnect always resumes from durable; never skip RAM-only bytes.
            offset,durable=checkpoint,checkpoint;phase=offset==job.size and 'VERIFY' or 'DATA'
        elseif q.kind==4 then
            local next_offset=q.offset+#q.payload
            if accepted<next_offset or checkpoint<durable then return fail('GR_ACK_REGRESSION') end
            offset,durable=next_offset,checkpoint
            phase=offset==job.size and 'VERIFY' or 'DATA'
        elseif q.kind==6 then
            if accepted~=total or checkpoint~=total or (flags&2)==0 then return fail('GR_VERIFY_NOT_CONFIRMED') end
            offset,durable,phase=total,total,'VERIFIED';return true
        end
        return false,'DOWNLOAD_PENDING'
    end
    function self:step()
        if phase=='FAILED' then return false,error end
        if phase=='VERIFIED' then return true end
        if not job then return false,'GR_JOB_MISSING' end
        local now=call(p,'now')
        if not uint(now,0xffffffff) then return fail('GR_CLOCK_UNAVAILABLE') end
        if call(p,'idle')~=true then paused=true;return false,'BUSINESS_BUSY_OR_UNKNOWN' end
        if paused and pending then pending.sent_at=now end
        paused=false
        if pending and pending.response and not pending.queued then
            local q=pending;pending=nil
            return response(q)
        end
        if pending then
            if pending.queued then
                if (now-pending.queued_at)%0x100000000>=5000 then return fail('GR_UART_QUEUE_TIMEOUT') end
                return false,'DOWNLOAD_PENDING'
            end
            if call(p,'owns')==true then return false,'DOWNLOAD_PENDING' end
            if (now-pending.sent_at)%0x100000000<2000 then return false,'DOWNLOAD_PENDING' end
            if pending.attempts>=3 then return fail('GR_UART_TIMEOUT') end
        else
            local kind,payload,at=1,'',0
            if phase=='BEGIN' then
                kind=3;payload=string.pack('<I4',job.size)..job.hash:gsub('..',function(h)return string.char(tonumber(h,16))end)
            elseif phase=='DATA' then
                kind,at=4,offset
                payload=call(p,'read',path,at,math.min(512,job.size-at))
                if type(payload)~='string' or #payload~=math.min(512,job.size-at) then return fail('GR_CANDIDATE_READ') end
            elseif phase=='VERIFY' then kind=6 end
            local raw=wire.encode(kind,epoch,sequence,at,payload)
            if not raw then return fail('GR_FRAME_INVALID') end
            -- Register the pending identity before enqueue; a fast reply cannot be lost.
            pending={kind=kind,payload=payload,offset=at,sequence=sequence,raw=raw,attempts=0}
            sequence=sequence+1
        end
        local q=pending
        if p.track_tx then
            q.queued=true;q.queued_at=now
            if call(p,'send',q.raw)~=true then return fail('GR_UART_QUEUE_REJECTED') end
        else
            -- Explicit injected synchronous ports retain their existing completion contract.
            q.attempts=q.attempts+1;q.sent_at=now;attempts=q.attempts
            call(p,'send',q.raw)
        end
        return false,'DOWNLOAD_PENDING'
    end
    return self
end
return M
