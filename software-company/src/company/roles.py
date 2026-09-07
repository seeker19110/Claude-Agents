"""Tên vai. ADR-0037 (PR-4): đây là NƠI DUY NHẤT id agent xuất hiện dưới dạng chuỗi trong `src/` (ngoài `agents/*.md`).

Mọi chỗ khác — bảng route, producer của bus, chủ namespace blackboard, actor của event, `truth.py` bên console —
tham chiếu hằng ở đây, nên đổi tên một agent chỉ sửa **một** file mã và file front matter của nó. Trong lúc gộp
21 agent thành 5 (PR-5a..5e) hằng đổi GIÁ TRỊ, không đổi tên: `ROLE.SECURITY` hôm nay là `"security-engineer"`,
sau PR-5a là `"security"`, code gọi nó không biết gì.

Ba nhóm hằng, cố ý tách:
- `ROLE.*` — id agent (khớp `id:` trong front matter; `tests/test_roles.py` đối chiếu hai chiều với `load_agents()`).
- `SOURCE.*` — nhãn `source` của `review-results` (`reviewer|qa|security`). KHÔNG phải id agent, dù trùng chữ:
  `REVIEW_AGENT` mới là bảng nguồn → agent chấm.
- `LEAD_ACTOR` — actor của event do `delivery.py` (code, không phải model) phát: `tasks`, `release-candidates`,
  gate release. Hôm nay trùng với `ROLE.LEAD` vì delivery-lead vừa là agent chia ticket vừa là "vai" của phần
  code đóng vòng; ADR-0037 gộp agent vào `product` còn actor này giữ nguyên.
"""
from __future__ import annotations

from typing import Final, Literal


class ROLE:
    """Namespace hằng, không khởi tạo. Nhóm theo đích ADR-0037; giá trị HIỆN TẠI là id agent cũ (PR-4 chưa đổi agent)."""

    # → `product` (PR-5e): intake + researcher + synthesizer + risk + clarifier + spec-writer + delivery-lead (pha `plan`)
    PRODUCT: Final = "spec-writer"
    INTAKE: Final = "intake"
    RESEARCHER: Final = "researcher"
    SYNTHESIZER: Final = "synthesizer"
    RISK: Final = "risk"
    CLARIFIER: Final = "clarifier"
    LEAD: Final = "delivery-lead"
    # → `builder` (PR-5d): sáu agent kỹ thuật thành một agent, sáu tên thành pha (`BUILD_PHASES` = `Task.stack`)
    BACKEND: Final = "backend"
    FRONTEND: Final = "frontend"
    MOBILE: Final = "mobile"
    DATABASE: Final = "database"
    PLATFORM: Final = "platform"
    DATA: Final = "data"
    # → `qa` (PR-5c): test-author (pha `author`) + reviewer + qa-debugger (pha `review`)
    QA: Final = "qa-debugger"
    TEST_AUTHOR: Final = "test-author"
    REVIEWER: Final = "reviewer"
    # → `security` (PR-5a): đổi tên 1:1
    SECURITY: Final = "security-engineer"
    # → `ops` (PR-5b): release-engineer (pha `deploy`) + support-docs (pha `docs`) + account-manager (pha `account`)
    OPS: Final = "release-engineer"
    SUPPORT_DOCS: Final = "support-docs"
    ACCOUNT_MANAGER: Final = "account-manager"
    # Code, không phải công đoạn — giữ nguyên qua ADR-0037
    SUPERVISOR: Final = "supervisor"


class SOURCE:
    """Nhãn `source` của `review-results` — ai CHẤM, theo góc nhìn nào. Trùng chữ với vài id agent là tình cờ lịch sử."""

    REVIEWER: Final = "reviewer"
    QA: Final = "qa"
    SECURITY: Final = "security"


LEAD_ACTOR: Final = "delivery-lead"  # actor của event do delivery.py phát — không phải agent

# Sáu agent kỹ thuật; thứ tự là thứ tự khai trong `Assignee`. `orch/routes.py::ENGINEERING` tham chiếu bảng này.
ENGINEERING: tuple[str, ...] = (ROLE.BACKEND, ROLE.FRONTEND, ROLE.MOBILE, ROLE.DATABASE, ROLE.PLATFORM, ROLE.DATA)

# `Literal` bắt buộc viết chuỗi tay (typing không nhận biến), nên hai kiểu này sống ở đây cùng chuỗi gốc của chúng;
# `tests/test_roles.py` khoá `get_args(Assignee) == ENGINEERING` và `get_args(ReviewSource)` khớp `SOURCE`.
Assignee = Literal["backend", "frontend", "mobile", "database", "platform", "data"]
ReviewSource = Literal["reviewer", "qa", "security"]
