# Trực ban và dừng khẩn

> Người trực mở **đúng file này** khi có chuyện. Mọi lệnh dưới đây **đã được chạy thật** ngày 2026-09-05,
> không phải suy đoán từ đọc code; chỗ nào chưa kiểm được thì ghi rõ là chưa.
> Bối cảnh vận hành ba người: `docs/QUY-TRINH-GIT.md` §8 (bảo vệ nhánh), `docs/HUONG-DAN-VAN-HANH.md` (cài đặt).

## 1. Dừng khẩn — làm gì trong 60 giây đầu

**Không có nút "kill switch" một phát.** Có ba mức, mức càng thấp càng ít thiệt hại:

| Mức | Khi nào | Lệnh | Đã đo |
|---|---|---|---|
| **1. Một ticket** | Một ticket chạy sai: sửa nhầm file, vòng lặp, tốn token bất thường | `publish` một `supervisor-actions` `pause` với `--key <ticket_id>` | **0,27 s** để phát lệnh |
| **2. Cả dự án** | Nhiều ticket cùng hỏng, hoặc chưa biết ticket nào | Như trên nhưng `--key <project_id>` và `project_id` trong payload | cùng cơ chế |
| **3. Toàn hệ thống** | Nghi ngờ nghiêm trọng (rò rỉ, agent chạm thứ không được phép) | **Dừng tiến trình `orchestrator run`** (Ctrl-C hoặc kill PID) | tức thì |

### Mức 1 — dừng một ticket

```bash
cd software-company
cat > /tmp/pause.json <<'JSON'
{"target": "TCK-1", "action": "pause", "reason": "ngắn gọn: vì sao dừng", "project_id": null}
JSON
uv run python -m company.orchestrator --db company.sqlite \
  publish supervisor-actions /tmp/pause.json --actor human:<tên bạn> --key TCK-1
# → published supervisor-actions key=TCK-1 event=9e0d1dc8...
```

**Hai chỗ dễ gõ sai lúc vội** (cả hai đều đã vấp khi diễn tập):

- **`--db` phải đứng TRƯỚC `publish`.** Đặt sau sẽ ra `error: unrecognized arguments: --db`.
- **`--key` là bắt buộc** với topic này. CLI tự suy key từ `ticket_id`/`release_id`/`project_id`/`change_id`
  trong payload, mà payload `supervisor-actions` chỉ có `target` — thiếu `--key` sẽ ra `cần --key`.

Sau khi publish: orchestrator đang chạy sẽ **hoãn** (`deferred`) mọi event của target đó
(`paused:<target>` trong `status`). Việc đang gọi model dở thì **chạy nốt lượt hiện tại** rồi mới dừng —
pause chặn *event tiếp theo*, không cắt ngang lời gọi đang bay.

### Mức 2 — dừng cả dự án

Cùng lệnh, đổi `--key` thành `project_id` và điền `"project_id": "<id>"` trong payload. Orchestrator kiểm
cả hai: target trùng ticket **hoặc** trùng dự án đều bị hoãn.

### Mức 3 — dừng tất cả

Không có lệnh CLI. Dừng tiến trình `orchestrator run`. An toàn vì mọi trạng thái nằm trong bus SQLite:
mở lại là replay dựng lại đúng chỗ, event chưa xử lý (`deferred`) được nhận lại.

### Chạy tiếp sau khi đã xử lý

```bash
cat > /tmp/resume.json <<'JSON'
{"target": "TCK-1", "action": "resume", "reason": "đã xử lý: <việc đã làm>"}
JSON
uv run python -m company.orchestrator --db company.sqlite \
  publish supervisor-actions /tmp/resume.json --actor human:<tên bạn> --key TCK-1
```

`resume` gỡ pause **và** gọi lại hàng đợi bị hoãn — không cần khởi động lại tiến trình.

### Giới hạn đã biết (đừng trông chờ những thứ này)

- **Không thu hồi thông tin xác thực.** Gói đăng ký / khoá API vẫn dùng được sau khi pause. Nghi rò rỉ
  thì phải thu hồi ở phía nhà cung cấp — pause không thay được việc đó.
