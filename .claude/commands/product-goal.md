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
