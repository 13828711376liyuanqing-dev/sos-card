"""SAM | 2026-11-10 +08:00 | Exercise initialization gates offline without J-Link access."""
import os
import re
from pathlib import Path
import subprocess
import unittest
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CSC = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
REFS = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.IO.Compression.dll',
        'System.IO.Compression.FileSystem.dll', 'System.Web.Extensions.dll', 'System.Numerics.dll']
PORTABLE = ROOT / 'tools/ota/portable'
SOURCES = [PORTABLE / name for name in ('PackCore.cs', 'Cat1Native.cs', 'BundleSigning.cs',
           'FirmwareIdentity.cs', 'StoredZipWriter.cs', 'GrProjectNative.cs')]


class InitializationTests(unittest.TestCase):
    def test_hung_commander_is_terminated_and_logged(self):
        directory = HERE / 'logs' / ('timeout_test_' + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        fake_source = directory / 'FakeCommander.cs'
        fake_source.write_text('class FakeCommander { static void Main() { System.Console.WriteLine("mock started"); '
                               'System.Console.Out.Flush(); System.Threading.Thread.Sleep(30000); } }', encoding='utf-8')
        fake = directory / 'FakeCommander.exe'
        subprocess.run([str(CSC), '-nologo', '-out:' + str(fake), str(fake_source)], check=True, capture_output=True)
        source = directory / 'FlasherUnderTest.cs'
        source.write_text(re.sub(r'const string JLINK = @"[^"]+";',
                          lambda _: 'const string JLINK = @"' + str(fake) + '";',
                          (HERE / 'src/GrJLinkFlash.cs').read_text(encoding='utf-8'), count=1), encoding='utf-8')
        harness = directory / 'TimeoutTest.cs'
        harness.write_text(r'''
using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
class TimeoutTest {
    static void Main(string[] args) {
        var watch = Stopwatch.StartNew();
        try {
            typeof(Flasher).GetMethod("JLink", BindingFlags.Static | BindingFlags.NonPublic).Invoke(null,
                new object[] { false, new string[0], args[0], 1000 });
            Environment.Exit(2);
        } catch (TargetInvocationException e) {
            if (!(e.InnerException is Flasher.Stop) || !e.InnerException.Message.Contains("超时") ||
                watch.ElapsedMilliseconds > 15000 || !File.Exists(args[0]))
                Environment.Exit(3);
        }
    }
}
''', encoding='utf-8')
        exe = directory / 'TimeoutTest.exe'
        subprocess.run([str(CSC), '-nologo', '-codepage:65001', '-main:TimeoutTest', '-out:' + str(exe)]
                       + ['-reference:' + ref for ref in REFS]
                       + [str(source), str(harness)] + [str(p) for p in SOURCES], check=True, capture_output=True)
        result = subprocess.run([str(exe), str(directory / 'timeout.log')], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_initialization_gates_and_pairing(self):
        directory = HERE / 'logs' / ('initialization_test_' + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        source = directory / 'InitializationTest.cs'
        source.write_text(r'''
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Collections.Generic;
class InitializationTest {
    static MethodInfo State, Prepare;
    static void Reject(Action action, string reason) {
        try { action(); }
        catch (TargetInvocationException e) {
            if (e.InnerException is Flasher.Stop) return;
            throw;
        }
        throw new Exception("Accepted forbidden case: " + reason);
    }
    static byte[] Blank(byte[] app) {
        byte[] pre = Enumerable.Repeat((byte)255, 0x100000).ToArray();
        BitConverter.GetBytes(0x202000u).CopyTo(pre, 8);
        BitConverter.GetBytes(0x202000u).CopyTo(pre, 12);
        app.CopyTo(pre, 0x2000);
        return pre;
    }
    static uint Crc(byte[] data, int offset, int size) {
        uint crc = 0xffffffff;
        for (int i = offset; i < offset + size; i++) {
            crc ^= data[i];
            for (int bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ ((crc & 1) == 0 ? 0u : 0xedb88320u);
        }
        return ~crc;
    }
    static void Owner(byte[] pre, int page, uint generation, byte phase, string target, uint total, uint durable) {
        int offset = 0xf9000 + page * 4096;
        Array.Clear(pre, offset, 368);
        BitConverter.GetBytes(0x594f5432u).CopyTo(pre, offset);
        BitConverter.GetBytes(generation).CopyTo(pre, offset + 4);
        BitConverter.GetBytes(3u).CopyTo(pre, offset + 8);
        pre[offset + 12] = phase;
        System.Text.Encoding.ASCII.GetBytes(new string('a', 64)).CopyTo(pre, offset + 13);
        System.Text.Encoding.ASCII.GetBytes(new string('b', 64)).CopyTo(pre, offset + 78);
        System.Text.Encoding.ASCII.GetBytes(target).CopyTo(pre, offset + 143);
        System.Text.Encoding.ASCII.GetBytes("future-rule").CopyTo(pre, offset + 151);
        System.Text.Encoding.ASCII.GetBytes("old-rule").CopyTo(pre, offset + 215);
        BitConverter.GetBytes(total).CopyTo(pre, offset + 352);
        BitConverter.GetBytes(durable).CopyTo(pre, offset + 356);
        BitConverter.GetBytes(Crc(pre, offset, 360)).CopyTo(pre, offset + 360);
    }
    [STAThread]
    static void Main(string[] args) {
        try { Run(args); }
        catch (Exception e) { Console.Error.WriteLine(e); Environment.Exit(1); }
    }
    static void Run(string[] args) {
        State = typeof(Flasher).GetMethod("CheckInitialState", BindingFlags.NonPublic | BindingFlags.Static);
        Prepare = typeof(Flasher).GetMethod("PrepareInitialBoot", BindingFlags.NonPublic | BindingFlags.Static);
        if (State == null || Prepare == null) throw new Exception("Missing initialization safety gates");
        byte[] app = File.ReadAllBytes(args[0]);
        byte[] pre = Blank(app);
        byte[] paired = (byte[])Prepare.Invoke(null, new object[] { pre, app });
        byte[] template = File.ReadAllBytes(args[1]);
        if (paired.Length != template.Length) throw new Exception("Boot length changed");
        for (int i = 0; i < paired.Length; i++)
            if ((i < 0x71f0 || i >= 0x7218) && paired[i] != template[i]) throw new Exception("Boot code modified");
        byte[] retainedB = (byte[])pre.Clone(); retainedB[0x80000] = 0x42;
        State.Invoke(null, new object[] { retainedB });
        byte[] emptyOwner = (byte[])retainedB.Clone(); Owner(emptyOwner, 0, 1, 1, "GR5526", 0, 0);
        State.Invoke(null, new object[] { emptyOwner });
        foreach (int offset in new[] {0xec000, 0xf6000, 0xf7000, 0xf8000, 0xf9000, 0xfa000}) {
            byte[] bad = (byte[])pre.Clone(); bad[offset] = 0;
            Reject(() => State.Invoke(null, new object[] { bad }), "nonempty reserved area " + offset);
        }
        foreach (byte phase in new byte[] {0, 2, 3, 4, 255}) {
            byte[] bad = (byte[])pre.Clone(); Owner(bad, 0, 1, phase, "GR5526", 0, 0);
            Reject(() => State.Invoke(null, new object[] { bad }), "active or unsupported owner phase");
        }
        foreach (uint total in new uint[] { 1, 4096, 0x80000000 }) {
            byte[] bad = (byte[])pre.Clone(); Owner(bad, 0, 1, 1, "GR5526", total, 0);
            Reject(() => State.Invoke(null, new object[] { bad }), "allocated or owned B");
        }
        byte[] catOwner = (byte[])pre.Clone(); Owner(catOwner, 0, 1, 1, "CAT1", 0, 0);
        Reject(() => State.Invoke(null, new object[] { catOwner }), "CAT1 owner");
        byte[] durableOwner = (byte[])pre.Clone(); Owner(durableOwner, 0, 1, 1, "GR5526", 0, 1);
        Reject(() => State.Invoke(null, new object[] { durableOwner }), "durable progress");
        byte[] badCrc = (byte[])emptyOwner.Clone(); badCrc[0xf9000 + 360] ^= 1;
        Reject(() => State.Invoke(null, new object[] { badCrc }), "bad owner CRC");
        byte[] conflict = (byte[])emptyOwner.Clone(); Owner(conflict, 1, 1, 1, "GR5526", 0, 0);
        conflict[0xfa000 + 13] = (byte)'c';
        BitConverter.GetBytes(Crc(conflict, 0xfa000, 360)).CopyTo(conflict, 0xfa000 + 360);
        Reject(() => State.Invoke(null, new object[] { conflict }), "conflicting generations");
        byte[] partial = (byte[])emptyOwner.Clone();
        BitConverter.GetBytes(0xffffffffu).CopyTo(partial, 0xf9000 + 364);
        Reject(() => State.Invoke(null, new object[] { partial }), "uncommitted owner");
        byte[] newer = (byte[])emptyOwner.Clone(); Owner(newer, 1, 2, 3, "GR5526", 0, 0);
        Reject(() => State.Invoke(null, new object[] { newer }), "newest record is installing");
        byte[] sameGeneration = (byte[])emptyOwner.Clone(); Owner(sameGeneration, 1, 1, 1, "GR5526", 0, 0);
        State.Invoke(null, new object[] { sameGeneration });
        byte[] futureFormat = (byte[])pre.Clone();
        string content = System.Text.Encoding.ASCII.GetString(futureFormat);
        int marker = content.IndexOf("YP001_FW|GR5526|");
        System.Text.Encoding.ASCII.GetBytes("YP001_FW|GR5526|CUSTOM-NAME|END").CopyTo(futureFormat, marker);
        State.Invoke(null, new object[] { futureFormat });
        byte[] wrongSca = (byte[])pre.Clone(); wrongSca[8] = 1;
        Reject(() => State.Invoke(null, new object[] { wrongSca }), "unknown startup target");
        byte[] unknownApp = (byte[])pre.Clone(); Array.Clear(unknownApp, 0x2000, app.Length);
        Reject(() => State.Invoke(null, new object[] { unknownApp }), "unknown application");
        byte[] corrupt = (byte[])app.Clone(); corrupt[100] ^= 1;
        Reject(() => Prepare.Invoke(null, new object[] { pre, corrupt }), "corrupt signature");
        byte[] unsigned = app.Take(app.Length - 904).ToArray();
        Reject(() => Prepare.Invoke(null, new object[] { pre, unsigned }), "unsigned application");
        Reject(() => State.Invoke(null, new object[] { new byte[16] }), "truncated snapshot");
        foreach (string file in args.Skip(2)) State.Invoke(null, new object[] { File.ReadAllBytes(file) });
        TestFlow(args[0], template, "cancel");
        TestFlow(args[0], template, "backup_changed");
        TestFlow(args[0], template, "changed");
        TestFlow(args[0], template, "missing_probe");
        TestFlow(args[0], template, "write_error");
        TestFlow(args[0], template, "no_bank");
        TestFlow(args[0], template, "wrong_device");
        TestFlow(args[0], template, "no_receipt");
        TestFlow(args[0], template, "wrong_range");
        TestFlow(args[0], template, "protected_error");
        TestFlow(args[0], template, "initialize");
        TestFlow(args[0], template, "normal");
        TestFlow(args[0], template, "recovery", emptyOwner);
        if (args.Length > 2) {
            byte[] field = File.ReadAllBytes(args[args.Length - 1]);
            bool ownerEmpty = field.Skip(0xf9000).Take(0x2000).All(b => b == 255);
            TestFlow(args[0], template, ownerEmpty ? "initialize" : "recovery", field);
        }
        using (var form = new MainForm()) {
            var fields = BindingFlags.Instance | BindingFlags.NonPublic;
            var init = (System.Windows.Forms.CheckBox)typeof(MainForm).GetField("initializeBoot", fields).GetValue(form);
            var clear = (System.Windows.Forms.CheckBox)typeof(MainForm).GetField("clearName", fields).GetValue(form);
            if (init.Checked) throw new Exception("Initialization enabled by default");
            init.Checked = true;
            if (clear.Checked || clear.Enabled) throw new Exception("Initialization allows factory clear");
            init.Checked = false;
            if (clear.Checked || !clear.Enabled) throw new Exception("Factory clear silently restored");
        }
        Console.WriteLine("PASS pairing, protected regions, signature rejection and real snapshot gates");
    }
    static void TestFlow(string image, byte[] template, string scenario, byte[] existing = null) {
        byte[] memory = existing == null ? Blank(File.ReadAllBytes(image)) : (byte[])existing.Clone();
        if (existing == null) memory[0x80000] = 0x42;
        byte[] before = (byte[])memory.Clone();
        bool normal = scenario == "normal", confirmed = false, started = false, postRead = false;
        int writes = 0;
        if (normal) template.CopyTo(memory, 0xec000);
        var prepareCommand = typeof(Flasher).GetMethod("PrepareJLink", BindingFlags.Static | BindingFlags.NonPublic);
        Flasher.TestJLink = (gr, commands, logfile, timeout) => {
            var list = commands.ToArray();
            string name = Path.GetFileNameWithoutExtension(logfile);
            var psi = (System.Diagnostics.ProcessStartInfo)prepareCommand.Invoke(null, new object[] { gr, list, logfile });
            string script = File.ReadAllText(Path.ChangeExtension(logfile, ".jlink"));
            if (name != "pre_snapshot" && scenario != "missing_probe" && !psi.Arguments.Contains("-SelectEmuBySN 12345678"))
                throw new Exception("Unbound probe: " + name);
            if (!normal && (gr || name == "init_check_snapshot" || name == "post_snapshot" || name.StartsWith("sca_")) &&
                (!script.Contains("SetRestartOnClose = 0") || list.Contains("g") || list.Contains("r")))
                throw new Exception("Initialization may start before protected-data verification");
            if (name == "init_check_snapshot" && scenario == "changed") memory[0xfb000] = 0;
            if (name == "post_snapshot" && scenario == "protected_error") memory[0x6e000] = 0;
            if (gr && !normal && !confirmed) throw new Exception("Writing without second confirmation");
            if (name.StartsWith("erase_") && scenario == "no_bank") return "No Flash bank within given address range 0x002F6000, 0x002FAFFF\nErasing done.";
            if (name.StartsWith("erase_") && scenario == "wrong_range") return "Flash sectors within Range [0x00280000 - 0x002EBFFF] deleted.";
            if (name.StartsWith("erase_") && scenario == "no_receipt") return "Erasing done.";
            if (name == "flash_app" && scenario == "write_error") { writes++; return "ERROR: simulated write failure"; }
            if (name == "connection_check" && scenario == "wrong_device") return "Device \"CORTEX-M4\" selected.";
            if (name.EndsWith("snapshot") && (Array.IndexOf(list, "h") < 0 || !list[0].Equals("h")))
                throw new Exception("Full snapshot must halt before reading XIP");
            foreach (string cmd in list) {
                if (cmd.StartsWith("savebin ")) {
                    string[] parts = cmd.Substring(8).Split(',');
                    int offset = Convert.ToInt32(parts[1].Substring(2), 16) - 0x200000;
                    int size = Convert.ToInt32(parts[2].Substring(2), 16);
                    File.WriteAllBytes(parts[0], memory.Skip(offset).Take(size).ToArray());
                }
                if (cmd.StartsWith("erase ")) {
                    string[] parts = cmd.Substring(6).Split(' ');
                    int lo = Convert.ToInt32(parts[0].Substring(2), 16) - 0x200000;
                    int hi = Convert.ToInt32(parts[1].Substring(2), 16) - 0x200000;
                    for (int i = lo; i <= hi; i++) memory[i] = 255;
                    writes++;
                }
                if (cmd.StartsWith("loadbin ")) {
                    string[] parts = cmd.Substring(8).Split(',');
                    uint address = Convert.ToUInt32(parts[1].Substring(2), 16);
                    File.ReadAllBytes(parts[0]).CopyTo(memory, (int)address - 0x200000);
                    BitConverter.GetBytes(address).CopyTo(memory, 8);
                    BitConverter.GetBytes(address).CopyTo(memory, 12);
                    writes++;
                }
                if (cmd == "g") {
                    if (!normal && !postRead) throw new Exception("Started before readback");
                    started = true;
                }
            }
            if (name == "post_snapshot") postRead = true;
            string result = (gr ? "Device \"YP001_GR5526\" selected.\r\n" : "") + (scenario == "missing_probe" ? "" : "S/N: 12345678\r\n") +
                string.Join("\n", list.Where(c => c.StartsWith("verifybin ")).Select(c => "Verify successful")) +
                string.Join("\n", list.Where(c => c.StartsWith("erase ")).Select(c => {
                    string[] words = c.Split(' ');
                    return string.Format("Flash sectors within Range [0x{0:X8} - 0x{1:X8}] deleted.", Convert.ToUInt32(words[1].Substring(2), 16), Convert.ToUInt32(words[2].Substring(2), 16));
                }));
            File.WriteAllText(logfile, result);
            return result;
        };
        bool stopped = false;
        try {
            Flasher.Run(image, "none", false, !normal, message => {
                if (!message.Contains("12345678") || !message.Contains("SHA256")) throw new Exception("Incomplete confirmation");
                if (!message.Contains("0x280000") || !message.Contains("b_before.bin") || !message.Contains("未知内容会被删除"))
                    throw new Exception("B deletion not explicitly disclosed");
                string backup = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(
                    message.Split(new[] { "烧前备份：" }, StringSplitOptions.None)[1].Split('\r')[0]), "b_before.bin");
                if (!System.IO.File.ReadAllBytes(backup).SequenceEqual(before.Skip(0x80000).Take(0x6c000)))
                    throw new Exception("B backup incomplete before confirmation");
                if (scenario == "recovery" && (!message.Contains("DOWNLOADING") || !message.Contains("job=")))
                    throw new Exception("Old owner not disclosed");
                if (scenario == "backup_changed") System.IO.File.WriteAllBytes(backup, new byte[0]);
                confirmed = scenario != "cancel";
                return confirmed;
            });
        } catch (Flasher.Stop) { stopped = true; }
        finally {
            Flasher.TestJLink = null;
            typeof(Flasher).GetField("holdForInitialization", BindingFlags.Static | BindingFlags.NonPublic).SetValue(null, false);
        }
        bool success = scenario == "initialize" || scenario == "recovery" || normal;
        if (success == stopped || success != started) throw new Exception("Flow result: " + scenario);
        if (success) {
            if (memory.Skip(0x80000).Take(0x6c000).Any(b => b != 255))
                throw new Exception("B slot not empty for the next OTA receiver");
            byte[] signed = File.ReadAllBytes(image);
            if (BitConverter.ToInt32(memory, 0xec000 + 0x71f0) != signed.Length - 904)
                throw new Exception("Wrong installed descriptor length");
            using (var sha = System.Security.Cryptography.SHA256.Create()) {
                byte[] digest = sha.ComputeHash(signed, 0, signed.Length - 904);
                if (!memory.Skip(0xec000 + 0x71f8).Take(32).SequenceEqual(digest))
                    throw new Exception("Wrong installed descriptor hash");
            }
        }
        if ((scenario == "cancel" || scenario == "changed" || scenario == "missing_probe" || scenario == "backup_changed" || scenario == "no_bank" || scenario == "no_receipt" || scenario == "wrong_range" || scenario == "wrong_device") && writes != 0)
            throw new Exception("Wrote Flash in rejected scenario: " + scenario);
        Console.WriteLine("PASS flow " + scenario);
    }
}
''', encoding='utf-8')
        exe = directory / 'InitializationTest.exe'
        command = [str(CSC), '-nologo', '-codepage:65001', '-define:FLASH_TEST', '-main:InitializationTest', '-out:' + str(exe)]
        command += ['-reference:' + ref for ref in REFS]
        command += ['-resource:' + str(HERE / 'resources/BootTemplate.bin') + ',BootTemplate',
                    '-resource:' + str(HERE / 'resources/BootPublic.xml') + ',BootPublic']
        command += [str(HERE / 'src/GrJLinkFlash.cs'), str(source)] + [str(p) for p in SOURCES]
        build = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        (directory / 'GR5xxx_16MB_Flash.FLM').write_bytes((HERE / 'GR5xxx_16MB_Flash.FLM').read_bytes())
        image = ROOT / 'tools/gr_release/GR_JLink_Flash/logs/20261108_144204_1.5.21_b25/app.bin'
        colleague_image = Path('E:/xwechat_files/wxid_xdxkqm32bczm11_bc84/temp/RWTemp/2026-11/'
                               '2829aeec41afcab5ad215617506c62ab/GR5526_1.5.24_b28_signed.bin')
        if colleague_image.exists():
            image = colleague_image
        snapshots = sorted(Path('D:/123/logs').rglob('pre.bin')) + sorted(Path('D:/123/logs1').rglob('pre.bin')) + sorted(Path('D:/123/logs2').rglob('pre.bin'))
        result = subprocess.run([str(exe), str(image), str(HERE / 'resources/BootTemplate.bin')]
                                + [str(p) for p in snapshots], capture_output=True, timeout=240)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
