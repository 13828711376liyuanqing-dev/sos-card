-- SAM | 2026-10-30 08:58 +08:00 | Short "quiet" UART leases requested by GR around its Flash writes (CAT1 must stay silent).
local wire=require('ota_wire')
local M={}
function M.new(io)
    local tx,waiting,hold,priority,failed,last
    local self={}
    local event,clock,write,idle=io.event,io.now,io.write,io.idle
    local function fault(reason)
        if not failed then
            failed=reason;if log then pcall(log.warn,'OTA_DIAG',reason) end
            event('OTA2_TX_FAILED',waiting and waiting.frame)
            event('OTA_UART_FAULT',reason)
        end
    end
    local function same(f,h)
        return h and f.session==h.session and f.sequence==h.sequence and f.payload==h.payload
    end
    local function answer(kind,h,status)
        local raw=wire.encode(kind,h.session,h.sequence,status or 0,h.payload)
        priority={raw=kind==243 and raw..raw or raw,kind=kind}
    end
    local function complete()
        if waiting and waiting.response and not tx then waiting=nil end
    end
    function self:blocked() return failed~=nil end
    function self:busy() return tx~=nil or waiting~=nil or hold~=nil or priority~=nil end
    function self:available() return not self:busy() end
    function self:owns(raw) return waiting and waiting.raw==raw or tx and tx.raw==raw end
    function self:hello()
        if failed and not hold and not tx and not priority then waiting=nil;return true end
        return false
    end
    function self:cancel()
        -- An in-flight transaction still needs its completion/release. Never reopen the physical UART here.
        if waiting then waiting.cancelled=true end
    end
    function self:sent()
        local done=tx;if not done then return end
        tx=nil
        if done.kind==244 then event("DFU_TX_SENT") end
        if done.kind==243 and same(wire.decode(done.raw:sub(1,44)),hold) then
            if hold.denied or failed then
                event('OTA2_TX_FAILED',waiting and waiting.frame);waiting=nil
                event('OTA_UART_FAULT','UART_QUIET_DENIED')
            end
            if waiting and not failed then waiting.at=clock() end
            last=hold;hold=nil
        elseif done.kind==241 and hold then hold.ack_sent=true
        elseif waiting and waiting.raw==done.raw then
            waiting.at=clock()
            if waiting.frame then event('OTA2_TX_SENT',waiting.frame) end
        end
        complete()
    end
    function self:write(raw,request,kind)
        if tx then return false end
        tx={raw=raw,at=clock(),kind=kind}
        if kind==241 and hold and hold.at==false then hold.at=tx.at end
        if request and not (request~=true and request.op=='ACTIVATE') then waiting={raw=raw,frame=wire.decode(raw),control=request~=true and request or nil} end
        local ok,n=pcall(write,raw)
        if not ok or n~=#raw then fault('UART_PARTIAL_OR_FAILED');return false end
        return true
    end
    -- SAM | 2026-11-01 +08:00 | Quiet lease limit 8 s -> 90 s: GR now commits the whole PSRAM-staged image to B inside one lease (~104 sectors).
    function self:pump()
        local now=clock()
        if tx and (now-tx.at)%0x100000000>2000 then fault('UART_SENT_TIMEOUT') end
        if not hold and waiting and waiting.at and not waiting.response and (now-waiting.at)%0x100000000>2000 then
            if not tx and (waiting.control and waiting.control.op=='QUERY' or waiting.frame and not waiting.cancelled) and not failed then waiting=nil
            else fault('UART_REPLY_TIMEOUT') end
        end
        if hold and hold.at and (now-hold.at)%0x100000000>90000 then fault('UART_QUIET_TIMEOUT') end
        -- Quiet ACK is the final CAT TX before Flash. It must follow completion of all previously submitted bytes.
        if not tx and priority then
            local p=priority;priority=nil
            self:write(p.raw,nil,p.kind)
        end
    end
    function self:on_frame(f)
        if f.type==240 or f.type==242 then
            if #f.payload~=16 or (f.type==240 and f.offset~=0) or f.offset>1 or f.session==0 or f.sequence==0 then return true end
            if f.type==240 then
                if hold and not same(f,hold) then fault('UART_QUIET_IDENTITY');return true end
                if not hold then
                    hold={session=f.session,sequence=f.sequence,payload=f.payload,at=false}
                    hold.denied=failed~=nil or (waiting and waiting.cancelled) or idle()~=true
                end
                if not hold.ack_sent then answer(241,hold,hold.denied and 1 or 0) end
            elseif same(f,hold) then
                if hold.at and (clock()-hold.at)%0x100000000>90000 then fault('UART_QUIET_TIMEOUT') end
                hold.at=nil
                hold.denied=hold.denied or f.offset==1
                answer(243,hold)
            elseif not hold and same(f,last) then answer(243,last) end
            return true
        end
        local q=waiting;local v=q and q.frame
        if v and f.session==v.session and f.sequence==v.sequence and f.offset==v.offset and #f.payload==16 and
           ((v.type==1 and f.type==2) or (v.type~=1 and (f.type==128 or f.type==129) and f.payload:byte(1)==v.type)) then
            q.response=true;complete()
        end
        return false
    end
    function self:on_control(f)
        local q=waiting;local v=q and q.control
        if not v or type(f)~='table' or f.job~=v.job or f.hash~=v.hash or f.target~=v.target then return end
        if v.op=='REQUEST' then
            if f.epoch==nil or f.epoch<1 or (f.op~='GRANT' and f.op~='STATUS' and f.op~='DENY') then return end
        elseif f.epoch~=v.epoch then return end
        local expected={QUERY='STATUS',PREPARED='STATUS',ACTIVATE='GRANT',COMPLETE='RELEASED',
            CAT_PROOF='PROOF_ACK',RESULT_QUERY='RESULT_CHALLENGE',CAT_RESULT='RESULT_ACK',REBOOT='REBOOT_GRANT',
            CANCEL_EMPTY='CANCELLED',RETIRE='RETIRED'}
        if f.op~='DENY' and f.op~=(expected[v.op] or 'STATUS') and not (v.op=='REQUEST' and f.op=='GRANT') then return end
        local phase={REQUEST='DOWNLOADING',PREPARED='PREPARED',ACTIVATE='INSTALL_PENDING',COMPLETE='COMPLETE',
            CANCEL_EMPTY='COMPLETE',RETIRE='COMPLETE',REBOOT='INSTALL_PENDING'}
        if f.op~='DENY' and phase[v.op] and f.phase~=phase[v.op] then return end
        if v.op=='CAT_PROOF' and f.op=='PROOF_ACK' and f.offset~=v.offset+#v.data/2 then return end
        if v.op=='REBOOT' and f.op=='REBOOT_GRANT' and f.ticket~=v.ticket then return end
        q.response=true;complete()
    end
    return self
end
return M
