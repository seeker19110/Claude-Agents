# Topics

Mỗi file JSON Schema mô tả envelope + payload của một topic. Bus (`src/company/bus.py`)
validate trước khi ghi. Owner ghi của `shared-context` theo namespace (nguồn sự thật:
`NAMESPACE_OWNERS` trong `src/company/events.py`; test `test_registry` kiểm tra khớp
với front matter agent):

| namespace | owner | nội dung |
|---|---|---|
| prd | product (pha `spec`) | PRD đã duyệt |
| glossary, design | product (pha `research`) | thuật ngữ nghiệp vụ; user flow, wireframe, design tokens (ADR-0006) |
| architecture | product (pha `plan`) | C4, ADR |
| api-contract | product (pha `plan`) khởi tạo, builder cập nhật | OpenAPI v1 rồi các version sau |
| schema | builder (stack `database`) | schema OLTP, migration |
| threat-model | security | DFD, STRIDE, rủi ro chấp nhận |
| infra | builder (stack `platform`) | IaC module, môi trường, SLO |
| analytics | builder (stack `data`) | data contract, định nghĩa metric |
| docs | ops (pha `docs`) | tài liệu người dùng, runbook |
| knowledge | supervisor | bài học, estimate vs actual |
| contract | ops (pha `account`) | SOW, tiêu chí nghiệm thu, kịch bản UAT |

Owner là **agent**, không phải pha: `NAMESPACE_OWNERS` chỉ biết `product`/`builder`/`ops`; cột trên ghi thêm pha
để nói lượt nào thường ghi, không phải một ràng buộc code.

`shared-context` phân vùng theo dự án (ADR-0012): payload có `project_id`, key event là `<project_id>/<namespace>`.
Ngoại lệ là `knowledge` — phạm vi toàn công ty, `project_id=null`, key trần.

## Quy ước khác trong payload
- `tasks.risk_tags`: có bất kỳ tag nào (auth, payment, pii, crypto, upload, admin, external-api)
  → `delivery.py` chờ thêm `review-results` source=security trước khi tạo release candidate.
- `tasks.estimate_tokens` bắt buộc trước dispatch; `budget_tokens ≥ estimate_tokens × 1.5`.
- `review-results.source` ∈ reviewer | qa | security (NHÃN góc nhìn chấm, không phải id agent: `reviewer` và `qa` đều do agent `qa` chạy — `roles.SOURCE`). `ticket_id` = release_id khi là QA hồi quy trên staging.
- `tasks.depends_on` + `tasks.priority` (1 cao nhất): `delivery.py` giữ ticket ở `waiting` đến khi phụ thuộc approved.
- `incidents.root_cause_class` ∈ requirement | design | code | ops | external quyết định incident quay về đâu.
- `change-requests` chỉ thành ticket khi `decision=accepted`; `acceptance-results.signed_by` là người của khách.
