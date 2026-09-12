# TRAPS.md — bẫy riêng của xagents-core

Bốn khuôn chung ở `../../TRAPS.md` §1 áp nguyên vẹn (mọi công ty dùng chung lõi này). Dưới đây là bẫy đã cắn
người ngay trong chính core — mỗi dòng có test hoặc đoạn code làm chốt chặn.

## Bẫy đã vá

| Bẫy | Đã xảy ra | Chốt chặn / lần sau |
|---|---|---|
| Đồng hồ Windows bước ~15,6ms làm 2 gate trùng khoá `once` | Hai gate cùng `subject_id` mở cách nhau <16ms có cùng `created_at` → khoá chống-trùng nuốt mất lần quá hạn thứ hai (đo 2026-09-09) | `GateRequest.seq` là bộ đếm tăng dần thay `created_at` để phân biệt thế hệ (`gates.py`) |
| `PersistentGate` tin `evidence.by` thay vì `env.actor` | Lỗ hổng "actor giả mạo qua evidence" bị vá 2 LẦN Ở 2 CHỖ KHÁC NHAU trước khi hai công ty hợp nhất về một `gate_cli.py` — cùng lỗ hổng, hai lần phát hiện độc lập | `trusted_decision` chỉ đọc `env.actor` (ACL producer lúc publish), không đọc trường tự khai trong payload |
| `RecordingClient` không chốt `prompt_version` đúng lúc | Sự cố 2026-09-05: ghi bản eval xong đổi prompt, bản ghi cũ vẫn coi là hợp lệ vì version chốt muộn | Chốt `prompt_version` lúc `__init__`; `save()` GỘP thay vì ghi đè (`evals.py`) |
| `QUOTA_PATTERNS` khớp không ranh giới từ | Studio production: chuỗi "insufficient"/"429" khớp nhầm "unlimited", "billingham", "4290" thành hết quota | Mẫu có ranh giới từ, đo chéo 23 câu thử giữa hai công ty trước khi gộp (`routing.py`) |
| Bộ lọc injection lệch giữa hai công ty | K3.4: company bắt 8 mẫu mà studio (cũ) trượt, studio bắt 4 mẫu mà company trượt — mỗi bên tự viết mẫu riêng không đối chiếu | Gộp về một bảng mẫu chung ở `guard.py`, viết lại `vi-ignore` sau khi phát hiện CẢ HAI bản cũ đều trượt cùng 2 câu tấn công tiếng Việt |
| Chống lặp bằng cờ RAM sai sau mở lại bus | `Supervisor` (khuôn 2 `../../TRAPS.md`): cờ "đã cảnh báo" sống trong RAM, mở lại tiến trình là mất, cảnh báo lặp lại vô hạn | Trạng thái chống lặp phải đọc lại từ audit-log lúc `_rehydrate`, không chỉ khởi tạo rỗng |

## Cách rà khi có lỗi mới

Cùng khuôn 4 lỗi ở `../../TRAPS.md` §1, thêm câu riêng cho lõi: *"nếu sửa ở đây, cả hai công ty (software-company
VÀ keeper) có cùng cần hành vi mới không?"* — core không biết tên công ty nào (ADR-0001 §2); một nhu cầu chỉ một
bên cần thuộc về lớp con của công ty đó, không thuộc đây. Sửa `routing.py`/`guard.py` xong: chạy lại test của cả
hai công ty (không chỉ `xagents-core/tests/`), vì cả hai import cùng một bản.
