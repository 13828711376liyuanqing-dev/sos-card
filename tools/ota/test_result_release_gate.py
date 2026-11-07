# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-23 +08:00 | Reproduce premature platform success while GR still rejects completion; no device IO."""
from test_runtime import check

SCENARIO = '''
port.resolve=function(c)return {id=string.rep('b',64),hash=string.rep('c',64),target='CAT1',
 version=c.TargetVersion,source=c.CurrentVersion,url=c.Address,md5=c.Md5,size=5000}end
port.outbox_topic=function()return '/test/ota'end
local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
assert(m:ack(m:status().outbox[1].id,true))
assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING')))
assert(m:finish({version=command.TargetVersion,healthy=true,installation_verified=true,data_ok=true}))
assert(m:status().phase=='COMPLETE_PENDING')
local r=R.new({port=port,store=newstore()})
local ok,why=r:flush_outbox()
assert(not ok and why=='GR_RELEASE_PENDING','platform result escaped before GR accepted completion')
assert(#published==0)
r=R.new({port=port,store=newstore()});assert(not r:flush_outbox());assert(#published==0)
local denied=reply(m,'DENY','INSTALL_PENDING');denied.reason='health_or_pending_unverified'
r:on_gr_line('OTA_GR='..json.encode(denied));assert(not r:flush_outbox());assert(#published==0)
local released=reply(m,'RELEASED','COMPLETE');released.outcome='success'
local wrong=clone(released);wrong.hash=string.rep('0',64)
assert(not r:on_gr_line('OTA_GR='..json.encode(wrong)));assert(not r:flush_outbox())
assert(r:on_gr_line('OTA_GR='..json.encode(released)));assert(r:status().phase=='IDLE')
assert(r:flush_outbox());assert(#published==1 and published[1]=='SEND_DATA_REQ')
'''
check('result publication waits for durable GR release across restart', SCENARIO)
check('failed durable release retains result and blocks publication', SCENARIO.split("assert(r:on_gr_line('OTA_GR='..json.encode(released)))")[0] + '''
fail_write=true;assert(not r:on_gr_line('OTA_GR='..json.encode(released)))
assert(not r:flush_outbox());assert(#published==0)
-- A storage error is latched; never pretend clearing the IO fault repairs the journal.
fail_write=false;assert(not r:flush_outbox());assert(#published==0)
''')
