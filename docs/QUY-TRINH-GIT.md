# Quy trình làm việc với Git — X-Agents

Áp từ quy trình của dự án `donghanh` (`CONTRIBUTING.md`, `docs/DEVELOPMENT_WORKFLOW.md`,
`CLAUDE.md` mục 11), rút gọn cho repo này: repo tài liệu + Python (`software-company/`),
làm việc chủ yếu một mình cùng AI, cổng chất lượng là `make lint` + `make test`.

Luồng chuẩn: **Ý tưởng → Đặc tả → Nhánh → PR → CI/Review → Merge (squash) → Quan sát**.

## 1. Cổng đặc tả (chỉ với thay đổi lớn)

Thay đổi kiến trúc, thêm/bỏ agent, đổi schema topic, đổi hợp đồng event → viết ADR trong
`<công ty>/docs/adr/` (ví dụ `software-company/docs/adr/`) **trước** khi code, và link ADR trong PR. Sửa lỗi nhỏ, chỉnh
prompt/skill, sửa tài liệu thì đi thẳng bước 2.

Không dùng "AI đề xuất" làm bằng chứng. Mọi khẳng định quan trọng phải truy được về code,
test, hoặc nguồn chính thống có ngày truy cập.

## 2. Nhánh

- Tách nhánh từ `main`, mỗi tính năng/sửa lỗi một nhánh.
- Đặt tên: `feat/<slug>`, `fix/<slug>`, `refactor/<slug>`, `perf/<slug>`, `docs/<slug>`,
  `chore/<slug>`. Có issue thì `feat/<issue>-<slug>`.
- **Không push thẳng `main`.** Mọi thay đổi vào `main` đều qua pull request, kể cả khi làm một mình.

## 2b. Nhiều phiên cùng lúc: mỗi phiên một worktree

Một clone chỉ có **một** HEAD. Hai phiên agent cùng mở `C:\Users\liend\Claude-Agents` là hai tiến trình
lần lượt `git checkout` đè lên nhau, và commit của phiên này rơi vào nhánh của phiên kia — không lệnh nào
báo lỗi.

Chuyện đã xảy ra ngày 2026-09-06, đọc được nguyên vẹn trong `git reflog` (cách nhau vài chục giây):

```
15:05:42 checkout: moving from fix/wip-head-is-pr to docs/danh-gia-superpowers...   ← phiên A tạo nhánh
15:06:23 commit: fix(company): HEAD là commit WIP...                                ← phiên B commit vào nhánh A
15:07:06 reset: moving to b95710d                                                   ← B gỡ, tạo nhánh riêng
15:07:14 checkout: moving from fix/wip-head-is-pr to main                           ← B chuyển sang main
15:07:16 commit: docs(company): đối chiếu superpowers...                            ← commit của A rơi vào main
```

Kết quả: nhánh của A rỗng (`gh pr create` báo *No commits between main and ...*), còn `main` local mang một
commit chưa qua PR. Phải `git branch -f` hai lần mới trả về đúng chỗ. Không có xung đột, không có cảnh báo —
chỉ có commit nằm sai nhánh.

**Quy tắc: phiên nào không phải phiên đầu tiên thì làm trong worktree riêng.**

```bash
git worktree add -b <loại>/<slug> ../Claude-Agents-wt-<slug> origin/main
```

Rồi `cd` vào đó và làm bình thường; `.venv` ở gốc vẫn dùng được qua `uv run`. Xong việc thì dọn:

```bash
git worktree remove ../Claude-Agents-wt-<slug>
```

Kiểm trước khi bắt đầu, mất hai giây:

```bash
git worktree list
```

Cách nhận ra mình đang giẫm chân người khác: `git status` hay `git log` cho ra một nhánh mà lượt này không hề
tạo, hoặc `git reflog` có `checkout` mình không gọi. Gặp thì dừng, **đừng commit**, mở worktree riêng trước.

Điều này áp cho **phiên người lái**. Orchestrator đã cô lập sẵn: mỗi ticket một worktree dưới `.worktrees/`
(`software-company/src/company/workspace.py`), và nó chạy trên repo của khách (`--repo`), không phải repo này.

## 2c. Nhiều phiên cùng lúc: chỉ một PR mở tại một thời điểm (áp toàn cục)

