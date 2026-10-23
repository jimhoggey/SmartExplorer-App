; Windows installer for Smart Explorer, built by CI with:
;   iscc /DAppVersion=0.6.0 packaging\windows-installer.iss
; Installs for the current user (no administrator needed, which suits church
; computers), adds a Start menu entry, an optional desktop icon and an uninstaller.

#define AppName "Smart Explorer"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change AppId: it is how Windows recognises an upgrade of the same app.
AppId={{79F49D73-4336-4323-A5E9-CC357B1AE8DC}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=jimhoggey
AppPublisherURL=https://github.com/jimhoggey/SmartExplorer-App
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=SmartExplorer-{#AppVersion}-windows-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppName}.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; The AppUserModelID lets background renaming's notifications carry the app's name and icon (notify.APP_ID).
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; AppUserModelID: "jimhoggey.SmartExplorer"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; An update started from inside the app runs Setup with /RELAUNCH=1: open the app again afterwards.
Filename: "{app}\{#AppName}.exe"; Flags: nowait; Check: Relaunch
; Background renaming starts with Windows (Settings, Watch a folder): start it again after an update,
; straight away (--now): the computer is already up, so there is no start-up wait.
Filename: "{app}\{#AppName}.exe"; Parameters: "--watch --now"; Flags: nowait; Check: WatchesAtStartup

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ""{#AppName}.exe"""; Flags: runhidden; RunOnceId: "StopSmartExplorer"

[UninstallDelete]
; autostart.NAME
Type: files; Name: "{userstartup}\Smart Explorer (background).lnk"

[Code]
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function WatchesAtStartup: Boolean;
begin
  Result := FileExists(ExpandConstant('{userstartup}\Smart Explorer (background).lnk'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { Background renaming has no window, so closing applications can miss it. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#AppName}.exe"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
