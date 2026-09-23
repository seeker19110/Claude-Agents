# ADR-0044 — lint/test của repo khách chạy bằng môi trường của khách, không phải venv của công ty

- Trạng thái: chấp nhận
- Ngày: 2026-09-23
- Liên quan: ADR-0013 (nhận diện stack), ADR-0010 (ranh giới tin cậy: model chọn tên lệnh, code ghép argv),
  ADR-0035 (sandbox cho lệnh con)

## Bối cảnh — số đo, không phải suy đoán

Dự án CAMPUS-UNI-20260922, ticket TCK-001 (scaffold Django + waitress + `/healthz`). Builder chạy đủ **3 lượt**,
mỗi lượt viết 43 file, mỗi lượt `local_checks` trả `{"lint": false, "tests": false}` rồi `ticket.blocked`
(`retry: 3, max_retries: 3`) và mở gate `escalation`.

Tái hiện bằng chính hai lệnh mà `stacks.py` ghép, chạy trong worktree `ticket/TCK-001` của repo khách:

| Trình thông dịch | Kết quả đo |
|---|---|
| `sys.executable` (venv của **orchestrator**) — cách đang làm | `ModuleNotFoundError: No module named 'django'`, `Interrupted: 4 errors during collection` |
| `uv run` trong worktree khách (venv của **khách**) | test chạy thật, còn đúng **2 fail nội dung** (thiếu mark `django_db`) |

Kết luận đo được: `stacks.PY` ghép argv bằng `sys.executable`, tức Python của công ty, rồi chạy nó trong repo của
khách. Phụ thuộc mà khách khai trong `pyproject.toml` (Django, `pytest-django`…) không bao giờ có ở đó. **Không
code nào của builder làm cho nó xanh được** — ticket bị chặn bởi hạ tầng nhưng mọi bằng chứng trên bus lại trỏ vào
builder. Lỗi này dính **mọi ticket Python của mọi dự án khách**, không riêng TCK-001.

Đây đúng khuôn mà chính ADR-0013 đã đặt ra và sửa một nửa: trước ADR-0013 lệnh cứng `ruff`+`pytest` khiến PR của
frontend mang bằng chứng hình thức. ADR-0013 sửa *lệnh nào*, nhưng bỏ sót *chạy bằng môi trường nào*.

## Quyết định

`detect()` trả stack `PY_UV` khi repo khách có `pyproject.toml` khai bảng `[project]` (dự án uv thật). Lệnh trở
thành `uv run -- python -m ruff check` và `uv run -- python -m pytest -q -p no:cacheprovider`. `uv run` tự đồng bộ
`.venv` của worktree trước khi chạy, nên môi trường khớp đúng thứ khách khai.

Không khai `[project]` (chỉ `[tool.*]`), hoặc chỉ có `setup.cfg`/`requirements.txt` → giữ nguyên `sys.executable`.
Thà rơi về đường cũ còn hơn ghép một lệnh chắc chắn không chạy. `pyproject.toml` đọc bằng `tomllib`, không grep:
`[project]` nằm trong một chuỗi nhiều dòng không phải là bảng.

`.venv/` đã có sẵn trong `JUNK_PATTERNS` (`workspace.py`) nên venv do `uv run` dựng không lọt vào commit của
ticket kể cả khi `.gitignore` của khách quên nó.

## Cái giá đã biết, nói thẳng

`uv run` **cài gói từ `pyproject.toml` do chính model viết ra**. Đây là mở rộng thật sự của ranh giới tin cậy:
trước ADR này, agent không có đường nào khiến máy vận hành tải và chạy mã bên thứ ba; sau ADR này thì có, qua
danh sách dependency mà agent tự soạn. Người vận hành đã cân nhắc và chọn đúng đánh đổi này (2026-09-23) để phễu
chạy không cần người dựng venv tay cho từng repo khách.

Hai điều kiện biên còn hở, ghi ra để không ai tưởng là đã kín:

- `RunSpec.network=False` là mặc định, nhưng backend `subprocess` **không** thật sự tắt mạng — chỉ backend
  `container` mới tắt. Nên `uv sync` chạy được là vì lớp bảo vệ chưa bật, không phải vì đã được cấp phép có kiểm.
- Chưa có lọc domain/egress proxy: không có cách nào hiện nay chặn một dependency trỏ tới index lạ.

Cả hai thuộc về một ADR egress proxy riêng, chưa viết. Cho tới lúc đó, chạy công ty với repo khách **của chính
mình** là điều kiện sử dụng, không phải lời khuyên.

## Phương án đã loại

- **Chỉ dùng `.venv` có sẵn, người vận hành `uv sync` tay.** Không mở đường cài gói, nhưng mỗi ticket thêm
  dependency lại kẹt chờ người — trái đúng thứ đang muốn sửa (phễu tự chạy).
- **Dựng venv một lần lúc tạo worktree ticket đầu tiên.** Vẫn là agent gọi cài gói, cùng bề mặt rủi ro, mà thêm
  một điểm đồng bộ hỏng được (ticket sau đổi dependency thì venv cũ sai).
- **Cài phụ thuộc của khách vào venv của công ty.** Hai dự án khách khác phiên bản Django là hỏng; và trộn môi
  trường công ty với môi trường khách là đúng thứ ADR này đang gỡ.
