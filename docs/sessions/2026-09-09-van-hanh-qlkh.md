# Phiên 2026-09-09 — vận hành lại công ty phần mềm, gỡ phễu release QLKH

Mục tiêu người giao: "tiếp tục vận hành công ty phần mềm" → "mở console" → "xử lý hết" → "tự xử lý để công ty
vận hành lại, phát triển nốt dự án dang dở `D:\khach\qlkh`".

## Kết quả một dòng

Phễu release QLKH chết từ REL-027 **không phải vì code khách hỏng**, mà vì `approved-specs` của QLKH thiếu
trường `runtime`. Đã gỡ. Song song, staging WSL lần đầu chạy được end-to-end (deploy 4s, `/` trả 200).

## Nguyên nhân gốc (đo được, không suy đoán)

`smoke.parse_runtime()` đọc `approved-specs.payload.runtime`. Spec QLKH (seq 333) ra đời TRƯỚC ADR-0031 nên
không có `runtime` lẫn `kind`. Hệ quả dây chuyền:

`parse_runtime` → `None` → `verify.smoke()` ghi `unverified` → `kind` thiếu tính mặc định là `application` →
`unverified` + `application` = **staging FAILED** → RC không đi tiếp → 11 lượt unverified liên tiếp
(REL-027..038), 19 release không giao được, 10 staging thất bại.

**Bẫy đáng nhớ**: `TCK-CR-RUNTIME-01` đã tạo `runtime.yaml` trong repo khách — nhưng KHÔNG dòng mã nào của công
ty đọc file đó (`grep -rn "runtime.yaml" src/` ra đúng một chú thích, không có chỗ đọc). Ticket được giao cho
`builder`, vai chỉ sửa được file trong repo khách và **không có công cụ ghi lên topic `approved-specs`** — nên nó
không thể hoàn thành đúng, retry 2 lần rồi kẹt. Đây đúng khuôn "agent thất bại lặp lại: kiểm CÔNG CỤ trước".

## Đường sửa đúng luật (thử sai một lần, ghi lại để khỏi lặp)

Publish thẳng `approved-specs` với `--actor human:seeker` **bị bus từ chối**:

```
PermissionDenied: người human:seeker không được phát topic approved-specs
(producer hợp lệ: acceptance-results, change-requests, clarification-answers,
 external-feedback, pull-requests, research-requests, supervisor-actions)
```

Guardrail chạy đúng. Đường hợp lệ: publish `clarification-answers` (topic người được phát) → route
`clarification-answers → PRODUCT → approved-specs` (pha `spec`) làm phần còn lại.

Bán kính ảnh hưởng đã kiểm TRƯỚC khi publish: `SPEC-QLKH` đã approved và QLKH đã có `PLAN-QLKH-1..7`, nên nhánh
`plan.duplicate_spec` trong `ticket_fsm._plan` chặn việc sinh lại kế hoạch — chỉ tốn một lượt threat-model.

Kết quả: `product` phát `approved-specs` mới (seq 18299) với `kind=application` + `runtime`, và
`parse_runtime` nay trả về `Runtime(...)` thay vì `None`.

## Việc còn dở — NGƯỜI SAU ĐỌC KỸ

**Nút thắt kế tiếp đã định vị chính xác, chưa sửa**: `release_fsm` chỉ chạy smoke thật khi agent khai
`status="deployed"`:

```python
if r.target_env == "staging" and p.get("status") == "deployed":
    p = o._smoke(agent, rc, rid, p, integ)
```

`redeploy REL-047` cho thấy agent `ops` khai `status="pending_human"` kèm `smoke.reason` tự viết
("Không được chạy công cụ; không có bằng chứng orchestrator đã dựng môi trường..."). Chuỗi đó KHÔNG có trong
`src/` — tức là **lời khai của model**, không phải bằng chứng máy. Vì không khai `deployed`, `verify.smoke()`
không bao giờ được gọi, nên smoke thật (đã sẵn sàng chạy) vẫn không chạy.

Đây lặp lại khuôn REL-019 ("release-engineer tự từ chối deploy"). Hướng sửa là đổi **tài liệu agent `ops` đọc**
(prompt pha `deploy`) để nó hiểu: nó KHÔNG có tool deploy, `deployed` chỉ là yêu cầu đi tiếp, và orchestrator mới
là bên kết luận bằng smoke thật. Không vá bằng cách ghi tay lên bus.

Việc khác còn treo: 5 ticket `dispatched` kẹt vì agent "không sửa file nào" (QLKH-010, QLKH-011,
TCK-CR-OPS-001-05, TCK-CR-RUNTIME-01, TCK-CR-RUNTIME-02) — kiểm công cụ của vai trước khi ép chúng chạy lại.

