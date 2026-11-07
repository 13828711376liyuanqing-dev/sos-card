"""SAM | 2026-11-05 +08:00 | Regress J-Link script paths without connecting hardware."""
import os
from pathlib import Path
import subprocess
import uuid
import unittest


HERE = Path(__file__).resolve().parent
CSC = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


class UnicodePaths(unittest.TestCase):
    def test_commander_uses_relative_paths_in_unicode_working_directory(self):
        harness = r'''
using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
class PathTest {
    static void Main(string[] args) {
        try { Run(args); }
        catch (Exception e) { Console.Error.WriteLine(e); Environment.Exit(1); }
    }
    static void Run(string[] args) {
        var method = typeof(Flasher).GetMethod("PrepareJLink", BindingFlags.Static | BindingFlags.NonPublic);
        if (method == null) throw new Exception("Missing Unicode-safe command preparation");
        foreach (bool gr in new[] { false, true }) {
            string logfile = Path.Combine(args[0], gr ? "flash.log" : "pre_snapshot.log");
            string image = Path.Combine(args[0], "app.bin");
            var psi = (ProcessStartInfo)method.Invoke(null, new object[] { gr,
                new[] { "savebin " + Path.Combine(args[0], "pre.bin") + ",0x200000,0x100000",
                        "loadbin " + image + ",0x202000", "verifybin " + image + ",0x202000" }, logfile });
            string script = File.ReadAllText(Path.ChangeExtension(logfile, ".jlink"));
            if (psi.WorkingDirectory != args[0] || psi.Arguments.Contains(args[0])) throw new Exception("Absolute command path");
            if (script.Contains(args[0]) || script.Contains("?") || !script.Contains("savebin pre.bin,")) throw new Exception("Lossy script path");
            if (!script.Contains("loadbin app.bin,") || !script.Contains("verifybin app.bin,")) throw new Exception("Image path");
            if (gr && (!script.Contains("JLinkDevicesXMLPath=.\\") || !File.Exists(Path.Combine(args[0], "JLinkDevices.xml")) ||
                       !File.Exists(Path.Combine(args[0], "GR5xxx_16MB_Flash.FLM")))) throw new Exception("Loader path");
        }
    }
}
'''
        root = HERE / 'logs' / ('path_test_' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        source = root / 'PathTest.cs'
        source.write_text(harness, encoding='utf-8')
        exe = root / 'PathTest.exe'
        subprocess.run([str(CSC), '-nologo', '-codepage:65001', '-main:PathTest',
                        '-out:' + str(exe), '-reference:System.Windows.Forms.dll',
                        '-reference:System.Drawing.dll', str(HERE / 'src/GrJLinkFlash.cs'),
                        str(source)], check=True, capture_output=True)
        (root / 'GR5xxx_16MB_Flash.FLM').write_bytes((HERE / 'GR5xxx_16MB_Flash.FLM').read_bytes())
        for name in ['ascii', '中文 工具包', '中文 空格 😀']:
            directory = root / name
            directory.mkdir()
            result = subprocess.run([str(exe), str(directory)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
