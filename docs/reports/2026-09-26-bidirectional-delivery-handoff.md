# Tích hợp hai chiều X-Agents và projects-template — 2026-09-26

## Quyết định

Giữ hai repo độc lập: template là phương pháp phát triển và nguồn spec; X-Agents là runtime,
validator và nơi thực thi quyền. Nối bằng dữ liệu có phiên bản, không copy cả framework.
Người dùng yêu cầu triển khai tích hợp hai repo trong phiên này; không suy ra quyền duyệt
spec ban đầu, phát hành, truy cập production hoặc sửa các PR khác từ yêu cầu đó.

Baseline đã đọc: X-Agents `b50a29d64bb248eba4dc797cb53879a1442b040f`;
projects-template `071faea09aeb2b529056399dc104c3a18bf6c7b1`.

## Đối chiếu ba cột

### Đã có và sâu hơn — giữ nguyên

| Cơ chế | Nơi giữ nguồn sự thật | Quyết định |
| --- | --- | --- |
| Bus/journal, DAG, retry/resume, CAS | X-Agents execution kernel | Không thêm scheduler vào template. |
| Xác minh approval, receipt có chữ ký, candidate và quyền gate | X-Agents delivery/quality pipeline | Không biến Markdown hoặc hash thành quyền. |
| Greenfield/brownfield, Research/Spec, Ready/Done/Complete, hồ sơ nhiều stack | Standard Delivery của template; X-Agents đã tiếp thu qua DeliveryContract | Không chép lại quy trình đã có. |
| Dispatcher, model routing, hooks, CI | Từng repo theo vai trò của nó | Không đè cấu hình và không kéo provider vào template. |

### Đã có nhưng nông hơn — lấy đúng phần còn thiếu

| Điểm cụ thể | Bằng chứng | Thay đổi |
| --- | --- | --- |
| Compiler template dùng câu Approved ở bất kỳ vị trí nào làm trạng thái | Test đỏ: chỉ dẫn trong Draft, lựa chọn chưa chọn, thân không metadata, State trùng | Chỉ đọc State đã chọn trong metadata; từ chối key metadata trùng. |
| Nhập delivery thủ công giữa hai repo | Native DeliveryContract đã ghim revision/schema, nhưng compiler chỉ xuất contract-test/JSON riêng | Export policy từ model thật; exporter nhận policy, plan và spec; consumer kiểm lại bằng native model. |

### Chưa có — không thêm chỉ vì repo kia có

| Ứng viên | Quyết định và điều kiện xem lại |
| --- | --- |
| Tự đồng bộ source/CI/hooks hai chiều | Chưa cần: dễ ghi đè chính sách. Xem lại khi có nhiều adoption cần nâng bản có owner và rollback. |
| Thêm orchestrator/daemon vào template | Không lấy: trái ranh giới repo drop-in; chỉ xem lại khi sản phẩm template đổi phạm vi. |
| Tự duyệt từ nội dung spec hoặc tự chạy command trong bundle | Không lấy: dữ liệu đầu vào không cấp quyền. |
| Tự thay toàn bộ source revision đã pin bằng main mới nhất | Không lấy: làm lệch contract/hash của run đang chạy. Revision đổi phải qua review riêng. |

Đính chính trong quá trình audit: ban đầu có thể tưởng X-Agents thiếu lớp delivery của template;
đọc delivery_contract, product_quality và quality_execution cho thấy lớp đó ĐÃ CÓ và sâu hơn
một bản checklist đơn giản. Vì vậy chỉ thêm cổng trao đổi dữ liệu, không dựng lại nghiệm thu.

## Hợp đồng mới

Protocol `xagents-template-handoff/1`. Consumer xuất native JSON Schema và adopted_source;
producer không vendor schema và không tự viết một JSON Schema validator thứ hai.
Bundle có đúng protocol, policy_sha256 và delivery. Consumer yêu cầu hash toàn bộ bytes
bundle được coordinator pin qua kênh tin cậy, danh sách AC đầy đủ và evidence root ổn định.
SHA-256 là kiểm toàn vẹn, KHÔNG phải xác thực người duyệt hay chữ ký.

Giới hạn mỗi input/spec: 1 MiB; JSON UTF-8, không key trùng, không NaN/Infinity/overflow,
độ sâu tối đa 64. Producer đọc spec một lần để parse và hash đúng cùng bytes; không âm thầm
thay pin cũ xung đột. AC phải map đầy đủ, duy nhất tới test. Đường dẫn không thoát project root.
Consumer dùng DeliveryContract và artifact_matches sẵn có, không nới native validator.
Không gọi shell/model/mạng, không ghi file, không chuyển journal, không tự chạy gate.

## Kiểm chứng và giới hạn

Đã chạy tại bản sao chọn lọc của source: 21 unittest của producer và 52 pytest của consumer.
Coverage riêng hai module mới đạt 100% dòng và nhánh; KHÔNG phải coverage toàn repo.
TDD trước sửa: 4 lỗi metadata; API/module mới chưa tồn tại. Thêm đối chứng lỗi JSON quá sâu,
overflow và pin sai kiểu; khôi phục bản sửa rồi chạy lại.
CLI thực: native policy → producer → native DeliveryContract; bytes xác định, hash spec đúng;
spec đổi và policy đổi đều bị từ chối; kết quả không tạo quyền duyệt/hoàn tất.

Môi trường này không clone/sync GitHub được; file nền dùng qua connector và đối chiếu Git blob SHA.
Chưa chạy full workspace gate, ruff/mypy/ShellCheck/radon hoặc production orchestration.
PR phải giữ nháp cho đến khi CI và review hoàn tất; không hạ ngưỡng để đổi trạng thái.

## Hoàn tác

Đây là đường opt-in: ngừng gọi exporter/prepare là quay về nhập native profile như cũ.
Không cần migration, không đổi run đã đăng ký, không đụng PR auto-compact 300k #352.
