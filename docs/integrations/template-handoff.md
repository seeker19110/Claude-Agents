# Cầu nối projects-template ↔ X-Agents

Opt-in, chạy từ checkout của hai repo. Không cần cài X-Agents vào template hoặc copy
framework lên hub. Công cụ không tự ghi file; redirection dưới đây do operator chọn.
Bản đối chiếu: ../reports/2026-09-26-bidirectional-delivery-handoff.md.

## Luồng chuẩn

1. Trong companies/software-company của X-Agents, xuất policy từ đúng consumer sẽ nhận:

```sh
uv run python -m company.template_handoff policy > /work/policy.json
```

2. Điền plan theo delivery_schema trong policy. Bắt buộc khai adoption, completion_level,
research_refs, no_change_rationale, alternatives_and_tradeoffs, spec approval claims,
acceptance_tests và gates. Brownfield cần baseline_ref. Không tự bịa approval_record.
Spec phải chọn State Approved for implementation trong bảng metadata, có Approver / date;
dòng hướng dẫn hay lựa chọn chưa chọn không phải trạng thái.

Ví dụ cấu trúc plan (dữ liệu MINH HỌA, không phải approval thật):

```json
{
  "adoption": "brownfield",
  "completion_level": "done",
  "baseline_ref": "baseline:REPLACE",
  "research_refs": ["research:REPLACE"],
  "no_change_rationale": "Describe the cost of doing nothing.",
  "alternatives_and_tradeoffs": "Record the reviewed alternatives.",
  "spec": {
    "artifact_ref": "docs/specs/feature.md",
    "approval_record": "REPLACE_WITH_REAL_RECORD",
    "approved_by": "REPLACE_WITH_REAL_PRINCIPAL",
    "approved_at": "2026-09-26T00:00:00Z"
  },
  "acceptance_tests": [{"acceptance_id": "AC-1", "test_ref": "tests/test_feature.py"}],
  "gates": [{"id": "unit", "phase": "done", "mechanism": "command", "applicable": true,
             "command": ["python", "-m", "unittest"]}]
}
```

3. Từ checkout projects-template, tạo bundle. Công cụ chỉ đóng gói; export thành công
KHÔNG chứng minh native schema, approval hay gate đã đạt.

```sh
python3 scripts/delivery-handoff.py --root /work/client --policy /work/policy.json --plan /work/plan.json > /work/handoff.json
```

4. Coordinator review và ghim SHA-256 của TOÀN BỘ bytes handoff.json qua kênh tin cậy
(kể cả newline cuối file). Không nhận hash chỉ do worker tự khai làm bằng chứng phê duyệt.
Sau đó, trong companies/software-company:

```sh
uv run python -m company.template_handoff prepare /work/handoff.json --sha256 COORDINATOR_PIN --evidence-root /work/client --acceptance-id AC-1 > /work/delivery.json
```

Lặp --acceptance-id cho MỌI AC trong profile do coordinator giữ, không lấy subset từ bundle.
Output là đối tượng delivery, KHÔNG phải toàn bộ ProjectProfile. Đưa vào profile mới qua
quy trình native hiện có, validate toàn bộ profile rồi dùng gate spec/ApprovalLookup và
pipeline receipt đã xác thực. Không thay profile của run đã đăng ký.

## Ranh giới và vận hành

Policy đổi → xuất lại, review lại, pin lại. Không tự cập nhật source revision hoặc migration.
Spec đổi → bundle cũ bị từ chối dù vẫn cùng tên file. Không chạy command chứa trong plan.
Root phải là snapshot ổn định; assessor native tiếp tục kiểm approval, spec và evidence.
Giới hạn mỗi tài liệu/spec 1 MiB, JSON depth 64; không key trùng hoặc số không hữu hạn.
Checksum không chứng minh ai duyệt. Prepare thành công không có nghĩa Ready/Done/Complete.
Exit 2 là input/IO bị từ chối; stdout không có contract thành công, stderr không echo input.
CLI mới này dùng trực tiếp từ checkout template; copy-framework không tự bật tích hợp.

## Sửa ở đâu, chạy lại gì

| Thay đổi | Nguồn sự thật | Kiểm tra |
| --- | --- | --- |
| Native schema, source pin và approval | company.delivery_contract; không fork | Native delivery/quality tests hiện có |
| Consumer policy/prepare/CLI | company.template_handoff | tests/test_template_handoff.py |
| Producer, safe path, plan/bundle | scripts/delivery-handoff.py trong template | tests/test_delivery_handoff_integrity.py |
| Metadata spec, CRLF | scripts/spec-compiler.py trong template | Cùng test integrity và engine tests hiện có |

Tắt đường tích hợp bằng ngừng gọi CLI; không cần đổi bus, journal hoặc run cũ.
