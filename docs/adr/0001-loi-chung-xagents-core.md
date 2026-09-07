# ADR-0001: lõi chung `xagents-core` cho mọi công ty AI

Ngày: 2026-09-07 · Trạng thái: được chấp nhận · Epic: K3 của `docs/DAC-TA-KICH-BAN-B.md`

## Bối cảnh

Tuyên bố của repo (`docs/DAC-TA-KICH-BAN-B.md` §0) là *"một công ty mới là một thư mục cấu hình, không phải một
bản fork"*. Đo tại `main@9006774` thì hiện trạng ngược lại — `software-company` và `Studio-creators` là hai bản
fork của cùng một bộ khung, đã trôi xa nhau:

| Module | company | studio | dòng trùng nguyên văn |
|---|---|---|---|
| `llm.py` | 1139 | 696 | 491 |
| `evals.py` | 350 | 281 | 210 |
| `runner.py` | 551 | 342 | 176 |
| `sandbox.py` | 190 | 216 | 158 |
| `routing.py` | 196 | 160 | 124 |
| `tools.py` | 335 | 307 | 97 |
| `gate_cli.py` | 136 | 126 | 84 |
| `registry.py` | 103 | 84 | 76 |
| `supervisor.py` | 308 | 124 | 72 |
| `events.py` | 200 | 314 | 67 |
| `bus.py` | 200 | 61 | 49 |
| `sqlite_bus.py` | 151 | 81 | 45 |
| `gates.py` | 51 | 65 | 42 |
| `blackboard.py` | 114 | 30 | 16 |
| **tổng** | | | **1707** |

(đo bằng `difflib.SequenceMatcher` trên từng cặp file; lệnh trong thân PR)

Ba hệ quả đã quan sát được, không phải suy đoán:

1. **Số import chéo giữa hai package là 0.** Mỗi lần sửa một lỗi lõi là hai lần sửa, và trong thực tế chỉ có một
   lần: `context.py` (126 dòng, cắt ngữ cảnh) và `guard.py` (146 dòng, chặn injection + ACL topic) **chỉ có ở
   company**; studio chưa từng nhận. Cột "dòng trùng" ở trên vì thế còn nói nhẹ: chỗ nguy hiểm nhất không phải
   phần trùng, mà phần company có mà studio không.
2. **Lớp cứng hoá đi một chiều.** `llm.py` của company dày hơn 443 dòng: `TransientError` + hoãn event thay vì
   dừng, `RetryingClient`, `Pricing`, cầu MCP, `CLI_NO_TOOL_TURNS`. Studio gặp `LLMError` giữa chừng thì orchestrator
   **dừng** — đúng khuôn lỗi TRAPS §1 mà company đã sửa từ lâu.
