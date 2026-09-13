# ADR-0014: Bí mật, state và gateway của hub container — bốn sửa đổi cho ADR-0013

Trạng thái: Chấp nhận (đã cài đặt) · Ngày: 2026-09-13 · Sửa đổi ADR-0013 (container hoá hub), liên quan
ADR-0039 (`companies/software-company`, deploy khách bằng compose), `AGENTS.md` luật cấm 3.
Nguồn: `docs/reports/2026-09-13-audit.md`.

## Bối cảnh

ADR-0013 chọn đúng hình dạng — **một image, một container, một máy** — và lý do vẫn đứng: bus là SQLite một
writer (`journal_mode=WAL`), ticket chạy trên `git worktree` của filesystem cục bộ, `deploy.py` gọi
`docker compose` qua `/var/run/docker.sock` của host, gateway đăng nhập bằng PKCE mở trình duyệt thật. Không
có gì ở đây scale ra nhiều node được, và cũng không cần.

Nhưng audit 2026-09-13 đọc lại bộ file ấy thì thấy **năm chỗ hở, tất cả đều im lặng**: không cổng nào đỏ,
`docker compose up -d` vẫn chạy, chỉ có bí mật nằm sai chỗ và state biến mất khi `down`.

1. `.dockerignore` loại `*.sqlite*`, `.console-token`, `.engine/`… nhưng **không loại `llm.yaml` và `.env`**,
   trong khi `Dockerfile` có `COPY . .`. Ngữ cảnh build không đọc `.gitignore`. Máy vận hành đã cấu hình xong
   (đúng máy sẽ chạy `up -d --build`) thì `llm.yaml` thật và `.env` mang `GH_TOKEN` **vào thẳng layer image**.
   gitleaks không bắt được lớp này vì file chưa từng vào git — cổng bí mật duy nhất của repo mù đúng chỗ này.
2. Không volume nào mang `llm.yaml` vào container. Nên hub hoặc chạy bằng bí mật đã bake (mục 1), hoặc không
   có cấu hình model nào — cả hai đều không phải ý định của ADR-0013 quyết định 4.
3. ADR-0013 **không nhắc chữ "gateway" lần nào**, và compose không có `network_mode` lẫn `extra_hosts`. Gateway
   là tiến trình trên host; trong container `base_url: http://127.0.0.1:1123/v1` trỏ về chính container. Hub
   container không dùng được pool tài khoản của chính dự án.
4. Bus chạy WAL, tức SQLite sinh `company.sqlite-wal` và `-shm` **cạnh** file DB. Compose bind-mount một FILE
   `.sqlite`, nên hai file anh em rơi vào layer container: mất khi `down`, và lệch trạng thái nếu host cũng mở
   cùng DB.
5. Volume artifacts mount ở `/app/companies/software-company/company.sqlite.artifacts`, nhưng tên code sinh ra
   là `company.artifacts` (`runner.artifact_store` = `db.with_suffix(".artifacts")` — đo thật:
   `Path("…/company.sqlite").with_suffix(".artifacts")` → `…/company.artifacts`). Volume ấy **chưa bao giờ**
   nhận gì; PRD, threat model, hồ sơ gate của blackboard nằm trong layer container và mất khi `down`.

Mục 1 nặng nhất và khác loại với bốn mục kia: đó là rò rỉ bí mật, không phải bất tiện vận hành.

## Quyết định

1. **Bí mật ra khỏi ngữ cảnh build.** `.dockerignore` loại `**/llm.yaml`, `**/media.yaml`, `.env`, `**/.env` —
   đúng danh sách `AGENTS.md` luật cấm 3, vì `COPY . .` và `.gitignore` là hai cơ chế khác nhau trên cùng một
   danh sách.
2. **Cấu hình model vào bằng volume**, mount `./companies/software-company/llm.yaml` `:ro`. Muốn đổi model
   ngay trên console (`--allow-config` ghi `llm.yaml`, giữ `.bak`) thì bỏ `:ro` — đó là lựa chọn của người vận
   hành, không phải mặc định.
