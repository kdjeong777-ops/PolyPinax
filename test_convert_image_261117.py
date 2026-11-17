# -*- coding: utf-8 -*-
"""261117-5: 변환 창 분류 '문서'·'이미지', 이미지 형식·화질·크기, 여러 장은 파일 이름 폴더 (형식 변환 SOT §2.3.1·§5, 디자인 SOT §2.24).

사용자 지시: "pdf '변환'에서 현재 이미지(PNG)만 있는데, 투명 등이 없을 경우 압축이되는 jpg 등으로 선택하여 변환할 수 있도록 하고,
화질의 높음, 보통으로 선택할 수 있도록 수정 검토. 왼쪽에 대표항목으로, 문서, 이미지로 하고, 오른쪽창에 문서일 경우 이미지 이외의 항목,
이미지일 경우 해당 형식과 사이즈를 선택할 수 있도록 수정. 여러 이미지는 기본적으로 파일명으로 폴더를 만들어서 저장"
사용자 결정: 형식 JPG·PNG·WebP / 화질과 크기 따로 / 한 장이면 폴더 없이 / 폴더가 있으면 새 폴더 ' (2)'.
  A  실제 `ConvertDialog`: 왼쪽 '문서'·'이미지', 문서 쪽에 이미지 형식 없음, 이미지 쪽 형식·화질·크기, PNG 면 화질 흐리게,
     미리 고른 `png` 면 이미지 분류, 사진 모드(문서 형식만)는 목록 숨김
  B  실제 `convert.run`(`test_fixtures.text_pdf()`): JPG·WebP·PNG 머리 바이트, 크기 dpi 대로 픽셀, 화질 보통 < 높음 용량
  C  여러 장 → `<이름>` 폴더, 있으면 `<이름> (2)`, 한 장 → 폴더 없이 `<이름>_p0003.jpg`, 겹치면 ` (2)`
  D  고른 값 기억 — [변환] 뒤 prefs(`convert_image`), 다음 창 처음 값, 설정 허용 목록(`_apply_prefs`)이 지킨다
**수정 전 코드로 A~D 실패.**
"""
import os, shutil, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pathlib import Path
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication
QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication(sys.argv)
import test_fixtures
from viewer import convert

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


