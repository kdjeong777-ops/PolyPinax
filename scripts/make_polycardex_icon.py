"""PolyCardex(명함 프로그램) 바로가기·창 아이콘 만들기 — 명함 SOT §5.27 '바로가기'.

본 화면 명함 아이콘(`icons._bizcard` — 모드 토글과 같은 TV)을 256px 로 그려 `resources/polycardex.png` 와
여러 크기를 담은 `resources/polycardex.ico` 로 저장한다. 그림을 바꾸면 이 스크립트를 다시 돌려 두 파일을 커밋한다
(빌드는 만들지 않고 저장소의 파일을 쓴다 — resources 는 --add-data 로 실린다).
    python scripts/make_polycardex_icon.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")            # 검사 작성 SOT §14.7.2-21 — 한글을 찍는다
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int = 256):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter
    from viewer.widgets import icons
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(size / 16.0, size / 16.0)
        icons._bizcard(p, False)                      # 밝은 그림 — 바로가기는 탐색기·시작 메뉴 배경과 무관하게 한 장
    finally:
        p.end()
    return img


def main() -> int:
    from PyQt6.QtWidgets import QApplication
    from PIL import Image
    app = QApplication.instance() or QApplication(sys.argv)   # noqa: F841 — QPainter 글꼴·색 준비
    res = os.path.join(ROOT, "resources")
    png = os.path.join(res, "polycardex.png")
    if not render(256).save(png, "PNG"):
        print("PNG 저장 실패", png)
        return 1
    Image.open(png).convert("RGBA").save(os.path.join(res, "polycardex.ico"), format="ICO", sizes=[(s, s) for s in SIZES])
    print("ok", png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
