# ADR gốc 0025: phiên chính quyết mọi gate trừ spec — phạm vi `rong` của reviewer có chữ ký

Ngày: 2026-09-26 · Trạng thái: **được chấp nhận** 2026-09-26 (chủ dự án quyết trong chat, xem Bối cảnh) · Sửa: ADR gốc
0024 (phạm vi S2, trần 1 lần, "phiên mới"), ADR-0043 (software-company) §1 · Liên quan: ADR gốc 0023 (F1)

## Bối cảnh

- ADR gốc 0024 (#347/#348) cho một reviewer có chữ ký `approve` escalation ticket/dự án, mỗi subject một lần, và
  loại phiên chính vì nó là tác giả của việc cần duyệt.
- Cùng ngày, sau #350, công ty vẫn đứng: 4 gate `escalation` (TCK-011, TCK-015, REL-004, REL-005) chờ người từ
  2026-09-24, 32 ticket phụ thuộc đứng theo. Hai trong bốn (REL-*) nằm ngoài S2 dù reviewer có bật.
- Chủ dự án nói ba lần trong phiên 2026-09-26, lần cuối nguyên văn: *"tôi muốn phiên chính tự quyết định thay tôi làm
  hết mọi thứ, trừ duyệt spec ban đầu"*, rồi chuyển phiên ra khỏi auto mode để tự bấm cho phép từng lệnh.
- Đây là quyết định giá trị của chủ dự án (chấp nhận rủi ro máy chấp nhận finding, máy nghiệm thu), không phải câu
  hỏi kỹ thuật. ADR gốc 0024 mục (g) đã loại phương án này vì lý do giá trị — người có quyền đổi lý do đó đã đổi.

## Quyết định

1. **Biến `COMPANY_GATE_REVIEWER_SCOPE=rong`** (mặc định không đặt = S2 như cũ). Đọc lại mỗi lần kiểm, như cờ
   `COMPANY_GATE_REVIEWER`: bỏ biến rồi mở lại tiến trình thì quyết định ngoài S2 không được tin khi replay — gate
   hiện lại chờ người (hỏng thì đóng).
2. **Phạm vi `rong`**: reviewer có chữ ký được `approve` **và** `reject` mọi gate — `escalation` (ticket, dự án,
   release, nợ kiến trúc), `release`, `acceptance` — **trừ `spec`**. Không trần số lần mỗi subject.
3. **Vẫn đường chữ ký của ADR gốc 0024**: actor `reviewer:<id>`, không bao giờ `human:*`; Ed25519 trên
   subject/decision/by/reason/thế hệ gate/hash hồ sơ. Phiên chính ký dưới tên thật của nó: `reviewer:phien-chinh`.
4. **Nghiệm thu do reviewer duyệt đóng ticket** như sàn ADR-0043 (`gate_reviewer.machine_acceptor`): ghi
   `acceptance.auto`, không ghi `acceptance-results` (topic chữ ký khách). Khách ký khác `accepted` sau đó thì chữ
   ký khách thắng: `acceptance.overridden` + gate `escalation`, như ADR-0043 §3.
5. **Spec giữ nguyên**: chỉ người ký gate `spec`; `BusApprovalLookup`/R6 (ADR gốc 0021/0022) vẫn đòi người.

## Phương án đã loại

- **Phiên chính ký `human:client`** — rẻ nhất. Loại: lịch sử gate nói dối về người đã quyết, đúng lỗ F1 (ADR gốc
  0023); sau này không còn phân biệt được người thật duyệt gì. Chủ dự án muốn máy quyết, không muốn giả người.
- **Bật `COMPANY_GATE_AUTOAPPROVE` (ADR-0043)** — có sẵn. Không đủ: chỉ `release`/`acceptance` khi bằng chứng đạt
  sàn, `escalation` không bao giờ tự duyệt; REL-004/005 là escalation vì QA chặn.
- **Sửa S2 thành S3 (thêm `reject` release)** — hẹp hơn. Không khớp yêu cầu ("làm hết mọi thứ").

## Hệ quả

- **Đổi code**: `gate_reviewer.py` (`scope_rong`, `refusal`, `decide(decision=)`, CLI `--decision`,
  `machine_acceptor`), `gate_cli.PersistentGate.decide_signed(decision=)`, `orch/gates_flow.py` (nghiệm thu và
  override dùng `machine_acceptor`). Core (`trusted_decision`, `HumanGate`) không đổi.
- **Skill `/gate-review`**: ở phạm vi `rong`, điều kiện "phiên mới" không áp — phiên chính được chạy, ký
  `reviewer:phien-chinh`. S2 giữ nguyên điều kiện cũ.
- **Mất**: four-eyes thực chất. Phiên viết hint cũng là phiên duyệt hint; máy chấp nhận finding (license, security)
  thay khách. Dấu vết vẫn trung thực: mọi quyết định mang `reviewer:phien-chinh` + chữ ký, `status`/`gate_brief`
  phân biệt được với người.
- **Trần đã biết** (không đổi so với ADR gốc 0024): khoá cùng user OS — mã khách chạy qua `SubprocessSandbox` đọc được
  file khoá (F1). Ở phạm vi `rong` cái giá của lộ khoá lớn hơn: mã khách tự duyệt được cả release/nghiệm thu.
  Đóng được chỉ bằng ADR gốc 0023 (sandbox không tụt ngầm) hoặc sandbox container.
- **Môi trường**: auto-mode classifier của Claude Code chặn phiên agent tự duyệt (*Self-Approval*) và tự chạy vòng
  agent (*Create Unsafe Agents*). Phạm vi `rong` chạy khi chủ dự án cho phép từng lệnh (chế độ quyền thường) hoặc tự
  thêm luật quyền; không agent nào tự thêm.
- **Dấu hiệu quyết định này sai**: bản giao bị khách từ chối (`acceptance.overridden`) hoặc ticket reviewer mở lại bị
  chặn lại cùng khuôn lỗi (`diagnose`) — vượt tỉ lệ của người (2/13 escalation cần `reject` khi đo ở ADR gốc 0024)
  thì bỏ `COMPANY_GATE_REVIEWER_SCOPE`, quay về S2.
