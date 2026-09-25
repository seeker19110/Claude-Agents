# ADR-0020: chữ ký bất đối xứng cho receipt chất lượng, xoay khoá và lộ trình rút HMAC

Ngày: 2026-09-25. Trạng thái: **Accepted** 2026-09-25. Chủ dự án đồng ý thêm dependency `cryptography`, tức phương án (a) (mục "Câu hỏi cho người").
Mở rộng ADR-0018 và ADR-0019; gói K1 của `docs/thi-hanh/pe2.md`, xử lý P3 (và khép P9) trong
`docs/reports/2026-09-25-danh-gia-pr335.md`. Không có code trong ADR này; code là gói K2.

## Bối cảnh

Hiện trạng đo trên nhánh `wt/pe2-ky` (`companies/software-company/src/company/product_quality.py`, 527 dòng):

| Đo | Giá trị | Chỗ |
|---|---|---|
| Scheme ký | HMAC-SHA256 khoá đối xứng, `hmac.new(key, _canonical(evidence), sha256)` | `sign_evidence`, dòng 325–330 |
| Verify | tính lại HMAC bằng **cùng khoá** rồi `compare_digest` | `assess`, dòng 429 |
| Registry | `{issuer: {principal_id, mode, allowed_checks, key_file}}`, `key_file` là file bí mật, verifier đọc **mọi** khoá | `_read_trust`, dòng 464–480 |
| Sàn khoá | `len(key) < 32` trên byte thô (32 ký tự hex = 128 bit vẫn qua — P9) | `TrustedIssuer.__post_init__` dòng 319, `sign_evidence` dòng 327 |
| Khoá dùng chung | so byte khoá giữa các issuer; hai `principal_id` cùng khoá → `identity:shared_key_across_principals` | `assess`, dòng 402–405 |
| Scheme ghim trong contract | `"evidence_policy": {..., "signature": "HMAC-SHA256"}` nằm trong thân băm `contract_hash` | `compile_contract`, dòng 264 |
| Kiểu chữ ký | `Receipt.signature: Digest` = `^[0-9a-f]{64}$` (vừa đúng HMAC-SHA256; chữ ký Ed25519 là 64 byte = 128 hex, không lọt) | dòng 48, 305–307 |
| Receipt lưu lâu dài | `commit_quality_result` ghi `receipt.model_dump(mode="json")` vào journal và fingerprint lost-ACK (không ghi khoá) | `quality_execution.py` ~dòng 183–212 |
| Số issuer | test: **2** (`ci`/`runtime-ci` mode `runner`, `qa`/`independent-qa` mode `independent_review`), `tests/test_product_quality.py:75–76`; `examples/`: **0** registry, 0 file khoá | grep `TrustedIssuer\|key_file` |
| Mode | 2: `runner`, `independent_review` (`Mode`, dòng 52) | |
| Policy version | `product-excellence/2` và `product-excellence/3`, cả hai đều ghim `"HMAC-SHA256"` | dòng 42–43 |
| `cryptography` trong `uv.lock` | **không có** — 0 dòng `name = "cryptography"` trên 79 package; `import cryptography` trong `.venv` → `ModuleNotFoundError` | `grep`, `uv run python` |
| Nếu thêm `cryptography` | `uv pip compile --python 3.11` (2026-09-25) phân giải **3** package: `cryptography==50.0.1`, `cffi==2.1.1`, `pycparser==3.0` | |
| `ssh-keygen` trong container CI/agent | không có (`which ssh-keygen` rỗng) | |
| Python | 3.11.15; stdlib không có Ed25519 (`hashlib`/`hmac` chỉ đối xứng) | |

Hệ quả của hiện trạng (P3): ai đọc được registry — coordinator, hay một tiến trình lọt vào máy coordinator — ký
được receipt `independent_review` dưới tên **bất kỳ** reviewer nào. Phép `self_approval` chỉ so `principal_id`,
không so người thực sự cầm khoá, nên tách quyền "người viết không tự duyệt" chỉ còn trên giấy. Docstring
`_read_trust` và `docs/PRODUCT-EXCELLENCE.md` dòng 167–169 đã thừa nhận điều này.

Mục tiêu đo được: **ai chỉ giữ registry thì không tạo được receipt hợp lệ.** Số principal có thể giả một receipt
`independent_review`: hiện tại = mọi tiến trình đọc được registry; mục tiêu = đúng 1 (reviewer cầm private key).

## Phương án

