# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-21 +08:00 | Real TCP MQTT packets against a strictly local test fixture."""
import json
import threading
import unittest
import hashlib
import test_disk_download
from sim_backend.mqtt_fixture import Broker, Client
from test_cat_manager import runtime

class Tests(unittest.TestCase):
    def test_mqtt_to_signed_http_disk_candidate(self):
        # SAM | 2026-10-21 +08:00 | Join real MQTT, actual manager and real disk/HTTP downloader; activation remains a counted stub.
        disk=test_disk_download.Tests(methodName='test_binary_resume_new_runtime')
        disk.setUp()
        try:
            self.device.subscribe('test/yp001/command')
            self.platform.subscribe('test/yp001/result')
            raw=disk.image;digest=hashlib.sha256(raw).hexdigest()
            cmd=dict(MsgType='otaMsg',CurrentVersion='1.0.0',TargetVersion='1.1.0',Address=disk.url,
                     Md5=hashlib.md5(raw).hexdigest(),Time=123)
            self.assertTrue(self.platform.publish('test/yp001/command',json.dumps(cmd)))
            _,incoming=self.device.receive()
            self.assertFalse(disk.checkpoint.exists())
            lua=runtime()
            lua.globals().incoming=incoming
            lua.globals().digest=digest
            def prepare():
                # Grant must precede all downloading, including the interrupted first chunk.
                self.assertFalse(disk.checkpoint.exists())
                downloader=disk.runtime()
                downloader.execute('assert(d:step())')
                del downloader
                downloader=disk.runtime()
                downloader.execute("while d:status().state=='DOWNLOADING' do assert(d:step()) end;assert(d:verify())")
                return True
            lua.globals().py_prepare=prepare
            lua.execute('''
              local original=port.resolve
              port.resolve=function(c)local j=original(c);j.hash=digest;return j end
              port.prepare=function()return py_prepare()end
              local m=newmanager();assert(m:accept(json.decode(incoming)))
              assert(activation==0);assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
              assert(m:prepare());assert(activation==0)
              assert(m:on_gr(reply(m,'STATUS','PREPARED')))
              assert(m:request_activation());assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING')))
              assert(activation==1)
              assert(m:finish({version='1.1.0',healthy=true,installation_verified=true,data_ok=true}))
              local r=reply(m,'RELEASED','COMPLETE');r.outcome='success';assert(m:on_gr(r))
              manager=m
            ''')
            self.assertEqual((disk.folder/'candidate.part').read_bytes(),raw)
            for _ in range(2):
                payload=lua.eval('json.encode(manager:status().outbox[1].payload)')
                confirmed=self.device.publish('test/yp001/result',payload)
                _,received=self.platform.receive()
                self.assertEqual(json.loads(payload),json.loads(received))
                lua.globals().confirmed=confirmed
                lua.execute('assert(manager:ack(manager:status().outbox[1].id,confirmed))')
            lua.execute('assert(#manager:status().outbox==0)')
        finally:disk.tearDown()

    def setUp(self):
        self.broker=Broker()
        self.thread=threading.Thread(target=self.broker.serve_forever,daemon=True)
        self.thread.start()
        self.platform=Client(self.broker.server_address[1],'platform')
        self.device=Client(self.broker.server_address[1],'device')

    def tearDown(self):
        self.platform.close();self.device.close()
        self.broker.shutdown();self.broker.server_close();self.thread.join(2)

    def test_qos1_customer_command_and_outbox_reconnect(self):
        self.device.subscribe('test/yp001/command')
        self.platform.subscribe('test/yp001/result')
        command={'MsgType':'otaMsg','CurrentVersion':'1.0.0','TargetVersion':'1.1.0',
                 'Address':'http://127.0.0.1/test.pkg','Md5':'a'*32,'Time':123}
        self.assertTrue(self.platform.publish('test/yp001/command',json.dumps(command)))
        topic,payload=self.device.receive()
        self.assertEqual(topic,'test/yp001/command')
        self.assertEqual(json.loads(payload),command)
        lua=runtime();lua.globals().incoming=payload
        lua.execute('''m=newmanager();assert(m:accept(json.decode(incoming)))
          assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
          assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')))
          assert(m:request_activation());assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING')))
          assert(m:finish({version='1.1.0',healthy=true,installation_verified=true,data_ok=true}))
          local r=reply(m,'RELEASED','COMPLETE');r.outcome='success';assert(m:on_gr(r))
          assert(#m:status().outbox==2)''')
        self.device.close()
        lua.execute("m=newmanager();assert(#m:status().outbox==2);assert(not m:ack(m:status().outbox[1].id,false))")
        self.device=Client(self.broker.server_address[1],'device-reconnected')
        for _ in range(2):
            body=lua.eval('json.encode(m:status().outbox[1].payload)')
            confirmed=self.device.publish('test/yp001/result',body)
            self.assertTrue(confirmed)
            _,received=self.platform.receive()
            self.assertEqual(json.loads(received),json.loads(body))
            lua.globals().confirmed=confirmed
            lua.execute('assert(m:ack(m:status().outbox[1].id,confirmed))')
        lua.execute('assert(#newmanager():status().outbox==0)')

    def test_unsubscribed_topic_not_routed(self):
        self.device.subscribe('test/other')
        self.platform.publish('test/yp001/command','{}')
        with self.assertRaises(TimeoutError):self.device.receive(timeout=.15)

if __name__=='__main__':unittest.main()
