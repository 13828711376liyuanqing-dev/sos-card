Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeLoader {
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool SetDllDirectory(string path);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern IntPtr LoadLibrary(string path);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool FreeLibrary(IntPtr handle);
}
'@
if ($env:YP001_DLL_DIRECTORY) {
  [void][NativeLoader]::SetDllDirectory($env:YP001_DLL_DIRECTORY)
}
foreach ($path in @(
  'C:\Keil_v5\ARM\Segger\JLinkARM.dll',
  'C:\Keil_v5\ARM\Segger\JLTAgdi.dll',
  'C:\Keil_v5\ARM\Segger\JL2CM3.dll'
)) {
  $handle = [NativeLoader]::LoadLibrary($path)
  $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
  Write-Output "$path handle=$handle error=$code"
  if ($handle -ne [IntPtr]::Zero) { [void][NativeLoader]::FreeLibrary($handle) }
}