| | (a) Ed25519 qua `cryptography` | (b) HMAC mỗi issuer, verifier tách tiến trình | (c) Sigstore / keyless |
|---|---|---|---|
| Ai giả được receipt `independent_review` | chỉ người cầm private key của reviewer (1) | reviewer **và** tiến trình verifier (2); lọt verifier = giả được mọi issuer | chỉ người qua được OIDC của reviewer |
| Registry còn là bí mật? | không — chỉ public key | có — verifier vẫn giữ mọi khoá | không |
| Dependency mới | 3 package (`cryptography`, `cffi`, `pycparser`), wheel có sẵn cho Linux/macOS/Windows | 0 | `sigstore` + chuỗi phụ thuộc (kéo cả `cryptography`) |
| Mạng khi verify | không | không | **có** (Fulcio, Rekor/transparency log, TUF root) |
| Hạ tầng mới | không | một daemon/IPC verifier + uid riêng, phải trực, phải resume | tài khoản OIDC, CA ngoài |
| Xoay khoá | nhiều public key + `not_after`, không phải phát lại bí mật | phát lại bí mật cho cả signer lẫn verifier | tự động (cert ngắn hạn) |
| Chữ ký | 64 byte, verify ~µs, xác định (deterministic) | 32 byte | bundle cert + log entry |
| Chống kiểu lỗi P9 | kích thước khoá cố định 32 byte, không có "khoá yếu" | vẫn phải đo entropy khoá | n-a |

Phương án đã cân nhắc thêm và loại:

- **PyNaCl (libsodium)** — cùng tính chất bảo mật với (a), cũng là dependency mới (PyNaCl + cffi + pycparser);
  loại vì `cryptography` phổ biến hơn, có sẵn PEM/`SubjectPublicKeyInfo` chuẩn cho `public_key_pem`, và có khả năng
  cao là sẽ bị kéo vào bởi dependency khác sau này.
- **Ed25519 thuần Python tự viết/vendor** — 0 dependency, nhưng không constant-time, không có người bảo trì, và
  "tự viết crypto" là loại rủi ro repo không nên gánh. Loại.
- **`ssh-keygen -Y sign/verify` qua subprocess** — 0 dependency Python, offline; loại vì container agent/CI hiện
  không có `ssh-keygen` (đo ở trên), hành vi khác nhau giữa bản OpenSSH của Git-for-Windows và Linux, và mỗi verify
  là một subprocess với định dạng `allowed_signers` riêng.

## Quyết định

**Đề xuất (a): Ed25519 qua `cryptography`**, thêm vào dependency của package `company` (chỉ package này ký/verify
receipt). Phiên bản ghim bằng `uv add` ở K2 và ghi vào PR; mốc tham chiếu hôm nay là `cryptography==50.0.1`.

Vì sao loại (b): nó chỉ **dời** bí mật từ coordinator sang một tiến trình khác — verifier vẫn giả được mọi issuer,
nên số principal giả được receipt là 2 chứ không phải 1, trong khi phải dựng và trực thêm một daemon (trái tinh
thần "không dựng scheduler/worker pool mới" của ADR-0019). Vì sao loại (c): cần mạng khi ký và verify, trái bất
biến "không mạng khi verify" dưới đây và nguyên tắc self-hosted của `ARCHITECTURE.md`; dependency còn nặng hơn (a).

### 1. Định dạng registry mới

```json
{
  "<issuer_id>": {
    "principal_id": "independent-qa",
    "mode": "independent_review",
    "allowed_checks": ["..."],
    "keys": [
      {"key_id": "<sha256 hex của 32 byte public key thô>",
       "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
       "not_after": "2027-03-31T00:00:00Z"}
    ]
  }
}
```

- `keys` không rỗng; `public_key_pem` là `SubjectPublicKeyInfo` Ed25519, loại khoá khác → lỗi cấu hình.
- `key_id` **bắt buộc bằng** `sha256(raw_public_key).hexdigest()`; verifier tính lại, lệch → lỗi cấu hình. Không có
  `key_id` tự đặt để hai khoá khác nhau trùng tên.
- `not_after` là datetime có múi giờ, bắt buộc.
- Registry mới **không chứa bí mật**: có thể đọc bởi coordinator, console, reviewer; không được ghi bởi worker.
- Entry cũ `{principal_id, mode, allowed_checks, key_file}` vẫn đọc được, nhưng khoá HMAC chỉ được dùng cho
  contract `legacy_hmac` (mục 3). Một issuer có thể có cả `keys` lẫn `key_file` trong giai đoạn chuyển.

