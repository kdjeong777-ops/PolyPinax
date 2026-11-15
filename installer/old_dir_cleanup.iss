// 이사 뒤 남은 옛 이름 설치 폴더 정리 도우미 — PolyPDF.iss 의 [Code] 가 #include 한다(시험 test_old_dir_cleanup.py 도 같은 파일).
// 필요한 정의: OldAppId·OldAppExe·MyAppName(#define). 함수: SameDir·IsOldAppDir·LnkTarget·InDir·DeleteLinksInto·CleanOldAppDir.
// [Code] 안이라 ';' 주석을 쓰지 않는다(Pascal 주석은 // 또는 중괄호).
{ ── 이사 뒤 남은 옛 이름 설치 폴더 정리 (261115-25, 릴리스 SOT §14.5 U26) ──
  옛 앱 안 업데이트(beta.8 전)가 제거 프로그램(unins000.exe)을 지운 PC 에서는 아래 PrepareToInstall 이 옛 제거를 건너뛴다.
  이사 전에는 같은 폴더에 덮어 설치해 문제가 없었지만, 이사 판(설치 폴더 Program Files\PolyPinax)부터는
  옛 Program Files\PolyPDF 가 등록 없이 통째로 남았다(사용자 보고 — 제거해도 그 폴더의 파일이 모두 남음).
  지우는 조건: 지금 설치 폴더(app 상수)와 다른 폴더이고, 옛 실행 파일(PolyPDF.exe)이 들어 있을 때만.
  ★ 이 주석 안에 중괄호를 쓰지 않는다 — Pascal 주석이 거기서 끝난다. }
function SameDir(const a, b: String): Boolean;
begin
  Result := CompareText(RemoveBackslashUnlessRoot(a), RemoveBackslashUnlessRoot(b)) = 0;
end;

function GetFileAttributesW(lpFileName: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

{ 심볼릭 링크·정션(재분석 지점)인가 — 따라가지 않는다(그 너머가 사용자 데이터일 수 있다) }
function IsReparse(const p: String): Boolean;
var
  a: Cardinal;
begin
  a := GetFileAttributesW(RemoveBackslashUnlessRoot(p));
  Result := (a <> $FFFFFFFF) and ((a and $400) <> 0);
end;

{ 폴더 아래 어디든 재분석 지점이 있으면 True — 있으면 통째로 지우지 않는다(DelTree 가 따라갈 수 있는지에 기대지 않는다) }
function HasReparseInside(const d: String; depth: Integer): Boolean;
var
  fr: TFindRec;
begin
  Result := False;
  if depth > 32 then
  begin
    Result := True;                                   { 너무 깊으면 모른다 — 지우지 않는 쪽으로 }
    Exit;
  end;
  if FindFirst(AddBackslash(d) + '*', fr) then
  begin
    try
      repeat
        if (fr.Name <> '.') and (fr.Name <> '..') then
        begin
          if (fr.Attributes and $400) <> 0 then
            Result := True
          else if (fr.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            Result := HasReparseInside(AddBackslash(d) + fr.Name, depth + 1);
        end;
      until Result or not FindNext(fr);
    finally
      FindClose(fr);
    end;
  end;
end;

{ 사용자 데이터 자리(%APPDATA%·%LOCALAPPDATA%·문서·사용자 프로필) 또는 그 아래면 True — 절대 지우지 않는다 }
function UnderUserData(const d: String): Boolean;
var
  roots: array[0..3] of String;
  i: Integer;
  r: String;
begin
  Result := False;
  roots[0] := ExpandConstant('{userappdata}');
  roots[1] := ExpandConstant('{localappdata}');
  roots[2] := ExpandConstant('{userdocs}');
  roots[3] := GetEnv('USERPROFILE');
  for i := 0 to 3 do
  begin
    r := RemoveBackslashUnlessRoot(roots[i]);
    if (r <> '') and (SameDir(d, r) or (CompareText(Copy(AddBackslash(d), 1, Length(AddBackslash(r))), AddBackslash(r)) = 0)) then
      Result := True;
  end;
end;

function IsOldAppDir(const d: String): Boolean;
begin
  { 261115-25(지휘 조건): 좁게 — 지금 설치 폴더와 다르고, 옛 실행 파일이 있고, 드라이브 루트·사용자 데이터 자리가 아니고,
    재분석 지점이 아니며, 휴대용 판(표식 파일 — 사용자 데이터가 그 폴더의 Data 에 있다, 마스터 §14.9)이 아닐 때만 }
  Result := (d <> '') and DirExists(d) and FileExists(AddBackslash(d) + '{#OldAppExe}')
            and not SameDir(d, ExpandConstant('{app}'))
            and (Length(RemoveBackslashUnlessRoot(d)) > 3)
            and not UnderUserData(d)
            and not IsReparse(d)
            and not FileExists(AddBackslash(d) + '{#OldAppId}.portable')
            and not FileExists(AddBackslash(d) + '{#MyAppName}.portable')
            and not DirExists(AddBackslash(d) + 'Data');
end;

function LnkTarget(const lnk: String): String;
var
  sh, s: Variant;
begin
  Result := '';
  try
    sh := CreateOleObject('WScript.Shell');
    s := sh.CreateShortcut(lnk);
    Result := s.TargetPath;
  except
    Result := '';
  end;
end;

function InDir(const path, dir: String): Boolean;
var
  d: String;
begin
  d := AddBackslash(dir);
  Result := (path <> '') and (CompareText(Copy(path, 1, Length(d)), d) = 0);
end;

{ 폴더 `folder` 안의 바로가기 중 이름이 `prefix` 로 시작하고 대상이 `dir` 안인 것을 지운다. 비면 폴더도(rmdir). }
procedure DeleteLinksInto(const folder, prefix, dir: String; removeFolder: Boolean);
var
  fr: TFindRec;
begin
  if not DirExists(folder) then Exit;
  if FindFirst(AddBackslash(folder) + prefix + '*.lnk', fr) then
  begin
    try
      repeat
        if InDir(LnkTarget(AddBackslash(folder) + fr.Name), dir) then
          DeleteFile(AddBackslash(folder) + fr.Name);
      until not FindNext(fr);
    finally
      FindClose(fr);
    end;
  end;
  if removeFolder then
    RemoveDir(folder);
end;

{ 옛 이름 설치 폴더를 지우고, 그 폴더를 가리키던 모든 사용자용 시작 메뉴 그룹·바탕 화면 바로가기도(옛 제거 프로그램이 지웠을 것). }
procedure CleanOldAppDir(const d: String);
begin
  if not IsOldAppDir(d) then Exit;
  if HasReparseInside(d, 0) then
  begin
    Log('old app dir kept (link or junction inside): ' + d);
    Exit;
  end;
  DeleteLinksInto(ExpandConstant('{commonprograms}\{#OldAppId}'), '', d, True);
  DeleteLinksInto(ExpandConstant('{commondesktop}'), '{#OldAppId}', d, False);
  { 지우지 못한 것(잠김)이 있어도 설치를 막지 않는다 — 기록만(다음 설치·제거가 다시 해 본다) }
  if DelTree(d, True, True, True) then
    Log('old app dir removed: ' + d)
  else
    Log('old app dir not fully removed (in use?): ' + d);
end;