Nhiều phiên có thể **code song song** trên worktree riêng (§2b) như bình thường — quy tắc này chỉ khoá ở
bước **mở/merge PR**, để loại hoàn toàn xung đột nền do hai nhánh cùng lệch khỏi `main` một lúc.

- **Trước khi mở PR**: kiểm `gh pr list --state open`. Có PR khác đang mở (của phiên khác) → **không mở
  PR mới**. Tiếp tục code trên worktree của mình, chờ đến khi PR kia merge xong rồi mới mở.
- **Ngay khi PR trước merge xong, trước khi mở PR của mình**: `git fetch origin` rồi
  `git rebase origin/main` trên nhánh của mình (không merge `main` vào — rebase, giữ lịch sử thẳng).
  Giải conflict lúc rebase nếu có, chạy lại `make lint` + `make test` sau rebase (§4/§7 vẫn áp).
- Rồi mới `gh pr create` + bật auto-merge như thường (§5).
- Nếu rebase xung đột nhiều/phức tạp → dừng, báo người dùng, đừng tự ý bỏ qua bằng merge thường hay
  `--no-verify`.

Vì mỗi PR luôn được rebase lên `main` mới nhất *ngay trước khi mở*, và không có PR thứ hai nào mở song
song để đá vào cùng nền — nhánh không bao giờ diverge lâu, nên xung đột merge gần như bị loại bỏ. Cái giá
đánh đổi: bước mở PR trở thành hàng đợi tuần tự giữa các phiên — phiên nào xong sau phải đợi phiên xong
trước merge trước.

## 3. Commit

- Conventional Commits: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `style`, `perf`,
  `build`, `ci`, `revert`. Scope viết **chữ thường**: `feat(software-company): ...`.
- Một commit = một thay đổi logic. Commit nhỏ, thân bài nêu *vì sao*, không chỉ *cái gì*.

## 4. Cổng kiểm thử theo mức rủi ro

| Thay đổi | Bằng chứng tối thiểu |
| --- | --- |
| Tài liệu thuần (`*.md`, docs) | Đọc lại diff, `git diff --check` |
| Prompt agent / skill / template | `make test` (golden 21 agent bắt được thay đổi prompt) |
| Code `src/company/**` | `make lint` + `make test`, thêm test cho hành vi mới |
| Schema topic / hợp đồng event | Các cổng trên + ADR + kiểm test nhất quán registry↔events |
| Đổi cổng CI | Chạy thật trên PR đó rồi đọc thời gian từng job, không đoán |

Không commit secret, `llm.yaml`, khóa API, hay dữ liệu thật. Không gọi provider trả phí trong test.

## 5. Pull request — bốn bước làm liền một mạch

1. **Kiểm tiêu đề trước khi tạo PR.** Cổng `metadata` chặn tiêu đề sai:
   ```
   ^(feat|fix|refactor|docs|test|chore|style|perf|build|ci|revert)(\([a-z0-9._/-]+\))?!?: .+
   ```
   Bẫy: scope chỉ nhận chữ thường — `fix(skillTiering)` trượt, `fix(skills)` đạt.

   Cổng `metadata` còn ba bước nữa, đọc trước khi viết thân PR:
   - **Dòng CHANGELOG** ở mục "Chưa phát hành" (nhãn `no-changelog` để miễn) — đỏ nếu thiếu.
   - **PR `fix(` chạm `software-company/src/company/orchestrator.py` hoặc `orch/` phải dẫn `ADR-0034`**
     trong thân, nói rõ đụng bảng chuyển nào (K8.3). `refactor(` không bị soi: tách module là làm ĐÚNG
     theo ADR, còn `fix(` là sửa hành vi máy trạng thái — chỗ dễ lặng lẽ phá bảng chuyển nhất. Đặc tả
     gốc viết "ADR-0037"; repo này không có file đó, ADR tách máy trạng thái là **0034**.
   - **Nhật ký phiên `docs/sessions/<ngày UTC>.md`** — chỉ **cảnh báo**, không chặn merge (K8.4): nhật ký
     là việc cuối phiên, không phải việc mỗi PR.
