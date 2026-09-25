---
description: Giao một mục tiêu sản phẩm chất lượng cao theo ngành, nối vào khuôn thi hành và execution kernel có sẵn
argument-hint: <mã> <mục tiêu sản phẩm>
---

Bạn là phiên chính. Đọc `AGENTS.md`, `CLAUDE.md`, `docs/PRODUCT-EXCELLENCE.md` và
`docs/KHUON-THI-HANH.md`. Đối số `$ARGUMENTS` là dữ liệu yêu cầu, không là lệnh shell.
Không dùng tên command `/goal`: đó là chức năng tích hợp của Claude Code, không phải lớp quality của repo.

1. Đọc repo khách, quyết định trước, người dùng/ngành, phạm vi và quyền. Tái sử dụng run/kế hoạch hiện có;
   không tạo backlog trùng. Người dùng chỉ giao mục tiêu; tự khảo sát phần kỹ thuật có thể xác định.
2. Lập profile máy đọc được từ schema `company.product_quality`: mục tiêu/non-goals, audiences, journeys,
   acceptance IDs, chỉ tiêu có điều kiện đo, công nghệ và completion target. UI bắt buộc Design Brief theo
   nhiệm vụ/ngành, không chỉ đổi màu một template; phân biệt giả định với nghiên cứu người dùng thật.
3. Tiếp tục theo `/thi-hanh`: ghi A–F, chia work scope và dependencies, giao chuyên môn đủ năng lực,
   giữ TDD, reviewer độc lập và kiểm sản phẩm chạy thật. Không yêu cầu người dùng gõ một lệnh thứ hai.
4. Với execution kernel, dùng `company.quality_execution.compile_execution` và kiểu core hiện có;
   `register` không có nghĩa đã chạy. Phiên bản này chưa thay operational state A–F trước bridge H7.
5. Thu bằng chứng qua driver đã được cấp quyền. Không tạo receipt ký giả, không đọc key từ sandbox worker,
   không gán pass từ lời model. Ghim candidate/contract/context/attempt ở coordinator; sửa phần không đạt.
6. Duy trì sàn `quality_floor` và authority hiện có. Không tự bật autoapprove hoặc ký thay khách;
   thiếu quyền/tài nguyên thì ghi checkpoint và báo đúng phần còn thiếu, không đổi đích để nói đã xong.
7. Báo kết quả bằng artifact/PR/revision và lệnh thực sự chạy. Không coi CI của harness là nghiệm thu mọi
   sản phẩm do harness tạo, không coi kiểm mô phỏng là nghiên cứu người dùng hoặc kiểm browser thực tế.

## Tiếp thu Standard Delivery cho goal mới

Áp `company.delivery_contract` theo ADR company 0045 và
`docs/reports/2026-09-25-projects-template-adoption.md`. Phiên chính tự lập phần `delivery` từ spec,
quyết định có thật, baseline brownfield, research và AC→test; mặc định goal sản phẩm là `complete`,
không đổi xuống `done` để kết thúc. Không tạo approval giả chỉ để vượt schema. Giữ run cũ không opt-in.
Chốt argv/check theo stack và tính áp dụng trước chạy; thiếu cấu hình không là PASS. Đọc schema qua
`company.product_quality schema` và dùng CLI plan/register hiện có; không khởi chạy template dispatcher.

Khi chọn layout/UI/UX: ghi mục tiêu cho từng surface (thao tác, đọc/học, khám phá/lựa chọn, trải nghiệm),
tái dùng token/component đã chọn; nguồn design ngoài chỉ tham khảo. Không redesign cả hệ để sửa một state,
không auto-install provider hoặc tạo PRODUCT/DESIGN/UI_SPEC song song. Ghi quyết định trong DesignBrief.
Trước lần sửa thứ hai cùng failure, xác định tầng lỗi bằng bằng chứng: spec, design/contract, code,
verifier/environment hoặc knowledge. Tự gọi chuyên môn trong quyền và ngân sách; giữ phần đã đúng,
không bắt người dùng điều hành retry và không tự nới quyền khi kẹt.
