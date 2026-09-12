# ADR-0012: PR theo hạng mục lớn — một nhánh nhiều task, không một-PR-một-task

Trạng thái: Chấp nhận · Ngày: 2026-09-12 · Liên quan `docs/QUY-TRINH-GIT.md` §2d, `docs/KHUON-THI-HANH.md`,
`docs/TASK-PACK.md`

## Bối cảnh

Luật cũ (`docs/KHUON-THI-HANH.md` §3.6 trước ADR này: "Mỗi PR một gói") quy định mỗi task nhỏ (một mã trong
bảng B) là một PR riêng, mở tuần tự. Đo trên các bản thi hành thật đã chạy (`docs/thi-hanh/*.md`) và 60 PR gần
nhất trước ADR này: luật đó **bị vi phạm ở mọi bản thi hành có từ 2 mã trở lên** — 6 mã gộp vào một PR (#198),
3 mã gộp vào một PR (#266) — không phải ngoại lệ hiếm mà là cách mọi phiên thực tế đã làm. Cùng lúc, luật
`docs/TASK-PACK.md` "điền đủ 7 mục" cũng bị bỏ ba mục (mục tiêu, kết quả mong đợi, bối cảnh) ở 3/4 bản thi hành
thật, với lý do "suy ra trực tiếp" không được luật cho phép nói ra.

Cả hai cho thấy cùng một sự thật: khi một việc chia thành nhiều task liên quan chặt (cùng mục tiêu, cùng bối
cảnh), việc mở PR/điền lại các mục dùng chung cho từng task là chi phí không ai muốn trả, và luật bị vi phạm
đều đặn thay vì được tuân theo. Chủ dự án yêu cầu chính thức hoá luồng đã quan sát được: chốt yêu cầu → đặc tả
kế hoạch + triển khai chi tiết → chia hạng mục lớn → chia task nhỏ → một nhánh mỗi hạng mục, chạy hết task nhỏ
(mỗi task một commit) rồi mới mở PR.

Ràng buộc phải giữ khi thiết kế lại: mỗi task vẫn cần CI thật trước khi commit tiếp (không đợi tới cuối hạng
mục mới biết task nào sai — quyết định rõ khi chốt: đây là đánh đổi KHÔNG chấp nhận được), và luật 2c ("chỉ một
PR mở tại một thời điểm") không được vô hiệu.

## Quyết định

1. **Đơn vị PR là hạng mục lớn** (2–8 task, một mảng), không phải task nhỏ. `docs/KHUON-THI-HANH.md` §3.6 đổi
   từ "mỗi PR một gói" thành "mỗi PR một hạng mục"; bảng B thêm cột "hạng mục" thay cột "loại PR" cũ.
2. **PR mở NHÁP ngay sau task đầu tiên của hạng mục**, không chờ xong cả hạng mục. Cơ chế cho phép: CI
   (`pull_request.synchronize`, `.github/workflows/ci.yml`) không lọc theo `draft` — mỗi task push vào nhánh
   vẫn kích CI thật. `gh pr ready` + bật auto-merge chỉ khi mọi task của hạng mục `xong`.
3. **Luật 2c áp nguyên vẹn cho cả PR nháp** — nháp vẫn tính là một PR đang mở, nhánh/hạng mục khác vẫn phải chờ
   nó merge rồi mới `gh pr create`. Không có ngoại lệ "nháp không tính": lý do 2c tồn tại (không hai nhánh cùng
   lệch nền một lúc khi merge) áp y hệt cho nháp.
4. **Mỗi task vẫn chạy đúng lệnh CI cục bộ trước khi commit** — không đợi PR báo. Test đỏ→xanh, `ruff`/`mypy`,
   coverage của package chạm tới, đo hai chiều khi sửa hành vi — y hệt yêu cầu cũ cho một-PR-một-task, chỉ khác
   ở chỗ kết quả gộp vào một PR thay vì mở riêng.
5. **Task hỏng giữa chừng** (luật bắt buộc 6: vá 3 lần lòi vấn đề mới ⇒ dừng hỏi người): các task đã `xong`
   trước đó trong hạng mục vẫn `ready` + merge được nếu tự đứng, không phụ thuộc task hỏng. Task hỏng tách sang
   một hạng mục mới trong bảng B — không giam cả hạng mục chờ một task không giải quyết được.
6. **`docs/TASK-PACK.md` mục 1/2/4 được viết một dòng "suy ra từ hạng mục lớn: ..."** khi ba mục đó đã trả lời
   chung ở tầm hạng mục, thay vì bắt buộc điền đầy đủ cho từng task. Điều kiện: câu "suy ra" phải **tường minh**
   (khác hẳn để trắng — người đọc sau biết đây là quyết định có chủ ý). Mã không thuộc hạng mục lớn nào (PR nhỏ
   độc lập) vẫn điền đủ 7 mục như cũ.

## Hệ quả

- Số PR mở/merge giảm hẳn cho việc lớn nhiều task (đo được ở chính đợt rà soát sinh ra ADR này: 5 hạng mục thay
  vì có thể tới vài chục PR một-task).
- CHANGELOG/session log gọn hơn: một mục cho cả hạng mục thay vì rải theo từng task.
- **Nhược điểm đã biết, không có cách vòng**: squash merge gộp mọi task của một hạng mục thành **một** commit
  trên `main`. Task giữa gây lỗi thì `git revert` cuốn theo mọi task khác trong cùng hạng mục — mất độ mịn revert
  so với một-PR-một-task cũ. Không dùng merge-commit thay squash để giữ độ mịn vì `.github/rulesets/main.json`
  chỉ cho squash. Chấp nhận đánh đổi này; không giả vờ nó không tồn tại.
- Trần "≤ 8 task, ≤ 2 package" cho một hạng mục cần theo dõi qua các đợt sau: hạng mục nào chạm trần liên tục
  là dấu hiệu chia hạng mục sai kích thước, cần vá quy tắc chia (không vá bằng cách nới trần).

## Liên quan

`docs/QUY-TRINH-GIT.md` §2d (luồng chi tiết + lệnh), `docs/KHUON-THI-HANH.md` (khuôn thi hành áp dụng quyết định
này), `docs/TASK-PACK.md` (mục 6). Không thay `docs/adr/README.md` (ADR này chạm quy trình toàn repo, đúng phạm
vi "ADR cấp repo").
