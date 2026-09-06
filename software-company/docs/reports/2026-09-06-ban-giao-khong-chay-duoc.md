# Bản giao đầu tiên không chạy được — quy trình đã bỏ lọt ở đâu

Ngày: 2026-09-06 · Dự án: QLKH (LMS Sao Mai, bản thử nghiệm) · Bản giao: REL-025 v0.15.1, sha `1f5734a`,
tag + push origin 13:07, khách ký nghiệm thu 13:10.

## Chuyện gì xảy ra

Sau 25 release-candidate, 6 bản vá cấu trúc trong một buổi sáng (PR #73–#78) và một bản giao được ký đủ bốn gate,
chủ dự án nói: "run dev dự án để kiểm thử". Kết quả: **không có gì để chạy.**

- Backend `qlkh/` có 20 module `*_service.py` / `*_http.py`, 389 test pass, nhưng KHÔNG có điểm vào: không
  `python -m qlkh...`, không router, không bind cổng. Chính docstring của `student_http.py` (QLKH-005) ghi rõ:
  *"kho mã QLKH CHƯA chọn framework HTTP … đó là quyết định kiến trúc chưa tồn tại, ngoài phạm vi ticket và ngoài
  năng lực agent backend tự quyết. Vì vậy module này KHÔNG đăng ký route thật."* Mọi ticket sau đó (006–014,
  CR-OPS-001) đều xây tiếp trên giả định "framework tương lai sẽ map request/response".
- Frontend `web/` (Vite + React) build được, 3 test pass, nhưng `BASE_URL` mặc định là
  `https://api.qlkh.example.vn/v1` — một địa chỉ ví dụ trong contract, không có server nào đứng sau.
- Hạ tầng: `infra/README.md` nói thẳng "chưa có tài nguyên: DEF-01 (nhà cung cấp cloud) chưa quyết".
- Mười bốn ticket, mỗi ticket đều đúng phạm vi của nó, đều pass 3 phiếu review, đều "hoàn thành".
  Tổng của mười bốn việc hoàn thành là một sản phẩm không khởi động được.

## Vì sao bốn gate không bắt được

| Gate | Câu nó hỏi | Câu nó KHÔNG hỏi |
|---|---|---|
| 1 spec | PRD, Gherkin, UX flow, rủi ro | "Sản phẩm này chạy ở đâu, bằng lệnh gì?" |
| 2 plan | ticket ≤ 1 ngày, estimate, risk_tags, contract, C4 | "Ticket nào tạo ra thứ khởi động được? Quyết định kiến trúc nào còn treo (framework, cloud) mà ticket đang né?" |
| 3 release | tests, scan, regression-staging, perf, a11y, runbook, rollback | "Staging là gì trong môi trường này? Có URL nào trả 200 không?" |
| 4 acceptance | uat-script, acceptance-criteria, known-issues, signed_by | "Người ký đã bấm vào cái gì?" |

Ba cơ chế cụ thể đã biến "không chạy được" thành "đã giao":

1. **"Deploy" là lời khai, không phải bằng chứng.** `release-events env=staging status=deployed` do
   release-engineer phát ra sau khi đọc payload; không có tool nào chạy lệnh, không có health-check, không có
   URL. Orchestrator chỉ ghi `release.staged` = sha của nhánh tích hợp. QA hồi quy chạy tool đọc worktree, tức
   là đọc code chứ không gọi dịch vụ. Cả dây chuyền "staging → QA → production" là một chuỗi văn bản tự nhất quán.
2. **Quyết định kiến trúc bị né có hệ thống.** Agent backend đúng khi từ chối tự chọn framework (ngoài quyền).
   Nhưng không có nơi nào để "quyết định còn treo" nổi lên: `plan.proposed` không có trường `open_decisions`,
   Gate 2 không hỏi, supervisor không đếm. DEF-01/DEF-03 được nhắc trong hàng chục review và threat-model
   (mục 28–33) như "nợ cũ vẫn mở" — và vẫn mở khi ký nghiệm thu.
3. **Definition of done của mọi vai đều là DoD của tài liệu.** delivery-lead: "contract tồn tại trước ticket
   đầu tiên; mọi ticket có requirement_id, acceptance, estimate". spec-writer: "100% Must có Gherkin".
   account-manager: "mỗi release production có biên bản nghiệm thu". Không vai nào có DoD "sản phẩm khởi động
   được bằng một lệnh và trả lời một request".

## Việc đã làm ngay

- CR-DEV-001 (13:20): adapter `http.server` stdlib + `python -m qlkh.devserver` với repository in-memory và dữ
  liệu seed, `.env.development` cho web, một test tích hợp login → /auth/me → /students. Không chọn framework
  production trong CR này; đó vẫn là ADR phải có người ký.
- Báo cáo này.

## Đề xuất hoàn thiện công ty (chưa làm, cần quyết)

1. **Gate 1 thêm mục "chạy ở đâu"**: spec phải ghi `runtime`: lệnh khởi động, cổng, phụ thuộc ngoài (DB, cache,
   cloud). Không có thì `request_changes`. PRD template thêm mục tương ứng.
2. **Gate 2 thêm `open_decisions`** trong `plan.proposed`: delivery-lead liệt kê mọi quyết định kiến trúc mà
   ticket đang né (framework, cloud, DB thật). Có ≥ 1 quyết định treo mà không có ticket ADR + người ký → plan
   có `problems`, không xin gate. Ticket "điểm vào chạy được" (entrypoint + smoke test) là ticket bắt buộc của
   plan đầu tiên cho dự án dạng ứng dụng.
3. **Gate 3: `regression-staging` phải có bằng chứng chạy**, không phải verdict. Tool `run` của QA hồi quy phải
   khởi động dịch vụ theo `runtime` của spec và gọi ít nhất một endpoint; kết quả (lệnh, mã thoát, mã HTTP) vào
   `evidence`. Release-engineer không có tool thì `status=deployed` chỉ được chấp nhận khi payload mang
   `evidence.smoke` do orchestrator tự chạy — cùng nguyên tắc với `local_checks` của PR (code chạy thật, không
   phải model tự khai).
4. **Gate 4: hồ sơ `gate_brief` cho acceptance tự khởi động sản phẩm** theo `runtime` và đính kèm kết quả smoke;
   khách ký trên thứ đã chạy, không trên biên bản.
5. **Supervisor đếm "nợ kiến trúc treo"** như đếm ngân sách: threat-model/schema/infra nhắc cùng một mã nợ
   (DEF-xx, SD-xx) quá N lần review liên tiếp → escalation cấp dự án, không đợi người tình cờ đọc.
6. **DoD của delivery-lead, release-engineer, account-manager** thêm một dòng giống nhau: *"sản phẩm khởi động
   bằng một lệnh ghi trong README và trả lời một request thật"*.

Mỗi đề xuất là một PR riêng (prompt là code: đổi agent/gate/template → cập nhật golden + eval recording).

## Bài học cho người trực ban

Bốn gate xanh, 100% test pass, 25 release, 0 sản phẩm. Số liệu đúng, chỉ là chúng đo cái khác. Trước khi tin
dashboard, hỏi câu của khách: *"Chạy cho tôi xem."*
