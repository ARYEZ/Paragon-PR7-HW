; Paragon PR7-HW installer (Inno Setup 6): hardware information, the way HWiNFO and CPU-Z show it.
;   iscc /DAppVersion=0.1.0 installer\pr7hw.iss      (after pyinstaller pr7hw.spec has made dist\PR7-HW)
;
; Per-user (no admin rights) into %LOCALAPPDATA%\Programs\PR7-HW, with a Start menu entry. PR7-HW reads the
; hardware when it's open; nothing runs in the background and nothing is registered.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId is permanent: it's how a new version finds and upgrades the installed one. Never change it.
AppId={{A805BD4F-97AC-4B0E-A173-574E7779EA1A}
AppName=Paragon PR7-HW
AppVersion={#AppVersion}
AppVerName=Paragon PR7-HW {#AppVersion}
AppPublisher=Paragon
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\PR7-HW
DefaultGroupName=Paragon PR7-HW
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=PR7-HW-Setup-{#AppVersion}
SetupIconFile=..\pr7hw\icons\app.ico
UninstallDisplayIcon={app}\PR7-HW.exe
UninstallDisplayName=Paragon PR7-HW
WizardStyle=modern
WizardImageFile=wizard-large-1x.bmp,wizard-large-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PR7-HW\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Paragon PR7-HW"; Filename: "{app}\PR7-HW.exe"; Comment: "Hardware information"
Name: "{autodesktop}\Paragon PR7-HW"; Filename: "{app}\PR7-HW.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PR7-HW.exe"; Description: "{cm:LaunchProgram,Paragon PR7-HW}"; Flags: nowait postinstall skipifsilent
; Updates (Check for updates runs this installer with /SILENT /relaunch=1): start PR7-HW again when done.
Filename: "{app}\PR7-HW.exe"; Flags: nowait runasoriginaluser; Check: Relaunch

[Code]
// True only when the updater asked for it (/relaunch=1): normal and CI installs behave as before.
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
