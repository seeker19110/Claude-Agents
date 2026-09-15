---
description: Sổ nợ kỹ thuật — thu mọi marker `no-ky-thuat:` thành một bảng, gắn cờ marker không có điều kiện quay lại
---

Thu hoạch **nợ kỹ thuật cố ý** đang nằm rải trong repo thành một bảng đọc được.

Marker là một dòng, khuôn định nghĩa ở `AGENTS.md` mục "Nợ kỹ thuật cố ý":

```
# no-ky-thuat: <trần đã biết>, <điều kiện quay lại>
```

## Làm gì

1. Thu marker (bỏ thư mục sinh ra và cây của phiên khác):

   ```bash
   grep -rnE '(#|//) ?no-ky-thuat:' . \
     --exclude-dir=.venv --exclude-dir=.git --exclude-dir=node_modules \
     --exclude-dir=__pycache__ --exclude-dir=.claude/worktrees
   ```

   Đọc **từng dòng** kết quả, đừng đếm bằng `wc -l`: nội dung marker là tiếng Việt có dấu và có dấu phẩy, đếm
   bằng shell trên Git Bash sai (`TRAPS.md` §3).

2. Với mỗi marker, tách phần sau `no-ky-thuat:` ở **dấu phẩy đầu tiên**: trước phẩy là **trần đã biết**, sau
   phẩy là **điều kiện quay lại**. Không có dấu phẩy ⇒ marker thiếu điều kiện quay lại → gắn cờ `no-trigger`.

3. In bảng, nhóm theo file, đường dẫn kèm số dòng để bấm được:

   | File:dòng | Trần đã biết | Điều kiện quay lại |
   |---|---|---|

   Marker `no-trigger` để ô cuối là **`no-trigger` — không nêu điều kiện quay lại**, và liệt kê lại chúng
   thành một khối riêng ở dưới: đây chính là những marker sẽ mục, vì không ai biết khi nào phải quay lại.

4. Kết đúng một dòng:

   ```
   <N> marker, <M> không có điều kiện quay lại
   ```

   Không tìm thấy marker nào thì nói thẳng **"sổ nợ sạch: 0 marker"** — đừng im lặng, im lặng đọc như lệnh hỏng.

## Không làm gì

- **Không sửa gì.** Lệnh này chỉ đọc. Muốn trả một món nợ thì đó là việc riêng, có test riêng, có PR riêng.
- **Không tự thêm marker** cho TODO bắt gặp dọc đường. Marker chỉ dành cho đơn giản hoá cắt góc **có trần đã
  biết** — `AGENTS.md` nói rõ ranh giới với `TRAPS.md` (bẫy đã mắc) và với TODO thường.
- **Không kết luận "repo sạch nợ"** từ sổ rỗng: sổ rỗng cũng có thể là chưa ai đặt marker (`TRAPS.md` §2, bẫy
  "tin dashboard xanh"). Nói đúng cái đo được: *0 marker*, không phải *0 nợ*.
