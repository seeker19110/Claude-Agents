---
description: Vòng chẩn đoán có kỷ luật cho bug khó/chập chờn — tra TRAPS.md, dựng phép thử đỏ-được trước, đo từng biến, sửa kèm test hai chiều
---

Chẩn đoán một bug **khó** (không tái hiện ngay, chập chờn, hồi quy hiệu năng) theo trình tự cố định.
Bug tái hiện ngay lập tức thì cứ sửa thẳng — không cần chạy hết sáu pha.

> Nền: `AGENTS.md` luật bắt buộc 6 (đo trước khi sửa) — **suy từ thông điệp lỗi đã sai 6/6 lần** trong lịch sử
> repo này. Và: vá 3 lần liên tiếp mà mỗi lần lòi vấn đề mới ở chỗ khác ⇒ **dừng**, đây là kiến trúc sai, mang
> giả thiết ra hỏi người, không vá lần 4 một mình.

## Pha 0 — Tra `TRAPS.md` trước khi ra giả thuyết

`TRAPS.md` ở gốc **và** `TRAPS.md` của package liên quan. Khớp một khuôn đã ghi → áp thẳng "cách rà" của mục
đó, tiết kiệm cả vòng Pha 1–4. `TRAPS.md` §6 còn liệt kê sẵn các câu tự biện hộ — đọc trước khi tự thuyết phục
mình là ngoại lệ. Không khớp → tiếp tục, và Pha 6 ghi mục mới.

Bốn khuôn lỗi lặp lại của hệ này (xem `TRAPS.md`): chế độ hỏng không tự khai báo · state chỉ sống trong RAM ·
khoá chống-trùng nuốt lần hai hợp lệ · event cũ trong hàng đợi phát lại như mới.

## Pha 1 — Dựng phép thử đỏ-được (dồn phần lớn công sức ở đây)

Có một lệnh **đỏ đúng trên bug này** thì phần sau chỉ là cơ học; không có thì càng đọc code càng vô ích.
Thử theo thứ tự: pytest ở đúng seam → chạy CLI thật (`uv run python -m company.orchestrator ...`) với bus
SQLite tạm → replay một event đã ghi → vòng lặp lặp 100 lần (bug chập chờn: mục tiêu là **tăng tỷ lệ tái
hiện**, không phải repro sạch tuyệt đối) → bisect qua commit đã biết tốt/xấu.

Hoàn thành pha này khi có **đúng một lệnh đã chạy thật** (dán lệnh + output), bắt đúng triệu chứng, ổn định,
chạy trong vài giây, không cần người canh. Không dựng được → nói rõ đã thử gì rồi hỏi người. **Không** nhảy
sang đoán nguyên nhân khi chưa có lệnh đỏ-được.

## Pha 2 — Tái hiện rồi thu nhỏ

Xác nhận đúng triệu chứng người mô tả (không phải lỗi khác na ná). Bớt từng phần input/cấu hình một, chạy lại
sau mỗi lần bớt. Xong khi bớt gì cũng làm nó xanh trở lại.

## Pha 3 — Giả thuyết (3–5 cái, xếp hạng, bác bỏ được)

Mỗi cái viết dạng "nếu X là nguyên nhân thì đổi Y sẽ hết, đổi Z sẽ nặng hơn". Không phát biểu được dạng này
thì đó là cảm tính. Cho người xem danh sách **trước khi** kiểm — họ thường loại trừ giúp được vài cái.

## Pha 4 — Đo

Mỗi phép đo nhắm đúng một giả thuyết, **đổi một biến một lần**, luôn có đối chứng. Log thêm phải gắn tiền tố
duy nhất (`[DEBUG-a4f2]`) để dọn sạch bằng một lệnh grep. Không "log tất cả rồi grep mò".

## Pha 5 — Sửa + test hai chiều

Viết test hồi quy **trước** khi sửa, ở seam thật (không phải seam nông cho xanh). Đỏ → sửa → xanh → **tắt bản
sửa, xác nhận đỏ trở lại** → bật lại. Ghi **cả hai chiều** vào commit message (luật bắt buộc 4).

## Pha 6 — Rà cả họ lỗi + ghi lại

Luật bắt buộc 5: viết câu hỏi kiểm tra rút từ lỗi vừa sửa, `grep` mọi chỗ dùng **cùng cơ chế**, ghi lại cả chỗ
an toàn và vì sao. Lịch sử repo: một lần rà như vậy biến 1 lỗi thành 5.

Rồi ghi `TRAPS.md` (khuôn mới, hoặc thêm "Tái phát &lt;ngày&gt;" vào mục cũ — không tạo mục trùng), gỡ sạch log
`[DEBUG-...]`, và ghi giả thuyết đúng vào commit/PR.

Bắt đầu: hỏi nhanh triệu chứng cụ thể + đã thử tái hiện chưa, rồi vào Pha 0.