- **Không cắt lời gọi model đang chạy.** Lượt hiện tại chạy hết; trần thật là `budget_tokens` của ticket.
- **Không có mức "một phiên bản agent".** Muốn chặn riêng một agent hỏng: pause từng ticket của nó, hoặc dừng cả tiến trình.
- **Không có lệnh tắt.** `orchestrator` không có subcommand `stop`/`pause`; đường duy nhất là `publish`.

> Đã diễn tập ngày 2026-09-05: publish pause thành công trong 0,27 s; thử giả danh (`--actor supervisor`)
> **bị chặn** đúng như thiết kế (`--actor phải là người (human:<tên>)`). Bảy test `pause`/`resume` xanh.

---

## 2. Lịch trực luân phiên (ba người)

Một người trực **một tuần**, đổi ca sáng thứ Hai. Người trực là **địa chỉ duy nhất** cho mọi việc bất thường
trong tuần đó — không phải người duy nhất làm, mà là người **không được bỏ qua**.

| Việc | Người trực | Nhịp |
|---|---|---|
| Hàng đợi cổng người (`gate_cli list`) | Xử lý hoặc chuyển đúng người | ≥ 2 lần/ngày làm việc |
| `orchestrator status` — việc hoãn, kẹt, gate quá hạn | Đọc, gỡ hoặc leo thang | đầu và cuối ngày |
| `orchestrator diagnose` — khuôn lỗi lặp, ticket quay vòng | Đọc | 1 lần/ngày |
| Chi phí (`orchestrator metrics`) | So với hôm trước; tăng > 50% thì dừng và tìm hiểu | 1 lần/ngày |
| Sự cố / dừng khẩn | **Là người bấm**, theo §1 | khi có |

**Bàn giao cuối ca (viết ra, không nói miệng):** việc đang dở · ticket đang pause và vì sao ·
gate đang chờ ai · bất thường chi phí · thứ người sau **không được quên**.

**Người trực KHÔNG tự duyệt việc của chính mình.** Cổng nào có `four-eyes` thì vẫn cần người thứ hai —
đang trực không phải lý do miễn trừ. Nếu chỉ còn một người ở thời điểm đó: **để việc chờ**, đừng tự ký.

---

## 3. Cổng phát hành gộp lô (G6)

Duyệt phát hành **theo lô, không lẻ từng việc** — mỗi lần mở màn duyệt tốn phần lớn thời gian ở việc dựng lại
bối cảnh, nên gộp 3–5 việc thì rẻ hơn nhiều lần duyệt lẻ.

- **Nhịp:** 1 lô/ngày làm việc, giờ cố định (đề xuất cuối buổi sáng). Ba người thì mỗi ngày một người duyệt.
- **Không gộp** thứ chạm `auth`, `payment`, `crypto`, hoặc có migration dữ liệu: những thứ này duyệt **riêng**,
  đọc kỹ, vì gộp làm loãng chú ý đúng chỗ cần chú ý nhất.
- **Trần lô:** 5 việc. Đông hơn thì tách lô — một màn duyệt 12 việc là một màn duyệt không ai đọc hết.
- **Chờ quá 24 giờ thì không gộp nữa**: phát hành ngay lô đang có, đừng để việc chín rục chờ cho đủ lô.

Sau mỗi lô, ghi lại: số việc, ai duyệt, mất bao lâu. Nếu thời gian duyệt trung bình **dưới 90 giây/việc**,
đó là dấu hiệu duyệt cho có — xem lại trước khi nó thành thói quen.

---

## 4. Việc chưa làm được (ghi để không ai tưởng đã có)

| Thiếu | Hệ quả | Cách tạm |
|---|---|---|
| Kill switch một lệnh, ba mức | Lúc khẩn phải soạn JSON rồi publish | §1, và giữ sẵn hai file `pause.json` / `resume.json` trong máy |
| Thu hồi thông tin xác thực khi dừng | Pause không chặn được rò rỉ đang diễn ra | Thu hồi thủ công ở nhà cung cấp |
| Cảnh báo tự động (R8) | Người trực phải tự đọc `status` | Nhịp đọc ở §2 |
| Đo thời gian người duyệt cổng | Không biết cổng đã thành nghi thức chưa | Ghi tay sau mỗi lô (§3) |
