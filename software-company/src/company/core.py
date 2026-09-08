"""`CORE` — công ty gia công phần mềm, nhìn từ `xagents_core` (ADR gốc 0001 §2).

Một chỗ DUY NHẤT nói "công ty này tên COMPANY, gốc ở đây, bus tên `company.sqlite`". Mọi module của company cần
một trong ba thứ đó thì đọc từ đây, không tự dựng lại từ `__file__` của mình — hai nguồn cho một sự thật thì sớm
muộn chúng lệch (và lệch đường dẫn gốc là đọc nhầm `llm.yaml` của repo khác mà không có lỗi nào nổi lên).

K3.4 điền ba trường của guard (`external_topics`, `derived_topics`, `untrusted_fields`). Các trường còn lại
(`topic_acl`, `payload_models`, `namespace_owners`, `transitions`) điền ở K3.5 khi bus chuyển sang core — khai
trước một bảng rỗng ở đây là mời người sau tin vào nó.

`extra_injection_patterns` để TRỐNG có chủ ý: bảng chung của `xagents_core.guard` đã là bảng của company. Hai
mẫu riêng của studio (`developer mode`, `jailbreak`) cố ý KHÔNG có ở đây — chúng là từ vựng nghiệp vụ hợp lệ của
một công ty phần mềm (`skills/mobile.md` dùng "jailbreak" cho yêu cầu bảo mật app di động), thêm vào là làm
ticket bảo mật mobile bị `injection_detected` và không chạy được.
"""
from __future__ import annotations

from pathlib import Path

from xagents_core.config import CoreConfig

CORE = CoreConfig(
    prefix="COMPANY",
    root=Path(__file__).resolve().parents[2],   # software-company/ : llm.yaml, agents/, skills/, topics/schemas/
    db_name="company.sqlite",
    # Topic mà payload đến từ ngoài công ty (khách, người dùng, hệ thống ngoài): lọc thay vì từ chối.
    external_topics=frozenset({"external-feedback", "research-requests", "clarification-answers",
                               "acceptance-results", "incidents", "change-requests"}),
    # Topic nội bộ nhưng payload dẫn xuất từ code/tài liệu khách: lọc thay vì từ chối (từ chối = lặp vô tận).
    derived_topics=frozenset({"pull-requests", "research-findings", "review-results"}),
    # `hint` và `content` KHÔNG nằm đây: chúng do agent nội bộ viết (delivery-lead, chủ namespace), nên injection
    # ở đó là dấu hiệu agent bị chiếm — từ chối chạy mới đúng.
    untrusted_fields=frozenset({"diff", "web", "fetched", "attachments", "text", "description", "feedback",
                                # chuỗi trích từ repo khách hoặc model viết tự do về nó: mô tả PR, tên file đã
                                # sửa, log lint/test (`local_checks.lint_output`), stdout của lệnh
                                "summary", "title", "body", "notes", "message", "comment",
                                "lint_output", "test_output", "changed_files", "files", "logs", "output", "stdout"}),
)
