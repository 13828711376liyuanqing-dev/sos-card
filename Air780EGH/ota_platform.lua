-- SAM | 2026-10-30 08:58 +08:00 | Device services binding (business state, MQTT topics, release resolver) for the runtime.
local M = {}
local services={}
local function loaded_service(name)
    if services[name]~=nil then return services[name] end
    -- Preserve standard-Lua host adapters without requiring this optional table on the device.
    local p=rawget(_G,'package')
    local loaded=type(p)=='table' and rawget(p,'loaded')
    if type(loaded)=='table' then return loaded[name] end
end
function M.bind_services(mqtt,business)
    services.mqtts_main=type(mqtt)=='table' and mqtt or nil
    services.business_runtime=type(business)=='table' and business or nil
    return services.mqtts_main~=nil and services.business_runtime~=nil
end
function M.business_status()
    local business=loaded_service('business_runtime')
    if type(business)~='table' or type(business.ota_status)~='function' then return nil end
    local ok,status=pcall(business.ota_status)
    if ok and type(status)=='table' then return status end
end
local function unavailable() return nil, "CAPABILITY_UNAVAILABLE" end
local last_ota_reject
function M.diag(r) if not r then last_ota_reject=nil elseif log and last_ota_reject~=r and pcall(log.warn,'OTA_DIAG',r) then last_ota_reject=r end;return false end
function M.default()

    local function identity()
        local main=loaded_service('mqtts_main')
        if type(main)~="table" or type(main.business_identity)~="function" then return nil end
        local ok,id=pcall(main.business_identity)
        if ok and type(id)=="string" and #id>=1 and #id<=128 and id:match('^[%w_.%-]+$') then return id end
    end
    return {
        resolve=unavailable, validate=unavailable, compare=unavailable,
        safe=unavailable, activate=unavailable,
        health=unavailable, health_default=true, stage_gr=unavailable, candidate_ready=unavailable,
        business_status=M.business_status,
        idle=function()
            local s=M.business_status()
            return type(s)=="table" and s.known==true and s.idle==true
        end,
        outbox_topic=function(payload)
            if type(payload)~="table" or (payload.MsgType~="otaReplyMsg" and payload.MsgType~="otaResultMsg") then return nil end
            local id=identity();if id then return "/iotplat/datapush3/notsos/WARNCARD3/"..id end
        end,
        accept_topic=function(topic)
            local id=identity()
            return id~=nil and topic=="/iotplat/render3/WARNCARD3/"..id.."/down_raw"
        end,
        now=function() return os.time() end,
        send_gr=function(msg)
            if type(_G.uart_send_raw)~="function" then return M.diag("NO_SENDER") end
            local ok,body=pcall(function()return json.encode(msg)end)
            if not ok or type(body)~="string" or #body>1000 then return M.diag("JSON") end
            return _G.uart_send_raw("OTA_CTL="..body)==true
        end,
    }
end
function M.bundle(bundle_port,base)
    local port={}
    for k,v in pairs(base or M.default()) do port[k]=v end
    local function number(s)
        if type(s)~='string' or #s>11 then return nil end
        local a,b,c=s:match('^(%d+)%.(%d+)%.(%d+)$')
        if not a then a,b=s:match('^(%d+)%.(%d+)$');c='0' end
        a,b,c=tonumber(a),tonumber(b),tonumber(c)
        if not a or not b or not c or a>999 or b>999 or c>999 then return nil end
        return a*1000000+b*1000+c
    end
    port.compare=function(a,b)
        a,b=number(a),number(b)
        if not a or not b then return nil end
        return a-b
    end
    local cached
    local function descriptor(cmd,target)
        if type(cmd)~='table' or type(cmd.Md5)~='string' or #cmd.Md5~=32 or
            cmd.Md5:find('[^%x]') then return nil,'COMMAND_INVALID' end
        local request={url=cmd.Address,md5=cmd.Md5,source_version=cmd.CurrentVersion,target_version=cmd.TargetVersion}
        if type(bundle_port.can_read)~='function' or bundle_port.can_read()~=true then return nil,'BUSINESS_PAUSED' end
        local hit=cached and cached.url==cmd.Address and cached.md5==cmd.Md5:lower() and
            cached.source==cmd.CurrentVersion and cached.target==cmd.TargetVersion and cached.key==bundle_port.trusted_key_id
        local reader,why
        if hit then
            local ok,current=pcall(bundle_port.current_version)
            if not ok or number(current)~=number(cached.summary.source_version) then return nil,'SOURCE_VERSION_MISMATCH' end
        else
            cached=nil
            reader,why=require('ota_bundle').open(bundle_port,request)
            if not reader and why=='HTTP_RANGE_REQUIRED' and type(bundle_port.open_stream)=='function' then
                reader,why=require('ota_seq_zip').open(bundle_port,request)
            end
            if not reader then return nil,why end
            local summary=reader:summary()
            if summary.device_installable~=true then return nil,'BUNDLE_NOT_INSTALLABLE' end
            local gr,cat=reader:component('GR5526'),reader:component('CAT1')
            if not gr or not cat or reader:close()~=true then return nil,'BUNDLE_METADATA_UNAVAILABLE' end
            cached={url=cmd.Address,md5=cmd.Md5:lower(),source=cmd.CurrentVersion,target=cmd.TargetVersion,
                key=bundle_port.trusted_key_id,summary=summary,GR5526=gr,CAT1=cat}
        end
        local summary=cached.summary
        if type(bundle_port.completed)~='function' then return nil,'COMPLETION_UNAVAILABLE' end
        local ok,gr_done=pcall(bundle_port.completed,'GR5526',summary.manifest_sha256)
        if not ok or type(gr_done)~='boolean' then return nil,'COMPLETION_UNAVAILABLE' end
        local selected=gr_done and 'CAT1' or 'GR5526'
        if target and target~=selected then return nil,'COMPONENT_SEQUENCE' end
        local c=cached[selected]
        local job={target=selected,hash=c.sha256,md5=c.md5,size=c.size,
            source=summary.source_version,version=summary.target_version,url=cmd.Address,
            bundle={md5=cmd.Md5:lower(),manifest_sha256=summary.manifest_sha256}}
        if type(bundle_port.sha256)~='function' then return nil,'HASH_UNAVAILABLE' end
        job.id=bundle_port.sha256('YP001_COMPONENT_JOB_V1\0'..summary.manifest_sha256..'\0'..selected)
        return job
    end
    port.resolve=function(cmd) return descriptor(cmd) end
    port.validate=function(job,cmd)
        if type(job)~='table' or type(job.bundle)~='table' then return false,'BUNDLE_JOB_INVALID' end
        local expected,why=descriptor(cmd or {Address=job.url,Md5=job.bundle.md5,
            CurrentVersion=job.source,TargetVersion=job.version},job.target)
        if not expected then return false,why end
        for _,key in ipairs({'id','target','hash','md5','size','source','version','url'}) do
            if job[key]~=expected[key] then return false,'BUNDLE_JOB_MISMATCH' end
        end
        if job.bundle.md5~=expected.bundle.md5 or
            job.bundle.manifest_sha256~=expected.bundle.manifest_sha256 then return false,'BUNDLE_JOB_MISMATCH' end
        return true
    end
    return port
end
return M
