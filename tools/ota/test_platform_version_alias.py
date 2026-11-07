"""SAM | 2026-11-05 +08:00 | OTA filename aliases must normalize only at the trusted downlink boundary."""
from test_runtime import check

SETUP = r'''
port.accept_topic=function(t)return t=='test/down' end
local resolve=port.resolve
port.resolve=function(c)
 if c.CurrentVersion~='1.5.10' or c.TargetVersion~='1.5.11' then return nil,'VERSION_MISMATCH' end
 return resolve(c)
end
function receive(source,target,meta,topic,md5)
 local r=R.new({store=newstore(),codec=json,port=port})
 local c=clone(command);c.CurrentVersion=source;c.TargetVersion=target
 if md5 then c.Md5=md5 end
 local before=json.encode(c)
 local ok,why=r:receive(topic or 'test/down',c,meta or {retain=false})
 assert(json.encode(c)==before,'must not mutate MQTT input')
 return ok,why,r
end
'''

check('platform filename aliases reach the strict resolver as canonical versions', SETUP + r'''
local ok,why,r=receive('YP001_1.5.10','1.5.11_FIRST')
assert(ok,tostring(why))
assert(r:status().job.source=='1.5.10' and r:status().job.version=='1.5.11')
assert(r:status().job.url==command.Address and r:status().job.md5==command.Md5)
local rebooted=R.new({store=newstore(),codec=json,port=port})
assert(rebooted:status().job.source=='1.5.10' and rebooted:status().job.version=='1.5.11')
''')
check('plain versions still accepted', SETUP + r'''
assert(receive('1.5.10','1.5.11'))
''')
check('unknown or repeated decorations remain rejected', SETUP + r'''
for _,v in ipairs({'OTHER_1.5.10','YP001_YP001_1.5.10','YP001_1.5.10.zip','x1.5.10','YP001_1.5.10_FIRST','YP001_1000.5.10'}) do
 fs={};assert(not receive(v,'1.5.11_FIRST'),v)
end
for _,v in ipairs({'1.5.11_OTHER','1.5.11_FIRST_FIRST','1.5.11_FIRST.zip','YP001_1.5.11_FIRST','1.5.11_FIRST '}) do
 fs={};assert(not receive('YP001_1.5.10',v),v)
end
''')
check('topic and retained-message gates still reject aliases', SETUP + r'''
local ok,why=receive('YP001_1.5.10','1.5.11_FIRST',{retain=false},'other/down')
assert(not ok and why=='OTA_TOPIC_UNTRUSTED')
ok,why=receive('YP001_1.5.10','1.5.11_FIRST',{retain=true})
assert(not ok and why=='OTA_RETAINED_OR_UNKNOWN')
''')
check('wrong actual version and invalid MD5 remain rejected', SETUP + r'''
assert(not receive('YP001_1.5.9','1.5.11_FIRST'))
fs={};assert(not receive('YP001_1.5.10','1.5.11_FIRST',nil,nil,'bad'))
''')
check('all six protocol fields remain required, including both versions', SETUP + r'''
for _,key in ipairs({'MsgType','CurrentVersion','TargetVersion','Address','Md5','Time'}) do
 fs={}
 local r=R.new({store=newstore(),codec=json,port=port})
 local c=clone(command);c.CurrentVersion='YP001_1.5.10';c.TargetVersion='1.5.11_FIRST';c[key]=nil
 local ok=r:receive('test/down',c,{retain=false})
 assert(not ok,'missing '..key..' must be rejected')
 assert(r:status().job==nil and activation==0)
end
''')
