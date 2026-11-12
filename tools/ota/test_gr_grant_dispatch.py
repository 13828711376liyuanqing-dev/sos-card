# SAM | 2026-11-10 +08:00 | Exercise callback/task separation, lease age and GR health routing without hardware.
import unittest
from test_cat_manager import runtime


class GrantDispatch(unittest.TestCase):
    def setUp(self):
        self.lua = runtime()
        self.lua.execute('''
          clock=1000;calls=0;health_calls=0;mcu={ticks=function()return clock end}
          j={id=string.rep('b',64),hash=string.rep('c',64),target='GR5526',version='1.1.0'}
          s={phase='WAIT_ACTIVATE',job=j,epoch=1}
          package.loaded.ota_manager={new=function()return {
            status=function()return s end,
            on_gr=function(_,msg)calls=calls+1;coroutine.yield('verify');return true end,
            reconcile=function()return true end,peek_outbox=function()return nil end
          }end}
          port.health=function()health_calls=health_calls+1;return nil,'HEALTH_IDENTITY'end
          r=require('ota_runtime').new({store=newstore(),codec=json,port=port})
          function frame(epoch)
            return 'OTA_GR='..json.encode({op='GRANT',phase='INSTALL_PENDING',reason='ok',
              commit_safe=true,job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=epoch or 1})
          end
        ''')

    def test_callback_defers_yielding_verification_and_deduplicates(self):
        self.lua.execute('''
          assert(r:receive_gr_line(frame()));assert(r:receive_gr_line(frame()));assert(calls==0)
          local c=coroutine.create(function()return r:tick()end)
          local ok,why=coroutine.resume(c);assert(ok and why=='verify',tostring(why))
          assert(calls==1);assert(coroutine.resume(c));assert(coroutine.status(c)=='dead')
          assert(r:tick());assert(calls==1)
        ''')

    def test_expired_or_paused_grant_never_refreshes_authority(self):
        self.lua.execute('''
          assert(r:receive_gr_line(frame()));clock=4000
          assert(r:receive_gr_line(frame()));local ok,why=r:tick()
          assert(not ok and why=='GR_GRANT_EXPIRED');assert(calls==0)
          clock=5000;assert(r:receive_gr_line(frame()));r:pause();r:tick();assert(calls==0)
        ''')

    def test_wrong_epoch_not_queued(self):
        self.lua.execute("local ok,why=r:receive_gr_line(frame(2));assert(not ok and why=='GR_GRANT_IDENTITY');assert(calls==0)")

    def test_gr_does_not_use_cat1_health_checker(self):
        self.lua.execute("s.phase='RECOVERY_HOLD';r:tick();assert(health_calls==0)")


class GrantRecheck(unittest.TestCase):
    def test_real_manager_accepts_yielding_file_check_in_ota_task(self):
        lua = runtime()
        lua.execute('''
          m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
          assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
          local candidates=require('ota_candidates')
          local api={exists=function()return true end,open=function()return {
            seek=function(_,w,o)return w=='end' and 4096 or (o or 0)end,
            read=function(_,n)return string.rep('x',n)end,close=function()return true end}end}
          local hash={hash_begin=function()return {} end,hash_update=function()return true end,
            hash_finish=function()return string.rep('a',64)end}
          local files=candidates.new(hash,api)
          sys={wait=function()coroutine.yield('file_wait')end}
          port.verify_candidate=function()return type(files.verify_file(candidates.path(string.rep('a',64)),{size=4096}))=='table'end
          package.loaded.ota_manager={new=function()return m end}
          mcu={ticks=function()return 1000 end}
          local r=require('ota_runtime').new({store=newstore(),codec=json,port=port})
          local msg=reply(m,'GRANT','INSTALL_PENDING');msg.reason='ok';msg.commit_safe=true
          assert(r:receive_gr_line('OTA_GR='..json.encode(msg)));assert(activation==0)
          local c=coroutine.create(function()return r:tick()end)
          local ok,why=coroutine.resume(c);assert(ok and why=='file_wait',tostring(why))
          assert(activation==0);assert(coroutine.resume(c));assert(activation==1)
          assert(m:status().phase=='INSTALLING')
        ''')

    def test_permission_must_still_be_fresh_after_yield(self):
        lua = runtime()
        lua.execute('''
          m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
          assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
          local safe=true;local diagnostics={};_G.ota_diag=function(x)diagnostics[#diagnostics+1]=x end
          port.safe=function()return safe end
          port.verify_candidate=function()coroutine.yield('verify');return true end
          local c=coroutine.create(function()return m:on_gr(reply(m,'GRANT','INSTALL_PENDING'))end)
          local ok,why=coroutine.resume(c);assert(ok and why=='verify')
          safe=false;assert(coroutine.resume(c));assert(activation==0)
          assert(m:status().reason=='ACTIVATION_RECHECK_FAILED')
          assert(diagnostics[1]=='[OTA] ACTIVATION_RECHECK_FAILED SAFE_AFTER_VERIFY')
        ''')


if __name__ == '__main__':
    unittest.main()