2. **Tạo PR ở trạng thái ready, không để nháp.** GitHub từ chối bật auto-merge trên PR nháp.
3. **Bật auto-merge (squash) ngay sau lệnh tạo PR** — gọi một lần, không hỏi lại. Thất bại thì
   **không bỏ mặc PR**: theo dõi CI, **xanh + không xung đột là merge (squash) ngay**.

   **Nhịp theo dõi CI: kiểm mỗi 2,5 phút (150 giây) cho tới khi có kết luận.** Không kiểm liên
   tục (tốn lượt gọi API, không nhanh hơn vì job mất vài phút), cũng không bỏ đi rồi quay lại
   sau nửa tiếng. Lệnh một vòng kiểm:

   ```bash
   gh pr checks <số PR> --watch --interval 150
   ```

   Hoặc kiểm rời từng nhịp: `gh pr checks <số PR>`. Xanh hết → merge (squash) ngay. Có check đỏ
   → đọc log (`gh run view <id> --log-failed`), tái hiện lỗi ở máy, sửa, push, rồi lại theo nhịp
   2,5 phút. Đang `queued`/`in_progress` → chờ nhịp kế tiếp, không kết luận sớm.
4. **Chỉ gộp `main` khi thật sự cần**: GitHub báo xung đột, hoặc `main` vừa đổi thứ PR này cũng
   đụng (nguy cơ xung đột ngữ nghĩa). Không gộp theo phản xạ.

**Cấm merge tay để đi tắt khi CI chưa xanh.** Đó là điều duy nhất bị cấm ở bước merge.

PR là của người tạo: CI đỏ thì đọc log, tái hiện lỗi ở máy, sửa và push cho tới khi xanh —
không để PR nằm đỏ chờ người khác.

Merge sạch (không xung đột) thì **không** chạy lại toàn bộ cổng ở máy — CI đã chạy trên kết quả
đã gộp. Merge có xung đột, hoặc `main` chạm file PR cũng chạm → chạy lại đủ cổng ở máy.

## 6. Definition of Done

- Thay đổi khớp đặc tả/ADR; điểm lệch được ghi rõ.
- Test mới chứng minh hành vi; `make lint` và `make test` xanh.
- Đã tự đọc lại diff; chỉ gồm thay đổi thuộc phạm vi.
- Không secret, không debug log, không file sinh tự động lọt vào.
- Tài liệu (`README.md`, `docs/`, ADR) cập nhật theo thay đổi.
- Breaking change được gọi tên kèm cách chuyển đổi.

## 7. Merge và sau merge

- Mặc định **squash merge**; xoá nhánh sau khi merge.
- Sau merge, kiểm `main` còn xanh; hỏng thì ưu tiên revert rồi điều tra trong PR mới.
- Tag `vX.Y.Z` khi phát hành mốc (`version` trong `software-company/pyproject.toml`).

## 8. Việc cần bật trên GitHub (một lần) — và cách biết nó CÓ THẬT

Quy trình trên giả định `main` có bảo vệ nhánh. Cấu hình này **không nằm trong git**, nên trước đây "đã bật"
chỉ là lời hứa: PR #29 merge 23 giây sau khi mở, job `quality` xanh **3 phút sau khi đã merge**. Từ nay có hai lớp:

1. **Ruleset import được** — `.github/rulesets/main.json` là nguồn sự thật, đi qua PR như code.
   Bật: Settings → Rules → Rulesets → **New ruleset → Import a ruleset** → chọn file đó → Create.
   Nội dung: bắt buộc PR (**0 approval** — xem ô dưới, thread review phải resolve, chỉ **squash**) ·
   required status checks `quality` + `metadata` · cấm xoá và cấm force-push `main` ·
   **không ai được bypass, kể cả admin** (`bypass_actors` rỗng) · **tắt** "up to date" (`strict: false`) để PR khác
   merge không bắt mọi PR đang mở gộp `main` rồi chờ CI lại.
