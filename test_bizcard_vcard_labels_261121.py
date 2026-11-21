# -*- coding: utf-8 -*-
"""vCard 가져오기 — 라벨·그룹 카드는 명함으로 넣지 않음 (명함 SOT §5.24.5 '라벨 카드 거르기', 261120-60). 가짜 vCard 만."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 — 아래 가져오기가 임시 명함 DB 를 쓴다
from viewer.bizcard.vcard import people_from_vcf
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


VCF = """BEGIN:VCARD
VERSION:3.0
FN:가짜홍
item1.TEL:010-0000-1111
item1.X-ABLabel:개인폰
CATEGORIES:myContacts,가짜모임,starred
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:가짜모임
CATEGORIES:가짜모임
END:VCARD
BEGIN:VCARD
VERSION:4.0
KIND:group
FN:가짜그룹
MEMBER:urn:uuid:0000
END:VCARD
BEGIN:VCARD
VERSION:3.0
X-ADDRESSBOOKSERVER-KIND:group
FN:가짜애플그룹
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:0001
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:starred
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:가짜모임
TEL:010-0000-2222
END:VCARD
"""
ps = people_from_vcf(VCF)
names = [p["name"] for p in ps]
chk(names == ["가짜홍", "가짜모임"], "라벨 이름뿐인 카드·그룹 카드는 빼고, 번호가 있는 같은 이름은 사람으로", str(names))
chk(ps[0]["memo"] == "" and [n for _k, n in ps[0]["phones"]] == ["010-0000-1111"], "라벨·칸 이름표는 칸 값에 넣지 않음", str(ps[0]))
chk(ps[0].get("labels") == ["가짜모임"], "구글 라벨은 해시태그 후보로(myContacts·starred 빼고, 사용자 지시 261121)", str(ps[0].get("labels")))
import tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from viewer import settings_store
_T = Path(tempfile.mkdtemp(prefix="bizcard_vlabels_"))
settings_store._LOCAL_DIR_OVERRIDE = str(_T)
from viewer.bizcard import people as P, store as S, gsync as G
st = S.BizcardStore(_T / "b.db")
P.apply_import(st, ps, "주소록", "google")
t0 = st._row(st.con.execute("SELECT * FROM cards WHERE name='가짜홍'").fetchone())["tags"]
chk("가짜모임" in t0 and "myContacts" not in t0 and "가짜모임" in G.label_tags(st),
    "가져오기 — 라벨은 해시태그로, 구글 라벨로 올릴 해시태그에도", str((t0, G.label_tags(st))))
st.close()
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