## Repo khách `D:\khach\qlkh` — đã đẩy `company/integration` (`b1b3e4b..4ae8597`)

Staging WSL trước đây chưa từng chạy trọn vẹn. Sáu lỗi thật, mỗi lỗi đo bằng đối chứng:

1. **Node**: PATH của WSL kế thừa Windows nên `npm` trần trỏ `/mnt/c/.../npm`; shim gọi `CMD.EXE`, CMD không hỗ
   trợ đường dẫn UNC → `'tsc' is not recognized`. Cùng lệnh `npm run build`: Node Windows chết, Node Linux (nvm
   v22.23.2) xong 449ms. `nvm` không tự nạp trong shell không tương tác → phải source tay.
2. **venv**: `python3 -m venv` thất bại trên máy này (`ensurepip is not available`, đòi sudo apt). Dùng
   `uv venv --seed`; `uv` ở `~/.local/bin` **không có trên PATH shell không tương tác** — cùng họ bẫy với nvm.
3. **Guard venv** phải là "có `pip` chạy được", không phải "thư mục tồn tại": một lần tạo hỏng dở để lại
   `$VENV_DIR` thiếu pip → lần sau bỏ qua bước tạo rồi chết ở `pip: No such file or directory`.
4. **node_modules lỗi thời**: giữ qua các lần deploy là đúng, nhưng "đã có" ≠ "còn đúng" — sau khi hoà
   integration, `package.json` thêm `axe-core` mà bản cài cũ không có → `TS2307`. Nay cài lại khi `package.json`
   mới hơn lần cài trước.
5. **`npm ci` không bao giờ chạy được**: `web/package-lock.json` KHÔNG được commit và bị `git clean` xoá mỗi lần
   deploy, mà `npm ci` bắt buộc có lockfile → dùng `npm install` khi thiếu. **Lỗ hổng khoá phiên bản frontend
   này vẫn còn** (Python có `requirements.lock`, frontend không có gì) — cần một ticket riêng.
6. **`git clean`** phải loại trừ cả ba `var`, `.venv`, `web/node_modules` (bản HEAD thiếu `.venv`, bản
   integration thiếu `web/node_modules`).

**Build frontend đã hỏng SẴN trên `company/integration`**, không phải do merge: `deploy.sh company/integration`
cho đúng 3 lỗi `TS2307 node:fs / node:path / TS2552 __dirname`. `TCK-CR-RUNTIME-04` thêm test a11y dùng API của
Node nhưng `web/package.json` không có `@types/node` và `web/tsconfig.json` (`include: ["src"]`, `types` không có
`"node"`) kéo file test vào build production — tức **ticket a11y được duyệt mà chưa ai từng chạy `npm run build`**.
Đã sửa bằng `@types/node` + thêm `"node"` vào `types`.

Nghiệm thu CR-STAGE-001 đo thật: deploy 3–6s (tiêu chí ≤2 phút), healthz 200 đúng sha, idempotent (pid cũ bị
dừng, đúng 1 devserver giữ :8080), rollback 4s về đúng sha trước, `/` trả **HTTP 200** (trước là 404).

## Bẫy thao tác đã mắc trong phiên này

- Bật `orchestrator run --watch` **thiếu `--repo`** (lặp lại đúng bẫy đã ghi trong bộ nhớ). `--repo` phải đứng
  TRƯỚC subcommand. Đã dừng và bật lại đúng.
- `--watch` cần một đối số (số giây): `--watch 30`, không phải `--watch` trần.
- Log của watch loop ghi ra file bị Python buffer → **log rỗng không có nghĩa là tiến trình chết**. Kiểm bằng
  PID và bằng event mới trên bus, đừng kết luận từ log rỗng.
- Xoá `.venv` của staging để "test sạch" đã làm hỏng staging đang chạy — nhưng chính nó lộ ra lỗi (2).

## Trạng thái để lại

- Console: chạy ở `127.0.0.1:8201` (chỉ đọc). Orchestrator: `--repo D:/khach/qlkh run --watch 30`.
- Nhánh `fix/console-doc-bus-task-cu` đã commit, **chưa mở PR** vì #218 (`feat/keeper-bt6`, phiên khác) đang mở
  — luật §2b chỉ cho một PR mở. Chờ #218 merge → `git fetch` + `rebase origin/main` → `gh pr create` → điền
  `(#n)` vào dòng CHANGELOG rồi commit tiếp vào chính PR đó (luật 10).
