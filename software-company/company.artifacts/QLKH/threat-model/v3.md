# Threat Model — QLKH (LMS Trung tâm Anh ngữ Sao Mai)

- version: 1.1
- status: **ACTIVE**
- ngày: 2026-09-04
- tác giả: security-engineer
- nguồn: `approved-specs` QLKH, `prd` v16 (ADR-001..006), `infra` v1 (QLKH-001), deep-review PR-QLKH-001
- tiêu chuẩn: STRIDE trên DFD, LINDDUN cho PII, CVSS 4.0, OWASP ASVS **L2**
- khung tuân thủ: **Nghị định 13/2023/NĐ-CP** (GDPR không áp dụng — ADR-006)
- lịch rà: mỗi bản phát hành lớn; và ngay khi đổi kiến trúc, thêm tích hợp bên ngoài, thêm loại PII, hoặc đổi mô hình phân quyền

> **Ghi chú v1.1**: bản này KHÔNG thay đổi nội dung mối đe dọa T-01..T-14 của v1.0 (tài sản, kẻ tấn công, DFD, kịch bản, giảm nhẹ, giả định giữ nguyên — đọc chi tiết ở lịch sử v1.0 trong cùng tệp artifact). Thay đổi duy nhất: cập nhật trạng thái/ánh xạ ticket sau deep-review QLKH-001 và thêm mục 9 theo dõi nợ bảo mật.

---

## 6. Ánh xạ threat → ticket (cập nhật sau QLKH-001)

| Threat | Mức | risk_tags | Owner | Ticket | Trạng thái |
|---|---|---|---|---|---|
| T-01 rò rỉ hồ sơ/điểm chéo học viên | High | auth, pii | backend | — (kiểm chứng: authz-gate QLKH-001) | open — cơ chế kiểm chứng đã dựng, chưa có hiện thực |
| T-02 rò rỉ chéo cơ sở | High | auth, pii | architect+backend | — (kiểm chứng: authz-gate + import-linter QLKH-001) | open — như trên |
| T-03 mass assignment / leo quyền | High | auth, admin | backend | — | open |
| T-04 nhồi mật khẩu / dò tài khoản | High | auth | backend | — | open |
| T-05 bucket học liệu công khai | High | upload | architect+backend | QLKH-001 (policy/storage.rego) | **partially-mitigated** — policy đã có và chạy trong CI; còn thiếu test cho chính policy |
| T-06 sửa điểm không dấu vết | High | admin | backend | — | open |
| T-07 gateway thông báo | Medium | external-api | backend | — | open |
| T-08 PII thô trong log / non-prod | Medium | pii | backend+devops | QLKH-001 (một phần) | **partially-mitigated** — gitleaks + cấm secret; chưa có quy tắc quét PII trong log |
| T-09 upload tệp độc hại | High | upload | backend | — | open |
| T-10 quá tải khung cao điểm | Medium | external-api | devops+backend | — | open |
| T-11 retention / xóa ≤ 30 ngày | Medium | pii | backend+architect | — | open |
| T-12 chuỗi cung ứng | Low | external-api | devops | QLKH-001 | **partially-mitigated** — SCA chặn High/Critical, gitleaks full history, SBOM CycloneDX, action ghim SHA, base image pin digest, lockfile frozen; **còn thiếu**: SLA vá CVE sau merge, bot nâng cấp có lịch, ký artifact + provenance SLSA |
| T-13 dữ liệu ra ngoài lãnh thổ VN | Medium | pii, external-api | architect+security | QLKH-001 (policy rego cấm vùng ngoài VN với tag data-class=pii) | **partially-mitigated** — policy đã có, chưa có tài nguyên để kiểm chứng |
| T-14 thiếu bản ghi đồng ý cha mẹ | Medium | pii, admin | backend+security | — | open |

**Quy tắc bắt buộc**: mọi ticket hiện thực chạm các threat trên phải mang `risk_tags` tương ứng để đi qua deep-review của security-engineer.