ROOT = Path(tempfile.mkdtemp(prefix="convimage_test_"))
try:
    src = ROOT / "보고서.pdf"
    shutil.copy2(test_fixtures.text_pdf(), str(src))
    import fitz
    d = fitz.open(str(src)); pw = d[0].rect.width; npg = d.page_count; d.close()

    # ── A. 변환 창 ──
    from viewer.widgets.convert_dialog import ConvertDialog
    dlg = ConvertDialog(None, files=[str(src)], page_count=npg)
    dlg.show(); app.processEvents()
    lst = getattr(dlg, "lst_groups", None)
    items = [lst.item(i).text() for i in range(lst.count())] if lst is not None else []
    chk(lst is not None and lst.isVisible() and items == ["문서", "이미지"], "A 왼쪽 분류 '문서'·'이미지'", str(items))
    chk("png" not in getattr(dlg, "_fmt_btn", {}) and dlg.format_key() == "docx_shape",
        "A 문서 쪽에는 이미지 밖 형식만, 처음은 Word (원본 모양)", str(list(getattr(dlg, "_fmt_btn", {}))))
    if lst is not None:
        lst.setCurrentRow(1); app.processEvents()
        img_ok = all(hasattr(dlg, a) for a in ("img_fmt", "img_q", "img_dpi"))
        chk(img_ok and dlg.format_key() == "png" and set(dlg.img_fmt) == {"jpg", "png", "webp"}
            and set(dlg.img_q) == {"high", "normal"} and set(dlg.img_dpi) == {96, 150, 300}
            and dlg.img_fmt["jpg"].isVisible(),
            "A 이미지 쪽 — 형식 JPG·PNG·WebP·화질 높음·보통·크기 96·150·300 dpi", str(dlg.format_key()))
        if img_ok:
            o = dlg.image_options()
            chk(o == {"fmt": "jpg", "quality": "high", "dpi": 150}, "A 처음 값 JPG·높음·150 dpi", str(o))
            dlg.img_fmt["png"].setChecked(True); app.processEvents()
            chk(not dlg.img_q["high"].isEnabled(), "A PNG 면 화질 흐리게")
            dlg.img_fmt["webp"].setChecked(True); app.processEvents()
            chk(dlg.img_q["high"].isEnabled(), "A WebP 면 화질 고를 수 있다")
    dlg.close()
    d2 = ConvertDialog(None, files=[str(src)], page_count=npg, preset="png")
    chk(hasattr(d2, "group") and d2.group() == "image" and d2.format_key() == "png", "A 미리 고른 형식이 이미지면 이미지 분류로")
    d3 = ConvertDialog(None, files=[str(src)], page_count=1, keys=convert.PHOTO_KEYS)
    d3.show(); app.processEvents()
    chk(getattr(d3, "lst_groups", None) is not None and not d3.lst_groups.isVisible() and d3.format_key() == "docx_shape",
        "A 분류가 하나면(사진 모드) 왼쪽 목록을 숨긴다")
    d3.close()

    # ── B. 형식·크기·화질 ──
    def run(pages, **o):
        try:
            return convert.run(str(src), "png", pages, image=o)
        except TypeError as e:
            chk(False, "B convert.run 이 image 선택값을 받는다", repr(e))
            return None
    heads = {}
    outs = {}
    for fk in ("jpg", "webp", "png"):
        p = run([0, 1], fmt=fk, quality="high", dpi=96)
        outs[fk] = p
        files = sorted(p.iterdir()) if p and p.is_dir() else []
        heads[fk] = (len(files), files[0].suffix if files else "", files[0].read_bytes()[:12] if files else b"")
    chk(heads["jpg"][0] == 2 and heads["jpg"][1] == ".jpg" and heads["jpg"][2][:3] == b"\xff\xd8\xff", "B JPG 는 JPEG 파일", str(heads["jpg"]))
    chk(heads["webp"][1] == ".webp" and heads["webp"][2][:4] == b"RIFF" and heads["webp"][2][8:12] == b"WEBP", "B WebP 는 WebP 파일", str(heads["webp"]))
    chk(heads["png"][1] == ".png" and heads["png"][2][:4] == b"\x89PNG", "B PNG 는 PNG 파일", str(heads["png"]))
    from PIL import Image
    widths = {}
    for dpi in (96, 300):
        p = run([4, 5], fmt="png", dpi=dpi)
        f = sorted(p.iterdir())[0] if p and p.is_dir() else None
        widths[dpi] = Image.open(str(f)).size[0] if f else 0
    chk(abs(widths[96] - pw * 96 / 72) <= 2 and abs(widths[300] - pw * 300 / 72) <= 2, "B 크기 — dpi 대로 픽셀",
        f"{widths} (쪽 폭 {pw:.0f}pt)")
    size = {}
    for q in ("high", "normal"):
        p = run([6, 7], fmt="jpg", quality=q, dpi=150)
        size[q] = sum(f.stat().st_size for f in p.iterdir()) if p and p.is_dir() else 0
    chk(0 < size["normal"] < size["high"], "B 화질 보통 < 높음 (용량)", str(size))

    # ── C. 폴더 ──
    first = outs.get("jpg")
    chk(first is not None and first == ROOT / "보고서" and first.is_dir(), "C 여러 장 → 파일 이름 폴더", str(first))
    chk(outs.get("webp") == ROOT / "보고서 (2)" and outs["webp"].is_dir(), "C 폴더가 있으면 새 폴더 ' (2)' — 있는 폴더에 섞지 않는다",
        str(outs.get("webp")))
    one = run([2], fmt="jpg", quality="high", dpi=96)
    chk(one is not None and one == ROOT / "보고서_p0003.jpg" and one.is_file(), "C 한 장 → 폴더 없이 원본 옆 '<이름>_p0003.jpg'", str(one))
    one2 = run([2], fmt="jpg", quality="high", dpi=96)
    chk(one2 is not None and one2 == ROOT / "보고서_p0003 (2).jpg" and one2.is_file(), "C 한 장 이름이 겹치면 ' (2)'", str(one2))

    # ── D. 기억 ──
    prefs = {}
    try:
        d4 = ConvertDialog(None, files=[str(src)], page_count=npg, preset="png", prefs=prefs)
        d4.img_fmt["webp"].setChecked(True); d4.img_q["normal"].setChecked(True); d4.img_dpi[300].setChecked(True)
        d4._accept()
        chk(prefs == {"fmt": "webp", "quality": "normal", "dpi": 300}, "D [변환] 뒤 고른 값을 prefs 에", str(prefs))
        d5 = ConvertDialog(None, files=[str(src)], page_count=npg, prefs=prefs)
        chk(d5.image_options() == prefs, "D 다음 창의 처음 값 = 지난번 고른 값", str(d5.image_options()))
    except (TypeError, AttributeError) as e:
        chk(False, "D 고른 값 기억", repr(e))
    from types import SimpleNamespace
    from viewer.app import MainWindow
    fake = SimpleNamespace(_prefs={"convert_image": {"fmt": "png"}})
    try:
        MainWindow._apply_prefs(fake, {"language": "ko"})
    except Exception:
        pass                                        # 뒤쪽 화면 적용은 가짜 창에 없다 — 허용 목록 dict 만 본다
    chk(fake._prefs.get("convert_image") == {"fmt": "png"}, "D 설정 허용 목록이 convert_image 를 지킨다(조용히 사라지지 않게)",
        str(fake._prefs.get("convert_image")))
finally:
    shutil.rmtree(ROOT, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
