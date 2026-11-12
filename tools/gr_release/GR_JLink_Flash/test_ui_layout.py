"""SAM | 2026-11-10 +08:00 | Catch wrapped labels and overlapping controls without accessing hardware."""
import os
from pathlib import Path
import subprocess
import unittest
import uuid

HERE = Path(__file__).resolve().parent
CSC = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


class LayoutTests(unittest.TestCase):
    def test_labels_fit_and_controls_do_not_overlap(self):
        directory = HERE / 'logs' / ('layout_test_' + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        source = directory / 'LayoutTest.cs'
        source.write_text(r'''
using System;
using System.Drawing;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;
class LayoutTest {
    [STAThread]
    static void Main(string[] args) {
        try { Run(args); }
        catch (Exception e) { Console.Error.WriteLine(e); Environment.Exit(1); }
    }
    static void Run(string[] args) {
        Application.EnableVisualStyles();
        var assembly = Assembly.LoadFrom(args[0]);
        foreach (float scale in new[] { 1.0f, 1.25f, 1.5f }) {
            using (var form = (Form)Activator.CreateInstance(assembly.GetType("MainForm"), true)) {
                form.ShowInTaskbar = false;
                form.StartPosition = FormStartPosition.Manual;
                form.Location = new Point(-30000, -30000);
                form.Show();
                form.Scale(new SizeF(scale, scale));
                form.PerformLayout();
                Application.DoEvents();
                var controls = form.Controls.Cast<Control>().Where(c => c.Visible || c.Parent == form).ToArray();
                foreach (var label in controls.OfType<Label>()) {
                    if (label.Text.StartsWith("GR 串口") &&
                        (label.Width < label.PreferredSize.Width || label.Height > label.Font.Height + 4))
                        throw new Exception("Serial label wraps or clips");
                }
                for (int i = 0; i < controls.Length; i++)
                    for (int j = i + 1; j < controls.Length; j++)
                        if (controls[i].Bounds.IntersectsWith(controls[j].Bounds))
                            throw new Exception("Overlapping controls: " + controls[i].Text + " / " + controls[j].Text);
                using (var bitmap = new Bitmap(form.Width, form.Height)) {
                    form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, bitmap.Size));
                    bitmap.Save(System.IO.Path.Combine(args[1], "layout_" + scale.ToString("0.00") + ".png"));
                }
            }
        }
    }
}
''', encoding='utf-8')
        exe = directory / 'LayoutTest.exe'
        subprocess.run([str(CSC), '-nologo', '-codepage:65001', '-reference:System.Windows.Forms.dll',
                        '-reference:System.Drawing.dll', '-reference:System.Core.dll',
                        '-out:' + str(exe), str(source)], check=True, capture_output=True)
        result = subprocess.run([str(exe), str(HERE / 'GR_JLink_Flash_Tool/GrJLinkFlash.exe'),
                                 str(directory)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
