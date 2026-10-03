; Inno Setup 6 Script for LumiTrans (AI real-time audio & screen subtitle translator)
#define MyAppName "LumiTrans"
#define MyAppEnglishName "LumiTrans"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "LumiTrans"
#define MyAppExeName "LumiTrans.exe"
; 이전 이름. 기존 설치를 업그레이드할 때 옛 실행 파일·바로가기·데이터를 정리하는 데 쓴다.
#define LegacyEnglishName "WiseEinstein"
#define LegacyExeName "WiseEinstein.exe"
#define LegacyAppName "실시간 AI 동시통역 자막기"

#ifndef Edition
  #define Edition "Full"
#endif

#if Edition == "Lite"
  #define MyAppTitle "LumiTrans (Lite)"
  #define MyOutputBaseFilename "LumiTrans_Lite_Setup_v" + MyAppVersion
#else
  #define MyAppTitle "LumiTrans (Full)"
  #define MyOutputBaseFilename "LumiTrans_Full_Setup_v" + MyAppVersion
#endif

[Setup]
AppId={{C4B18A57-8971-4712-B6B1-356C19E75BA3}
AppName={#MyAppTitle}
AppVersion={#MyAppVersion}
AppVerName={#MyAppTitle} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppEnglishName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename={#MyOutputBaseFilename}
SetupIconFile=assets\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppTitle}
CloseApplications=yes
RestartApplications=no
LicenseFile=LICENSE

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "cleanconfig"; Description: "기존 설정 초기화 (새로운 기본값으로 클린 설치)"; GroupDescription: "추가 옵션:"; Flags: unchecked

[InstallDelete]
; 이전 버전 가속 팩이 llama_cpp\lib 에 덮어쓴 CUDA DLL 이 남으면 CPU 전용 라이브러리와 섞이므로 먼저 비운다.
Type: filesandordirs; Name: "{app}\_internal\llama_cpp\lib"
Type: filesandordirs; Name: "{app}\_internal\llama_cuda"
; 앱은 AppData 설정이 없으면 설치 폴더의 config.json 을 복사해 오므로 클린 설치 때 함께 지운다.
Type: files; Name: "{app}\config.json"; Tasks: cleanconfig
; 이전 이름(WiseEinstein)으로 설치된 것을 업그레이드할 때 옛 실행 파일과 바로가기를 지운다.
Type: files; Name: "{app}\{#LegacyExeName}"
Type: filesandordirs; Name: "{autoprograms}\{#LegacyAppName}"
Type: files; Name: "{autodesktop}\{#LegacyAppName}.lnk"

[Files]
Source: "dist\LumiTrans\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} (디버그 모드)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--console"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "실시간 로그 콘솔 창과 함께 실행 (문제 진단용)"
Name: "{group}\{#MyAppName} 삭제"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\{#MyAppEnglishName}"
Type: filesandordirs; Name: "{localappdata}\{#MyAppEnglishName}"
Type: filesandordirs; Name: "{userappdata}\{#LegacyEnglishName}"
Type: filesandordirs; Name: "{localappdata}\{#LegacyEnglishName}"
; 앱이 설치 폴더에 만든 파일. 사용자가 설치 경로를 바꿨을 수 있으므로 {app} 전체는 지우지 않는다.
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\clean_install.id"
Type: filesandordirs; Name: "{app}\output"
Type: dirifempty; Name: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// 앱은 종료할 때 메모리의 설정 전체를 다시 저장한다. 설정을 지우기 전에 강제 종료해야
// 지운 뒤에 이전 설정이 되살아나지 않는다. (정상 종료는 "종료하시겠습니까?" 확인 창에 막힐 수도 있다.)
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#LegacyExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

procedure DeleteUserData();
begin
  DelTree(ExpandConstant('{userappdata}\{#MyAppEnglishName}'), True, True, True);
  DelTree(ExpandConstant('{localappdata}\{#MyAppEnglishName}'), True, True, True);
  DelTree(ExpandConstant('{userappdata}\{#LegacyEnglishName}'), True, True, True);
  DelTree(ExpandConstant('{localappdata}\{#LegacyEnglishName}'), True, True, True);
end;

function InitializeUninstall(): Boolean;
begin
  KillRunningApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    DeleteUserData();
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if WizardIsTaskSelected('cleanconfig') then
  begin
    KillRunningApp();
    DeleteUserData();
  end;
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('cleanconfig') then
    begin
      DeleteUserData();
      // 관리자 권한 설치에서는 {userappdata} 가 실제 사용자와 다른 계정일 수 있어,
      // 앱이 첫 실행 때 자기 계정의 설정을 지우도록 설치마다 새 표식을 남긴다.
      SaveStringToFile(ExpandConstant('{app}\clean_install.id'), GetDateTimeString('yyyymmddhhnnss', #0, #0), False);
    end;
  end;
end;
