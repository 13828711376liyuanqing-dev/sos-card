// SAM | 2026-11-05 +08:00 | Launch the local COM31 GUI using the installed Python runtime.
using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
class Launcher {
 [STAThread] static void Main() {
  try {
   string folder=AppDomain.CurrentDomain.BaseDirectory;
   string python=Path.Combine(folder,"python","pythonw.exe");
   if(!File.Exists(python))python=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","Python","Python312","pythonw.exe");
   if(!File.Exists(python))throw new FileNotFoundException("需要本机 Python 3.12，未找到 "+python);
   Process.Start(new ProcessStartInfo(python,"-I -B \""+Path.Combine(folder,"com31_console.py")+"\"") {WorkingDirectory=folder,UseShellExecute=false,CreateNoWindow=true});
  } catch(Exception e) {MessageBox.Show(e.Message,"COM31 BLE 工具启动失败");}
 }
}
