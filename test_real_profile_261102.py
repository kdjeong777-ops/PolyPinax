# -*- coding: utf-8 -*-
"""261102-1: 시험 도구는 사용자 실제 설정 폴더를 패키지 가상화 밖에서 읽는다 — 마스터 §14.2.1.

Claude 데스크톱(MSIX) 셸은 `%APPDATA%` 를 파일 단위로 복사본과 섞어 본다 — 낡은 복사본 index.db + 실제 -wal 을 함께 봐
'malformed' 가 났고, 빌드 시험 시드도 그 섞인 보기를 복사해 '손상' 으로 보였다(10-31 T4).
  A  `real_profile.admin_share` 가 드라이브를 관리 공유로 바꾼다
  B  관리 공유를 쓸 수 있으면 그 길로, 못 쓰면 `%APPDATA%` 그대로 — 패키지 복사본이 있으면 믿지 않는다(ok=False)
  C  실제 폴더를 읽는 도구(`probe_installed.seed`·`stable_check.REAL`)가 `real_profile` 을 쓴다 — `%APPDATA%` 를 바로 읽지 않는다
  D  (261115-22) 폴더 이름은 branding 의 지금 이름 — 이사 전 PC(옛 폴더만)만 옛 이름. seed 는 재는 판의 이름(REAL.name)
  E  (261115-22) overlap·prune_dist·vprinter_check·release_test 가 앱 이름을 branding 에서 읽는다(옛 'PolyPDF' 고정 결함)
"""
import inspect, os, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts"))
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


try:
    import real_profile
except ImportError as e:
    real_profile = None
    chk(False, "real_profile 모듈이 있다", e)

if real_profile is not None:
    chk(str(real_profile.admin_share(Path(r"C:\Users\u\AppData\Roaming\LocalTools\PolyPDF")))
        == r"\\localhost\C$\Users\u\AppData\Roaming\LocalTools\PolyPDF", "A 관리 공유 경로")
    p, ok = real_profile.real_dir()
    plain = Path(os.environ["APPDATA"]) / "LocalTools" / real_profile.current_name()
    share = real_profile.admin_share(plain)
    if share.parent.is_dir():
        chk(p == share and ok, "B 관리 공유를 쓸 수 있으면 그 길로 읽는다", (p, ok))
    else:
        chk(p == plain and ok == (not real_profile.package_copies()), "B 관리 공유가 없으면 그대로 — 패키지 복사본이 있으면 믿지 않는다", (p, ok))
    # 실제로 섞여 보이는 기계(이 PC)라면: 관리 공유 쪽 index.db 가 셸 쪽과 다를 수 있다 — 관리 공유 쪽이 진짜
    cp = real_profile.package_copies()
    if cp and (cp[0] / "index.db").exists() and (share / "index.db").exists():
        chk(p == share, "B 복사본 index.db 가 있는 기계에서는 관리 공유로 읽는다(섞인 보기를 피한다)", p)

    import probe_installed, stable_check
    src = inspect.getsource(probe_installed.seed)
    chk("real_profile.real_dir" in src and "copytree(REAL," not in src, "C probe_installed.seed 가 real_profile 로 읽는다")
    chk(stable_check.REAL == real_profile.real_dir()[0], "C stable_check.REAL 이 real_profile 경로", stable_check.REAL)

    # D(261115-22): 폴더 이름은 branding — 이사 뒤 옛 'PolyPDF' 를 시드·무결성 대상으로 읽지 않는다(이사 전 PC 만 옛 이름)
    import tempfile
    sys.path.insert(0, str(HERE))
    from viewer import branding as br
    chk("real_dir(REAL.name)" in src, "D probe_installed.seed 가 재는 판의 폴더 이름(REAL.name)으로 읽는다")
    keep = os.environ["APPDATA"]
    with tempfile.TemporaryDirectory() as td:
        os.environ["APPDATA"] = td
        try:
            lt = Path(td) / "LocalTools"
            (lt / br.OLD_ID).mkdir(parents=True)
            chk(real_profile.current_name() == br.OLD_ID, "D 이사 전 PC(옛 폴더만) → 옛 이름", real_profile.current_name())
            (lt / br.APP_ID).mkdir()
            chk(real_profile.current_name() == br.APP_ID and real_profile.real_dir()[0].name == br.APP_ID,
                "D 지금 이름 폴더가 있으면 그것(옛 폴더가 남아 있어도)", real_profile.real_dir())
        finally:
            os.environ["APPDATA"] = keep

    # E(261115-22): 시험·빌드 스크립트가 앱 이름을 branding 에서 — 옛 이름 고정이 이사 판을 놓쳤다
    import overlap, prune_dist, vprinter_check, release_test
    chk(all(n.lower() in overlap.HEAVY for n in br.ALL_EXE_NAMES), "E overlap.HEAVY 에 새·옛 실행 파일 이름", sorted(overlap.HEAVY))
    chk("_br.EXE_STEM" in inspect.getsource(prune_dist.main), "E prune_dist 기본 dist 폴더 = branding.EXE_STEM")
    chk(vprinter_check.INSTALLED_DIR.name == br.EXE_STEM and br.EXE_STEM in vprinter_check.INSTALLED_GS,
        "E vprinter_check 설치 폴더 = branding.EXE_STEM", vprinter_check.INSTALLED_GS)
    chk(all(Path(n).stem in release_test._PROCS for n in br.ALL_EXE_NAMES), "E release_test 가 닫는 프로세스 = 새·옛 이름",
        release_test._PROCS)

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
sys.stdout.flush()
os._exit(0 if not fails else 1)