### 2. Receipt

- Thêm `Receipt.signature_scheme: Literal["hmac-sha256", "ed25519"]` và `Receipt.key_id: str | None`.
- Receipt HMAC cũ **không có** hai trường này. Serializer bỏ chúng khi `signature_scheme == "hmac-sha256"` và
  `key_id is None` (cùng kỹ thuật `model_serializer` đang giữ byte cho `delivery_report`), nên `model_dump` của
  receipt v2 ra đúng byte cũ → fingerprint lost-ACK trong journal (ADR-0019) không đổi.
- `signature`: 64 hex cho HMAC, 128 hex cho Ed25519, ràng buộc theo scheme (không nới `Digest` cho HMAC).
- Nội dung được ký giữ nguyên: `_canonical(evidence.model_dump(mode="json"))`. Evidence đã chứa `issuer`,
  `contract_hash`, `run_id`, `candidate_sha`, nên không cần bọc thêm domain separation ở tầng này; `key_id` và
  scheme được chọn bởi verifier theo registry + contract, không tin vào lời khai của receipt.

### 3. Contract ghim `allowed_schemes`

- Profile có trường mới (trong `evidence_policy`) `allowed_schemes`; giá trị hợp lệ duy nhất cho contract mới là
  `["ed25519"]` — validator từ chối `"hmac-sha256"` ở profile mới.
- Profile có `allowed_schemes` compile ra `policy_version = "product-excellence/4"` và `evidence_policy` chứa
  `"signature": "Ed25519", "allowed_schemes": ["ed25519"]`.
- Profile **không có** `allowed_schemes` compile ra đúng byte cũ (v2 hoặc v3, `"signature": "HMAC-SHA256"`) — đó
  là contract `legacy_hmac`, chỉ nhận receipt HMAC. Không có contract nào nhận cả hai scheme.
- Contract mới không được là `legacy_hmac`: đường đăng ký run mới của coordinator (`quality_execution`) từ chối
  profile thiếu `allowed_schemes` sau khi K2 merge. `assess` vẫn tính lại `contract_hash` từ profile nên run cũ
  giữ nguyên hash.
- Receipt có scheme không nằm trong scheme của contract → blocker `<check>:scheme_not_allowed` (fail-closed).

### 4. Xoay khoá

- Một issuer giữ **nhiều** key trong `keys`. Xoay = thêm key mới, signer chuyển sang key mới, giữ key cũ tới khi
  mọi evidence ký bằng nó đã hết hạn (≤ `max_age_seconds` của policy, mặc định 24h) rồi mới gỡ.
- Receipt hợp lệ với key chỉ khi `evidence.created_at < key.not_after` **và** `now` nằm trong cửa sổ evidence như
  hiện nay. Key hết `not_after` không ký được receipt mới được nhận; receipt đã ký trước đó vẫn verify trong cửa sổ
  tuổi evidence.
- Lộ khoá: gỡ key khỏi registry (thu hồi ngay). Quyết định đã ghi trong journal không bị verify lại (ADR-0019:
  retry chỉ ACK quyết định cũ), nên thu hồi không viết lại lịch sử.
- `key_id` không khớp key nào của issuer → blocker `<check>:unknown_key`.

### 5. Nơi giữ private key

- Private key Ed25519 nằm ở **tiến trình signer của đúng issuer** (trusted driver CI cho `runner`; máy/tài khoản
  reviewer cho `independent_review`), file quyền `0600` thuộc uid của issuer đó.
- **Ngoài worktree ticket** và ngoài `company.artifacts/`; **ngoài quyền worker** (uid/sandbox worker không đọc
  được, không mount vào container worker — ADR-0013/0014); coordinator **không** giữ private key nào.
- Không commit (luật cấm 3, gitleaks). Test sinh cặp khoá trong fixture lúc chạy, không commit khoá mẫu.

### 6. Cùng public key cho hai principal → blocker

Verifier giải PEM về 32 byte thô rồi so (không so chuỗi PEM, tránh lách bằng khoảng trắng/header). Cùng khoá thô
xuất hiện dưới hai `principal_id` khác nhau → blocker `identity:shared_key_across_principals`, giữ đúng tên
blocker hiện có. Cùng khoá dưới hai issuer của **cùng** principal được phép (như hành vi HMAC hiện tại).

### 7. Lộ trình rút HMAC

