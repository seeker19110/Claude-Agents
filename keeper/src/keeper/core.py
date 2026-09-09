"""`CORE` — công ty bảo trì `keeper`, nhìn từ `xagents_core` (ADR gốc 0001 §2, ADR `0006-cong-ty-bao-tri-keeper`).

Một chỗ DUY NHẤT nói "công ty này tên KEEPER, gốc ở đây, bus tên `keeper.sqlite`". Mọi module của `keeper` cần
một trong ba thứ đó thì đọc từ đây, không tự dựng lại từ `__file__` của mình.

Tên phân phối của package VÀ tên import ở đây TRÙNG NHAU — cả hai đều là `keeper` — khác `video-creators`/
`studio` hay `company` (dist khác import). Vì trùng nhau nên rất dễ quên LÝ DO `prefix` bám theo tên import chứ
không theo tên dist: `prefix` là tiền tố của biến môi trường (`KEEPER_LLM_PROVIDER`…) và của mọi thông điệp lỗi
có nhắc biến — nó phải khớp với tên mà người vận hành gõ trong shell (`import keeper`), không phải tên hiện
trên PyPI/`pyproject.toml [project.name]`. Ở `studio`/`company` sự khác biệt hai tên buộc người viết phải chọn
có ý thức; ở `keeper` chọn "đúng vì tình cờ trùng" là chọn không hiểu lý do — xem `Studio-creators/src/studio/core.py:6-8`.

**`topic_acl` của `keeper` ĐO ra, không suy ra** — cùng lý do đã ghi ở `Studio-creators/src/studio/core.py:10-19`:
phần lớn event của `keeper` do CODE phát (`adapter:github`, `orchestrator`, `release`), không do agent. Bảng
dưới đây là phiên bản BT1: chưa có mã sinh event thật (BT2 trở đi mới có `github.py`/`orchestrator.py`), nên nó
được viết theo bảng "Topic của `keeper`" ở `DAC-TA-KEEPER.md` §1 và SẼ được đo lại (bọc `InMemoryBus.publish`,
chạy toàn suite) khi các khối đó tồn tại — đúng quy trình studio đã đi qua.
"""
from __future__ import annotations

from pathlib import Path

from xagents_core.config import CoreConfig, TopicACL

from .events import NAMESPACE_OWNERS, PAYLOAD_MODELS

# Bảng "Topic của keeper" — `DAC-TA-KEEPER.md` §1. Producer là AGENT hoặc CODE (`adapter:github`, `orchestrator`,
# `release`) tuỳ topic. Ở BT1 chưa có actor nào trong bảng này TỒN TẠI dưới dạng mã: chúng là hợp đồng khai
# trước, sẽ được đo lại (bọc `InMemoryBus.publish`, chạy toàn suite) khi BT3-BT7 sinh event thật.
TOPIC_PRODUCERS: dict[str, frozenset[str]] = {
    "maintenance-signals": frozenset({"dependency-scout", "health-monitor", "drift-detector", "adapter:github"}),
    "maintenance-tickets": frozenset({"triager"}),
    "patch-proposals": frozenset({"patcher", "refactorer"}),
    "verification-reports": frozenset({"regression-guard"}),
    "security-findings": frozenset({"security-auditor"}),
    "debt-ledger": frozenset({"triager", "keeper-supervisor"}),
    "release-notes": frozenset({"release-clerk"}),
    "supervisor-actions": frozenset({"keeper-supervisor"}),
}
# Người nạp tay được MỘT việc bảo trì thô (`maintenance-signals`), nhưng KHÔNG nạp tay ticket: ticket phải đi
# qua `triager` để có `risk_tier` (`DAC-TA-KEEPER.md` §1, cuối).
HUMAN_TOPICS = frozenset({"maintenance-signals"})
OPEN_TOPICS = frozenset({"audit-log", "shared-context"})  # audit: ai cũng ghi; shared-context: kiểm theo namespace

CORE = CoreConfig(
    prefix="KEEPER",
    # File này ở `src/keeper/core.py`. `parents[1]` là `src/` — không phải gốc package (không có `pyproject.toml`,
    # không có `llm.yaml`, không có `topics/`). `parents[2]` mới là `keeper/` — nơi thật sự có các thư mục đó.
    root=Path(__file__).resolve().parents[2],
    db_name="keeper.sqlite",
    topic_acl=TopicACL(producers=TOPIC_PRODUCERS, human_topics=HUMAN_TOPICS, open_topics=OPEN_TOPICS),
    payload_models=PAYLOAD_MODELS,
    namespace_owners=NAMESPACE_OWNERS,
    global_namespaces=frozenset({"knowledge"}),
    # Topic mà payload đến từ NGOÀI công ty: tín hiệu GitHub (`dependabot`, `code-scanning`, `gh` API) không do
    # agent kiểm soát nội dung. Lọc thay vì từ chối cả lô — đọc một alert Dependabot CHÍNH LÀ việc của
    # `dependency-scout`.
    external_topics=frozenset({"maintenance-signals"}),
    # Nội bộ nhưng nội dung dẫn xuất từ đầu ra công cụ ngoài (diff `gh`, output `pytest`/`ruff`/`mypy`): từ chối
    # là kẹt vĩnh viễn trên cùng một event.
    derived_topics=frozenset({"verification-reports", "security-findings"}),
    # Trường mang nội dung không tin cậy dù event nội bộ.
    untrusted_fields=frozenset({"detail", "evidence", "summary", "output_tail", "changelog_line", "session_line"}),
    # Mẫu injection RIÊNG của công ty bảo trì: nó đọc log CI, diff, và alert bảo mật — nơi kẻ tấn công dễ nhét
    # câu lệnh giả trang thông điệp lỗi nhất. Xem `guard.py` quyết định 2.
    extra_injection_patterns=(
        ("ignore-previous", r"\bignore\s+(all\s+)?previous\s+instructions\b"),
        ("developer-mode", r"\bdeveloper\s+mode\b"),
    ),
)
