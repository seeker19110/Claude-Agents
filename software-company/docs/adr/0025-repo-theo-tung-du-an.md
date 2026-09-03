# ADR-0025: Repo khách theo từng dự án — `research-requests.repo` thay vì một `--repo` cho cả tiến trình

## Bối cảnh
Cho tới ADR-0024, "làm code thật" nghĩa là chạy `python -m company.orchestrator run --repo ../khach --base main`:
**một** repo cho **cả tiến trình**. `Orchestrator.repo` / `Orchestrator.integration` là số ít, và mọi chỗ cần
đến repo (worktree ticket, merge vào nhánh tích hợp, tool chỉ đọc cho QA, tool nghiên cứu, `status()`) đều đọc
thẳng hai thuộc tính đó.

Điều này ổn khi một người vận hành một dự án. Nhưng bus của công ty vốn nhiều dự án (`project_id` có mặt trên mọi
topic, blackboard đã phân vùng theo dự án từ ADR-0018), và từ khi console có màn *Giao việc* thì người giao việc
ngồi ở trình duyệt, không ở terminal nơi `--repo` được gõ. Câu hỏi "dự án này lưu ở đâu" phải trả lời được **ngay
lúc giao việc**, từng dự án một — không phải bằng cách khởi động lại orchestrator với cờ khác.

## Quyết định
- `research-requests` nhận thêm hai trường tuỳ chọn: `repo` (đường dẫn repo git của khách, tuyệt đối hoặc tương đối
  với cwd của orchestrator) và `base` (nền để rẽ nhánh tích hợp; mặc định `--base`). Schema đã `additionalProperties:
  true` nên bus cũ vẫn đọc được; hai trường được khai tường minh để có mô tả.
- Orchestrator giữ `project_repos: {project_id → Integration}`. Học từ **log** lúc mở lại (`_rehydrate`) và từ
  **event** lúc chạy (`process`, trước khi intake chạy). `--repo` trở thành **mặc định** cho dự án không tự chỉ repo.
- Mọi điểm chạm chọn repo theo dự án: `workspace(ticket)` qua `lead.tickets[ticket].project_id`; merge tích hợp,
  RC, tool chỉ đọc của QA qua ticket đầu của RC; tool nghiên cứu qua `project_for(event)`. `status()["integration"]`
  giữ hình cũ cho repo mặc định và thêm `projects: {pid: {branch, sha, repo}}`.
- Repo khai sai (không có `.git`): **không dừng dự án**. Nó chạy như dự án không repo (PR ghi `local_checks.unverified`,
  ADR-0010) và audit `project.repo_invalid` **một lần**, kèm repo mặc định sẽ dùng thay. Sửa bằng cách publish lại
  `research-requests` với `repo` đúng — orchestrator cập nhật, không cần khởi động lại.
- Cùng `project_id` publish lại với `repo` khác → đổi sang repo mới (audit `project.repo`). Worktree cũ không bị xoá.

## Hệ quả
- Một tiến trình orchestrator phục vụ nhiều khách, mỗi khách một repo; console giao việc kèm "nơi lưu dự án".
- `lead.require_integration` bật khi có bất kỳ repo nào (mặc định hoặc theo dự án): ticket phụ thuộc chỉ bắt đầu
  sau khi ticket trước lên nhánh tích hợp — cùng luật với ADR-0011, nay theo từng repo.
- Đường dẫn tương đối phụ thuộc cwd của orchestrator; console và orchestrator có thể chạy ở cwd khác nhau, nên form
  khuyến nghị đường dẫn tuyệt đối. Repo phải nằm trên máy chạy orchestrator (console chỉ chuyển chuỗi).
- Chưa làm: nhiều dự án chung một repo với nhánh tích hợp khác nhau (hiện cùng `--integration`), và dọn worktree
  khi dự án đóng.