3. **Gateway ở lại trên host, hub nối tới qua `extra_hosts: host.docker.internal:host-gateway`.** Không chuyển
   gateway vào container: nó cần trình duyệt thật cho `gateway login`, và pool token của nó (`$XAGENTS_HOME`)
   là dữ liệu cá nhân của máy người vận hành, không phải state của công ty. Hệ quả người vận hành phải biết:
   `llm.yaml` của **bản container** khai `base_url: http://host.docker.internal:1123/v1`, khác bản chạy trần
   (`127.0.0.1:1123`). Không chọn `network_mode: host` vì nó bỏ luôn `ports:` và kéo theo mọi cổng khác của
   container ra host — đắt hơn thứ cần mua.
4. **State mount theo THƯ MỤC `var/`, không theo file.** `./companies/<công ty>/var` mount vào container;
   entrypoint truyền `--company-db …/var/company.sqlite` và `--keeper-db …/var/keeper.sqlite`. Ba thứ phải sống
   qua `down` — file DB, `-wal`/`-shm`, và `<db>.artifacts/` — khi đó đều nằm trong cùng một thư mục được
   mount, nên mục 4 và mục 5 của phần Bối cảnh đóng bằng **một** quyết định thay vì hai bản vá đường dẫn.
   `keeper` vốn đã có quy ước `var/` (`.gitignore:58`); software-company nay theo cùng quy ước.
   Không đổi một dòng mã nào: `console/__main__.py` đã có `--company-db`/`--keeper-db`, và `console/engine.py`
   truyền tiếp đúng đường dẫn ấy cho orchestrator con qua `--db`.

## Việc KHÔNG làm (cố ý)

- **Không chuyển DB của bản chạy trần** sang `var/`. Người chạy tay vẫn dùng `companies/software-company/company.sqlite`
  như `AGENTS.md` §"Chạy cái gì ở đâu" đã ghi. Cái giá phải nói rõ: bản container và bản chạy trần nhìn **hai
  file DB khác nhau** — chạy `orchestrator status` trên host trong lúc hub chạy trong container là đang đọc bus
  rỗng. Ghi vào compose và `docs/TRUC-VA-DUNG-KHAN.md`, không cố hợp nhất bằng symlink (symlink + WAL qua bind
  mount là đúng lớp lỗi vừa sửa).
- **Không đưa gateway vào compose thành service thứ hai** — lý do ở quyết định 3.
- **Không rolling update / nhiều node / registry** — giữ nguyên ranh giới ADR-0013 đã đặt.

## Hệ quả

- Người vận hành phải **tạo `llm.yaml` trước khi `up -d`** — trước đây file ấy lọt vào image nên "chạy được"
  một cách tình cờ trên đúng máy đã build. Thiếu file ⇒ mount hỏng, thấy ngay lúc `up`, không âm thầm.
- `llm.yaml` của bản container khai `host.docker.internal:1123`, bản chạy trần khai `127.0.0.1:1123`.
- State của bản container nằm ở `companies/<công ty>/var/` (đã `.gitignore`), khác chỗ bản chạy trần.
  `docs/TRUC-VA-DUNG-KHAN.md` Mức 0 không đổi lệnh (`docker compose down`), nhưng người đọc bus bằng CLI trên
  host phải trỏ `--db` vào `var/` khi hub đang chạy trong container.
- Ai đã `up -d --build` bằng bộ file cũ thì **image đang có `llm.yaml`/`.env` bên trong**: build lại sau khi
  lấy bản vá này, và nếu image cũ từng được push đi đâu thì coi như khoá trong đó đã lộ, thu hồi ở nhà cung cấp
  (`docs/TRUC-VA-DUNG-KHAN.md` §1 "không thu hồi thông tin xác thực").

## Đo hai chiều (thay cho TDD của file cấu hình thuần)

File cấu hình thuần là ngoại lệ của luật bắt buộc 4 (`AGENTS.md`), nhưng ở đây **không dùng ngoại lệ ấy**: bốn
quyết định trên đều kiểm được bằng test thật, nên có cổng cứng `platform/console/tests/test_cong_docker.py`
(6 ca, chạy trong job `console-unit`), viết TRƯỚC bản vá.

- Tắt bản vá (bộ file như trước PR này): **6/6 đỏ**, mỗi ca chỉ đúng một chỗ hở.
- Bật bản vá: **6/6 xanh**.

Thứ cổng này KHÔNG canh, nói rõ để không ai tưởng đã canh: nó đọc file cấu hình, **không chạy `docker compose
up`**. Một lần `up -d` thật trên máy có Docker Engine vẫn là bước nghiệm thu cuối, và chưa chạy trong phiên viết
ADR này (phiên đó không có docker daemon).
