"""Năm khuôn lỗi lặp lại của TRAPS.md §1 (root), mỗi khuôn một test (K1.6/K1.7 đặc tả kịch bản B).
Đây không phải test tính năng — là test QUY ƯỚC: mọi module mới trong `orch/` phải tuân, không chỉ những
module đã viết tại thời điểm này. Đỏ ở đây nghĩa là một PR sau đã phá quy ước, không phải một tính năng hỏng."""
from __future__ import annotations

import re
from pathlib import Path

from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orch.routes import _can_author_tests
from company.orchestrator import Orchestrator
from test_orchestrator import T1, handler
from test_tools_and_agentic import _init_repo

ORCH_DIR = Path(__file__).resolve().parents[1] / "src" / "company" / "orch"
ORCH_SRC = {p.name: p.read_text(encoding="utf-8") for p in ORCH_DIR.glob("*.py")}


# ---------- khuôn 1: mọi nhánh `except` chung ghi phân biệt được LOẠI lỗi, không phải một chuỗi cố định ----------

def test_khuon1_except_chung_trong_scheduler_ghi_type_name():
    """`watch()` là vòng chạy DÀI NHẤT trong orch/ — một nhịp lỗi không được giết vòng, nhưng cũng không được
    che mọi nguyên nhân sau một nhãn `tick_error` chung chung (khuôn 1: thông điệp phải nói rõ ĐANG LÀ lỗi gì)."""
    src = ORCH_SRC["scheduler.py"]
    m = re.search(r"except Exception as e:.*?\n(?:.*\n){0,4}", src)
    assert m, "watch() phải còn nhánh except Exception chung quanh tick()"
    assert "type(e).__name__" in m.group(0), "phải ghi TÊN LOẠI lỗi, không phải một chuỗi tick_error cố định"


# ---------- khuôn 2: bất biến restart — bảng chuyển giao K1.7 không được lén thêm state RAM-only ----------

def test_khuon2_bang_chuyen_giao_la_du_lieu_tinh_khong_phai_state():
    """`TICKET_TRANSITIONS`/`RELEASE_TRANSITIONS` (orch/fsm.py) phải là hằng số module-level bất biến — nếu một
    PR sau lỡ biến nó thành state đổi lúc chạy (vd. thêm/bớt hàng theo request), khôi phục qua restart sẽ dựng
    lại bảng khác nhau giữa hai tiến trình mà không ai biết (khuôn 2: state RAM không sống sót qua restart)."""
    from company.orch.release_fsm import RELEASE_TRANSITIONS
    from company.orch.ticket_fsm import TICKET_TRANSITIONS
    assert isinstance(TICKET_TRANSITIONS, list) and isinstance(RELEASE_TRANSITIONS, list)
    for row in (*TICKET_TRANSITIONS, *RELEASE_TRANSITIONS):
        assert row.__class__.__dataclass_params__.frozen, f"{row.name}: Transition phải frozen=True"
    # OrchState (K1.3) vẫn là nơi DUY NHẤT giữ state cần rehydrate; bảng K1.7 không định nghĩa trường nào ở đó.
    from company.orch.state import OrchState
    field_names = {f.name for f in __import__("dataclasses").fields(OrchState)}
    assert not ({"ticket_transitions", "release_transitions"} & field_names)


# ---------- khuôn 3: mọi khoá `once`/`_remember` phải mang THẾ HỆ, trừ danh sách miễn có lý do ----------

# Miễn vì lý do RÕ, không phải vì "chưa ai kêu ca":
# - uat:{rid} / lesson:{tid} / closed:{tid}: đích của chúng (gate nghiệm thu, gói bài học, trạng thái cuối) tự nó
#   chỉ xảy ra MỘT LẦN trong đời chủ thể — không có "lần thứ hai hợp lệ" để bị nuốt oan.
# - no_draft:{e.event_id}: khoá đã mang thế hệ THẬT SỰ — `event_id` đổi mỗi lần một `clarification-answers` MỚI
#   tới, nên một lượt "hợp lệ lặp lại" tự nhiên có key khác, không đụng khoá cũ.
# - delivery.skipped / smoke.unverified: audit phụ (đường ống đã có audit chính mang bằng chứng thật cho MỖI lần
#   thử — `release.smoke`/`release-events` mang payload smoke riêng từng lượt); khoá once ở đây chỉ chặn TIẾNG ỒN
#   audit-log cho một NGUYÊN NHÂN đã biết (thiếu runtime/thiếu repo), không che mất bằng chứng. Nếu sau này audit
#   phụ này trở thành nguồn DUY NHẤT người đọc để biết lượt có unverified hay không, phải bỏ khỏi danh sách này.
KHOA_MIEN: frozenset[str] = frozenset({"uat", "lesson", "closed", "no_draft", "delivery.skipped", "smoke.unverified"})


