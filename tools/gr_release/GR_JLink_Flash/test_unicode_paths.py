"""SAM | 2026-11-05 +08:00 | Regress J-Link script paths without connecting hardware."""
import os
from pathlib import Path
import subprocess
import uuid
import unittest
from test_boot_initialization import REFS, SOURCES


HERE = Path(__file__).resolve().parent
CSC = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


class UnicodePaths(unittest.TestCase):
    def test_commander_uses_relative_paths_in_unicode_working_directory(self):
        harness = r'''
using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
using System.Linq;
class PathTest {
    [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet=System.Runtime.InteropServices.CharSet.Unicode)]
    static extern IntPtr LoadLibrary(string path);
    [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet=System.Runtime.InteropServices.CharSet.Ansi)]
    static extern IntPtr GetProcAddress(IntPtr module, string name);
    [System.Runtime.InteropServices.UnmanagedFunctionPointer(System.Runtime.InteropServices.CallingConvention.Cdecl)]
    delegate int DeviceIndex([System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.LPStr)] string name);
    [System.Runtime.InteropServices.UnmanagedFunctionPointer(System.Runtime.InteropServices.CallingConvention.Cdecl)]
    delegate int ExecCommand([System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.LPStr)] string command, System.Text.StringBuilder error, int size);
    static void Main(string[] args) {
        try { Run(args); }
        catch (Exception e) { Console.Error.WriteLine(e); Environment.Exit(1); }
    }
    static void Run(string[] args) {
        var method = typeof(Flasher).GetMethod("PrepareJLink", BindingFlags.Static | BindingFlags.NonPublic);
        if (method == null) throw new Exception("Missing Unicode-safe command preparation");
        var check = typeof(Flasher).GetMethod("Check", BindingFlags.Static | BindingFlags.NonPublic);
        bool rejected = false;
        try { check.Invoke(null, new object[] { "No Flash bank within given address range 0x00280000, 0x002EBFFF\nErasing done.\nVerify successful", 1, "fixture.log" }); }
        catch (TargetInvocationException e) { rejected = e.InnerException is Flasher.Stop; }
        if (!rejected) throw new Exception("Missing Flash bank must stop the operation");
        foreach (bool gr in new[] { false, true }) {
            string logfile = Path.Combine(args[0], gr ? "flash.log" : "pre_snapshot.log");
            string image = Path.Combine(args[0], "app.bin");
            var psi = (ProcessStartInfo)method.Invoke(null, new object[] { gr,
                new[] { "savebin " + Path.Combine(args[0], "pre.bin") + ",0x200000,0x100000",
                        "loadbin " + image + ",0x202000", "verifybin " + image + ",0x202000" }, logfile });
            string script = File.ReadAllText(Path.ChangeExtension(logfile, ".jlink"));
            if (psi.WorkingDirectory != args[0] || psi.Arguments.Contains(args[0])) throw new Exception("Absolute command path");
            if (script.Contains("savebin " + args[0]) || script.Contains("?") || !script.Contains("savebin pre.bin,")) throw new Exception("Lossy script path");
            if (!script.Contains("loadbin app.bin,") || !script.Contains("verifybin app.bin,")) throw new Exception("Image path");
            if (gr) {
                string[] lines = script.Split('\n');
                int xmlAt = Array.FindIndex(lines, l => l.StartsWith("exec JLinkDevicesXMLPath="));
                int deviceAt = Array.FindIndex(lines, l => l.Trim() == "device YP001_GR5526");
                int haltAt = Array.FindIndex(lines, l => l.Trim() == "h");
                if (xmlAt < 0 || deviceAt <= xmlAt || haltAt <= deviceAt)
                    throw new Exception("XML and device must precede the first halt/implicit target connection");
                string command = lines[xmlAt].Substring(5).Trim();
                string path = command.Substring("JLinkDevicesXMLPath=".Length).Trim('"');
                if (!Path.IsPathRooted(path) || path.Any(c => c >= 128) ||
                    !File.Exists(Path.Combine(path, "JLinkDevices.xml")) ||
                    !File.Exists(Path.Combine(path, "GR5xxx_16MB_Flash.FLM"))) throw new Exception("Loader path");
                // Real x86 J-Link DLL, local device enumeration only. Never opens USB or connects a target.
                IntPtr library = LoadLibrary(Path.Combine(Path.GetDirectoryName(psi.FileName), "JLinkARM.dll"));
                if (library == IntPtr.Zero) throw new Exception("Cannot load actual Commander DLL");
                var exec = (ExecCommand)System.Runtime.InteropServices.Marshal.GetDelegateForFunctionPointer(
                    GetProcAddress(library, "JLINKARM_ExecCommand"), typeof(ExecCommand));
                var error = new System.Text.StringBuilder(1024);
                if (exec(command, error, error.Capacity) != 0) throw new Exception("XML setup: " + error);
                var index = (DeviceIndex)System.Runtime.InteropServices.Marshal.GetDelegateForFunctionPointer(
                    GetProcAddress(library, "JLINKARM_DEVICE_GetIndex"), typeof(DeviceIndex));
                if (index("YP001_GR5526") < 0) throw new Exception("Actual J-Link DLL does not recognize GR5526");
                if (!script.Contains("SetRestartOnClose = 0")) throw new Exception("Erase session can restart target");
            }
        }
    }
}
'''
        root = HERE / 'logs' / ('path_test_' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        source = root / 'PathTest.cs'
        source.write_text(harness, encoding='utf-8')
        exe = root / 'PathTest.exe'
        subprocess.run([str(CSC), '-nologo', '-codepage:65001', '-main:PathTest', '-platform:x86',
                        '-out:' + str(exe)] + ['-reference:' + ref for ref in REFS] +
                        [str(HERE / 'src/GrJLinkFlash.cs'), str(source)] + [str(p) for p in SOURCES],
                       check=True, capture_output=True)
        (root / 'GR5xxx_16MB_Flash.FLM').write_bytes((HERE / 'GR5xxx_16MB_Flash.FLM').read_bytes())
        for name in ['ascii', '中文 工具包', '中文 空格 😀']:
            directory = root / name
            directory.mkdir()
            result = subprocess.run([str(exe), str(directory)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
