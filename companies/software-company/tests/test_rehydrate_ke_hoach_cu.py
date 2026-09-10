"""Bản ghi `plan.proposed` của thời 21 agent phải nạp lại được sau khi `Assignee` thắt về `builder`.

Đo trên dữ liệu chạy thật (`company.sqlite` của dự án QLKH, 2026-09-09): 7 bản ghi `plan.proposed` mang
`assignee` là `platform`/`database`/`frontend`/`backend` — từ vựng trước ADR-0037/PR-5d. `Task.model_validate`
thẳng tay trên chúng ném `ValidationError` trong `_rehydrate`, tức là trong `Orchestrator.__init__`, nên
**không lệnh nào** mở nổi DB đó nữa — kể cả `status` chỉ đọc. 18 293 event còn nguyên vẹn mà công ty không
khởi động lại được.

Cả HỌ lỗi, không chỉ chỗ vỡ đầu tiên: `tasks` cũng là bản ghi bền mang `assignee`, nên `delivery._replay_task`
và hai chỗ đọc `tasks` của `supervisor` vỡ y hệt — vá xong chỗ thứ nhất thì lộ ra chỗ thứ hai. Một đường khoan
dung duy nhất (`Task.tu_log`) cho mọi đường PHÁT LẠI; đường sinh MỚI (`ticket_fsm:98`) vẫn nghiêm ngặt.

Đo hai chiều: đổi `Task.tu_log` về `Task.model_validate` ở bất kỳ chỗ nào trong bốn chỗ thì có ca đỏ.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError

from company.events import Envelope
from company.llm import FakeClient
from company.orch.routes import ACTOR
from company.orchestrator import Orchestrator
from company.roles import BUILD_PHASES, ROLE
from company.sqlite_bus import SQLiteBus


def _ticket(tid: str, assignee: str, **kw):
    t = {"ticket_id": tid, "project_id": "QLKH", "requirement_id": "R1", "assignee": assignee,
         "title": "x", "acceptance": ["a"]}
    t.update(kw)
    return t


def _gieo(bus, tickets):
    bus.publish(Envelope(topic="audit-log", key=ACTOR, actor=ACTOR,
                         payload={"actor": ACTOR, "action": "plan.proposed",
                                  "evidence": json.dumps({"plan_id": "PLAN-QLKH-7", "project_id": "QLKH",
                                                          "tickets": tickets})}))


@pytest.mark.parametrize("cu", BUILD_PHASES)
def test_ke_hoach_cu_nap_lai_duoc_va_assignee_thanh_stack(cu, tmp_path):
    """Sáu `assignee` cũ đều mở lại được, và giá trị cũ KHÔNG bị vứt: nó là `stack` ngày nay."""
    db = tmp_path / "c.sqlite"
    _gieo(SQLiteBus(db), [_ticket("TCK-1", cu)])

    o = Orchestrator(SQLiteBus(db), FakeClient())   # trước bản vá: ValidationError ngay ở đây

    t = o.lead.tickets["TCK-1"]
    assert t.assignee == ROLE.BUILDER
    assert t.stack == cu, "assignee cũ mang đúng nghĩa `stack` ngày nay — chuyển sang, không vứt"


def test_stack_da_co_thi_khong_bi_de(tmp_path):
    """Bản ghi mới hơn có sẵn `stack`: `assignee` cũ chuyển vai nhưng không được ghi đè `stack` thật."""
    db = tmp_path / "c.sqlite"
    _gieo(SQLiteBus(db), [_ticket("TCK-1", "platform", stack="data")])

    o = Orchestrator(SQLiteBus(db), FakeClient())

    assert o.lead.tickets["TCK-1"].stack == "data"


def test_assignee_la_rac_van_do(tmp_path):
    """Khoan dung ĐÚNG sáu giá trị lịch sử, không phải khoan dung mọi thứ: `assignee` lạ vẫn phải nổ.

    Nếu không có ca này thì bản vá dễ trôi thành `except ValidationError: pass`, và một kế hoạch hỏng thật sẽ
    lặng lẽ biến mất khỏi hàng đợi sau restart."""
    db = tmp_path / "c.sqlite"
    _gieo(SQLiteBus(db), [_ticket("TCK-1", "khong-ton-tai")])

    with pytest.raises(ValidationError):
        Orchestrator(SQLiteBus(db), FakeClient())


def test_tasks_cu_tren_bus_khong_lam_chet_restart(tmp_path):
    """Chỗ vỡ THỨ HAI cùng họ: `tasks` là bản ghi bền và cũng mang `assignee`.

    Vá xong `plan.proposed` mà chạy lại trên DB thật của QLKH thì lỗi chuyển sang `supervisor.replay` →
    `delivery._replay_task` — cùng một `ValidationError`, cùng một hậu quả (không mở được DB). Ca này khoá cả
    ba chỗ đọc `tasks`: bỏ `Task.tu_log` ở `supervisor._on`, `supervisor._sprint_report` hay
    `delivery._replay_task` đều làm nó đỏ."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    _gieo(bus, [_ticket("TCK-9", "backend")])   # kế hoạch cũ: đưa TCK-9 vào `lead.tickets`
    bus.publish(Envelope(topic="tasks", key="TCK-9", actor="delivery-lead",
                         payload=_ticket("TCK-9", ROLE.BUILDER, retry=1, hint="lam lai")))
    # `guard` chặn `assignee` cũ ngay lúc PUBLISH — đúng như phải thế, event MỚI không được mang từ vựng chết.
    # Nhưng bản ghi đã nằm trong DB từ trước khi schema thắt lại thì không đi qua cổng đó lần nữa, nên tái hiện
    # đúng hiện trạng: sửa thẳng hàng đã lưu, y như dữ liệu thật của QLKH.
    with closing(sqlite3.connect(db)) as con, con:
        (body,) = con.execute("select body from events where topic='tasks'").fetchone()
        d = json.loads(body); d["payload"]["assignee"] = "backend"
        con.execute("update events set body=? where topic='tasks'", (json.dumps(d),))

    o = Orchestrator(SQLiteBus(db), FakeClient())

    assert o.lead.tickets["TCK-9"].retry == 1, "delivery._replay_task phải đọc được task cũ"
    assert o.lead.tickets["TCK-9"].stack == "backend"
    assert o.supervisor.ticket_project["TCK-9"] == "QLKH", "supervisor._on"
    assert o.supervisor.sprint_report()["tickets"]["TCK-9"]["retry"] == 1, "supervisor._sprint_report"
