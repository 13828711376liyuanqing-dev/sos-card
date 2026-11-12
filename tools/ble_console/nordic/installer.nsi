; SAM | 2026-11-05 +08:00 | Per-user offline installer; keep user logs and remove only packaged manifest files.
Unicode True
!include "MUI2.nsh"
Name "YP001 Nordic BLE Console"
OutFile "release\YP001_BLE_Setup_0.2.5_x64.exe"
InstallDir "$LOCALAPPDATA\Programs\YP001BleConsole"
RequestExecutionLevel user
SetCompressor /SOLID zlib
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
Function .onInit
 SetRegView 64
FunctionEnd
Section "Application"
 SetOutPath "$INSTDIR"
 File /r "package\YP001BleConsole\*"
 SetOutPath "$INSTDIR\prerequisites"
 File "VC_redist.x64.exe"
 SetOutPath "$INSTDIR"
 ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
 StrCmp $0 1 runtime_ready
 MessageBox MB_YESNO "缺少 Microsoft Visual C++ x64 运行库。现在安装官方运行库？该步骤可能需要管理员授权。" IDNO runtime_ready
 ExecShellWait "runas" "$INSTDIR\prerequisites\VC_redist.x64.exe" "/install /passive /norestart" SW_SHOWNORMAL $0
 runtime_ready:
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 CreateDirectory "$SMPROGRAMS\YP001 BLE"
 CreateShortcut "$SMPROGRAMS\YP001 BLE\YP001 BLE 调试工具.lnk" "$INSTDIR\YP001_COM31_BLE.exe"
 CreateShortcut "$SMPROGRAMS\YP001 BLE\卸载.lnk" "$INSTDIR\Uninstall.exe"
 CreateShortcut "$DESKTOP\YP001 BLE 调试工具.lnk" "$INSTDIR\YP001_COM31_BLE.exe"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YP001BleConsole" "DisplayName" "YP001 Nordic BLE Console 0.2.5"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YP001BleConsole" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YP001BleConsole" "DisplayVersion" "0.2.5"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YP001BleConsole" "Publisher" "YP001"
SectionEnd
Section "Uninstall"
 !include "uninstall_files.nsh"
 Delete "$INSTDIR\prerequisites\VC_redist.x64.exe"
 RMDir "$INSTDIR\prerequisites"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
 Delete "$SMPROGRAMS\YP001 BLE\YP001 BLE 调试工具.lnk"
 Delete "$SMPROGRAMS\YP001 BLE\卸载.lnk"
 RMDir "$SMPROGRAMS\YP001 BLE"
 Delete "$DESKTOP\YP001 BLE 调试工具.lnk"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YP001BleConsole"
SectionEnd
