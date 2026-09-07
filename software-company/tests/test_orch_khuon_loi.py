"""Năm khuôn lỗi lặp lại của TRAPS.md §1 (root), mỗi khuôn một test (K1.6/K1.7 đặc tả kịch bản B).
Đây không phải test tính năng — là test QUY ƯỚC: mọi module mới trong `orch/` phải tuân, không chỉ những
module đã viết tại thời điểm này. Đỏ ở đây nghĩa là một PR sau đã phá quy ước, không phải một tính năng hỏng."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
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
# - review.escalate:{key}: một thành phần nhưng `key` là biến ĐÃ ghép sẵn `review:{tid}:{src}:{since}` ngay
#   trên đó — thế hệ (`since`) nằm trong biến, mẫu regex không nhìn xuyên biến được.
# - delivery.skipped / smoke.unverified TỪNG được miễn với lý do "audit phụ, đường ống đã có audit chính".
#   K1.4 bỏ miễn: lý do đó chỉ đúng cho nhánh CÓ chạy được smoke (`release.smoke` mang payload từng lượt) —
#   đúng hai nhánh dùng khoá này là nhánh KHÔNG chạy được (thiếu `runtime`, thiếu worktree) và ở đó audit phụ
#   là bản ghi DUY NHẤT nói lượt ấy chưa kiểm. Cả hai nay mang `event_id` của lượt.
KHOA_MIEN: frozenset[str] = frozenset({"uat", "lesson", "closed", "review.escalate"})


def _co_the_he(key_tmpl: str) -> bool:
    """Khoá mang thế hệ khi có ≥ 2 thành phần, HOẶC khi thành phần duy nhất là `event_id` — `event_id` đổi mỗi
    lần một event mới tới, nên một lượt "hợp lệ lặp lại" tự nhiên có khoá khác và không đụng khoá cũ."""
    phan = re.findall(r"\{([^}]+)\}", key_tmpl)
    return len(phan) >= 2 or any(x.strip().endswith("event_id") for x in phan)


def test_khuon3_khoa_once_mang_the_he_hoac_nam_trong_danh_sach_mien():
    """`re.findall` theo đúng khuôn đặc tả K1.6: mọi `_remember(f"...")`/`once=f"..."`/`once_key=f"..."` viết
    trực tiếp bằng f-string literal (không qua biến trung gian) phải mang thế hệ (`_co_the_he`) hoặc có tiền tố
    nằm trong `KHOA_MIEN`. `once_key=` (đường của `supervisor.escalate_gate`) từng lọt lưới vì mẫu cũ chỉ bắt
    `once=`, mà `"once_key="` không chứa chuỗi con `"once="` — `gate.escalate:{sid}` sống sót nhờ lỗ đó."""
    pattern = re.compile(r'(?:_remember|once(?:_key)?=)\(?f"([^"]+)"')
    vi_pham: list[str] = []
    for name, src in ORCH_SRC.items():
        for key_tmpl in pattern.findall(src):
            prefix = key_tmpl.split(":", 1)[0].split("{", 1)[0]
            if _co_the_he(key_tmpl) or prefix in KHOA_MIEN: continue
            vi_pham.append(f"{name}: {key_tmpl!r} (không mang thế hệ, không nằm trong KHOA_MIEN)")
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


def test_khuon3_gate_the_he_hai_van_duoc_escalate(tmp_path):
    """K1.4: `gate.escalate:{sid}` (một thành phần) nuốt gate THỨ HAI của cùng subject. Cùng một `subject_id`
    mở gate nhiều lần trong đời là chuyện thường (`escalation` sau `release`, gate mở lại sau khi hỏng), và
    `HumanGate.pending` khoá theo `subject_id` nên gate mới ghi đè gate cũ dưới đúng cái tên đó — không có gì
    trong khoá cũ phân biệt được hai thế hệ. Đo hai chiều: bỏ `:{_the_he(...)}` khỏi hai khoá trong
    `scheduler.py` thì cả hai assert của thế hệ hai đỏ."""
    from company.gates import GateRequest

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    def _mo_va_qua_han():
        orch.gate.request(GateRequest(kind="escalation", subject_id="G1", created_by="supervisor",
                                      checklist=["root_cause", "decision:reopen|close", "hint"]))
        orch.tick(now=datetime.now(UTC) + orch.gate.timeout + timedelta(minutes=1))

    _mo_va_qua_han()
    assert len([a for a in orch.supervisor.actions if a.target == "G1" and a.action == "escalate"]) == 1
    orch.gate.decide("G1", "approve", by="human:pm", reason="root_cause: kẹt; decision: reopen; hint: chạy lại")

    _mo_va_qua_han()   # thế hệ hai: gate MỚI cho cùng subject, cũng quá hạn
    esc = [a for a in orch.supervisor.actions if a.target == "G1" and a.action == "escalate"]
    assert len(esc) == 2, f"gate thế hệ hai quá hạn phải escalate lần nữa, nhận được {len(esc)}"
    overdue = [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.overdue"]
    assert len(overdue) == 2, "và phải vào audit-log lần nữa — audit-log là bản ghi bền duy nhất"


def test_khuon3_smoke_unverified_ghi_lai_o_lan_deploy_thu_hai():
    """K1.4: `smoke.unverified:{rid}` nuốt lần deploy thứ hai của cùng release. Hai nhánh dùng khoá này là hai
    nhánh KHÔNG chạy được smoke (thiếu `runtime`, thiếu worktree) — ở đó audit phụ này là bản ghi DUY NHẤT nói
    lượt ấy chưa kiểm, nên nuốt là mất bằng chứng thật. Đo hai chiều: bỏ `:{rc.event_id}` thì assert == 2 đỏ."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    for _ in range(2):   # cùng release id, hai lượt deploy staging riêng biệt (redeploy sau khi sửa)
        rc = Envelope(topic="release-candidates", key="REL-1", actor="delivery-lead",
                      payload={"release_id": "REL-1", "project_id": "P1"})
        orch._smoke("release-engineer", rc, "REL-1", {"status": "deployed"}, None)
    acts = [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "release.smoke_unverified"]
    assert len(acts) == 2, f"hai lượt deploy phải ghi hai audit unverified, nhận được {len(acts)}"


def test_khuon3_delivery_skipped_ghi_lai_o_lan_giao_thu_hai():
    """K1.4: `delivery.skipped:{rid}` nuốt lần giao thứ hai. Nhánh này không đưa `rid` vào `o.delivered` (chưa
    giao được gì cả) nên lượt production sau của cùng release ĐI TỚI đây lần nữa — và im lặng. Đo hai chiều:
    bỏ `:{env.event_id}` thì assert == 2 đỏ."""
    from company.orchestrator import StepResult

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler), deliver=True)
    for _ in range(2):
        env = Envelope(topic="release-events", key="REL-1", actor="release-engineer",
                       payload={"release_id": "REL-1", "env": "production", "status": "deployed"})
        orch._deliver(env, StepResult(env.event_id, env.topic, env.key))
    acts = [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "delivery.skipped"]
    assert len(acts) == 2, f"hai lượt production phải ghi hai audit skipped, nhận được {len(acts)}"


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
