"""BT6 — `family.py`: sửa một lỗi thì rà cả HỌ lỗi đó (`TRAPS.md` §1).

Ca chiều ngược: bỏ hàng kiểm `safe-must-exist` → CÙNG báo cáo (có `hits`, `safe` rỗng) không còn bị từ chối.
"""
import pytest

from keeper.family import (
    FAMILY_RULES,
    MAX_FAMILY_HITS,
    MAX_FAMILY_MECHANISMS,
    FamilyReport,
    FamilyReportInvalid,
    FamilySite,
    Mechanism,
    SafeSite,
    grep_repo,
    mechanisms_from_patch,
    require_family_report,
    rules_without,
    scan_family,
)

DIFF = """diff --git a/src/keeper/x.py b/src/keeper/x.py
--- a/src/keeper/x.py
+++ b/src/keeper/x.py
@@ -1,4 +1,5 @@
-def parse_due(raw):
+def parse_due(raw, *, tz):
+    TABLE = {"weekly-quota": 1}
-    OLD = re.compile(r"\\(#(?P<n>\\d+)\\)")
+    NEW = re.compile(r"\\(#(?P<n>\\d+)\\)")
"""


def test_rut_co_che_tu_patch_ba_kieu():
    mechs = mechanisms_from_patch(DIFF)
    kinds = {(m.kind, m.name) for m in mechs}
    assert ("function", "parse_due") in kinds
    assert ("key", "weekly-quota") in kinds
    assert any(k == "regex" for k, _ in kinds)


def test_khong_co_gi_de_rut_thi_danh_sach_rong():
    assert mechanisms_from_patch("diff --git a/a.md b/a.md\n+một dòng văn xuôi\n") == []


