# -*- coding: utf-8 -*-
"""261115-25(릴리스 SOT §14.5 U26): 이사 뒤 남은 옛 이름 설치 폴더(Program Files\\PolyPDF) 정리 — 설치 프로그램의 실제 Pascal 코드로.

사용자 보고(다른 PC): 프로그램 관리에서 제거했는데 'Program Files\\PolyPDF' 의 파일이 모두 남았다(창 없이 끝남).
원인: 옛 앱 안 업데이트(beta.8 전)가 unins000.exe 를 지운 PC 에서 설치 프로그램은 옛 제거를 건너뛰고 `_internal` 만 지운다 —
이사 판부터는 새 폴더(PolyPinax)에 설치하므로 옛 폴더가 등록 없이 통째로 남았다.

  A  (실행) `installer/old_dir_cleanup.iss` 를 include 한 작은 설치 파일을 ISCC 로 만들어 조용히 돌린다(권한 없음·제거 기록 없음):
     옛 폴더(PolyPDF.exe 있음)는 지운다 · 지금 설치 폴더와 같은 폴더·휴대용 판(표식·Data)·PolyPDF.exe 없는 폴더는 남긴다 ·
     옛 폴더를 가리키는 바로가기만 지우고 다른 바로가기는 남긴다. ISCC 가 없으면 명시적 SKIP.
  B  (정적) PolyPDF.iss 가 그 파일을 include 하고, 설치 전(등록 없음·제거 프로그램 없음·제거 뒤)과 직접 제거 뒤에 정리를 부르며,
     옛 제거 대기가 120초다.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
INC = HERE / "installer" / "old_dir_cleanup.iss"
ISS = HERE / "installer" / "PolyPDF.iss"
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def iscc():
    for base in (os.environ.get("LOCALAPPDATA", "") + r"\Programs", os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramFiles", "")):
        p = Path(base) / "Inno Setup 6" / "ISCC.exe"
        if base and p.exists():
            return p
    return None


def lnk(path: Path, target: Path) -> None:
    import win32com.client
    s = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(path))
    s.TargetPath = str(target)
    s.Save()


TEST_ISS = r'''
#define OldAppId "PolyPDF"
#define OldAppExe OldAppId + ".exe"
#define MyAppName "PolyPinax"
[Setup]
AppName=PolyPinaxOldDirCleanupTest
AppVersion=1
DefaultDirName={param:NEWDIR}
Uninstallable=no
PrivilegesRequired=lowest
DisableDirPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
DisableWelcomePage=yes
OutputDir=__OUT__
OutputBaseFilename=cleanup_test
[Code]
#include "__INC__"
function B(v: Boolean): String;
begin
  if v then Result := '1' else Result := '0';
end;
procedure CurStepChanged(CurStep: TSetupStep);
var
  r: String;
begin
  if CurStep = ssPostInstall then
  begin
    r := 'old=' + B(IsOldAppDir(ExpandConstant('{param:OLD}'))) + ';port=' + B(IsOldAppDir(ExpandConstant('{param:PORT}')))
       + ';data=' + B(IsOldAppDir(ExpandConstant('{param:DATA}'))) + ';noexe=' + B(IsOldAppDir(ExpandConstant('{param:NOEXE}')))
       + ';app=' + B(IsOldAppDir(ExpandConstant('{app}')))
       + ';udata=' + B(IsOldAppDir(ExpandConstant('{param:UDATA}')))
       + ';jlink=' + B(IsOldAppDir(ExpandConstant('{param:JLINK}')))
       + ';tgt=' + LnkTarget(ExpandConstant('{param:LNKDIR}') + '\PolyPDF.lnk') + ';';
    DeleteLinksInto(ExpandConstant('{param:LNKDIR}'), '', ExpandConstant('{param:OLD}'), False);
    CleanOldAppDir(ExpandConstant('{param:OLD}'));
    CleanOldAppDir(ExpandConstant('{param:PORT}'));
    CleanOldAppDir(ExpandConstant('{app}'));
    CleanOldAppDir(ExpandConstant('{param:UDATA}'));
    CleanOldAppDir(ExpandConstant('{param:JIN}'));
    CleanOldAppDir(ExpandConstant('{param:JLINK}'));
    SaveStringToFile(ExpandConstant('{param:OUT}'), r, False);
  end;
end;
'''

# ── A ──
cc = iscc() if os.name == "nt" else None
if cc is None:
    print("SKIP - A ISCC(Inno Setup 6)가 없다 — 실행 확인은 건너뛴다")
else:
    # 사용자 데이터 자리(%LOCALAPPDATA%\Temp 등)는 정리 대상에서 빠지므로 시험 폴더는 저장소 폴더 안에(끝나면 지운다)
    tmp = Path(tempfile.mkdtemp(prefix="_olddir_test_", dir=str(HERE)))
    # %LOCALAPPDATA%\Temp — 사용자 데이터 자리. tempfile 기본값은 쓰지 않는다(검사 실행기가 TEMP 를 다른 곳으로 바꾼다)
    _la_tmp = Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")) / "Temp"
    _la_tmp.mkdir(parents=True, exist_ok=True)
    udata = Path(tempfile.mkdtemp(prefix="polypdf_olddir_udata_", dir=str(_la_tmp)))
    try:
        old, port, data, noexe, new, lk = (tmp / n for n in ("Program Files", "port", "data", "noexe", "new", "links"))
        old = old / "PolyPDF"
        jin, victim, jlink_target = tmp / "jin", tmp / "victim", tmp / "jt"
        for d in (old / "_internal", port, data / "Data", noexe, new, lk, jin, victim, jlink_target):
            d.mkdir(parents=True, exist_ok=True)
        for d in (old, port, data, new, udata, jin, jlink_target):
            (d / "PolyPDF.exe").write_bytes(b"x")
        (victim / "user.txt").write_text("user data")
        import _winapi
        _winapi.CreateJunction(str(victim), str(jin / "linked"))                # 옛 폴더 안의 정션 → 사용자 데이터
        jlink = tmp / "jlink"
        _winapi.CreateJunction(str(jlink_target), str(jlink))                   # 옛 폴더 자리 자체가 정션
        (old / "_internal" / "a.pyd").write_bytes(b"x")
        (old / "unins_gone.txt").write_text("x")
        (port / "PolyPDF.portable").write_text("")
        (noexe / "keep.txt").write_text("x")
        lnk(lk / "PolyPDF.lnk", old / "PolyPDF.exe")
        lnk(lk / "Other.lnk", noexe / "keep.txt")
        (tmp / "t.iss").write_text(TEST_ISS.replace("__OUT__", str(tmp)).replace("__INC__", str(INC)), encoding="utf-8-sig")
        r = subprocess.run([str(cc), "/Q", str(tmp / "t.iss")], capture_output=True, timeout=120)
        chk(r.returncode == 0, "A 시험 설치 파일이 컴파일된다(old_dir_cleanup.iss include)", (r.stdout + r.stderr).decode("cp949", "replace")[-600:])
        out = tmp / "out.txt"
        if r.returncode == 0:
            r2 = subprocess.run([str(tmp / "cleanup_test.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                 "/NEWDIR=%s" % new, "/OLD=%s" % old, "/PORT=%s" % port, "/DATA=%s" % data,
                                 "/NOEXE=%s" % noexe, "/LNKDIR=%s" % lk, "/UDATA=%s" % udata, "/JIN=%s" % jin,
                                 "/JLINK=%s" % jlink, "/OUT=%s" % out], timeout=120)
            res = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
            print("  결과:", res)
            chk("old=1;" in res, "A 옛 폴더(PolyPDF.exe 있음·설치 폴더와 다름)는 정리 대상", res)
            chk("port=0;" in res and "data=0;" in res, "A 휴대용 판(표식·Data 폴더)은 대상 아님", res)
            chk("noexe=0;" in res and "app=0;" in res, "A PolyPDF.exe 없는 폴더·지금 설치 폴더는 대상 아님", res)
            chk(str(old / "PolyPDF.exe").lower() in res.lower(), "A 바로가기 대상 읽기(WScript.Shell)", res)
            chk(not old.exists(), "A 옛 폴더가 통째로 지워졌다(_internal 만이 아니라)", list(old.rglob("*")) if old.exists() else "")
            chk((port / "PolyPDF.exe").exists() and (data / "PolyPDF.exe").exists() and (new / "PolyPDF.exe").exists(),
                "A 휴대용·지금 설치 폴더는 그대로")
            chk(not (lk / "PolyPDF.lnk").exists() and (lk / "Other.lnk").exists(), "A 옛 폴더를 가리킨 바로가기만 지움")
            chk("udata=0;" in res and (udata / "PolyPDF.exe").exists(), "A 사용자 데이터 자리(%LOCALAPPDATA% 아래)는 대상 아님", res)
            chk((victim / "user.txt").exists() and (jin / "PolyPDF.exe").exists(),
                "A 안에 정션이 있는 폴더는 지우지 않는다(정션 너머 사용자 데이터 보존)")
            chk("jlink=0;" in res and (jlink_target / "PolyPDF.exe").exists(), "A 폴더 자리 자체가 정션이면 대상 아님", res)
    finally:
        for j in (tmp / "jin" / "linked", tmp / "jlink"):              # 정션은 먼저 떼어 낸다(rmtree 가 너머를 지우지 않게)
            try:
                os.rmdir(j)
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(udata, ignore_errors=True)

# ── B ──
s = ISS.read_text(encoding="utf-8-sig")
code = s[s.index("[Code]"):]
prep = code[code.index("function PrepareToInstall"):code.index("procedure CurUninstallStepChanged")]
unin = code[code.index("procedure CurUninstallStepChanged"):]
chk('#include "old_dir_cleanup.iss"' in code, "B PolyPDF.iss 가 정리 도우미를 include")
chk(prep.count("CleanOldAppDir(") >= 4 and "{autopf}\\{#OldAppId}" in prep,
    "B 설치 전 — 등록 없음·제거 프로그램 없음·제거 뒤 모두 옛 폴더 정리", prep.count("CleanOldAppDir("))
chk("IsOldAppDir(oldDir)" in prep and prep.index("ReadUninstVal('Inno Setup: App Path')") < prep.index("Exec(uninstExe"),
    "B 옛 폴더 경로는 제거 전에 읽는다(제거하면 사라짐)")
chk("i < 240" in prep, "B 옛 제거 대기 120초(500ms × 240)")
chk("usPostUninstall" in unin and "CleanOldAppDir(" in unin and "{userprograms}" in unin,
    "B 직접 제거 뒤 — 남은 옛 폴더·앱이 고친 사용자 바로가기 정리")
chk('#define OldAppId "PolyPDF"' in s, "B 옛 ID 는 한 곳(#define OldAppId)")

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
sys.exit(1 if fails else 0)
