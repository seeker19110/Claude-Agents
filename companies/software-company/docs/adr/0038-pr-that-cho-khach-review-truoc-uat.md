# ADR-0038: PR thật trên GitHub của khách để review trước khi ký UAT — mở, không merge

Trạng thái: Accepted · Ngày: 2026-09-07 · Bổ sung ADR-0027 (giao hàng thật), giữ nguyên ADR-0011 (nhánh tích hợp)
và ADR-0017 (nghiệm thu là gate thật)

## Bối cảnh

ADR-0027 làm phần git của giao hàng thành thật: tag `v<version>` + fast-forward `company/release` trong repo
khách, tuỳ chọn push. Nhưng §5 của nó dừng đúng một bước trước chỗ khách **nhìn thấy** bản giao: "đưa
`company/release` vào `main` là quy trình của khách". Trong thực tế khách nhận được một tag và một nhánh, rồi
phải tự mở PR (hoặc tự merge) để xem diff — tức là điểm review quen thuộc nhất của họ (UI PR trên GitHub) nằm
**ngoài** vòng đời công ty, và gate `acceptance` (ADR-0017) hỏi khách ký trên thứ họ chưa chắc đã mở ra xem.

Hai ràng buộc không được phá:

- **`main` của khách không bị chạm** (ADR-0011 §1, ADR-0027 §5): orchestrator không merge, không push lên `main`,
  không chạy hook/CI của khách thay họ.
- **Review nội bộ giữa các ticket giữ nguyên nhánh tích hợp** (ADR-0011): ticket rẽ từ và merge vào
  `company/integration` ngay khi đủ review; nó chạy nhanh, không cần khách có mặt. PR thật chỉ ở **cuối** — một
  PR cho một bản giao, không phải một PR cho mỗi ticket.

## Quyết định

1. **Cờ `--deliver-pr`, mặc định tắt**, chỉ có nghĩa khi đã có `--deliver` và `--push-remote`. Bật thì sau khi
   `Integration.deliver` đã **push thành công** nhánh release + tag, orchestrator mở PR thật
   `<release_branch> → <nhánh --base>` trên repo GitHub mà `--push-remote` trỏ tới (`orch/release_fsm.py::_delivery_pr`,
   `github_pr.open_pr`). Mở bằng `gh pr create`; **không merge, không approve, không đóng**. Thân PR ghi tag, sha,
   danh sách ticket, và câu "đưa vào `<base>` là quyết định của khách".
2. **Idempotent theo head/base.** Trước khi tạo, `gh pr list --head <release_branch> --base <base> --state open`;
   có PR đang mở thì dùng lại (`created=false`, audit `delivery.pr_reused`). Release sau fast-forward
   `company/release` thì chính PR đó cập nhật — PR là "những gì đang chạy production mà `main` chưa có", không phải
   một PR mỗi phiên bản. Rollback (ADR-0027 §3) đẩy `company/release` lùi bằng `--force-with-lease` nên PR tự lùi
   theo; không có thao tác PR nào khi rollback.
3. **Kết quả là bằng chứng máy ghi, nằm trong `delivery.done`.** Trường `pr` của bản ghi giao hàng:
   `{url, number, created, slug, base, head}`; hoặc `{skipped: lý do}` khi không có gì để mở (chưa bật; thiếu
   `--push-remote`; push chưa thành công; `--base` không phải nhánh (HEAD tách rời); remote không phải GitHub);
   hoặc `{error: lý do}` khi `gh` lỗi (không cài, chưa `auth login`, quyền, mạng). Mỗi trường hợp thêm một dòng
   audit riêng `delivery.pr_opened` / `pr_reused` / `pr_skipped` / `pr_failed`. Vì nằm trong `delivery.done`,
   mở lại bus **dựng lại được** (`Orchestrator.delivered[rid]["pr"]`, `status()["delivery"][rid]["pr"]`) và không
   gọi `gh` lần hai.
4. **`gh` lỗi không chặn vòng đời** — cùng nguyên tắc `delivery.push_failed` của ADR-0027 §4: tag và nhánh đã có,
   người mở PR tay. `gh` chạy trên máy vận hành với env đã lọc bí mật (`clean_env` bỏ `GH_*`/`GITHUB_*`), nên xác
   thực phải nằm trong cấu hình gh trên đĩa (`gh auth login`), không qua biến môi trường. `github_pr.py` là ngoại
   lệ có lý do của test quy ước "không `subprocess` ngoài Sandbox" (ADR-0035), cùng hạng với `git`: argv do code
   ghép, không chạy mã của khách, và nhốt vào container mạng tắt là cắt đường lên GitHub.
5. **Gate `acceptance` hỏi thẳng.** `gates/checklists.md` (gate nghiệm thu) thêm mục tự kiểm "Khách đã xem bản giao trong PR
   thật trên GitHub"; `gate_brief` trả lời từ `delivery.done.pr` (ok kèm số PR + `base ← head`; gap kèm lý do
   skipped/error; unknown khi chưa bật hoặc chưa giao). Bản dẫn xuất `.claude/agents/sc-gate-acceptance.md` sinh
   lại bằng `make subagents`. Prompt `release-engineer` **không đổi**: PR do code mở, không phải lời khai của model.

## Hệ quả

- Khách review bản giao ở đúng chỗ họ quen (diff, comment, CI của họ chạy trên PR), **trước** khi ký `UAT-<rid>`;
  hồ sơ gate nêu số PR để người duyệt đối chiếu. `main` vẫn chỉ đổi khi khách bấm merge.
- Với remote không phải GitHub (GitLab, Gitea, bare cục bộ) cờ này chỉ sinh `pr_skipped` — không có adapter nào
  khác trong ADR này; thêm nền tảng khác là ADR sau, cùng khuôn `open_pr(repo, remote_url, head, base, …)`.
- Thêm một lệnh ngoài (`gh`) phải cài và đăng nhập trên máy vận hành; `docs/HUONG-DAN-VAN-HANH.md` phần giao hàng
  ghi rõ. Thiếu nó thì hệ vẫn chạy, chỉ thiếu PR.
- Chưa làm: comment lên PR khi rollback; đóng PR khi khách reject UAT; PR mỗi phiên bản thay vì một PR trượt theo
  `company/release`. Cả ba là chính sách của khách, để họ nói rồi mới làm.

## Đo hai chiều (ghi trong commit)

`tests/test_delivery_real.py` §ADR-0038: bỏ lời gọi `_delivery_pr` trong `_deliver` → `test_orchestrator_mo_pr_that…`
đỏ (không có `pr` trong `delivered`, thiếu audit `pr_opened`); bỏ nhánh `pr list` → ca "dùng lại" đỏ; bỏ điều kiện
`pushed is not True` → ca "push chưa thành công" đỏ; bỏ ngoại lệ `CHI_GH` → `test_pham_vi_khong_module_nao…` đỏ vì
`github_pr.py` gọi subprocess. Bật lại → xanh.