def test_khuon3_khoa_once_mang_the_he_hoac_nam_trong_danh_sach_mien():
    """`re.findall` theo đúng khuôn đặc tả K1.6: mọi `_remember(f"...")`/`once=f"...")` viết trực tiếp bằng
    f-string literal (không qua biến trung gian) phải có ≥ 2 thành phần `{}` hoặc tiền tố nằm trong `KHOA_MIEN`."""
    pattern = re.compile(r'(?:_remember|once=)\(?f"([^"]+)"')
    vi_pham: list[str] = []
    for name, src in ORCH_SRC.items():
        for key_tmpl in pattern.findall(src):
            n_placeholder = key_tmpl.count("{")
            prefix = key_tmpl.split(":", 1)[0].split("{", 1)[0]
            if n_placeholder >= 2 or prefix in KHOA_MIEN: continue
            vi_pham.append(f"{name}: {key_tmpl!r} (chỉ {n_placeholder} thành phần, không nằm trong KHOA_MIEN)")
    assert not vi_pham, "khoá không thế hệ, không miễn — event lặp lại hợp lệ sẽ bị once nuốt:\n" + "\n".join(vi_pham)


def test_khuon3_no_test_author_ghi_lai_o_moi_lan_rework(tmp_path):
    """Hồi quy cho đúng bẫy K1.2 đã ghi trong đặc tả nhưng chưa sửa tới K1.7: `once=f"no-test-author:{tid}"`
    (không thế hệ) nuốt lần ghi thứ hai — ticket rework mà vẫn không phân vùng được vùng test chỉ hiện MỘT LẦN
    trong audit dù mất lớp bảo vệ ở MỌI lần dispatch. Đo hai chiều nằm trong lịch sử sửa (routes.py)."""
    repo = _init_repo(tmp_path / "repo")
    (repo / "pyproject.toml").unlink()
    import subprocess
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "bỏ dấu hiệu stack"], check=True, capture_output=True)
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=repo, base="main", test_author=True)
    orch.lead.tickets["T1"] = __import__("company.events", fromlist=["Task"]).Task.model_validate({**T1, "retry": 0})
    for retry in (0, 1):
        orch.lead.tickets["T1"] = orch.lead.tickets["T1"].model_copy(update={"retry": retry})
        env = Envelope(topic="tasks", key="T1", actor="delivery-lead", payload={**T1, "retry": retry})
        assert _can_author_tests(env, orch) is False
    acts = [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "tests_authored_by_assignee"]
    assert len(acts) == 2, "hai lần rework (retry khác nhau) phải ghi hai audit riêng, không bị once nuốt"


# ---------- khuôn 4: event cũ (đã bị vượt) không được phát lại như mới sau resume/restart ----------

def test_khuon4_task_cu_bi_vuot_khong_duoc_chay_lai_tren_worktree_da_commit():
    """Kịch bản QLKH-004 (PR #55): task cũ + PR cũ nằm trong hàng đợi hoãn, mở lại bus/duyệt gate → phát lại →
    KHÔNG được giao cho backend chạy trên worktree đã commit tiếp (đó là superseded, không phải việc mới)."""
    from company.orch.ticket_fsm import TICKET_TRANSITIONS
    names = {t.name for t in TICKET_TRANSITIONS}
    assert "superseded" in names, "TICKET_TRANSITIONS phải còn dòng superseded — đây là chốt chặn khuôn 4"
    row = next(t for t in TICKET_TRANSITIONS if t.name == "superseded")
    assert {"tasks", "pull-requests"} <= row.topics, "phải canh cả tasks lẫn pull-requests, không chỉ một trong hai"


# ---------- khuôn 5: mọi sort/sorted theo dấu thời gian phải có khoá phụ `seq` (thứ tự ghi vào bus) ----------

def test_khuon5_moi_sorted_theo_at_hoac_ts_co_khoa_phu():
    """`sorted(...)`/`.sort(...)` mà `key=` chạm `.at`/`.ts`/`["at"]`/`["ts"]` (dấu thời gian) mà KHÔNG có `seq`
    trong cùng biểu thức key là nghi vấn: hai event ghi trong cùng lượt có thể trùng `ts` tới micro giây (#108)."""
    pattern = re.compile(r"(?:\.sort|sorted)\([^)]*key=[^,)]*\b(?:at|ts)\b[^,)]*\)", re.S)
    vi_pham = []
    for name, src in ORCH_SRC.items():
        for m in pattern.finditer(src):
            if "seq" not in m.group(0): vi_pham.append(f"{name}: {m.group(0)!r}")
    assert not vi_pham, "sort theo thời gian thiếu khoá phụ seq — trùng ts tới micro giây sẽ chập chờn:\n" + "\n".join(vi_pham)


# ---------- nghiệm thu cuối K1 (đặc tả kịch bản B): mỗi module orch/ ≤ 400 dòng ----------

def test_kich_thuoc_module_orch_duoi_400_dong():
    """Chốt để không ai vô tình biến MỘT module `orch/` thành `orchestrator.py` thứ hai — mục tiêu của K1 là chia
    nhỏ, một module phình lại tới ~1000 dòng là dấu hiệu cần tách tiếp, không phải "thêm chút cho tiện"."""
    qua_kho: list[str] = []
    for name, src in ORCH_SRC.items():
        n = len(src.splitlines())
        if n > 400: qua_kho.append(f"{name}: {n} dòng")
    assert not qua_kho, "module orch/ vượt 400 dòng, cần tách tiếp:\n" + "\n".join(qua_kho)
