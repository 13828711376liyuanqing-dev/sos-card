"""SAM | 2026-11-10 +08:00 | Regress Unicode probe scripts, bounded child reads and stop/restart ownership without hardware."""
import os
from pathlib import Path
import subprocess
import unittest
import uuid

HERE = Path(__file__).resolve().parent
CSC = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Management.dll', 'System.Core.dll']

class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = HERE / 'logs' / ('regression_' + uuid.uuid4().hex)
        cls.work.mkdir(parents=True)
        fake = cls.work / 'Fake.cs'
        fake.write_text(r'''using System;using System.IO;using System.Linq;using System.Text.RegularExpressions;
class Fake { static void Main(string[] args) {
 if (AppDomain.CurrentDomain.FriendlyName.StartsWith("Hang")) { Console.WriteLine("started");Console.Out.Flush();System.Threading.Thread.Sleep(15000);return; }
 string file=args[Array.IndexOf(args,"-CommandFile")+1];
 string script=File.ReadAllText(file);
 if(file.Any(c=>c>127)||script.Any(c=>c>127)){Console.WriteLine("Could not open file for writing.");Environment.Exit(1);}
 foreach(string line in script.Split('\n')) {
  if(!line.StartsWith("savebin "))continue;
  string target=line.Substring(8).Split(',')[0].Trim('"');
  string fixture=target=="owner.bin"?"owner_fixture.bin":"journal_fixture.bin";
  File.WriteAllBytes(target,File.Exists(fixture)?File.ReadAllBytes(fixture):Enumerable.Repeat((byte)255,8192).ToArray());
 }
 Console.WriteLine("O.K.");
}}''', encoding='utf-8')
        for name in ['FakeCommander.exe', 'HangCommander.exe']:
            subprocess.run([str(CSC), '-nologo', '-out:' + str(cls.work / name), str(fake)], check=True, capture_output=True)
        source = cls.work / 'Source.cs'
        source.write_text((HERE / 'src/YpOtaMonitor.cs').read_text('utf-8').replace('WaitForExit(60000)', 'WaitForExit(1000)'), encoding='utf-8')
        harness = cls.work / 'Regression.cs'
        harness.write_text(r'''using System;using System.IO;using System.Diagnostics;using System.Reflection;using System.Threading;using System.Windows.Forms;
class Regression {
 [STAThread]static int Main(string[] args){try{Run(args);return 0;}catch(Exception e){Console.Error.WriteLine(e);return 1;}}
 static void Run(string[] args){
  if(args[0]=="commands"){
   using(var form=new MainForm()){
    var flags=BindingFlags.NonPublic|BindingFlags.Instance;
    var input=(TextBox)typeof(MainForm).GetField("commandInput",flags).GetValue(form);
    input.Text="进度";typeof(MainForm).GetMethod("SubmitCommand",flags).Invoke(form,null);
    var output=(RichTextBox)typeof(MainForm).GetField("commandOutput",flags).GetValue(form);
    if(!output.Text.Contains("当前已知记录")||!output.Text.Contains("未选择GR串口"))throw new Exception("Normal command entry did not report");
   }
   if(MonitorCommands.Normalize(" 查询进度 ")!="进度"||MonitorCommands.Normalize("版本")!="版本"||MonitorCommands.Normalize("cat1_power key")!="")throw new Exception("Command whitelist broken");
   var e=new MonitorEvidence();e.Observe("OTA_PROGRESS=GR5526:385288/385288");e.Observe("OTA_STEP=HEALTH_IDENTITY");
   e.Owner(new OwnerState{Ok=true,Phase="INSTALL_PENDING",Target="GR5526",Version="1.5.30",Boot="TRIAL"});
   if(!e.Summary.Contains("385288/385288")||!e.Summary.Contains("TRIAL")||!e.Summary.Contains("HEALTH_IDENTITY"))throw new Exception("Summary incomplete");
   e.Owner(new OwnerState{Ok=false,Error="read failed"});
   if(!e.Summary.Contains("read failed"))throw new Exception("Failed refresh hidden by cached success");
   foreach(var c in MonitorCommands.Queries("进度"))if(c.Contains("key")||c.Contains("reset")||c.Contains("hold_on"))throw new Exception("Progress query changes power");
   return;
  }
  if(args[0]=="startup"){
   var x=new Cat1Startup();var h=new HoldSession();int keys=0;bool on=false;
   Func<string,int,string> ask=(c,t)=>{
    if(c=="cat1_power on")return "[CAT1 POWER] rail_request=on code=0x0000;";
    if(c=="cat1_power status")return "[CAT1 POWER] rail_request=1 factory_hold=0;";
    if(c=="cat1_power key"){keys++;on=true;return "[CAT1 POWER] manual_key code=0x0000;";}
    if(c=="cat1_power hold_on")return "[CAT1 POWER] factory_hold=1 result=0;";
    return on?"[CAT1 RX] [AT_INFO] running":"";
   };
   if(!x.Start(ask,m=>{},h,false)||keys!=1||!h.Confirmed)throw new Exception("Cold start failed");
   if(!x.Start(ask,m=>{},h,false)||keys!=1)throw new Exception("Running module pulsed twice");
   var lost=new Cat1Startup();int lostKeys=0;
   Func<string,int,string> lostAsk=(c,t)=>c=="cat1_power on"?"[CAT1 POWER] rail_request=on code=0x0000;":c=="cat1_power status"?"[CAT1 POWER] rail_request=1 factory_hold=0;":c=="cat1_power key"?(++lostKeys>0?"":""):"";
   lost.Start(lostAsk,m=>{},new HoldSession(),false);lost.Start(lostAsk,m=>{},new HoldSession(),false);
   if(lostKeys!=1)throw new Exception("Lost ACK retried key");
   var usb=new Cat1Startup();int unsafeKeys=0;
   usb.Start((c,t)=>{if(c=="cat1_power key")unsafeKeys++;return c=="cat1_power on"?"[CAT1 POWER] rail_request=on code=0x0000;":"";},m=>{},new HoldSession(),true);
   if(unsafeKeys!=0)throw new Exception("USB-present module toggled");
   return;
  }
  if(args[0]=="hold"){
   var h=new HoldSession();var commands=new System.Collections.Generic.List<string>();
   Func<string,string> ask=c=>{commands.Add(c);return c.EndsWith("status")?"[CAT1 POWER] rail_request=0 factory_hold=0; VBAT and boot unverified":c.EndsWith("hold_on")?"[CAT1 POWER] factory_hold=1 result=0; ends on release or reboot":"[CAT1 POWER] factory_hold=0; normal policy restored, rail unchanged";};
   if(!h.Acquire(ask)||!h.Owned||commands.Count!=2)throw new Exception("Hold not acquired");
   if(!h.Release(ask)||h.Owned)throw new Exception("Hold not released");
   commands.Clear();var borrowed=new HoldSession();
   if(!borrowed.Acquire(c=>"[CAT1 POWER] rail_request=1 factory_hold=1; VBAT and boot unverified")||borrowed.Owned)throw new Exception("Existing hold claimed");
   borrowed.Release(c=>{throw new Exception("Foreign hold released");});
   var refused=new HoldSession();if(refused.Acquire(c=>c.EndsWith("status")?"[CAT1 POWER] rail_request=0 factory_hold=0; VBAT and boot unverified":"[PWR] deny hold_on owner=OTA"))throw new Exception("Denied hold counted active");
   var unknown=new HoldSession();if(unknown.Acquire(c=>""))throw new Exception("Unknown status changed power");
   return;
  }
  if(args[0]=="evidence"){
   var e=new MonitorEvidence();
   e.Observe("OTA_PROGRESS=GR5526:385288/385288");
   if(!e.Versions.Contains("未读到"))throw new Exception("Target became actual version");
   e.Observe("[FW_VERSION] YP001_FW|GR5526|001.005.029|33");
   e.Observe("LuatOS Ver: 001.005.027");
   if(!e.Versions.Contains("1.5.29")||!e.Versions.Contains("1.5.27"))throw new Exception("Independent versions missing");
   e.Observe("[FOTA_STATUS] RECOVERY_HOLD");e.Observe("OTA_REASON=ACTIVATION_RECHECK_FAILED");
   e.Observe("[OTA] ACTIVATION_RECHECK_FAILED VERIFY_CANDIDATE");
   if(!e.Status.Contains("RECOVERY_HOLD")||!e.Status.Contains("VERIFY_CANDIDATE"))throw new Exception("Reason/detail lost");
   if(!MainForm.GrExplain(new OwnerState{Boot="TRIAL",Phase="INSTALL_PENDING",Target="GR5526"}).Contains("尚未确认"))throw new Exception("Trial counted installed");
   if(!MainForm.OtaRisk("TRIAL=SPENT").Contains("单独不代表失败"))throw new Exception("SPENT alone counted failed");
   return;
  }
  if(args[0]=="beacon"){
   var basic=MainForm.ParseBeacon("[OTA] B PAUSED nil/0 SPENT GR_NACK_4 N none S TRIAL_SPENT P G385288/385288");
   if(basic==null||basic.Reason!="GR_NACK_4"||basic.Step!="TRIAL_SPENT"||basic.Progress!="G385288/385288"||basic.Ticket!="SPENT")throw new Exception("Basic beacon misparsed");
   var native=MainForm.ParseBeacon("[OTA] B INSTALLING INSTALL/1 SPENT nil N WRITING RETRY nil 4096 S NATIVE_WAIT P none");
   if(native==null||native.Native!="WRITING RETRY nil 4096"||native.Reason!="nil"||native.Step!="NATIVE_WAIT")throw new Exception("Variable-width native beacon misparsed");
   if(MainForm.ParseBeacon("[OTA] B incomplete")!=null)throw new Exception("Incomplete beacon accepted");
   return;
  }
  if(args[0]=="completion"){
   if(!MainForm.VersionsMatch("001.005.031","001.005.031","1.5.31"))throw new Exception("Matching versions rejected");
   if(MainForm.VersionsMatch("1.5.30","1.5.31","1.5.31")||MainForm.VersionsMatch("1.5.31","","1.5.31")||MainForm.VersionsMatch("999999999999999999.0.1","1.5.31","1.5.31"))throw new Exception("Unverified versions accepted");
   var successState=new OwnerState{Ok=true,Generation=10,Epoch=4,Job=new string('a',64),Hash=new string('b',64),Phase="COMPLETE",Target="CAT1",Version="1.5.31",Actual="1.5.31",Outcome="success",Boot="CONFIRMED"};
   if(!MainForm.SuccessRecord(successState))throw new Exception("Verified success rejected");
   var latest=new OwnerState{Ok=true,Generation=11,Epoch=4,Job=new string('a',64),Hash=new string('b',64),Phase="COMPLETE",Target="CAT1",Version="1.5.31",Actual="1.5.31",Outcome="success",Boot="CONFIRMED"};
   if(!MainForm.SameCompletedTask(successState,latest))throw new Exception("Same completed task rejected");
   latest.Job=new string('c',64);if(MainForm.SameCompletedTask(successState,latest))throw new Exception("Different job counted complete");
   latest.Job=successState.Job;latest.Epoch=5;if(MainForm.SameCompletedTask(successState,latest))throw new Exception("Different epoch counted complete");
   latest.Epoch=4;latest.Hash=new string('d',64);if(MainForm.SameCompletedTask(successState,latest))throw new Exception("Different hash counted complete");
   successState.Boot="TRIAL";if(MainForm.SuccessRecord(successState))throw new Exception("Trial counted complete");
   successState.Boot="CONFIRMED";successState.Actual="1.5.30";if(MainForm.SuccessRecord(successState))throw new Exception("Wrong actual version counted complete");
   successState.Actual="1.5.31";successState.Job=new string('0',64);if(MainForm.SuccessRecord(successState))throw new Exception("Missing identity counted complete");
   return;
  }
  if(args[0]=="risk"){
   if(MainForm.OtaRisk("[FOTA_STATUS] OTA_STEP=TRIAL_SPENT")==""||MainForm.OtaRisk("OTA_REASON=GR_NACK_4")==""||MainForm.OtaRisk("OTA_REASON=nil")!="")throw new Exception("Paused task was misclassified");
   return;
  }
  if(args[0]=="stop"){
   using(var form=new MainForm()){
    var f=BindingFlags.NonPublic|BindingFlags.Instance;
    typeof(MainForm).GetField("running",f).SetValue(form,true);
    var workers=(System.Collections.Generic.List<Thread>)typeof(MainForm).GetField("workers",f).GetValue(form);
    var worker=new Thread(()=>Thread.Sleep(600));workers.Add(worker);worker.Start();
    typeof(MainForm).GetMethod("Stop",f).Invoke(form,null);
    var start=(Button)typeof(MainForm).GetField("btnStart",f).GetValue(form);
    if(start.Enabled)throw new Exception("Start enabled before previous workers released ports");
    var clock=Stopwatch.StartNew();
    while(worker.IsAlive&&clock.ElapsedMilliseconds<4000){Application.DoEvents();Thread.Sleep(10);}
    for(int i=0;i<20;i++){Application.DoEvents();Thread.Sleep(10);}
    if(worker.IsAlive)throw new Exception("Worker did not stop");
   }return;
  }
  var watch=Stopwatch.StartNew();var state=GrProbe.Read(args[1],args[2]);
  if(args[0].StartsWith("record_")){
   bool expect=args[0]=="record_valid";
   if(state.Ok!=expect)throw new Exception("Invalid/ambiguous record was accepted or valid legacy/current record rejected: "+state.Error);
   if(expect){byte[] raw=File.ReadAllBytes(Path.Combine(args[2],"owner_fixture.bin"));uint generation=0;
    foreach(int offset in new[]{0,4096})if(BitConverter.ToUInt32(raw,offset)!=0xffffffff)generation=Math.Max(generation,BitConverter.ToUInt32(raw,offset+4));
    if(state.Generation!=generation)throw new Exception("Newest committed owner not selected");}
   return;
  }
  if(args[0]=="unicode"){
   if(!state.Ok)throw new Exception(state.Error);
   string script=File.ReadAllText(Path.Combine(args[2],"probe.jlink"));
   if(script.IndexOf("SetRestartOnClose = 0")<0)throw new Exception("Probe must preserve target run state");
   foreach(string line in script.Split('\n'))if(line.Trim()=="h"||line.Trim()=="r"||line.Trim()=="g"||line.StartsWith("erase ")||line.StartsWith("loadbin "))throw new Exception("Monitor changes target state");
  }else{
   if(state.Ok||watch.ElapsedMilliseconds>6000)throw new Exception("Hung process was not bounded");
   if(!File.Exists(Path.Combine(args[2],"jlink.txt")))throw new Exception("Timeout log missing");
  }
 }
}''', encoding='utf-8')
        cls.exe = cls.work / 'Regression.exe'
        subprocess.run([str(CSC), '-nologo', '-codepage:65001', '-main:Regression', '-out:' + str(cls.exe)] + ['-reference:' + r for r in REFS] + [str(source), str(harness)], check=True, capture_output=True)

    def test_unicode_probe_uses_relative_ascii_paths(self):
        folder = self.work / '中文 工具6 😀' / 'jlink'
        result = subprocess.run([str(self.exe), 'unicode', str(self.work / 'FakeCommander.exe'), str(folder)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_hung_probe_is_bounded(self):
        result = subprocess.run([str(self.exe), 'timeout', str(self.work / 'HangCommander.exe'), str(self.work / 'timeout')], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_owner_and_boot_records_reject_invalid_samples(self):
        import struct
        import zlib
        def owner(generation=1, committed=True, legacy=False):
            page = bytearray(b'\xff' * 4096)
            size = 360 if legacy else 368
            page[:size] = b'\0' * size
            struct.pack_into('<III', page, 0, 0x594f5431 if legacy else 0x594f5432, generation, 4)
            page[12] = 4
            for offset, value in [(13, b'a'*64), (78, b'b'*64), (143, b'CAT1'), (151, b'1.5.31'), (215, b'1.5.30'), (279, b'1.5.31'), (343, b'success')]:
                page[offset:offset+len(value)] = value
            crc_at = 352 if legacy else 360
            struct.pack_into('<II', page, crc_at, zlib.crc32(page[:crc_at]), 0 if committed else 0xffffffff)
            return page
        erased = b'\xff' * 4096
        valid = owner()
        bad_crc = bytearray(valid); bad_crc[20] ^= 1
        bad_tail = bytearray(valid); bad_tail[500] = 0
        conflict = owner(); conflict[13] = ord('c'); struct.pack_into('<I', conflict, 360, zlib.crc32(conflict[:360]))
        words = [0] * 31
        words[0:4] = [0x59504231, 8, 0xbcc4a6a4, 5]
        words[7] = words[17] = 389000; words[27] = 1
        header = struct.pack('<31I', *words)
        words[29] = zlib.crc32(header[:116])
        journal = struct.pack('<31I', *words) + b'\xff' * (4096-124)
        words[2] ^= 1; words[29] = zlib.crc32(struct.pack('<31I', *words)[:116])
        bad_layout = struct.pack('<31I', *words) + b'\xff' * (4096-124)
        cases = [('record_valid', valid+erased, journal+erased),
                 ('record_invalid', valid+erased, bad_layout+erased),
                 ('record_invalid', valid+erased, journal+journal),
                 ('record_valid', valid+erased, erased*2), ('record_valid', owner(legacy=True)+erased, erased*2),
                 ('record_invalid', bad_crc+erased, erased*2), ('record_invalid', bad_tail+erased, erased*2),
                 ('record_invalid', valid+conflict, erased*2), ('record_invalid', owner(committed=False)+erased, erased*2)]
        for i, (mode, own, journal) in enumerate(cases):
            with self.subTest(case=i):
                folder = self.work / ('record_' + str(i)); folder.mkdir()
                (folder / 'owner_fixture.bin').write_bytes(own)
                (folder / 'journal_fixture.bin').write_bytes(journal)
                result = subprocess.run([str(self.exe), mode, str(self.work / 'FakeCommander.exe'), str(folder)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_saved_real_board_snapshots_remain_readable(self):
        flash_logs = HERE.parent / 'gr_release/GR_JLink_Flash/logs'
        candidates = [flash_logs / 'bench_20261110_b35/pre.bin', flash_logs / 'newboard_20261110_b35/stable1.bin']
        snapshots = [p for p in candidates if p.exists()]
        if not snapshots:
            self.skipTest('Saved board snapshots are not present on this computer')
        for i, path in enumerate(snapshots):
            with self.subTest(snapshot=path.name, folder=path.parent.name):
                data = path.read_bytes()
                folder = self.work / ('saved_board_' + str(i)); folder.mkdir()
                (folder / 'owner_fixture.bin').write_bytes(data[0xf9000:0xfb000])
                (folder / 'journal_fixture.bin').write_bytes(data[0xf7000:0xf9000])
                result = subprocess.run([str(self.exe), 'record_valid', str(self.work / 'FakeCommander.exe'), str(folder)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_command_whitelist_and_progress_summary(self):
        result = subprocess.run([str(self.exe), 'commands'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_startup_and_lost_ack_never_double_pulse(self):
        result = subprocess.run([str(self.exe), 'startup'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_hold_requires_ack_and_preserves_foreign_hold(self):
        result = subprocess.run([str(self.exe), 'hold'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_versions_pause_details_and_trial_are_distinct(self):
        result = subprocess.run([str(self.exe), 'evidence'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_beacon_fields_follow_current_firmware_markers(self):
        result = subprocess.run([str(self.exe), 'beacon'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_completion_requires_matching_versions_and_confirmed_boot(self):
        result = subprocess.run([str(self.exe), 'completion'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_spent_and_nack_are_reported(self):
        result = subprocess.run([str(self.exe), 'risk'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_stop_waits_for_worker_release(self):
        result = subprocess.run([str(self.exe), 'stop'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

if __name__ == '__main__':
    unittest.main()
