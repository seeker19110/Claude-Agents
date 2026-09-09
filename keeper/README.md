# keeper — công ty con bảo trì

Package thứ sáu của workspace X-Agents. Khách hàng số 0 và mặc định của nó là **chính repo này**.

**Trạng thái: chưa có một dòng mã.** Hiện chỉ có quyết định và đặc tả:

- Quyết định: [`docs/adr/0006-cong-ty-bao-tri-keeper.md`](../docs/adr/0006-cong-ty-bao-tri-keeper.md)
- Đặc tả triển khai, PR theo PR: [`docs/DAC-TA-KEEPER.md`](docs/DAC-TA-KEEPER.md) (BT0–BT8)

## Nó làm gì

Không viết lại Renovate / CodeQL / Scorecard — nó *tiêu thụ* đầu ra của chúng làm tín hiệu, rồi làm phần không
công cụ nào ngoài kia làm được: quyết định **cái gì đáng sửa, sửa theo luật của repo này, và chứng minh đã sửa**.

Sáu khối, tám agent, một human gate `keeper`:

| Khối | Agent |
|---|---|
| `watch` | `dependency-scout`, `health-monitor`, `drift-detector` |
| `triage` | `triager` |
| `engineering` | `patcher`, `refactorer` |
| `quality` | `regression-guard`, `security-auditor` |
| `release` | `release-clerk` |
| `supervisor` | `keeper-supervisor` |

## Bốn thứ khiến nó khác một chồng GitHub Action

1. **Bằng chứng đo hai chiều bắt buộc** — không có output *tắt bản sửa → đỏ / bật lại → xanh* thì ticket không
   rời pha quality. `AGENTS.md` bắt buộc §4 thành cổng máy.
2. **Bậc rủi ro tự động** — patch dev-dependency tự merge; chạm `xagents-core`/`agents/`/CI thì bắt buộc gate người.
3. **Ngân sách thay đổi** — trần PR mỗi tuần và đúng một PR mở, để chính công ty này không gây bão PR.
4. **Sổ nợ có đáo hạn** — mọi thứ hoãn đều mang ngày; quá hạn thì escalate.

## Chạy

Chưa chạy được. Sau BT1:

```bash
cd keeper && uv run pytest -q --cov
```