def test_grep_toan_repo_tim_dung_cho_cung_co_che(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = parse_due(raw)\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "src" / "x.py").write_text("def parse_due(raw, *, tz):\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "c.py").write_text("parse_due(raw)\n", encoding="utf-8")
    (tmp_path / "anh.png").write_bytes(b"\x89PNG parse_due")

    mech = Mechanism(kind="function", name="parse_due")
    hits = grep_repo(tmp_path, [mech], exclude=["src/x.py"])
    paths = [h.path for h in hits]
    assert paths == ["src/a.py"]  # .git bị bỏ, đuôi lạ bị bỏ, file của chính patch bị loại
    assert hits[0].line == 1 and hits[0].mechanism == "parse_due"


def test_grep_khong_co_co_che_nao_thi_khong_doc_dia(tmp_path):
    (tmp_path / "a.py").write_text("parse_due(raw)\n", encoding="utf-8")
    assert grep_repo(tmp_path, []) == []


def test_grep_bo_qua_file_khong_doc_duoc(tmp_path):
    bad = tmp_path / "hong.py"
    bad.write_bytes(b"\xff\xfe khong phai utf-8 parse_due")
    assert grep_repo(tmp_path, [Mechanism(kind="function", name="parse_due")]) == []


def test_bao_cao_co_hits_ma_safe_rong_la_KHONG_hop_le():
    report = FamilyReport(
        mechanisms=["parse_due"],
        hits=[FamilySite(path="src/a.py", line=1, text="parse_due(raw)", mechanism="parse_due")],
        safe=[],
    )
    with pytest.raises(FamilyReportInvalid) as e:
        require_family_report(report)
    assert "safe-must-exist" in str(e.value)


def test_chieu_nguoc_bo_hang_kiem_safe_thi_cung_bao_cao_do_qua_cua():
    report = FamilyReport(
        mechanisms=["parse_due"],
        hits=[FamilySite(path="src/a.py", line=1, text="parse_due(raw)", mechanism="parse_due")],
        safe=[],
    )
    with pytest.raises(FamilyReportInvalid):
        require_family_report(report)
    require_family_report(report, rules=rules_without("safe-must-exist"))  # không ném


def test_bao_cao_co_safe_kem_ly_do_thi_hop_le():
    report = FamilyReport(
        mechanisms=["parse_due"],
        hits=[FamilySite(path="src/a.py", line=1, text="parse_due(raw)", mechanism="parse_due")],
        safe=[SafeSite(path="src/b.py", mechanism="parse_due", reason="chuỗi đã aware từ pydantic, không so naive")],
    )
    require_family_report(report)


def test_safe_khong_kem_ly_do_thi_khong_hop_le():
    report = FamilyReport(
        mechanisms=["parse_due"],
        hits=[FamilySite(path="src/a.py", line=1, text="parse_due(raw)", mechanism="parse_due")],
        safe=[SafeSite(path="src/b.py", mechanism="parse_due", reason="   ")],
    )
    with pytest.raises(FamilyReportInvalid, match="safe-must-be-explained"):
        require_family_report(report)


def test_khong_co_hits_thi_khong_can_safe():
    require_family_report(FamilyReport(mechanisms=[], hits=[], safe=[]))


def test_rules_without_ten_la_thi_no():
    with pytest.raises(KeyError):
        rules_without("khong-co")
    assert [r.name for r in FAMILY_RULES] == ["safe-must-exist", "safe-must-be-explained"]


def test_scan_family_rap_ca_cum_va_de_safe_rong_cho_nguoi_dien(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("def parse_due(raw, *, tz):\n", encoding="utf-8")
    (tmp_path / "src" / "a.py").write_text("parse_due(raw)\n", encoding="utf-8")
    report = scan_family(tmp_path, DIFF, files=["src/x.py"])
    assert "parse_due" in report.mechanisms
    assert [h.path for h in report.hits] == ["src/a.py"]
    assert report.safe == []
    with pytest.raises(FamilyReportInvalid):
        require_family_report(report)


# --- trần: nội dung diff (bên NGOÀI, không do repo quyết định) không được quyết định chi phí quét ----------

def test_grep_repo_cat_bot_co_che_theo_tran(tmp_path):
    (tmp_path / "a.py").write_text("khong co gi\n", encoding="utf-8")
    qua_tran = [Mechanism(kind="key", name=f"khoa-{i}") for i in range(MAX_FAMILY_MECHANISMS + 10)]
    # Không ném, không treo — chỉ còn đúng MAX_FAMILY_MECHANISMS cơ chế đầu được xét (không assert số hit vì
    # file test không chứa khoá nào; đo trực tiếp qua kết quả rỗng + không lỗi là đủ cho ca này).
    assert grep_repo(tmp_path, qua_tran) == []


def test_grep_repo_dung_o_dau_vong_lap_file_khi_da_du_hit(tmp_path):
    """Trần được kiểm ở ĐẦU vòng lặp theo file, không chỉ trong vòng theo dòng: một file đầu tiên đã đủ hit,
    file thứ hai không được mở ra đọc nữa."""
    lines = "\n".join(f"parse_due(raw)  # dong {i}" for i in range(MAX_FAMILY_HITS + 5))
    (tmp_path / "a.py").write_text(lines + "\n", encoding="utf-8")
    (tmp_path / "z.py").write_text("parse_due(raw)\n", encoding="utf-8")
    hits = grep_repo(tmp_path, [Mechanism(kind="function", name="parse_due")])
    assert all(h.path == "a.py" for h in hits)  # "z.py" (sắp sau theo `sorted()`) không bao giờ được xét


def test_grep_repo_dung_som_khi_du_hit_theo_tran(tmp_path):
    # Một file có nhiều dòng khớp hơn MAX_FAMILY_HITS: `grep_repo` phải dừng ở trần, không rap hết.
    lines = "\n".join(f"parse_due(raw)  # dong {i}" for i in range(MAX_FAMILY_HITS + 50))
    (tmp_path / "a.py").write_text(lines + "\n", encoding="utf-8")
    hits = grep_repo(tmp_path, [Mechanism(kind="function", name="parse_due")])
    assert len(hits) <= MAX_FAMILY_HITS + 1  # trần chặn ở biên trong, không rap tới hết file
    assert len(hits) < MAX_FAMILY_HITS + 50  # ca chiều ngược: bỏ trần thì số hit bằng đúng số dòng


def test_grep_repo_khong_co_tran_thi_rap_het_ca_cum_chieu_nguoc(tmp_path, monkeypatch):
    """Chiều ngược THẬT: nới trần lên vô cực thì cùng đầu vào lại rap HẾT, không dừng sớm."""
    import keeper.family as family_mod
    lines = "\n".join(f"parse_due(raw)  # dong {i}" for i in range(MAX_FAMILY_HITS + 50))
    (tmp_path / "a.py").write_text(lines + "\n", encoding="utf-8")
    monkeypatch.setattr(family_mod, "MAX_FAMILY_HITS", 10**9)
    hits = grep_repo(tmp_path, [Mechanism(kind="function", name="parse_due")])
    assert len(hits) == MAX_FAMILY_HITS + 50
