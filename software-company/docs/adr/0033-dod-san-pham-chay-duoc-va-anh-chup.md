# ADR-0033: "Định nghĩa xong" phải gồm sản phẩm chạy được; ticket frontend phải đính ảnh chụp giao diện

Trạng thái: chấp nhận · Ngày: 2026-09-06 · Mục B6 của `docs/DAC-TA-NANG-CAP-2026-09.md` · Nối tiếp ADR-0029, ADR-0031

## Bối cảnh

ADR-0029 vá **cơ chế**: orchestrator tự khởi động sản phẩm sau `deployed` ở staging và trước lượt QA hồi quy, ghi
`smoke.verified_by=orchestrator`. ADR-0031 vá **đầu vào**: spec dạng ứng dụng không khai `runtime` thì không có Gate 1.
Cả hai đều là code. Nhưng "xong" trong đầu ba agent điều phối vẫn là *xong tài liệu*:

- delivery-lead: "mọi ticket có requirement_id, acceptance, estimate" — một kế hoạch đủ điều kiện này vẫn có thể
  không chứa ticket nào làm ra điểm vào chạy được. Đó đúng là chuyện đã xảy ra ở QLKH
  (`docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md`): 14/14 ticket xong, 0 lệnh khởi động.
- release-engineer: "mọi stage pass; rollback thử được" — mô tả pipeline, không chạm sản phẩm.
- account-manager: "mỗi release production có biên bản nghiệm thu" — biên bản ký trên biên bản.

Khoảng trống còn lại của ADR-0029 được chính nó ghi ở mục "Chưa làm": **ảnh chụp giao diện cho ticket frontend** —
cùng hình dạng bệnh (lời khai thay bằng chứng), khác kênh bằng chứng. `smoke` chứng minh server trả HTTP 200; nó
không chứng minh màn hình có gì trên đó. Một PR frontend "xong" hôm nay có thể là một trang trắng có route.

## Quyết định

### 1. Một dòng DoD chung cho ba agent điều phối

`delivery-lead` (v11), `release-engineer` (v8), `account-manager` (v8) đều nhận cùng một điều kiện, diễn đạt theo
văn phong từng vai nhưng **nội dung là một**:

> sản phẩm khởi động bằng một lệnh ghi trong README và trả lời một request thật

- delivery-lead: ticket điểm vào phải nằm trong **lô đầu**, không để sau.
- release-engineer: bằng chứng là `smoke` do orchestrator chạy (ADR-0029), **không phải** mô tả pipeline.
- account-manager: không mời khách ký khi smoke chưa xanh; `unverified` thì hỏi *"chạy cho tôi xem"* trước.

Đây là prompt, không phải cổng code — cổng code đã có ở ADR-0029/0031. Prompt tồn tại để agent **tự** dừng trước
khi chạm cổng, thay vì làm xong rồi bị cổng đánh về.

### 2. Ticket frontend đính ảnh chụp giao diện

`frontend` (v13): mỗi màn hình đã chạm có ít nhất một ảnh, ghi vào `pull-requests.payload.evidence.screenshots[]` —
`{path, screen, state, how}`, `path` là file ảnh **đã commit** trong worktree, `how` là lệnh đã sinh ra nó.
Trường `evidence` được khai tường minh trong `topics/schemas/pull-requests.json` và `PullRequest` (`events.py`).

### 3. Công cụ: KHÔNG thêm playwright — và nói rõ vì sao

Đặc tả B6 gợi ý một tool `screenshot` chạy playwright headless. Bác bỏ, ba lý do đo được:

1. **Phải tải browser.** `playwright install chromium` kéo ~150 MB nhị phân ngoài `uv.lock`, mỗi runner CI, mỗi
   máy trực, mỗi worktree. Repo hiện chạy offline hoàn toàn (provider `fake` + eval replay); một bước tải mạng
   bắt buộc phá tính chất đó.
2. **Nặng và chậm ở chỗ không cần.** 20/21 agent không chụp ảnh; chi phí rơi lên toàn bộ CI vì một vai.
3. **Vượt ranh giới tin cậy ADR-0013/0029.** Tool `run` cố ý không có shell: model chỉ chọn **tên** lệnh trong
   allowlist do `Stack` sinh, code ghép `argv`. Một tool `screenshot` nhận URL tuỳ ý là một trình duyệt đầy đủ
   chạy nội dung do model chọn — đó là quyết định sandbox (D2/ADR-0035), không phải quyết định DoD.

**Chọn đường nhẹ:** không tool mới. Ảnh chụp sinh bằng **lệnh khai trong `runtime` của spec** — cùng kênh tin cậy
với `runtime.command` của ADR-0029 (spec-writer viết, người ký ở Gate 1, chạy qua allowlist của `run`). Dự án nào
cần ảnh thì tự mang theo công cụ chụp của stack mình (`npm run screenshots`, `vitest --browser`, script của khách),
và nó hiện ra ở Gate 1 để người ký thấy — thay vì công ty ép mọi dự án dùng một trình duyệt.

### 4. Không có đường chụp thì phải **nói ra**, không im lặng

Đây là điều kiện chặt hơn cả bản thân ảnh. Bẫy đã trả giá bốn vòng rework (`TRAPS.md` §2, "ép agent làm việc nó
không có tool"): agent thiếu năng lực thì **lặng lẽ sửa việc khác**, không ai biết. Nên `frontend` bắt buộc ghi
một mục `{screen, state, skipped: true, reason}` khi không chụp được — mảng rỗng và mảng có `skipped` là hai
trạng thái khác nhau, và chỉ trạng thái thứ hai là hợp lệ khi có màn hình bị chạm. Cùng hình dạng với
`smoke.unverified` (ADR-0029 mục 3) và `local_checks.unverified` (ADR-0010): **không đường nào được kết thúc
trong im lặng**.

## Hệ quả

- 4 agent tăng version, ghi lại eval bằng model thật, golden + `.claude/agents/` sinh lại (7 bước `CONTRIBUTING.md` §3).
- `pull-requests` có `evidence` tường minh; `PullRequest.evidence` mặc định `{}` nên PR cũ vẫn hợp lệ.
- `gates/checklists.md` **không đổi**: ảnh chụp là DoD của ticket, người ký ở Gate 3 chấm release chứ không chấm
  từng PR; reviewer đọc `evidence.screenshots[]` trong payload PR như đọc `local_checks`. Nếu về sau muốn chặn
  cứng (PR frontend không có `screenshots[]` → `request_changes`) thì đó là một cổng code, cần ADR riêng và nguồn
  bằng chứng khai trước ở `src/company/gate_checklists.py`.

## Giới hạn (nói thẳng, đừng để người sau tưởng đã đủ)

1. **Không có ảnh nào được chụp tự động.** Cho tới khi một spec khai lệnh chụp, mọi PR frontend sẽ trả
   `skipped` — đúng thiết kế, nhưng nghĩa là ADR này hôm nay mua được *tính minh bạch*, chưa mua được *bằng chứng*.
2. **Ảnh không được máy chấm.** Không so sánh pixel, không phát hiện trang trắng; `verified_by` không áp dụng.
   Người đọc PR nhìn ảnh. Đây vẫn là một cấp trên "không có gì để nhìn".
3. **`path` là lời khai.** Reviewer có tool đọc file (#87) nên kiểm được file có tồn tại; nội dung ảnh thì không.
4. Chụp ảnh do orchestrator chạy (đối xứng với `run_smoke`) là bước tiếp theo tự nhiên — nó thuộc D1/D2 khi đã có
   sandbox container, không thuộc ADR này.
