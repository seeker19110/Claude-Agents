# QLKH-001 — Khung monolith + cổng chất lượng CI + fitness function

Nguồn: ADR-003 (monolith), ADR-004 (kiểm quyền tầng dữ liệu), ADR-005/006, threat-model T-05/T-08/T-12, NFR-001/NFR-003.

## 1. Cấu trúc repo

```
src/qlkh/
  domain/          # thực thể, quy tắc nghiệp vụ thuần; KHÔNG import ORM/HTTP/framework
  application/     # use case, port; import domain
  infrastructure/  # ORM, HTTP, adapter storage, session store; import application + domain
tests/
  unit/ integration/ authz/
infra/             # IaC (chưa có tài nguyên; DEF-01 chưa quyết nhà cung cấp)
policy/            # rego cho conftest
.github/workflows/ci.yml
pyproject.toml     # lockfile: uv.lock / poetry.lock BẮT BUỘC commit
importlinter.ini
```

Hướng phụ thuộc cho phép: `infrastructure -> application -> domain`. Mọi chiều ngược lại là lỗi build.

## 2. Fitness function hướng phụ thuộc

`importlinter.ini`:

```ini
[importlinter]
root_package = qlkh

[importlinter:contract:layers]
name = Huong phu thuoc theo lop
type = layers
layers =
    qlkh.infrastructure
    qlkh.application
    qlkh.domain

[importlinter:contract:domain-pure]
name = Domain khong cham framework
type = forbidden
source_modules = qlkh.domain
forbidden_modules =
    sqlalchemy
    django
    fastapi
    flask
    starlette
    requests
    httpx
    psycopg

[importlinter:contract:no-cycles]
name = Khong vong phu thuoc
type = independence
modules =
    qlkh.domain.identity
    qlkh.domain.people
    qlkh.domain.teaching
    qlkh.domain.content
    qlkh.domain.compliance
```

Tiêu chí chấp nhận 1 thỏa mãn: PR có `domain` import ORM → job `fitness` fail với thông điệp của import-linter nêu rõ contract bị vi phạm.

## 3. Hook test uỷ quyền cho endpoint PII (chuẩn bị NFR-001)

Script `tools/check_authz_tests.py`: đọc `api/QLKH/openapi.yaml`, lấy mọi operationId của path trả PII (students, parents, grades, attendance, materials, consents), đối chiếu với tên test trong `tests/authz/`. Thiếu test → exit 1.
Giai đoạn QLKH-001 chưa có endpoint hiện thực nên job chạy ở chế độ cảnh báo (`continue-on-error: true`), bật chặn cứng ở ticket đầu tiên thêm endpoint PII.

## 4. Workflow CI (GitHub Actions)

Job chạy song song, tất cả là required check; không có đường bỏ qua.

| job | công cụ | điều kiện fail |
|---|---|---|
| lint | ruff, ruff format --check, mypy | bất kỳ lỗi nào |
| test | pytest + coverage | test đỏ hoặc branch coverage < 80% |
| fitness | lint-imports (import-linter) | vi phạm contract lớp/vòng |
| authz-gate | tools/check_authz_tests.py | endpoint PII thiếu test uỷ quyền (hiện warn) |
| sast | semgrep --config p/ci --config p/python --severity ERROR | có finding ERROR |
| sca | pip-audit / osv-scanner | có lỗ hổng HIGH hoặc CRITICAL |
| secrets | gitleaks detect --redact (full history: fetch-depth 0) | phát hiện secret |
| iac | checkov -d ./infra ; conftest test ./infra --policy ./policy | vi phạm policy (public-read, IAM *, cổng quản trị mở, không mã hóa at-rest) |
| license | syft + policy chặn GPL/AGPL/SSPL/BUSL | license bị cấm không có ADR ký |
| image-pin | grep chặn `FROM ...:latest` trong Dockerfile | có tag latest |
| sbom | syft -o cyclonedx-json | không sinh được SBOM |

Artifact upload: `sbom.cdx.json`, báo cáo coverage, báo cáo SCA.

Ghi chú kỹ thuật: mọi bước dùng action ghim theo commit SHA, không dùng tag di động. Runner không lưu secret dài hạn; khi cần quyền cloud sẽ dùng OIDC workload identity (xem `secrets-management`).

## 5. Quy tắc build tái lập

- Lockfile (`uv.lock`) commit; CI cài bằng chế độ frozen, lệch lockfile là fail.
- Base image ghim theo digest: `FROM python:3.12-slim@sha256:<digest>`.
- Artifact build một lần, dùng lại qua các môi trường (xem `devops`).

## 6. Policy IaC (conftest, `policy/storage.rego` — trích yếu)

- Cấm bucket có ACL/policy công khai (`public-read`, `*` principal) — T-05, ADR-005.
- Cấm tài nguyên lưu PII không bật mã hóa at-rest — ADR-006.
- Cấm security group mở 0.0.0.0/0 tới cổng quản trị (22, 3389, 5432, 6379).
- Bắt buộc tag: `project`, `env`, `owner`, `cost-center`.
- Cấm tài nguyên đặt ngoài vùng Việt Nam khi có tag `data-class=pii` — ADR-006/T-13.

Policy đã có sẵn để mọi PR hạ tầng sau này bị chặn tự động, dù `infra/` hiện chưa có tài nguyên.

## 7. Chi phí và rollback

- Không tạo tài nguyên cloud: delta hạ tầng 0 USD/tháng. Chi phí duy nhất là phút CI, ước tính ~600 phút/tháng ≈ 5 USD.
- Không có `terraform plan` vì DEF-01 (nhà cung cấp) chưa quyết; ticket hạ tầng thật sẽ kèm plan và ước tính chi tiết.
- Rollback: revert PR; không có state từ xa bị thay đổi, không có tài nguyên cần hủy.

## 8. Việc còn mở

- Bật chặn cứng `authz-gate` khi endpoint PII đầu tiên xuất hiện (NFR-001).
- Ký artifact (Sigstore) và lưu provenance SLSA: làm ở ticket dựng pipeline phát hành.
- Khởi tạo backend state từ xa (khóa + mã hóa) sau khi DEF-01 chốt nhà cung cấp vùng VN.
