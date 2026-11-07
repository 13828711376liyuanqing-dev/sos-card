-- SAM | 2026-10-30 08:58 +08:00 | Bounded HTTP client over the LuatOS socket API (Range and plain sequential reads).
local M={}
local function need(ok,code) if not ok then error(code,0) end end
local function integer(n,lo,hi) return type(n)=='number' and n%1==0 and n>=lo and n<=hi end
local function tag(s) return type(s)=='string' and #s>=2 and #s<=128 and s:match('^"[^"%c]*"$') end
-- SAM | 2026-11-04 +08:00 | New backend (openresty) repeats Accept-Ranges/Vary and sends an unquoted ETag. Headers this client
-- reads (or that change framing/target) must still be unique; others keep their first value. An unquoted ETag of plain
-- visible characters is quoted here, so checkpoints and entity checks keep the quoted form unchanged.
local SINGLE={['content-length']=true,['content-range']=true,etag=true,['transfer-encoding']=true,
 ['content-encoding']=true,location=true}
local function quote_etag(v)
 if type(v)=='string' and #v>=1 and #v<=126 and v:match('^[!#-~]+$') and not v:find('^W/') then return '"'..v..'"' end
 return v
end
local function stream_body(read,buffer,h,guard,cleanup)
 local chunked=h['transfer-encoding']=='chunked'
 local length=h['content-length']
 local remaining=tonumber(length)
 need(not (chunked and length) and (chunked or (h['transfer-encoding']==nil and type(length)=='string' and length:match('^%d+$') and integer(remaining,1,2097152))),'HTTP_STREAM_FRAMING')
 need(h['content-encoding']==nil or h['content-encoding']=='identity','HTTP_CONTENT_ENCODING')
 local left,decoded,chunks,wire=0,0,0,#buffer
 local separator,eof,closed
 local function close()
  if closed then return true end
  closed=true;return cleanup()
 end
 local function take(n)
  while #buffer<n do
   local s=read(math.min(512,n-#buffer));wire=wire+#s
   need(wire<=4194304,'HTTP_STREAM_LIMIT');buffer=buffer..s
  end
  local s=buffer:sub(1,n);buffer=buffer:sub(n+1);return s
 end
 local function line()
  local s=''
  repeat need(#s<128,'HTTP_CHUNK_LINE');s=s..take(1) until s:sub(-2)=='\r\n'
  return s:sub(1,-3)
 end
 local function finish()
  need(#buffer==0,'HTTP_BODY_EXTRA');eof=true
  need(close(),'HTTP_CLEANUP')
 end
 local function consume(n)
  need(integer(n,1,16384),'HTTP_STREAM_READ')
  if eof then return '' end
  need(not closed,'HTTP_STREAM_CLOSED');guard()
  if not chunked then
   local s=take(math.min(n,remaining));remaining=remaining-#s
   if remaining==0 then finish()end
   return s
  end
  local parts,total={},0
  while total<n and not eof do
   if left==0 then
    if separator then need(take(2)=='\r\n','HTTP_CHUNK_CRLF');separator=false end
    local hex,extra=line():match('^(%x+)(.*)$')
    need(hex and #hex<=6 and (extra=='' or (extra:sub(1,1)==';' and not extra:find('%c'))),'HTTP_CHUNK_SIZE')
    left=tonumber(hex,16);chunks=chunks+1
    need(chunks<=65536 and left<=2097152-decoded,'HTTP_STREAM_LIMIT')
    if left==0 then
     local trailers=0
     while true do
      local value=line();trailers=trailers+#value+2
      need(trailers<=2048,'HTTP_TRAILER_LIMIT')
      if value=='' then break end
      local key=value:match('^([%w%-]+):')
      need(key and not value:find('%c'),'HTTP_TRAILER')
      key=key:lower();need(key~='content-length' and key~='transfer-encoding' and key~='etag','HTTP_TRAILER')
     end
     finish();break
    end
   end
   local s=take(math.min(left,n-total));parts[#parts+1]=s
   left=left-#s;decoded=decoded+#s;total=total+#s
   if left==0 then separator=true end
  end
  return table.concat(parts)
 end
 return {read=function(n)
  local ok,s=pcall(consume,n)
  if ok then return s end
  close()
  return nil,type(s)=='string' and s:match('^[A-Z0-9_]+$') and s or 'HTTP_STREAM_ERROR'
 end,close=close,headers=h,status=200}
end
local function has(module,name)
 if type(module)~='table' and type(module)~='userdata' then return false end
 local ok,value=pcall(function()return module[name]end)
 return ok and type(value)=='function'
end

local function build(d,diagnostic)
 if type(d)~='table' then return nil,'HTTP_NATIVE_API' end
 local s,z=d.socket,d.zbuff
 if not has(z,'create') then return nil,'HTTP_NATIVE_API' end
 for _,name in ipairs({'create','config','connect','tx','rx','close','release'})do
  if not has(s,name) then return nil,'HTTP_NATIVE_API' end
 end
 for _,name in ipairs({'now_ms','wait','can_read'})do
  if type(d[name])~='function' then return nil,'HTTP_NATIVE_API' end
 end
 local busy=false
 local function get(url,headers,count,probe,streaming)
  if busy then return nil,'HTTP_BUSY' end
  busy=true
  local sc
  local function cleanup()
   local good=true
   if sc then local a=pcall(s.close,sc);local b=pcall(s.release,sc);good=a and b;sc=nil end
   busy=false;return good
  end
  local ok,result=pcall(function()
   need(type(url)=='string' and #url<=2048 and not url:find('[%c%s#]'),'HTTP_URL')
   local tls=diagnostic==true and url:match('^https://')~=nil
   local authority,path=url:match(tls and '^https://([^/%?]+)(.*)$' or '^http://([^/%?]+)(.*)$')
   need(authority~=nil and not authority:find('@',1,true),'HTTP_URL')
   local host,port=authority:match('^([%w%.%-]+):(%d+)$')
   if not host then host=authority;port=tls and '443' or '80';need(host:match('^[%w%.%-]+$'),'HTTP_URL') end
   port=tonumber(port);need(#host<=253 and integer(port,1,65535),'HTTP_URL')
   local ca
   if tls then
    need(type(d.tls_ca)=='function','HTTP_TLS_CA');ca=d.tls_ca(host)
    need(type(ca)=='string' and #ca>0 and #ca<=16384,'HTTP_TLS_CA')
   end
   if path=='' then path='/' elseif path:sub(1,1)=='?' then path='/'..path end
   need(path:sub(1,1)=='/' and type(headers)=='table' and integer(count,1,16384),'HTTP_ARGUMENT')
   for name in pairs(headers)do need(name=='Range' or name=='If-Range' or (diagnostic==true and name=='Cookie'),'HTTP_REQUEST_HEADER') end
   if headers.Cookie then need(type(headers.Cookie)=='string' and #headers.Cookie<=2048 and not headers.Cookie:find('%c'),'HTTP_REQUEST_HEADER') end
   local first,last=(type(headers.Range)=='string' and headers.Range or ''):match('^bytes=(%d+)%-(%d+)$')
   first,last=tonumber(first),tonumber(last)
   need(streaming==true or (integer(first,0,16777215) and integer(last,first,16777215) and last-first+1==count),'HTTP_REQUEST_RANGE')
   if streaming then need(headers.Range==nil and headers['If-Range']==nil,'HTTP_STREAM_ARGUMENT')end
   need(headers['If-Range']==nil or tag(headers['If-Range']),'HTTP_REQUEST_HEADER')
   local started=d.now_ms();need(integer(started,0,4294967295),'HTTP_CLOCK')
   local progress=started
   local online,transmitted,fault,peer_closed=false,false,false,false
   local function guard()
    need(d.can_read()==true,'BUSINESS_PAUSED')
    local now=d.now_ms();need(integer(now,0,4294967295),'HTTP_CLOCK')
    need((now-started)%4294967296<(streaming and 900000 or 30000),'HTTP_TIMEOUT')
    if streaming then need((now-progress)%4294967296<30000,'HTTP_IDLE_TIMEOUT') end
    need(not fault or transmitted,'HTTP_SOCKET')
   end
   guard()
   -- SAM | 2026-11-06 +08:00 | Range segments go through the firmware HTTP library when it exists. On the test backend (QingCloud ELB) the raw
   -- socket below is closed right after the request or never receives the body, while the library downloads the same URL from the same
   -- device and SIM. Request, 206 / Content-Range / length / ETag checks and the size bound are the same as the raw path. Streaming reads
   -- and hosts without the library (tests) keep the raw socket.
   local lib=(not streaming) and (type(http)=='userdata' or type(http)=='table') and http or nil
   if lib then
    local req={}
    if headers.Range then req.Range=headers.Range end
    if headers['If-Range'] then req['If-Range']=headers['If-Range'] end
    if headers.Cookie then req.Cookie=headers.Cookie end
    local okc,code,h,b=pcall(function() return lib.request('GET',url,req,nil,{timeout=30000}).wait() end)
    guard()
    need(okc and type(code)=='number','HTTP_LIB_ERROR')
    local rh={}
    for k,v in pairs(type(h)=='table' and h or {}) do rh[tostring(k):lower()]=tostring(v) end
    if diagnostic==true and probe==true and code~=206 then return {status=code,headers=rh,body='',final_url=url} end
    need(code==206,'HTTP_RANGE_REQUIRED')
    need(type(b)=='string' and #b==count,'HTTP_LENGTH')
    local a1,b1,t1=(rh['content-range'] or ''):match('^bytes (%d+)%-(%d+)/(%d+)$')
    need(tonumber(a1)==first and tonumber(b1)==last and integer(tonumber(t1),last+1,16777216),'HTTP_CONTENT_RANGE')
    rh.etag=quote_etag(rh.etag)
    need(tag(rh.etag),'HTTP_ETAG')
    need(not headers['If-Range'] or headers['If-Range']==rh.etag,'HTTP_ENTITY_CHANGED')
    return {status=206,headers=rh,body=b,final_url=url}
   end
   sc=s.create(d.adapter,function(_,event,param)
    if event==s.CLOSED then peer_closed=true end
    if param and param~=0 then fault,peer_closed=true,true end
    if event==s.ON_LINE then online=true elseif event==s.TX_OK then transmitted=true end
   end)
   need(sc~=nil,'HTTP_CREATE')
   local configured
   if tls then configured=s.config(sc,nil,false,true,nil,nil,nil,ca)
   else configured=s.config(sc,nil,false,false) end
   need(configured==true,'HTTP_CONFIG')
   local connected,immediate=s.connect(sc,host,port);need(connected==true,'HTTP_CONNECT')
   online=online or immediate==true
   while not online do guard();need(not peer_closed,'HTTP_EOF');d.wait(20) end
   guard()
   local request='GET '..path..' HTTP/1.1\r\nHost: '..authority..'\r\n'
   if headers.Range then request=request..'Range: '..headers.Range..'\r\n'end
   request=request..'Connection: keep-alive\r\nAccept-Encoding: identity\r\n'
   if headers['If-Range'] then request=request..'If-Range: '..headers['If-Range']..'\r\n' end
   if headers.Cookie then request=request..'Cookie: '..headers.Cookie..'\r\n' end
   request=request..'\r\n'
   while true do
    guard();need(not peer_closed,'HTTP_EOF')
    transmitted=false
    local sent,full,done=s.tx(sc,request)
    need(sent==true and type(full)=='boolean','HTTP_SEND')
    if not full then transmitted=transmitted or done==true;break end
    transmitted=false
    guard();need(not peer_closed,'HTTP_EOF');d.wait(20)
   end
   while not transmitted do guard();need(not peer_closed,'HTTP_EOF');d.wait(20) end
   local buffer=z.create(512);need(buffer~=nil,'HTTP_BUFFER')
   local function read(limit)
    guard();buffer:del()
    -- API documentation has an outdated 3-argument example. C implementation
    -- tests lua_gettop >= 4: never put limit into the reserved flag argument.
    local success,n=s.rx(sc,buffer,0,limit)
    need(success==true and integer(n,0,limit),'HTTP_NATIVE_OVERFLOW')
    if n>0 then progress=d.now_ms() end
    need(n>0 or not peer_closed,'HTTP_EOF')
    local data=n>0 and buffer:query(0,n) or ''
    need(type(data)=='string' and #data==n,'HTTP_NATIVE_READ')
    d.wait(n>0 and 1 or 20);guard();return data
   end
   local head,at='',nil
   repeat
    need(#head<4096,'HTTP_HEADER_LIMIT')
    head=head..read(math.min(512,4096-#head));at=head:find('\r\n\r\n',1,true)
   until at
   local raw,body=head:sub(1,at-1),head:sub(at+4)
   local line_end=raw:find('\r\n',1,true)
   local status_line=line_end and raw:sub(1,line_end-1) or raw
   local code=tonumber(status_line:match('^HTTP/1%.[01] (%d%d%d) [^%c]*$'))
   need(code==206 or (streaming==true and code==200) or (diagnostic==true and probe==true and (code==200 or code==302 or code==303 or code==307 or code==308)),'HTTP_RANGE_REQUIRED')
   local response_headers={}
   local lines=line_end and raw:sub(line_end+2)..'\r\n' or ''
   for line in lines:gmatch('(.-)\r\n')do
    local name,value=line:match('^([!#$%%&\'*+%.%^_`|~%w%-]+):[ \t]*(.-)[ \t]*$')
    need(name and not value:find('[%z\1-\8\10-\31\127]'),'HTTP_HEADER')
    name=name:lower()
    if response_headers[name]==nil then response_headers[name]=value else need(not SINGLE[name],'HTTP_DUPLICATE_HEADER') end
   end
   if streaming then
    need(code==200,'HTTP_STREAM_STATUS')
    return stream_body(read,body,response_headers,guard,cleanup)
   end
   if diagnostic==true and probe==true and code~=206 then
    guard();return {status=code,headers=response_headers,body='',final_url=url}
   end
   need(response_headers['transfer-encoding']==nil,'HTTP_TRANSFER_ENCODING')
   need(response_headers['content-encoding']==nil or response_headers['content-encoding']=='identity','HTTP_CONTENT_ENCODING')
   local length=response_headers['content-length']
   need(type(length)=='string' and length:match('^%d+$') and tonumber(length)==count,'HTTP_LENGTH')
   local a,b,total=(response_headers['content-range'] or ''):match('^bytes (%d+)%-(%d+)/(%d+)$')
   need(tonumber(a)==first and tonumber(b)==last and integer(tonumber(total),last+1,16777216),'HTTP_CONTENT_RANGE')
   response_headers.etag=quote_etag(response_headers.etag)
   need(tag(response_headers.etag),'HTTP_ETAG')
   need(not headers['If-Range'] or headers['If-Range']==response_headers.etag,'HTTP_ENTITY_CHANGED')
   need(#body<=count,'HTTP_LENGTH')
   while #body<count do body=body..read(math.min(512,count-#body+1));need(#body<=count,'HTTP_LENGTH') end
   guard()
   return {status=206,headers=response_headers,body=body,final_url=url}
  end)
  -- Always release our own socket, including timeout, thrown driver calls and SOS.
  if ok and streaming then return result end
  local cleaned=cleanup()
  if not cleaned then return nil,'HTTP_CLEANUP' end
  if ok then return result end
  return nil,type(result)=='string' and result:match('^[A-Z0-9_]+$') and result or 'HTTP_PORT_ERROR'
 end
 local result={http_get=function(url,h,n)return get(url,h,n,false)end}
 result.open_stream=function(url)return get(url,{},1,false,true)end
 if diagnostic==true then result.probe=function(url,h)return get(url,h,1,true)end end
 return result
end
function M.new(d)
 if type(d)~='table' or d.native_rx_limit_verified~=true then return nil,'HTTP_NATIVE_CONTRACT' end
 return build(d)
end
function M.new_diagnostic(d) return build(d,true) end
return M