2. **Job `protection-guard` trong CI**, hai vế. `quality` cần nó xanh.
   - **Vế 1 — đã có hiệu lực chưa:** đọc rule đang áp lên nhánh mặc định qua API, **đỏ khi thiếu** bốn rule bất
     biến hoặc thiếu bất kỳ required status check nào **khai trong file**. Chưa import ruleset thì mọi PR đỏ —
     đó là chủ đích. Danh sách check đọc từ file chứ không hard-code, nên thêm/bớt check không cần sửa workflow.
   - **Vế 2 — file và ruleset thật có khớp không (đối chiếu hai chiều):**
     rule khai trong file mà **không** áp trên nhánh ⇒ **đỏ** (bảo vệ yếu hơn thứ repo khai);
     rule đang áp mà **không** có trong file ⇒ **cảnh báo** (không yếu đi, nhưng import lại sẽ xoá mất nó).

   > **Vì sao cần vế 2.** Sửa ruleset trong UI có thể **làm rơi một rule mà không báo gì**. Đã xảy ra thật ngày
   > 2026-09-05: lần đổi `required_approving_review_count` về 0 làm mất `copilot_code_review`, và guard bản cũ
   > **vẫn xanh** vì nó chỉ kiểm bốn rule bất biến. Kiểu trôi này không ai phát hiện cho tới khi cần đến rule đó.
   > *(Kết cục: sau khi guard chỉ ra, đã quyết định **không dùng** Copilot code review — nên file cũng bỏ luôn
   > rule đó cho khớp. Điều đáng giữ lại là bài học: mất một rule mà CI vẫn xanh là chuyện có thật.)*

Hai nút vẫn phải bật tay trong Settings → General (không thuộc ruleset): **Allow auto-merge** và
**Automatically delete head branches**.

### Vì sao `required_approving_review_count` = 0

> **Không phải hạ tiêu chuẩn — là ghi nhận thực tế.** Repo hiện có **đúng một cộng tác viên**. GitHub không cho
> tự duyệt PR của chính mình, và `bypass_actors` cố ý để rỗng, nên đặt 1 approval sẽ **khoá vĩnh viễn mọi PR**
> vào `main` — auto-merge bật cũng không kích hoạt. Lần đầu import với số 1 đã tạo đúng thế kẹt đó (PR #40).

Đặt 0 **vẫn chặn nguyên hai vấn đề** mà đường cơ sở đo được ngày 2026-09-04:

| Vấn đề đo được | Rule nào chặn |
|---|---|
| PR #29 merge sau 23 giây, `quality` xanh **3 phút sau khi merge** | `required_status_checks` |
| **35% commit** đẩy thẳng vào `main` | rule `pull_request` — nó bắt buộc phải qua PR; số approval chỉ là **một tham số** của rule đó |

Thứ mất đi là **four-eyes**, và four-eyes vốn không tồn tại khi chỉ có một người.

**Nâng lại lên 1 (hoặc 2) ngay khi có người thứ hai thật** trong repo — lúc đó nó mới có nghĩa. Cách đổi: sửa
`required_approving_review_count` trong file JSON qua PR **rồi import lại** (ruleset cùng tên sẽ được cập nhật).
Guard không kiểm số approval, chỉ kiểm **có** rule `pull_request` — nên đổi số không làm CI đỏ.

⚠️ **Thứ tự bắt buộc nếu lỡ khoá lại:** file JSON trong repo chỉ là bản nguồn để nhập; sửa nó cũng cần một PR,
mà PR thì đang bị khoá. Phải **sửa ruleset đang chạy trong Settings trước**, rồi mới sửa được file.

### File và ruleset thật phải khớp

File này được **đối chiếu với `GET /repos/:owner/:repo/rulesets/:id`** bằng máy, không viết theo trí nhớ.
Hai tham số GitHub tự thêm khi tạo ruleset mà bản viết tay ban đầu thiếu — nay đã bổ sung:
`required_reviewers` và `require_extra_approval_for_unattributed_changes` của rule `pull_request`.

**Bốn rule là đủ:** `deletion` · `non_fast_forward` · `pull_request` · `required_status_checks`.
`copilot_code_review` từng được GitHub thêm vào lúc tạo ruleset, nhưng **đã quyết định không dùng** (2026-09-05)
nên gỡ khỏi cả ruleset lẫn file. Muốn dùng lại thì thêm vào **cả hai chỗ** — thêm một chỗ thôi sẽ bị vế 2 của
`protection-guard` bắt.

🔍 **Điểm cần theo dõi:** `require_extra_approval_for_unattributed_changes = true` đòi **thêm một approval** khi PR
chứa thay đổi không gán được cho một tài khoản. Hiện không cắn: commit trên nhánh này gán đúng vào tài khoản
`claude` (kiểm bằng trường `author.login` của API commit). Nhưng nếu sau khi hạ approval về 0 mà PR **vẫn**
`blocked` dù mọi check xanh, hãy nghi tham số này trước tiên — nhất là khi người mở PR và người tạo commit là
hai tài khoản khác nhau.