| Pha | Việc | Điều kiện sang pha sau |
|---|---|---|
| 0 (K1) | ADR này; không đổi hành vi | người đồng ý dependency |
| 1 (K2) | thêm Ed25519, `allowed_schemes`, registry `keys`; contract mới bắt buộc Ed25519; HMAC chỉ cho `legacy_hmac` | K2 merge, gate xanh |
| 2 | `sign_evidence` HMAC chỉ còn cho run `legacy_hmac` đã đăng ký trước mốc K2; ghi cảnh báo khi dùng | journal có **0** run `legacy_hmac` chưa terminal |
| 3 | gỡ đường **ký** HMAC (`sign_evidence` HMAC, sàn `len(key) < 32`, tài liệu `key_file` cho issuer mới) | — |
| mãi mãi | giữ đường **verify** HMAC chỉ-đọc cho contract `legacy_hmac` | không bao giờ gỡ |

P9 (sàn 32 byte thô) không được siết hồi tố cho khoá HMAC đang dùng — siết sẽ làm run cũ không verify được; nó
khép lại khi pha 3 gỡ đường ký HMAC. Ed25519 không có khái niệm khoá ngắn.

### Bất biến

1. **Run v2 (và v3 đã compile trước K2) verify được mãi**: profile cũ compile ra đúng byte và `contract_hash` cũ;
   receipt cũ dump ra đúng byte và chữ ký cũ; đường verify HMAC không bị gỡ. Test đối chiếu byte với fixture của
   code parent, như test giữ byte `delivery` hiện có.
2. **Contract mới không nhận HMAC**: `allowed_schemes` không chấp nhận `"hmac-sha256"`; contract `legacy_hmac`
   không sinh được cho run đăng ký sau K2.
3. **Không mạng khi verify**: verify chỉ dùng registry cục bộ, public key trong đó và thư viện offline; không gọi
   CA, transparency log, OIDC hay tải khoá từ URL.
4. Fail-closed giữ nguyên: mọi lỗi scheme/key/cấu hình thành blocker hoặc exit 2, không nhánh mặc định cho qua.

## Hệ quả

- Tách quyền `independent_review` có thật: coordinator đọc registry không ký thay reviewer được. Lọt máy coordinator
  vẫn chặn được evidence (không gửi), nhưng không **tạo** được PASS.
- Thêm 3 package vào `uv.lock` (có extension biên dịch sẵn qua `cffi`); phải theo dõi CVE của `cryptography`
  như dependency bảo mật. Đây là lý do ADR ở trạng thái Proposed.
- Registry có hai dạng entry trong giai đoạn chuyển; code `_read_trust` phức tạp hơn cho tới pha 3.
- Chữ ký chứng thực **nguồn** (driver/reviewer), không chứng thực phương pháp kiểm của driver đúng — giới hạn cũ
  của docstring `assess` không đổi.
- Không giải quyết: reviewer thật sự độc lập với tác giả hay không (vẫn do `author_principals` coordinator cấp);
  phân phối public key tin cậy vào registry (vẫn là thao tác out-of-band của người vận hành).
- Nếu người **không** đồng ý dependency: gói K2 phải viết lại theo (b) trước khi giao (`docs/thi-hanh/pe2.md`
  mục phụ thuộc), và mục tiêu "chỉ 1 principal giả được" hạ xuống 2 — phải ghi rõ trong `docs/PRODUCT-EXCELLENCE.md`.

## Câu hỏi cho người

Đã trả lời ngày 2026-09-25: đồng ý `cryptography`.

1. **Chọn dependency** (quyết định duy nhất cần người ký): đồng ý thêm `cryptography` (kéo `cffi`, `pycparser`)
   vào `companies/software-company/pyproject.toml` để dùng Ed25519 — phương án (a)? Hay từ chối, chấp nhận (b)
   HMAC + verifier tách tiến trình với tính chất bảo mật yếu hơn đã nêu?

## Liên quan

- `docs/reports/2026-09-25-danh-gia-pr335.md` — P3, P9.
- `docs/thi-hanh/pe2.md` — gói K1, K2.
- ADR-0018 (`docs/adr/0018-product-quality-execution-adapter.md`), ADR-0019 (`docs/adr/0019-atomic-quality-result-journal.md`).
- ADR-0013, ADR-0014 — ranh giới container và bí mật.
- `companies/software-company/src/company/product_quality.py`, `quality_execution.py`, `docs/PRODUCT-EXCELLENCE.md`.
