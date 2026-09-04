# Tech decisions (ADR) — QLKH

Định dạng: Bối cảnh → Quyết định → Hệ quả → Phương án đã loại.

---

## ADR-001 — Đơn tổ chức (single-tenant), ba cơ sở là phạm vi phân quyền
- **Trạng thái**: accepted (2026-09-04), **thay thế bản trước** (bản trước ghi nhầm "một cơ sở")
- **Bối cảnh**: OQ-02 được human:owner trả lời: 3 cơ sở tại TP.HCM thuộc **cùng một tổ chức**, không phải ranh giới tin cậy tách biệt.
- **Quyết định**: Không thiết kế multi-tenant. Dữ liệu thuộc một tổ chức duy nhất. Phân quyền theo **vai + phạm vi cơ sở** (`branch_id` trên học viên/lớp/nhân sự) và theo quan hệ (giáo viên–lớp, phụ huynh–học viên). `branch_id` là bộ lọc phân quyền, không phải tenant boundary.
- **Hệ quả**: T-02 của threat-model hạ từ "rò rỉ xuyên tenant" xuống **rò rỉ chéo học viên/cơ sở**, mức High (không còn Critical vì không có ranh giới tin cậy giữa pháp nhân). Vẫn **bắt buộc kiểm quyền ở tầng dữ liệu** (ADR-004) cho cả trục cơ sở lẫn trục quan hệ.
- **Đã loại**: multi-tenant chia sẻ schema (không có nhu cầu thật); bỏ hẳn trục cơ sở (sẽ để quản lý cơ sở A thấy dữ liệu cơ sở B).
- **Liên quan**: OOS-4, ASM-02, REQ-002, REQ-009.

## ADR-002 — Xác thực bằng phiên phía máy chủ, mật khẩu băm argon2id
- **Trạng thái**: accepted
- **Bối cảnh**: Người dùng là phụ huynh và giáo viên, thiết bị đa dạng; cần thu hồi phiên ngay khi giáo viên nghỉ việc (REQ-001 ca biên).
- **Quyết định**: Phiên phía máy chủ với cookie HttpOnly + SameSite=Lax; mật khẩu băm argon2id (fallback bcrypt cost ≥ 12); khóa tạm 15 phút sau 5 lần sai trong 15 phút.
- **Hệ quả**: Thu hồi phiên tức thì; cần kho phiên chia sẻ nếu chạy nhiều tiến trình.
- **Đã loại**: JWT không trạng thái (khó thu hồi); OAuth bên thứ ba (OOS-5).
- **Liên quan**: REQ-001, NFR-002.

## ADR-003 — Kiến trúc đơn khối (monolith) trên cơ sở dữ liệu quan hệ managed
- **Trạng thái**: accepted (cập nhật số liệu tải theo OQ-01)
- **Bối cảnh**: Tải cao điểm **60 giáo viên điểm danh đồng thời khung 17h30–18h00**, 1.200 học viên, ~1.000 tài khoản phụ huynh. Đội nhỏ, ngân sách vận hành hạn chế.
- **Quyết định**: Một ứng dụng web đơn khối, một cơ sở dữ liệu quan hệ managed có sao lưu tự động và point-in-time recovery. Nhà cung cấp cụ thể hoãn tới DEF-01, **ràng buộc bởi ADR-006 (vùng Việt Nam)**.
- **Hệ quả**: Đáp ứng NFR-003/004/005 với chi phí thấp. Nếu tải tăng 10 lần thì tách dịch vụ đọc trước, không tách microservice sớm.
- **Đã loại**: microservices; tự vận hành cơ sở dữ liệu (không đảm bảo RPO/RTO).
- **Liên quan**: NFR-003, NFR-004, NFR-005, NFR-009, RISK-4.