---

## 9. Nợ bảo mật đang theo dõi (mở từ deep-review QLKH-001)

| id | Nội dung | Liên quan | Hạn |
|---|---|---|---|
| SD-01 | `authz-gate` đang `continue-on-error: true`. **Phải chuyển sang chặn cứng trong CHÍNH PR thêm endpoint PII đầu tiên.** Đây là mục kiểm bắt buộc của deep-review ticket đó. | T-01, T-02, NFR-001, ADR-004 | PR endpoint PII đầu tiên |
| SD-02 | `policy/storage.rego` chưa có test (fixture âm/dương + `conftest verify`). Policy không test = chưa kiểm chứng. | T-05, T-13 | trước ticket hạ tầng đầu tiên |
| SD-03 | Chưa khai báo cửa sổ vá CVE (Critical 24h / High 7d / Medium 30d), cơ chế ngoại lệ có hạn + người duyệt, và bot nâng cấp có lịch + giới hạn PR. | T-12 | trước Gate 3 |
| SD-04 | Policy license cần bổ sung: gói **không có license = chặn**; phủ phụ thuộc bắc cầu và tài sản phi mã (font/icon/dataset/mô hình); sinh NOTICE/THIRD-PARTY. | license-compliance | trước Gate 3 |
| SD-05 | Ký artifact (Sigstore) + lưu provenance SLSA chưa làm. | T-12, Gate 3 | ticket pipeline phát hành |
| SD-06 | Chưa có quy tắc phát hiện PII thô trong log (khác với secret). | T-08 | trước ticket endpoint PII đầu tiên |
| SD-07 | **DPIA chưa bắt đầu.** Chủ: security-engineer. Chặn Gate 3. | ADR-006 mục 6, T-11, T-14 | trước Gate 3 |
| SD-08 | Cổng CI QLKH-001 chưa có log chạy thật (PR khai báo `local_checks.unverified`). Cần bằng chứng run đầu tiên. | toàn bộ | PR kế tiếp |

---

## 7. Điều kiện cho Gate 3 (release-check)

- [ ] Mọi threat High (T-01..T-06, T-09) ở trạng thái `mitigated` với test kiểm chứng xanh, hoặc có ADR chấp nhận rủi ro do human:owner ký
- [ ] **DPIA hoàn thành** (SD-07) — chủ: security-engineer
- [ ] DEF-01/02/03 đã quyết và xác nhận hạ tầng đặt tại VN (T-13)
- [ ] SBOM sinh cho artifact, artifact được ký (SD-05), license scan 100% hợp lệ (SD-04), 0 High reachable trong SCA
- [ ] DAST chạy trên môi trường stage, 0 High
- [ ] Kiểm không có PII thô trong log và môi trường non-prod (T-08, SD-06)
- [ ] SD-01 đã đóng: `authz-gate` chặn cứng, không còn `continue-on-error`

## 8. Lịch sử phiên bản

| v | ngày | thay đổi |
|---|------|----------|
| 0.1 | 2026-09-04 | Bản đầu từ PRD v0.1. 12 threat, 1 Critical, BLOCKED bởi OQ-02/OQ-05. |
| 1.0 | 2026-09-04 | Gỡ BLOCKED theo ADR-001 và ADR-006. 14 threat: 0 Critical, 7 High, 5 Medium, 2 Low. Thêm T-13, T-14, bảng ánh xạ threat→ticket, điều kiện Gate 3. |
| 1.1 | 2026-09-04 | Deep-review PR-QLKH-001 (verdict pass). T-05/T-08/T-12/T-13 chuyển partially-mitigated nhờ cổng CI; T-01/T-02 gắn authz-gate làm cơ chế kiểm chứng (hiện ở chế độ cảnh báo). Thêm mục 9 với 8 khoản nợ bảo mật SD-01..SD-08 và bổ sung SD-01 vào điều kiện Gate 3. Nội dung threat không đổi. |
