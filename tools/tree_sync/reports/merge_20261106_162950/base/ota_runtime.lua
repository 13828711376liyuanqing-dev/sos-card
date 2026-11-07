-- SAM | 2026-10-30 08:58 +08:00 | Wires the manager to the device: download/bundle ports, GR UART transfer, CAT1 native FOTA, health monitor,
-- GR control lines (OTA_GR=...) and the 1 s tick that drives the manager. GR authority (gr_safety) is valid for 3 s only.
local candidate_paths=require("ota_candidates")
local M = {}
local singleton,started
local function invoke(port,name,...)
    if type(port[name])~="function" then return nil,"CAPABILITY_"..name end
    local ok,a,b=pcall(port[name],...)
    if not ok then return nil,"PORT_"..name end
    return a,b
end
function M.new(options)
    options=options or {}
    local codec=options.codec or json
    local base=options.port or require("ota_platform").default()
    local function business_idle() return invoke(base,'idle')==true end
    local manager
    local bundle_port,bundle_crypto_error,bundle_http_error
    if type(options.bundle_port)=="table" then
        bundle_port={}
        for k,v in pairs(options.bundle_port) do bundle_port[k]=v end
        if bundle_port.decode==nil and codec and type(codec.decode)=="function" then
            bundle_port.decode=codec.decode
        end
        local defaults={owns="owns_component",owns_bundle="owns_bundle",
            archive_verified="archive_verified",save_archive_proof="save_archive_proof"}
        for name,method in pairs(defaults) do
            if bundle_port[name]==nil then
                bundle_port[name]=function(...)
                    if not manager then return false end
                    return manager[method](manager,...)
                end
            end
        end
        local prior_completed=bundle_port.completed
        bundle_port.completed=function(target,manifest)
            if manager and manager:component_complete(target,manifest) then return true end
            if type(prior_completed)=="function" then return prior_completed(target,manifest) end
            return false
        end
        if bundle_port.http_get==nil and type(options.http_native)=="table" then
            local deps={}
            for k,v in pairs(options.http_native) do deps[k]=v end
            local native_gate=deps.can_read
            deps.can_read=function()
                return invoke(bundle_port,"can_read")==true and
                    (native_gate==nil or native_gate()==true)
            end
            local binding,why=require("ota_http_range").new(deps)
            if binding then bundle_port.http_get=binding.http_get;bundle_port.open_stream=binding.open_stream else bundle_http_error=why end
        end
        if type(bundle_port.verify_manifest)~="function" then
            local crypto_module=require("ota_crypto")
            local trust=require("ota_trust")
            local binding,why=crypto_module.new(crypto,rsa,codec,trust)
            if binding then for k,v in pairs(binding) do bundle_port[k]=v end
            else bundle_crypto_error=why end
        end
    end
    if options.port==nil and bundle_port and not bundle_http_error and not bundle_crypto_error then
        base=require("ota_platform").bundle(bundle_port,base)
    elseif options.port==nil and bundle_port then
        local why=bundle_http_error or bundle_crypto_error
        base.resolve=function()return nil,why end
    end
    local store_module=require("ota_store")
    local store=options.store or store_module.new(store_module.file_port(),codec)
    local port,down_port={},{}
    for k,v in pairs(base) do port[k]=v end
    local gr_safety,native_installer,reboot_request,install_receipt
    local native_code_identity='NOT_CHECKED'
    local health_monitor
    local prebusiness_read=false
    local bundle,bundle_id
    local reboot_ticket=0
    local result_query
    local function monotonic_ms()
        local ok,n=pcall(function() return mcu.ticks() end)
        if ok and type(n)=="number" and n>=0 and n<math.huge and n%1==0 then return n end
    end
    local function owner_matches(msg,status)
        local j=status.job
        return j and msg.job==j.id and msg.hash==j.hash and msg.target==j.target and
            msg.version==j.version and msg.epoch==status.epoch
    end
    local function fresh_safety()
        local s=manager and manager:status()
        local t=monotonic_ms()
        if not s or s.error or not business_idle() or not gr_safety or not t or
            t<gr_safety.at or t-gr_safety.at>=3000 or not owner_matches(gr_safety,s) then
            gr_safety=nil;return nil
        end
        return s
    end
    local function install_receipt_matches(job,epoch)
        local r=install_receipt
        return r and type(job)=='table' and type(job.bundle)=='table' and r.epoch==epoch and
            r.id==job.id and r.hash==job.hash and r.md5==job.md5 and r.size==job.size and
            r.source==job.source and r.version==job.version and r.url==job.url and
            r.bundle_md5==job.bundle.md5 and r.manifest==job.bundle.manifest_sha256 and business_idle()
    end
    if options.port==nil then
        port.safe=function()
            local s=fresh_safety();if not s then return false end
            if s.phase=="PREPARED" then return gr_safety.phase=="PREPARED" end
            if s.phase=='RECOVERY_HOLD' and s.io=='ARMED' then
                return gr_safety.op=='STATUS' and gr_safety.phase=='INSTALL_PENDING'
            end
            return s.phase=="WAIT_ACTIVATE" and gr_safety.op=="GRANT" and gr_safety.phase=="INSTALL_PENDING"
        end
    end
    -- SAM | 2026-11-04 +08:00 | OTA speed-up, enabled only by options.download_tuning (device options): chunk_size (A, component
    -- download step, checkpointed per chunk as before), scan_bytes (A, archive MD5 step), burst_ms (B, keep stepping
    -- within one tick while business stays idle). Absent = old 4KiB, one step per tick. Checks/install unchanged.
    local tuning=type(options.download_tuning)=='table' and options.download_tuning or {}
    local BURST_MS=tuning.burst_ms or 0
    if bundle_port and tuning.scan_bytes then bundle_port.scan_bytes=tuning.scan_bytes end
    local file_port=options.download_port
    if file_port==nil and bundle_port then file_port=require("ota_candidates").new(bundle_port) end
    for k,v in pairs(file_port or {}) do down_port[k]=v end
    -- SAM | 2026-11-04 +08:00 | Never exceed what the file port accepts per call (io_limit, else its own chunk_size).
    if tuning.chunk_size then down_port.chunk_size=math.min(tuning.chunk_size,down_port.io_limit or down_port.chunk_size or 4096) end
    local downloader,download_id,paused,inflight
    local cat_proof=require('ota_cat_proof').new({
        send=function(msg)return invoke(base,'send_gr',msg)end,
        now=monotonic_ms,can_send=function()
            return business_idle() and (paused~=true or (manager and manager:status().phase=='COMPLETE_PENDING'))
        end})
    local gr_transfer,gr_epoch,gr_running
    -- install-only path state (set up with the native installer below)
    local armed_since,rebuild_errors,rearm_ticks,last_write_error
    local take_reboot_base,take_install_base,has_install_base,native_owner,refresh_gr_safety
    if options.port==nil or type(options.gr_transfer_port)=="table" then
        local gr_port={
            track_tx=true,
            owns=function()return type(_G.ota_uart_owned)=='function' and _G.ota_uart_owned()==true end,
            idle=business_idle,
            now=monotonic_ms,
            send=function(raw) return type(_G.ota_uart_send)=="function" and _G.ota_uart_send(raw)==true end,
            cancel=function() return type(_G.ota_uart_cancel)=="function" and _G.ota_uart_cancel()==true end,
            read=function(path,offset,length)
                if not candidate_paths.allowed(path) then return nil end
                local f=io.open(path,"rb");if not f then return nil end
                local ok,data=pcall(function()
                    if f:seek("set",offset)~=offset then return nil end
                    return f:read(length)
                end)
                local closed,result=pcall(f.close,f)
                if ok and closed and result then return data end
            end,
        }
        for k,v in pairs(options.gr_transfer_port or {}) do gr_port[k]=v end
        gr_transfer=require("ota_gr_transfer").new(gr_port)
        base.stage_gr=function(job,path,epoch)
            local ok,why=gr_transfer:start(job,path,epoch)
            if not ok then return false,why end
            gr_epoch=epoch
            local done,reason=gr_transfer:step()
            gr_running=gr_transfer:status().phase~="FAILED" and not done
            return done,reason
        end
        base.candidate_ready=function(job) return gr_transfer:ready(job,gr_epoch) end
        port.stage_gr=base.stage_gr;port.candidate_ready=base.candidate_ready
        local activate_other=base.activate
        base.activate=function(job,epoch)
            if job.target=="GR5526" then
                return gr_transfer:ready(job,epoch)
            end
            if type(activate_other)=="function" then return activate_other(job,epoch) end
            return false,"CAPABILITY_activate"
        end
        port.activate=base.activate
    end
    if type(options.native_fota_port)=="table" then
        local native_port={}
        for k,v in pairs(options.native_fota_port) do native_port[k]=v end
        if options.port==nil then
            native_port.safe=function()
                local s=fresh_safety()
                return paused~=true and s~=nil and gr_safety.phase=="INSTALL_PENDING" and
                    (s.phase=="ACTIVATION_ISSUED" or s.phase=="INSTALLING")
            end
            native_port.owner=function(job,epoch)
                local s=manager and manager:status();local j=s and s.job
                if not j or s.error or epoch~=s.epoch or type(job)~="table" then return false end
                for _,key in ipairs({"id","hash","target","version","source","size"}) do
                    if j[key]~=job[key] then return false end
                end
                return j.target=="CAT1" and native_port.safe()
            end
            native_port.read=function(path,offset,length) return invoke(down_port,"read",path,offset,length) end
            native_port.reboot=function()
                if not native_port.safe() or not gr_safety or gr_safety.op~="REBOOT_GRANT" or
                    not rtos or type(rtos.reboot)~="function" then return false end
                rtos.reboot();return true -- Dispatch only; actual boot/health is confirmed later.
            end
            native_port.verify=function(job,path)
                if job.bundle then
                    if not native_port.owner(job,manager:status().epoch) or not bundle or bundle_id~=job.id or
                        bundle:summary().manifest_sha256~=job.bundle.manifest_sha256 or
                        bundle:summary().device_installable~=true or not cat_proof:ready(job,manager:status().epoch) or
                        path~=candidate_paths.path(job.hash) then return false end
                    local c=bundle:component('CAT1');local expected={size=job.size,sha256=job.hash,md5=job.md5}
                    local actual=invoke(down_port,'verify_file',path,expected)
                    return c and c.sha256==job.hash and c.size==job.size and c.md5==job.md5 and
                        type(actual)=='table' and actual.sha256==c.sha256 and actual.md5==c.md5 and actual.size==c.size and
                        native_port.owner(job,manager:status().epoch) and native_port.safe()
                end
                return native_port.owner(job,manager:status().epoch) and
                    path==candidate_paths.path(job.hash) and
                    port.verify_candidate(job)==true and native_port.safe()
            end
            if native_port.expected_identity==nil then
                native_port.expected_identity=function(job)
                    if bundle and bundle_id==job.id and bundle:summary().device_installable==true then
                        return bundle:cat_identity()
                    end
                end
            end
            if native_port.code_identity==nil then
                local scanner,scanner_key
                native_port.code_identity=function(expected)
                    local key=expected.manifest_sha256..expected.package_sha256..expected.build_record_sha256
                    if not scanner or scanner_key~=key then
                        local why
                        scanner,why=require('ota_boot_identity').new(expected,bundle_port,io,function()return prebusiness_read or business_idle() end)
                        if not scanner then return false,why end
                        scanner_key=key
                    end
                    local ok,why=scanner:step()
                    if ok and why=='VERIFIED' then return true end
                    return false,ok and 'BOOT_IDENTITY_CHECKING' or why
                end
            end
        end
        if native_port.load==nil and native_port.save==nil then
            local journal=require("ota_native_store").new(nil,codec)
            native_port.load=journal.load;native_port.save=journal.save
        end
        if options.port==nil and native_port.require_data_identity==true and native_port.data_snapshot==nil then
            native_port.data_snapshot=function(job,path,boot)
                return require('ota_data_inventory').transaction_snapshot(job,path,
                    boot and function()return true end or native_port.safe,boot,native_port.allow_unavailable_kv)
            end
        end
        if type(native_port.first_trial)=='table' then
            local reviewed=native_port.native_contract_verified
            native_port.native_contract_verified=function(job)
                if type(reviewed)=='function' and reviewed(job)==true then return true end
                return native_port.first_trial:install(job,invoke(native_port,'expected_identity',job))
            end
        end
        -- CAT1 install-only path. GR authority lasts 3 s, while a candidate rehash takes ~11-20 s and the user-data scan a few
        -- seconds, so that slow work is done before authority is requested (install_base, reboot_base) and reused inside the window.
        local install_base,reboot_base
        local function take_baseline(job)
            if native_port.require_data_identity~=true then return {} end
            return require('ota_data_inventory').transaction_snapshot(job,candidate_paths.path(job.hash),business_idle,false,native_port.allow_unavailable_kv)
        end
        -- Native start of an armed install-only attempt: receipt (rehashed candidate) and baseline already in hand.
        local function starting(job,epoch)
            local s=manager and manager:status()
            return s and s.io=='RUNNING' and s.phase=='ACTIVATION_ISSUED' and job.target=='CAT1' and install_receipt_matches(job,epoch) and
                install_base and install_base.id==job.id and install_base.epoch==epoch
        end
        local verify0,snap0,safe0=native_port.verify,native_port.data_snapshot,native_port.safe
        -- During the final-commit rehash/scan GR safety is replaced by business idle; a fresh GR STATUS is required right after.
        local relaxed
        native_port.safe=function() if relaxed then return business_idle() end;return safe0() end
        -- The last chunk of a native write (the commit recheck).
        local function final_commit(job)
            local s=manager and manager:status();return s and s.io=='RUNNING' and s.phase=='INSTALLING' and job.target=='CAT1' and
                native_installer and native_installer:status().phase=='WRITING'
        end
        local function refresh()
            local a0=gr_safety and gr_safety.at;manager:reconcile()
            for _=1,50 do if gr_safety and gr_safety.at~=a0 and fresh_safety() then return true end;sys.wait(50) end
            return false
        end
        native_port.verify=function(job,path)
            local e=manager:status().epoch
            if starting(job,e) then return path==candidate_paths.path(job.hash) and native_port.owner(job,e) and native_port.safe() end
            if final_commit(job) then
                relaxed=true;local c,ok=pcall(verify0,job,path);relaxed=nil
                return c and ok==true and refresh() and native_port.owner(job,e) and native_port.safe()
            end
            return verify0(job,path)
        end
        native_port.data_snapshot=function(job,path,boot)
            if not boot and starting(job,manager:status().epoch) then local d=install_base.d;install_base=nil;return d end
            if not boot and reboot_base and reboot_base.id==job.id and native_installer:status().phase=='COMMITTED' then local d=reboot_base.d;reboot_base=nil;return d end
            if not boot and final_commit(job) then
                relaxed=true;local c,d=pcall(snap0,job,path,boot);relaxed=nil
                return c and refresh() and d or nil
            end
            return snap0 and snap0(job,path,boot)
        end
        has_install_base=function(job,epoch)return install_base~=nil and install_base.id==job.id and install_base.epoch==epoch end
        native_owner=function(job,epoch)return native_port.owner(job,epoch) end
        refresh_gr_safety=refresh
        port.io_clear=function(job)return native_installer:clear_unwritten(job)end
        take_reboot_base=function(job)
            local d=take_baseline(job);reboot_base=d and {id=job.id,d=d} or nil;return d~=nil
        end
        take_install_base=function(job,epoch)
            local d=take_baseline(job);install_base=d and {id=job.id,epoch=epoch,d=d} or nil;return d~=nil
        end
        native_installer=require("ota_native_fota").new(native_port)
        if options.port==nil and base.health_default==true then
            health_monitor=require('ota_health').new({now=monotonic_ms,
                version=function()return _G.VERSION,_G.PRODUCT_VERSION,_G.FW_RELEASE_BUILD end,
                business=function()
                    return invoke(base,'business_status')
                end,
                native_status=function()return native_installer:status()end,
                code_identity=function()return native_code_identity end,
                data_evidence=native_port.require_data_identity==true and function(job,epoch)
                    return native_installer:data_evidence(job,epoch,monotonic_ms())
                end or native_port.data_evidence})
            base.health=function(job,epoch)return health_monitor:check(job,epoch)end
        end
        port.activate=function(job,epoch)
            if job.target~="CAT1" then return invoke(base,"activate",job,epoch) end
            if not downloader or download_id~=job.id or paused then return false,"CANDIDATE_UNAVAILABLE" end
            local path=downloader:status().path
            local ok,why=native_installer:start(job,path,epoch)
            if ok~=true and _G.ota_diag then
                local s,f=manager:status(),fresh_safety();local g=''
                for _,v in ipairs({f~=nil,paused~=true,gr_safety and gr_safety.phase=='INSTALL_PENDING',s.phase=='ACTIVATION_ISSUED',
                    install_receipt_matches(job,epoch),has_install_base and has_install_base(job,epoch),path==candidate_paths.path(job.hash),
                    native_owner and native_owner(job,epoch)}) do g=g..(v and 1 or 0) end
                _G.ota_diag('[OTA] START '..tostring(why)..' '..g)
            end
            return ok,why
        end
    end
    local prepared_poll=0
    local self={}
    local pause_generation=0;local resume_generation
    function self:observe_boot_data()
        if started or not native_installer then return false,'BOOT_WINDOW_CLOSED' end
        prebusiness_read=true
        local called,ok,why=pcall(native_installer.observe_boot_data,native_installer)
        prebusiness_read=false
        if not called then return false,'BOOT_DATA_READ_FAILED' end
        return ok,why
    end
    local function burst_open(t0)
        if BURST_MS<=0 then return false end
        local t=monotonic_ms()
        return t0~=nil and t~=nil and t-t0<BURST_MS and business_idle()
    end
    down_port.checkpoint=function(record)
        if not manager or type(manager.save_download)~="function" then return false end
        return manager:save_download(record)
    end
    port.install_recovery_ready=function(job,epoch)
        return not paused and install_receipt_matches(job,epoch)==true
    end
    if bundle_port then port.space=function(job)
        if bundle_http_error or bundle_crypto_error then return false,bundle_http_error or bundle_crypto_error end
        if not job.bundle then return true end
        local size=invoke(down_port,'size',candidate_paths.path(job.hash))
        local free=invoke(bundle_port,'free_bytes')
        return type(size)=='number' and size%1==0 and size>=0 and size<=job.size and
            type(free)=='number' and free%1==0 and free>=0 and free<=524288 and job.size-size+16384<=free,'COMPONENT_SPACE'
    end end
    local function restore(job)
        local active_port=down_port
        if job.bundle~=nil then
            local spec=job.bundle
            if type(spec)~="table" or type(spec.md5)~="string" or #spec.md5~=32 or spec.md5:find('[^0-9a-f]') or
                type(spec.manifest_sha256)~="string" or #spec.manifest_sha256~=64 or spec.manifest_sha256:find('[^0-9a-f]') then
                return false,"BUNDLE_JOB_INVALID"
            end
            if type(bundle_port)~="table" then return false,"BUNDLE_PORT_UNAVAILABLE" end
            if bundle_http_error then return false,bundle_http_error end
            if bundle_crypto_error then return false,bundle_crypto_error end
            if not bundle or bundle_id~=job.id then
                local request={url=job.url,md5=spec.md5,source_version=job.source,target_version=job.version}
                local candidate,why=require("ota_bundle").open(bundle_port,request)
                if not candidate and why=="HTTP_RANGE_REQUIRED" and type(bundle_port.open_stream)=="function" then
                    candidate,why=require("ota_seq_zip").open(bundle_port,request)
                end
                if not candidate then return false,why end
                local descriptor=candidate:component(job.target)
                if candidate:summary().manifest_sha256~=spec.manifest_sha256 or not descriptor or
                    descriptor.sha256~=job.hash or descriptor.md5~=job.md5 or descriptor.size~=job.size then
                    return false,"BUNDLE_JOB_MISMATCH"
                end
                bundle,bundle_id=candidate,job.id
            end
            local t0,checked,why=monotonic_ms()
            repeat
                checked,why=bundle:preflight_step()
                if not checked then return false,why end
            until why=="VERIFIED" or not burst_open(t0)
            -- A bounded whole-archive scan is normal progress, not a failed retry.
            if why~="VERIFIED" then return false,"DOWNLOAD_PENDING" end
            active_port,why=bundle:component_port(job.target,manager:status().epoch,down_port)
            if not active_port then return false,why end
        end
        downloader=require("ota_download").new(active_port)
        local candidate={}
        for k,v in pairs(job) do candidate[k]=v end
        candidate.sha256=job.hash
        local saved=manager:status()
        local ok,why=downloader:start(candidate,saved.download)
        if not ok then return false,why end
        download_id,paused=job.id,false
        return true
    end
    port.prepare=function(job)
        if not business_idle() then return false,"BUSINESS_BUSY_OR_UNKNOWN" end
        if not downloader or download_id~=job.id or paused then
            local ok,why=restore(job)
            if not ok then return false,why end
        end
        local status=downloader:status()
        local t0=monotonic_ms()
        while status.state=="DOWNLOADING" do
            local ok,why=downloader:step()
            if not ok then
                if bundle then bundle:close() end
                paused=true
                return false,why
            end
            status=downloader:status()
            if not burst_open(t0) then break end
        end
        if status.offset~=job.size then return false,"DOWNLOAD_PENDING" end
        local verified,why=downloader:verify()
        if not verified then paused=true;return false,why end
        if job.bundle and (not bundle or bundle:summary().device_installable~=true) then
            return false,"BUNDLE_NOT_INSTALLABLE"
        end
        if job.target=="GR5526" then
            return invoke(base,"stage_gr",job,status.path,manager:status().epoch)
        end
        if job.bundle then
            local ok,why=cat_proof:start(job,manager:status().epoch,bundle:cat_proof())
            if not ok then return false,why end
            return cat_proof:step()
        end
        return true
    end
    port.verify_candidate=function(job)
        if paused then return false end
        if not downloader or download_id~=job.id then
            if restore(job)~=true then return false end
        end
        if downloader:verify()~=true then return false end
        if job.bundle and (not bundle or bundle:summary().device_installable~=true) then return false end
        if job.target=="GR5526" then return invoke(base,"candidate_ready",job)==true end
        if job.bundle then return cat_proof:ready(job,manager:status().epoch) end
        return true
    end
    manager=require("ota_manager").new(store,port,codec)
    -- SAM | 2026-11-04 +08:00 | Beacon progress: V=whole-archive MD5 scan, D=component download, G=UART transfer to GR (bytes/total).
    function self:transfer_progress()
        local j=manager:status().job;if not j then return 'none' end
        if gr_transfer and j.target=='GR5526' then
            local g=gr_transfer:status()
            if g and (g.phase=='BEGIN' or g.phase=='DATA' or g.phase=='VERIFY' or g.phase=='VERIFIED') then
                return 'G'..tostring(g.durable)..'/'..tostring(j.size)
            end
        end
        if downloader and download_id==j.id then return 'D'..tostring(downloader:status().offset)..'/'..tostring(j.size) end
        if bundle and bundle_id==j.id then local p=bundle:preflight_status();return 'V'..tostring(p.offset)..'/'..tostring(p.size) end
        return 'none'
    end
    function self:native_diag()
        local n=native_installer and native_installer:status();if not n then return 'none' end
        return tostring(n.phase)..' '..tostring(n.recovery_phase)..' '..tostring(n.reason)..' '..tostring(n.offset)
    end
    function self:status()
        local status=manager:status()
        if status.job then
            status.progress={target=status.job.target,total=status.job.size,
                committed=status.download and status.download.offset or 0,step=self.last_tick_reason}
        end
        if native_installer then status.native_code_identity=native_code_identity end
        if health_monitor then status.native_health=health_monitor:status() end
        return status
    end
    for _,name in ipairs({'accept','ack','reboot_allowed','prune_history'}) do
        self[name]=function(_,a,b,c,d) return manager[name](manager,a,b,c,d) end
    end
    for _,name in ipairs({'arm_io'}) do self[name]=function(_,md5,which)
        if resume_generation~=nil then return false,'RECOVERY_BUSY' end
        resume_generation=pause_generation
        local ok,a,b=pcall(manager[name],manager,md5,which)
        resume_generation=nil
        if not ok then return false,'RECOVERY_ERROR' end
        return a,b
    end end

    function self:receive(topic,cmd,metas)
        if type(topic)~="string" or invoke(base,"accept_topic",topic)~=true then
            return false,"OTA_TOPIC_UNTRUSTED"
        end
        if type(metas)~="table" or (metas.retain~=false and metas.retain~=0) then
            return false,"OTA_RETAINED_OR_UNKNOWN"
        end
        return manager:accept(cmd)
    end

    function self:pause()
        pause_generation=pause_generation+1
        if health_monitor then health_monitor:reset('BUSINESS_PAUSED') end
        gr_safety=nil
        install_receipt=nil
        local s=manager and manager:status()
        if s and s.io=='ARMED' then manager:transport_fault('INSTALL_RECOVERY_INTERRUPTED',true) end
        reboot_request=nil
        result_query=nil
        paused=true
        if bundle then bundle:close() end
        if downloader then downloader:pause() end
        gr_running=false
        if gr_transfer then gr_transfer:pause() end
    end
    function self:uart_fault(reason)
        manager:transport_fault(reason);self:pause()
    end
    function self:uart_idle() return business_idle() and not (_G.business_uart_backlog and _G.business_uart_backlog()) end
    for _,name in ipairs({'on_tx_sent','on_tx_failed'}) do
        self[name]=function(_,frame) return gr_transfer and gr_transfer[name](gr_transfer,frame) end
    end
    function self:on_wire_frame(frame)
        return gr_transfer and gr_transfer:on_frame(frame) or false
    end
    function self:pump_gr()
        if not gr_transfer or not gr_running then return false end
        gr_transfer:step()
        local phase=gr_transfer:status().phase
        if phase=="VERIFIED" or phase=="FAILED" then gr_running=false end
        return gr_running
    end
    function self:on_gr_line(line)
        if type(line)~="string" or #line>1024 or line:sub(1,7)~="OTA_GR=" then return false,"FRAME" end
        local ok,msg=pcall(codec.decode,line:sub(8))
        if not ok or type(msg)~="table" then return false,"JSON" end
        if msg.op=='PROOF_ACK' then return cat_proof:on_reply(msg) end
        local current=manager:status()
        if msg.op=='RESULT_CHALLENGE' then
            local now=monotonic_ms()
            if not result_query or not now or now<result_query or now-result_query>3000 or
                current.phase~='COMPLETE_PENDING' or not owner_matches(msg,current) or msg.reason~='ok' or
                msg.phase~='INSTALL_PENDING' or type(msg.nonce)~='string' or #msg.nonce~=32 or
                msg.nonce:find('[^0-9a-f]') or not business_idle() or not native_installer then return false,'RESULT_CHALLENGE' end
            result_query=nil
            local report,why=native_installer:completion_report(current.job,current.epoch)
            if not report then return false,why end
            report.proof=nil;report.op='CAT_RESULT';report.nonce=msg.nonce
            report.job=current.job.id;report.hash=current.job.hash;report.target='CAT1'
            report.version=current.job.version;report.epoch=current.epoch
            return invoke(base,'send_gr',report)==true
        end
        if msg.op=='RESULT_ACK' then
            if current.phase~='COMPLETE_PENDING' or not owner_matches(msg,current) or msg.reason~='ok' then return false,'RESULT_IDENTITY' end
            return manager:reconcile()
        end
        if ((msg.op=='STATUS' and msg.reason=='ok') or (msg.op=='DENY' and
            (msg.reason=='result_challenge_unavailable' or msg.reason=='health_or_pending_unverified'))) and owner_matches(msg,current) and
            msg.target=='CAT1' and msg.cat_proof_ready==false and cat_proof:ready(current.job,current.epoch) then cat_proof:reset() end
        if msg.op=="REBOOT_GRANT" then
            local s=manager:status();local t=monotonic_ms();local request=reboot_request
            if options.port~=nil or s.error or not t or not request or t<request.at or t-request.at>=3000 or
                msg.ticket~=request.ticket or not owner_matches(msg,s) or s.phase~="INSTALLING" or
                msg.phase~="INSTALL_PENDING" or msg.reason~="ok" or msg.commit_safe~=true or
                not native_installer or native_installer:status().phase~="COMMITTED" then
                return false,"REBOOT_GRANT_INVALID"
            end
            reboot_request=nil
            gr_safety={job=msg.job,hash=msg.hash,target=msg.target,version=msg.version,
                epoch=msg.epoch,phase=msg.phase,op=msg.op,at=t}
            local accepted,why=native_installer:reboot(s.job,s.epoch)
            gr_safety=nil
            return accepted,why
        end
        if options.port==nil then
            gr_safety=nil
            local s=manager:status();local t=monotonic_ms()
            if not s.error and t and owner_matches(msg,s) and msg.reason=="ok" and msg.commit_safe==true and
                ((msg.op=="STATUS" and msg.phase=="PREPARED" and
                    (s.phase=="PREPARED" or s.phase=="WAIT_ACTIVATE")) or
                 (msg.op=="GRANT" and msg.phase=="INSTALL_PENDING" and s.phase=="WAIT_ACTIVATE") or
                 (msg.op=="STATUS" and msg.phase=="INSTALL_PENDING" and s.phase=="RECOVERY_HOLD" and
                    s.io=='ARMED') or
                 (msg.op=="STATUS" and msg.phase=="INSTALL_PENDING" and s.phase=="INSTALLING" and
                    native_installer and native_installer:status().phase=="WRITING")) then
                gr_safety={job=msg.job,hash=msg.hash,target=msg.target,version=msg.version,
                    epoch=msg.epoch,phase=msg.phase,op=msg.op,at=t}
            end
        end
        local accepted,why=manager:on_gr(msg)
        if not accepted then gr_safety=nil end
        return accepted,why
    end
    function self:flush_outbox()
        if inflight then return false,"IN_FLIGHT" end
        local status=manager:status()
        if status.error or type(status.outbox)~="table" then return false,status.error or "OUTBOX_INVALID" end
        local item=status.outbox[1]
        if not item then return true end
        if status.phase=="COMPLETE_PENDING" and type(item.payload)=="table" and item.payload.MsgType=="otaResultMsg" then
            return false,"GR_RELEASE_PENDING"
        end
        local topic=invoke(base,"outbox_topic",item.payload)
        if type(topic)~="string" or #topic<1 or #topic>256 or topic:find("[%z\r\n+#]") then
            return false,"OUTBOX_TOPIC_UNMAPPED"
        end
        if not sys or type(sys.publish)~="function" then return false,"MQTT_UNAVAILABLE" end
        local ok,payload=pcall(codec.encode,item.payload)
        if not ok or type(payload)~="string" then return false,"OUTBOX_ENCODE" end
        local token={id=item.id}
        inflight=token
        local sent,accepted=pcall(sys.publish,"SEND_DATA_REQ","ota",topic,payload,1,{
            para=item.id,
            func=function(confirmed,id)
                if inflight~=token or id~=token.id then return end
                inflight=nil
                if confirmed==true then manager:ack(id,true) end
            end,
        })
        if not sent or accepted==false then inflight=nil;return false,"MQTT_ENQUEUE" end
        return true
    end
    function self:tick()
        local status=manager:status()
        if status.error then return false,status.error end
        self:flush_outbox()
        if status.phase=='COMPLETE_PENDING' and status.job and status.job.target=='CAT1' and options.port==nil then
            if not business_idle() then result_query=nil;return false,'BUSINESS_PAUSED' end
            if not native_installer then return false,'NATIVE_EVIDENCE_UNAVAILABLE' end
            local report,why=native_installer:completion_report(status.job,status.epoch)
            if not report then manager:reconcile();return false,why end
            local ok,why=cat_proof:start(status.job,status.epoch,report.proof)
            if not ok then return false,why end
            if not cat_proof:ready(status.job,status.epoch) then
                -- QUERY also detects a GR restart that discarded an already acknowledged proof.
                manager:reconcile();return cat_proof:step()
            end
            local now=monotonic_ms();if not now then return false,'CAT_PROOF_CLOCK' end
            if result_query and now>=result_query and now-result_query<3000 then return false,'RESULT_CHALLENGE_PENDING' end
            result_query=now
            local j=status.job
            if invoke(base,'send_gr',{op='RESULT_QUERY',job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=status.epoch})~=true then
                result_query=nil;return false,'RESULT_QUERY_SEND_FAILED'
            end
            return true,'RESULT_CHALLENGE_PENDING'
        elseif status.phase=="IDLE" then
            local released=manager:pending_native_release()
            if released then
                if not native_installer then return false,"NATIVE_EVIDENCE_UNAVAILABLE" end
                local ok,why=native_installer:retire(released)
                if not ok then return false,why end
                return manager:native_release_done(released)
            end
            local candidate=manager:pending_cleanup()
            if candidate then
                local ok,why=manager:reserve_cleanup(candidate.target,candidate.hash)
                if not ok then return false,why end
                if invoke(down_port,"remove",candidate_paths.path(candidate.hash))~=true then
                    return false,"CANDIDATE_CLEANUP_PENDING"
                end
                return manager:cleanup_done(candidate.target,candidate.hash)
            end
            local command=manager:next_command()
            if command then return manager:accept(command,true) end
        elseif status.phase=="GR_GRANTED" or status.phase=="PAUSED" then
            return manager:prepare()
        elseif status.phase=="PREPARED" then
            if status.job and status.job.target=='CAT1' and status.job.bundle and not cat_proof:ready(status.job,status.epoch) then
                local ok,why=port.prepare(status.job);if not ok then return false,why end
            end
            if status.prepared_ack~=true or (options.port==nil and port.safe()~=true) then
                if prepared_poll==0 then manager:reconcile() end
                prepared_poll=(prepared_poll+1)%5 -- runtime task ticks once per second
            else
                prepared_poll=0
            end
            return manager:request_activation()
        elseif status.phase=="INSTALLING" or status.phase=="ACTIVATION_ISSUED" or status.phase=="RECOVERY_HOLD" then
            -- Armed CAT1 install-only attempt: rebuild bundle/candidate/proof (no re-download), take the user-data baseline, bind a
            -- receipt, then QUERY. The manager starts the install on the next commit-safe STATUS. Bounded to 20 min (IO_TIMEOUT).
            if options.port==nil and status.phase=="RECOVERY_HOLD" and status.io=='ARMED' and status.job and status.job.target=='CAT1' then
                local t=monotonic_ms() or 0
                if install_receipt_matches(status.job,status.epoch) then manager:reconcile();return false,'IO_WAIT_STATUS' end
                armed_since=armed_since or t
                if t-armed_since>1200000 then armed_since=nil;manager:transport_fault('IO_TIMEOUT',true);return false,'IO_TIMEOUT' end
                local ok,why=port.prepare(status.job)
                if ok~=true then
                    if why=='DOWNLOAD_PENDING' then return false,why end -- normal progress (proof chunk awaiting its ACK); never interleave a QUERY
                    rebuild_errors=(rebuild_errors or 0)+1
                    if rebuild_errors%10==1 then manager:reconcile();if _G.ota_diag then _G.ota_diag('[OTA] '..tostring(why)) end end
                    return false,why
                end
                local j=status.job
                if take_install_base and not take_install_base(j,status.epoch) then
                    if _G.ota_diag then _G.ota_diag('[OTA] SNAPSHOT') end
                    return false,'IO_SNAPSHOT'
                end
                install_receipt={id=j.id,hash=j.hash,md5=j.md5,size=j.size,source=j.source,version=j.version,url=j.url,
                    bundle_md5=j.bundle.md5,manifest=j.bundle.manifest_sha256,epoch=status.epoch}
                manager:reconcile();return true,'IO_READY'
            end
            -- A stopped CAT1 install is re-armed every 30 s; the manager allows at most 3 re-arms per job.
            local np=native_installer and native_installer:status()
            if options.port==nil and status.job and status.job.target=='CAT1' and status.io~='ARMED' and status.io~='FINISHED' and
                (status.phase=='RECOVERY_HOLD' or (status.phase=='INSTALLING' and np and (np.phase=='HOLD' or np.recovery_phase=='HOLD'))) then
                rearm_ticks=(rearm_ticks or 0)+1
                if rearm_ticks%30==0 then
                    local ok,why=self:arm_io();if _G.ota_diag then _G.ota_diag('[OTA] arm '..tostring(ok or why)) end
                    if ok then return true,'IO_ARMED' end
                end
            end
            if options.port==nil and native_installer and status.phase=="INSTALLING" and
                status.job and status.job.target=="CAT1" and native_installer:status().phase=="COMMITTED" then
                local t=monotonic_ms()
                if paused==true or not t or not business_idle() then reboot_request=nil;return false,"REBOOT_WAIT_SAFE" end
                if reboot_request and t>=reboot_request.at and t-reboot_request.at<3000 then return false,"REBOOT_GRANT_PENDING" end
                if reboot_ticket>=0xffffffff then return false,"REBOOT_TICKET_EXHAUSTED" end
                -- The REBOOT_GRANT handler runs in the UART task inside GR's 3 s grant, so the reboot-time data check uses this baseline.
                if take_reboot_base and not take_reboot_base(status.job) then return false,'REBOOT_SNAPSHOT' end
                t=monotonic_ms();if not t or not business_idle() then reboot_request=nil;return false,"REBOOT_WAIT_SAFE" end
                reboot_ticket=reboot_ticket+1;reboot_request={ticket=reboot_ticket,at=t}
                local j=status.job
                if invoke(base,"send_gr",{op="REBOOT",job=j.id,hash=j.hash,target=j.target,
                    version=j.version,epoch=status.epoch,ticket=reboot_ticket})~=true then
                    reboot_request=nil;return false,"REBOOT_SEND_FAILED"
                end
                return true,"REBOOT_GRANT_PENDING"
            end
            if native_installer and status.job and status.job.target=="CAT1" and
                native_installer:status().phase=="WRITING" then
                if options.port==nil then manager:reconcile() end
                -- A slow vendor call (e.g. fota.init) can leave GR authority older than 3 s; wait <=2.5 s for a fresh STATUS first.
                if options.port==nil and status.io=='RUNNING' and not fresh_safety() and refresh_gr_safety then refresh_gr_safety() end
                local ok,why=native_installer:step()
                if not ok then
                    if why~=last_write_error and _G.ota_diag then last_write_error=why;_G.ota_diag('[OTA] W '..tostring(why)..' '..tostring(native_installer:status().offset)) end
                    return false,why
                end
                return true,"NATIVE_INSTALL_PENDING"
            end
            if native_installer and status.job and status.job.target=='CAT1' then
                local native_phase=native_installer:status().phase
                if native_phase=='RECOVERY_HOLD' or native_phase=='CONFIRMED' then
                    local ok,why=native_installer:verify_running_identity()
                    native_code_identity=ok and (why or 'VERIFIED') or why
                    if not ok then
                        if health_monitor then health_monitor:reset(why) end
                        manager:reconcile();return false,why
                    end
                end
            end
            local info,health_reason=invoke(base,"health",status.job,status.epoch)
            if type(info)=="table" then
                if status.job and status.job.target=="CAT1" then
                    if not native_installer then return false,"NATIVE_EVIDENCE_UNAVAILABLE" end
                    local ok,result=native_installer:confirm(status.job,status.epoch,info)
                    if not ok then return false,result end
                    info=result
                end
                return manager:finish(info)
            end
            if health_monitor and health_reason then manager:reconcile();return false,health_reason end
        end
        return manager:reconcile()
    end
    local advance=self.tick
    function self:tick()
        local ok,why=advance(self);self.last_tick_reason=why;return ok,why
    end
    return self