## ADR-004 — Kiểm quyền tại tầng dữ liệu, không chỉ ở tầng giao diện
- **Trạng thái**: accepted
- **Bối cảnh**: IDOR là mối đe dọa nghiêm trọng nhất (phụ huynh/giáo viên xem dữ liệu học viên khác hoặc cơ sở khác).
- **Quyết định**: Mọi truy vấn trả dữ liệu cá nhân đi qua một lớp truy vấn bắt buộc nhận ngữ cảnh chủ thể (vai + `branch_id` được phép + tập id quan hệ) và tự áp điều kiện lọc. Cấm truy vấn thô theo id không có ngữ cảnh. Test uỷ quyền tự động chạy trong CI cho mọi endpoint trả PII (NFR-001), phủ cả trục cơ sở.
- **Hệ quả**: Chi phí thiết kế cao hơn; đổi lại không lọt IDOR do quên kiểm ở một endpoint lẻ. Endpoint mới thiếu test uỷ quyền → CI chặn merge.
- **Đã loại**: kiểm quyền ở tầng controller.
- **Liên quan**: REQ-005, REQ-006, REQ-009, NFR-001, RISK-3, T-02.

## ADR-005 — Tài liệu lưu ở bucket riêng tư, phát qua URL ký hạn ≤ 15 phút
- **Trạng thái**: accepted
- **Bối cảnh**: Bucket công khai hoặc đường dẫn đoán được sẽ bị người ngoài lớp tải.
- **Quyết định**: Bucket riêng tư tuyệt đối; client không nói chuyện trực tiếp với storage. Mọi lượt tải qua endpoint kiểm quyền rồi cấp URL ký hiệu lực ≤ 15 phút. Tên đối tượng ngẫu nhiên. Bucket đặt tại vùng Việt Nam (ADR-006).
- **Hệ quả**: Không dùng được CDN cache công khai; chấp nhận. Cấu hình public bucket là lỗi chặn phát hành.
- **Đã loại**: bucket công khai + tên tệp khó đoán.
- **Liên quan**: REQ-007, RISK-5, ASM-03.

## ADR-006 — Dữ liệu cư trú tại Việt Nam, tuân thủ Nghị định 13/2023, DPIA bắt buộc
- **Trạng thái**: accepted (2026-09-04) — trả lời OQ-05
- **Bối cảnh**: Chủ thể dữ liệu là học viên (phần lớn là trẻ em) và phụ huynh tại Việt Nam. Chủ sở hữu yêu cầu không chuyển dữ liệu xuyên biên giới.
- **Quyết định**:
  1. Toàn bộ dữ liệu cá nhân **lưu trữ và xử lý trong lãnh thổ Việt Nam**; cấm chuyển ra nước ngoài, kể cả log và bản sao lưu.
  2. Mọi dịch vụ bên thứ ba chạm PII (gửi SMS/thông báo, giám sát, phân tích) phải có hạ tầng tại VN hoặc bị loại; dịch vụ ngoài VN chỉ được nhận dữ liệu đã ẩn danh.
  3. Khung tuân thủ là **Nghị định 13/2023/NĐ-CP**; GDPR không áp dụng.
  4. Cơ sở pháp lý: hợp đồng dịch vụ giáo dục + **đồng ý của cha mẹ** cho dữ liệu trẻ em; lưu bản ghi đồng ý có phiên bản (REQ-010).
  5. Vòng đời dữ liệu: trực tuyến 2 năm → lưu trữ lạnh; **xóa theo yêu cầu trong ≤ 30 ngày** (REQ-011, NFR-007).
  6. **DPIA bắt buộc**, hoàn thành trước Gate 3, chủ: security-engineer.
- **Hệ quả**: Thu hẹp lựa chọn nhà cung cấp ở DEF-01; cần cơ chế lưu trữ lạnh và quy trình xóa có biên bản (DEF-02). Log giám sát phải cắt PII trước khi rời hệ thống.
- **Đã loại**: hạ tầng đa vùng toàn cầu; dùng dịch vụ phân tích nước ngoài trên dữ liệu thô.
- **Liên quan**: NFR-006, NFR-007, REQ-010, REQ-011, REQ-012, RISK-8, RISK-9.

---

## Quyết định còn hoãn

| id | Nội dung | Hạn quyết | Chủ |
|---|---|---|---|
| DEF-01 | Chọn nhà cung cấp hạ tầng có vùng tại Việt Nam đáp ứng NFR-005 | trước Gate 3 | architect |
| DEF-02 | Cơ chế lưu trữ lạnh và quy trình xóa/ẩn danh cho dữ liệu > 2 năm | trước Gate 3 | architect |
| DEF-03 | Chọn kênh thông báo (SMS/Zalo/email) đặt tại VN cho REQ-008 | trước Gate 3 | architect |