3. **Bản tạm đã nằm sẵn trong repo.** `studio/sandbox.py` (K2.3, #119) là bản chép có ghi chú "xoá ở K3.2" —
   158/190 dòng giống hệt bản company. Nợ này được vay có ý thức và có hẹn trả; ADR này là chỗ trả.

Không làm gì thì công ty thứ ba tốn đúng bằng công ty thứ hai đã tốn, và câu hỏi T1 của kịch bản B ("dựng bằng
cấu hình, không fork code?") vĩnh viễn trả lời "không".

## Quyết định

Dựng **package thứ năm `xagents-core`** (module `xagents_core`) trong cùng uv workspace, chứa phần khung mà mọi
công ty dùng chung. `company` và `studio` import từ đó.

1. **Company là gốc, studio được nâng.** Với mỗi module, bản company là bản vào core (nó dày hơn vì đã ăn nhiều
   sự cố thật). Studio nhận theo, kể cả khi điều đó **đổi hành vi** của studio — `LLMError` giữa chừng chuyển từ
   "dừng" sang "hoãn event". Đây là thay đổi có chủ ý, ghi ở CHANGELOG studio, không phải tác dụng phụ.

2. **Core không biết tên công ty.** Mọi điểm khác nhau đi qua một `CoreConfig` do package dựng một lần
   (`company/core.py`, `studio/core.py`): `prefix` ("COMPANY"/"STUDIO" — tiền tố biến môi trường, thông điệp lỗi,
   tên tool MCP), `root`, `db_name`, `schema_dir`, `topic_acl`, `payload_models`, `namespace_owners`,
   `transitions`, `external_topics`/`derived_topics`, `approvers_env`. Không có `if prefix == "COMPANY"` trong
   core — đó là fork mọc lại dưới dạng câu điều kiện.

3. **Cái gì Ở LẠI package.** Miền nghiệp vụ không lên core: `Topic`/`Namespace` Literal, mô hình payload
   (`Task` vs `VideoBrief`), `tools_prompt` (chữ ký lệch), `rollback_target` (miền video). Core giữ *cơ chế*,
   package giữ *nghĩa*.

4. **Tương thích ngược bằng shim.** Mọi tên `company.X`/`studio.X` mà console, test, tài liệu đang import vẫn
   import được: module cũ thành `from xagents_core.X import *` (≤ 3 dòng), hoặc hàm bọc `functools.partial(...,
   core=CORE)` với module cần cấu hình. **Console và gateway không sửa một dòng nào vì lý do tách lõi** — đó là
   thước đo của "tương thích ngược", không phải lời hứa.

5. **Bảy bước, mỗi bước một PR, thứ tự bắt buộc** (K3.0–K3.7 trong đặc tả): khung + CI → `context` → `tools` →
   `llm`+`routing` (một PR, có chu trình import) → `guard` → `events`+`bus`+`sqlite_bus` → `registry`+
   `blackboard`+`runner`+`evals` → `gates`+`gate_cli`+`supervisor`. Rủi ro dồn vào bước 6 (dữ liệu sqlite thật của
   studio), nên **sau bước 6 phải để hệ chạy thật ≥ 5 ngày lịch trước khi đi bước 7**.

6. **`strict = true` cho mypy ở core từ ngày đầu** (K6.1), `fail_under = 100` như bốn package còn lại. Core là
   chỗ mọi công ty tin cậy; nó không được lỏng hơn nơi gọi nó.

## Hệ quả

**Được.** Một chỗ sửa cho một lỗi lõi. Studio nhận miễn phí 16 module đã cứng hoá (kể cả `context`/`guard` chưa
từng có). Công ty thứ ba là một `CoreConfig` + thư mục `agents/`, không phải một bản fork. `sandbox.py` bản tạm
của studio biến mất đúng hẹn.

**Mất.** Một package nữa để bảo trì: hai job CI (`core-static`, `core-unit`), một dòng nữa trong `make test`,
`uv.lock` phải khoá lại. Một tầng gián tiếp khi đọc mã: `company.llm` → shim → `xagents_core.llm`. Đổi core là
đổi cho cả hai công ty cùng lúc — sức mạnh và rủi ro là một.

**Nợ có hẹn.** Shim sống tới chân trời 3 (khi console đổi import sang `xagents_core`). Mỗi shim mang ghi chú
"xoá khi console đổi import"; không có ghi chú thì nó sẽ ở lại vĩnh viễn — đúng cách `studio/sandbox.py` suýt ở lại.

**Không thuộc phạm vi.** Hợp nhất `events` miền (`Task` vs `VideoBrief`); hợp nhất `tools` miền; đổi tên module
`company`/`studio`; xoá shim.

## Liên quan

- `docs/DAC-TA-KICH-BAN-B.md` K3 (yêu cầu, nghiệm thu từng bước) và `docs/DAC-TA-TRIEN-KHAI-KICH-BAN-B.md` K3
  (PR theo PR, `file:dòng`).
- `docs/adr/0002-bus-phien-ban-va-doc-luoi.md` (K4) — xây trên `xagents_core.sqlite_bus` sau bước 6.
- `software-company/docs/adr/0035-sandbox-tien-trinh.md` (K2) — `Sandbox` là interface core nhận ở bước 3.
- `Studio-creators/docs/adr/0010` "nhận lớp cứng hoá từ core" (viết ở bước 4).
- `TRAPS.md` §1 khuôn 1 (lỗi im lặng) và khuôn 2 (state không sống sót restart) — hai khuôn mà bản company đã
  chữa và studio sẽ nhận theo.