end
function M.instance()
    if not singleton then singleton=M.new(require("ota_device_options").new()) end
    return singleton
end
function M.set_instance(instance)
    assert(not started,"runtime already started")
    singleton=instance
end
function M.start()
    if started then return M.instance() end
    local instance=M.instance()
    started=true
    _G.at_cmd_handlers=_G.at_cmd_handlers or {}
    _G.at_cmd_handlers.OTA_GR=function(line) instance:on_gr_line(line) end
    _G.ota_uart_idle=function()return instance:uart_idle()end
    local bindings={'OTA2_TX_SENT','on_tx_sent','OTA2_TX_FAILED','on_tx_failed','OTA_UART_FAULT','uart_fault','OTA2_FRAME','on_wire_frame'}
    for i=1,#bindings,2 do
        local name=bindings[i+1]
        sys.subscribe(bindings[i],function(value) instance[name](instance,value) end)
    end

    for _,event in ipairs({"SIM_LOST","IP_LOSE","OTA_BUSINESS_BUSY"}) do
        sys.subscribe(event,function() instance:pause() end)
    end
    sys.taskInit(function()
        while true do instance:tick();sys.wait(1000) end
    end)
    sys.taskInit(function()
        while true do local active=instance:pump_gr();sys.wait(active and 10 or 100) end
    end)
    return instance
end
return M
