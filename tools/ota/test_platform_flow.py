# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-21 +08:00 | Customer-field release mapping and actual Lua manager sequential component flow."""
import hashlib
import unittest
from test_cat_manager import runtime
from sim_backend.release_mapping import command, resolve

class Tests(unittest.TestCase):
    def test_mapping_rejects_changed_command(self):
        release=dict(target='GR5526',source='1.0.0',version='1.1.0',url='http://127.0.0.1:8766/packages/test',
                     md5='a'*32,hash='b'*64,id='c'*64)
        cmd=command(release,123)
        self.assertEqual(resolve([release],cmd)['target'],'GR5526')
        self.assertEqual(set(cmd),{'MsgType','CurrentVersion','TargetVersion','Address','Md5','Time'})
        for key in ('Address','CurrentVersion','TargetVersion','Md5'):
            changed=dict(cmd);changed[key]='changed'
            with self.assertRaises(ValueError):resolve([release],changed)
        with self.assertRaises(ValueError):resolve([release,release],cmd)

    def test_gr_then_cat_and_pending_results(self):
        lua=runtime()
        releases=[]
        for target,source,version in [('GR5526','1.0.0','1.1.0'),('CAT1','1.1.0','1.2.0')]:
            digest=hashlib.sha256(target.encode()).hexdigest()
            releases.append(dict(target=target,source=source,version=version,url='http://127.0.0.1:8766/packages/'+digest,
                md5=hashlib.md5(target.encode()).hexdigest(),hash=digest,id=hashlib.sha256((target+version).encode()).hexdigest()))
        for index,release in enumerate(releases):
            lua.globals()['cmd'+str(index+1)]=lua.table_from(command(release,123))
            lua.globals()['mapped'+str(index+1)]=lua.table_from(resolve(releases,command(release,123)))
        lua.execute('''
          port.resolve=function(c)
            if c.Address==cmd1.Address then return clone(mapped1) end
            if c.Address==cmd2.Address then return clone(mapped2) end
            return nil
          end
          local m=newmanager()
          assert(m:accept(cmd1));assert(not m:accept(cmd2));assert(activation==0)
          assert(m:on_gr(reply(m,'GRANT','DOWNLOADING',1)))
          assert(m:prepare());assert(not m:accept(cmd2))
          assert(m:on_gr(reply(m,'STATUS','PREPARED',1)))
          assert(m:request_activation());assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING',1)))
          assert(activation==1);assert(not m:accept(cmd2))
          m=newmanager();assert(m:status().phase=='INSTALLING')
          assert(m:finish({version='1.1.0',healthy=true,installation_verified=true,data_ok=true}))
          assert(not m:accept(cmd2))
          local result=reply(m,'RELEASED','COMPLETE',1);result.outcome='success';assert(m:on_gr(result))
          assert(m:status().phase=='IDLE' and #m:status().outbox==2)
          assert(m:accept(cmd2));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING',2)))
          assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED',2)))
          assert(m:request_activation());assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING',2)))
          assert(activation==2)
          assert(m:finish({version='1.1.0',healthy=true,installation_verified=true,data_ok=true}))
          result=reply(m,'RELEASED','COMPLETE',2);result.version='1.1.0';result.outcome='fail'
          assert(m:on_gr(result));assert(m:status().phase=='IDLE')
          local q=m:status().outbox;assert(#q==4)
          assert(q[2].payload.Status=='success' and q[2].payload.Version=='1.1.0')
          assert(q[4].payload.Status=='fail' and q[4].payload.Version=='1.1.0')
          assert(not m:ack(q[1].id,false));assert(#m:status().outbox==4)
          for i=1,4 do assert(m:ack(m:status().outbox[1].id,true)) end
          assert(#newmanager():status().outbox==0)
        ''')

if __name__=='__main__':unittest.main()
