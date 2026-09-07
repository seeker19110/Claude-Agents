"""Tên vai. ADR-0037 (PR-4): đây là NƠI DUY NHẤT id agent xuất hiện dưới dạng chuỗi trong `src/` (ngoài `agents/*.md`).

Mọi chỗ khác — bảng route, producer của bus, chủ namespace blackboard, actor của event, `truth.py` bên console —
tham chiếu hằng ở đây, nên đổi tên một agent chỉ sửa **một** file mã và file front matter của nó. Trong lúc gộp
21 agent thành 5 (PR-5a..5e) hằng đổi GIÁ TRỊ, không đổi tên: `ROLE.SECURITY` trước PR-5a là `"security-engineer"`,
từ PR-5a là `"security"`, code gọi nó không biết gì.

Ba nhóm hằng, cố ý tách:
- `ROLE.*` — id agent (khớp `id:` trong front matter; `tests/test_roles.py` đối chiếu hai chiều với `load_agents()`).
- `BUILD_PHASES` — sáu mảng kỹ thuật: `stack` của TICKET và pha của `builder`, KHÔNG phải id agent (PR-5d).
- `SOURCE.*` — nhãn `source` của `review-results` (`reviewer|qa|security`). KHÔNG phải id agent, dù trùng chữ:
  `REVIEW_AGENT` mới là bảng nguồn → agent chấm.
- `LEAD_ACTOR` — actor của event do `delivery.py` (code, không phải model) phát: `tasks`, `release-candidates`,
  gate release. Hôm nay trùng với `ROLE.LEAD` vì delivery-lead vừa là agent chia ticket vừa là "vai" của phần
  code đóng vòng; ADR-0037 gộp agent vào `product` còn actor này giữ nguyên.
"""
from __future__ import annotations

from typing import Final, Literal


class ROLE:
    """Namespace hằng, không khởi tạo. Nhóm theo đích ADR-0037; hằng của agent chưa gộp vẫn mang id cũ."""

    # → `product` (PR-5e): intake + researcher + synthesizer + risk + clarifier + spec-writer + delivery-lead (pha `plan`)
    PRODUCT: Final = "spec-writer"
    INTAKE: Final = "intake"
    RESEARCHER: Final = "researcher"
    SYNTHESIZER: Final = "synthesizer"
    RISK: Final = "risk"
    CLARIFIER: Final = "clarifier"
    LEAD: Final = "delivery-lead"
    # → `builder` (PR-5d: xong) — sáu agent kỹ thuật GỘP thành một hằng, sáu tên cũ thành PHA của nó
    # (`BUILD_PHASES` bên dưới = `Task.stack`). Như PR-5b/5c, `test_hang_role_khop_front_matter_hai_chieu` cấm
    # hai hằng cùng giá trị nên năm hằng cũ không còn; sáu id cũ vào `MIGRATED` trỏ về `"builder"`.
    # Sáu tên ấy vẫn tồn tại trong hệ, nhưng là `stack` của TICKET (dữ liệu, ADR-0013), không phải id agent.
    BUILDER: Final = "builder"
    # → `qa` (PR-5c: xong) — test-author (pha `author`) + reviewer + qa-debugger (pha `review`) GỘP thành một
    # hằng, như `ops` ở PR-5b: `test_hang_role_khop_front_matter_hai_chieu` cấm hai hằng cùng giá trị nên
    # `TEST_AUTHOR` và `REVIEWER` không còn; ba id cũ vào `MIGRATED` trỏ về `"qa"`. Nhãn `source` của
    # `review-results` vẫn là `SOURCE.REVIEWER`/`SOURCE.QA` — hai GÓC NHÌN chấm, không phải hai agent.
    QA: Final = "qa"
    # → `security` (PR-5a: xong, đổi tên 1:1)
    SECURITY: Final = "security"
    # → `ops` (PR-5b: xong) — release-engineer (pha `deploy`) + support-docs (pha `docs`) + account-manager
    # (pha `account`) GỘP thành một hằng: khác PR-5a (đổi tên 1:1), đây là gộp 3→1 nên hai hằng cũ
    # (`SUPPORT_DOCS`, `ACCOUNT_MANAGER`) không còn — `test_hang_role_khop_front_matter_hai_chieu` cấm hai hằng
    # cùng giá trị, và ba id cũ đều vào `MIGRATED` trỏ về `"ops"`.
    OPS: Final = "ops"
    # Code, không phải công đoạn — giữ nguyên qua ADR-0037
    SUPERVISOR: Final = "supervisor"


class SOURCE:
    """Nhãn `source` của `review-results` — ai CHẤM, theo góc nhìn nào. Trùng chữ với vài id agent là tình cờ lịch sử."""

    REVIEWER: Final = "reviewer"
    QA: Final = "qa"
    SECURITY: Final = "security"


LEAD_ACTOR: Final = "delivery-lead"  # actor của event do delivery.py phát — không phải agent

# Agent viết code; từ PR-5d chỉ còn một (`bus.ENGINEERING_ACTORS` là producer hợp lệ của `pull-requests`).
ENGINEERING: tuple[str, ...] = (ROLE.BUILDER,)

class STACK:
    """Mảng kỹ thuật của một TICKET (ADR-0013), đồng thời là tên pha của `builder` (ADR-0037).

    Sáu chuỗi này trùng sáu id agent cũ (PR-5d gộp chúng), nên `tests/test_roles.py` chặn chúng ở mọi file `src/`
    khác — ai cần một stack thì tham chiếu hằng ở đây. Không phải id agent: `Task.stack` là dữ liệu do product
    điền khi chia ticket, còn `Task.assignee` luôn là `builder`.
    """

    BACKEND: Final = "backend"
    FRONTEND: Final = "frontend"
    MOBILE: Final = "mobile"
    DATABASE: Final = "database"
    PLATFORM: Final = "platform"
    DATA: Final = "data"


BUILD_PHASES: tuple[str, ...] = (STACK.BACKEND, STACK.FRONTEND, STACK.MOBILE, STACK.DATABASE, STACK.PLATFORM, STACK.DATA)

# `Literal` bắt buộc viết chuỗi tay (typing không nhận biến), nên ba kiểu này sống ở đây cùng chuỗi gốc của chúng;
# `tests/test_roles.py` khoá `get_args(Assignee) == ENGINEERING`, `get_args(BuildPhase) == BUILD_PHASES` và
# `get_args(ReviewSource)` khớp `SOURCE`.
Assignee = Literal["builder"]
BuildPhase = Literal["backend", "frontend", "mobile", "database", "platform", "data"]
ReviewSource = Literal["reviewer", "qa", "security"]
