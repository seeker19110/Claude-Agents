# Khuôn thi hành — từ một đề bài tới mọi PR đã merge, người ra lệnh một lần

Ngày lập: 2026-09-08. Rút từ phiên làm `docs/KIEN-TRUC-4-LOP.md` (bản thi hành đầu tiên theo khuôn này).

Khuôn này tồn tại vì một chuỗi việc lớn (đặc tả → chi tiết → triển khai → chia subagent → thực thi) nếu làm rời
từng bước thì người phải ra lệnh năm lần và mỗi lần một cách hiểu khác. Ở đây **người ra lệnh một lần**
(`/thi-hanh <mã>`), phiên chính đi hết sáu giai đoạn, tự chia subagent, chạy tới khi mọi PR merge, và chỉ dừng
ở bốn trường hợp `AGENTS.md` §"Khi bối rối" cho phép.

## 1. Sáu giai đoạn và sản phẩm của mỗi giai đoạn

Mọi giai đoạn ghi vào **một file duy nhất** `docs/thi-hanh/<mã>.md` (mã: chữ thường + số, ví dụ `4l`, `k4`,
`s5`). Một file, năm phần A–E cố định. Không tách ba file — phiên 2026-09-08 tách ba file rồi phải gộp lại.

| # | Giai đoạn | Sản phẩm (phần trong file) | Điều kiện sang giai đoạn kế | Ai làm |
|---|---|---|---|---|
| 1 | **Đặc tả** — đề bài là gì, đo hiện trạng | **A. Hiện trạng**: kết luận ≤ 6 dòng; bảng đối chiếu *đề bài đòi gì · repo có gì · ở đâu (file:dòng)*, mỗi ô thiếu trỏ tới một mã việc | mọi ô có `file:dòng` hoặc "không có"; không ô nào là ấn tượng đọc mã | phiên chính + subagent `Explore` song song (một mỗi package/mảng, chỉ đọc) |
| 2 | **Đặc tả chi tiết** — làm gì, không làm gì | **B. Kế hoạch**: một bảng *mã · việc · lớp/mảng · hạng mục · mức C1/C2/C3 · ưu · nhược · khi nào*; danh sách "cố ý không làm" có lý do; dòng "rủi ro của chính file này" | mỗi việc gắn vào đúng một hạng mục (2–8 mã, một mảng), không hạng mục nào rỗng; không mở kế hoạch thứ hai | phiên chính |
| 3 | **Đặc tả triển khai** — từng việc làm thế nào | **C. Gói việc**: mỗi mã một khối 7 mục `docs/TASK-PACK.md`; mục 5 chứa khung code mức chữ ký hàm, mục 7 chứa ca test bắt buộc (có ca chiều ngược) + tiêu đề PR | mỗi gói tự đứng: subagent chỉ đọc gói đó + `AGENTS.md` là làm được | phiên chính (đọc code thật trước khi viết chữ ký — tránh ghi tên hàm không tồn tại, nhật ký 2026-09-07) |
| 4 | **Chia subagent** — ai, mức nào, song song hay tuần tự | **D. Điều phối**: bảng đợt *song song (phát triển) · thứ tự PR · điều kiện vào đợt*; quy tắc mức → model; `sc-*` nào chấm gói nào; khuôn giao việc | đồ thị phụ thuộc không vòng; mỗi đợt ≤ 3 gói song song; PR tuần tự | phiên chính |
| 5 | **Lệnh** — một dòng | **F. Lệnh thi hành** ghi cuối file: lệnh nguyên văn + điều kiện trước khi gõ; phiên soạn in lại mục F làm câu cuối cùng của nó | file A–D+F đã commit; người copy được một dòng | phiên chính viết, người gõ |
| 6 | **Thi hành** — tới xong | bảng B cột "khi nào" → `xong #n` cho mọi mã; A cập nhật ◐ → ✅; CHANGELOG + session log mỗi PR | mọi PR merge, CI xanh, không gói nào bị bỏ im lặng | phiên chính điều phối, subagent thực thi |

**F. Lệnh thi hành** (bắt buộc, cuối file): lệnh nguyên văn để thi hành chính file này, điều kiện trước khi gõ,
và lệnh biến thể (xem kế hoạch trước, chạy lại từ chỗ dở). Kế hoạch không có mục F là kế hoạch chưa lập xong —
người đọc xong phải copy được một dòng và gõ, không phải tự suy ra.

**E. Khuôn cho lần sau** (tuỳ chọn): nếu đề bài sẽ lặp lại cho đối tượng khác (công ty mới, package mới), phần E
là bảng nghiệm thu không phụ thuộc tên đối tượng.

## 2. Ba mức phức tạp → model, cố định cho mọi đề bài

| Mức | Nhận biết | Model · `effort` (`companies/software-company/docs/adr/0026-...`) | Ai kiểm lại |
|---|---|---|---|
| **C1 cơ học** | có mẫu, một file, sai thì CI bắt: tài liệu, điền yaml từ số đo, CHANGELOG, chạy lệnh CI dán output | Haiku 4.5, hoặc Sonnet 5 `low` | CI + phiên chính đọc diff |
| **C2 cục bộ** | một module, hợp đồng cho sẵn (chữ ký hàm, ca test): hàm thuần, nhánh parse, metrics, test đỏ theo khung | Sonnet 5 `medium` | test hai chiều + một `sc-*` |
| **C3 xuyên module** | đổi hành vi runtime, chạm ≥ 2 package, phải quyết điều gói chưa quyết, hoặc cần ADR | Opus 5 `high` (`xhigh` khi ADR) | test hai chiều + `sc-qa` + `sc-security`/`sc-builder` tuỳ vùng + phiên chính đọc toàn diff |

Trong một gói, phần *ghép vào runtime* là C3, phần *thuần / parse / test* là C2, phần *đo / điền / tài liệu* là C1.
Không hạ C3 (giá là một vòng PR đỏ), không nâng C1 (Opus viết CHANGELOG không tốt hơn Haiku).

## 3. Luật thi hành (giai đoạn 6)

1. **Phiên chính không code.** Nó tách gói → tiểu gói, giao subagent (`Agent` với `model` theo mức, mỗi subagent
   một `git worktree`), gom kết quả, chạy lại lệnh CI trong worktree (báo cáo subagent là lời khai — luật cấm 8),
   commit, mở PR, bật auto-merge, theo dõi CI, ghi CHANGELOG + session log, cập nhật bảng B.
2. **Một nhánh cho cả hạng mục, PR mở tuần tự giữa các hạng mục** (`QUY-TRINH-GIT.md` §2d, ADR-0012): mọi mã của
   một hạng mục dùng chung một nhánh, mỗi mã một commit; mở PR **nháp** ngay sau mã đầu tiên của hạng mục (CI
   chạy thật trên nháp), `gh pr ready` + bật auto-merge khi mọi mã của hạng mục `xong`. Hạng mục kế chỉ mở PR
   (kể cả nháp) sau khi PR hạng mục trước merge và nhánh đã `rebase origin/main` (luật 2c/2b) — song song là
   song song **phát triển** trên worktree riêng, không song song **mở PR**.
3. **Thứ tự trong một mã cố định**: test đỏ (dán output) → code → test xanh + lệnh CI (dán output) → `sc-*` chấm
   (C3 chấm ngay khi mã đó xong; C1/C2 chấm một lượt cuối hạng mục) → phiên chính đọc diff → commit + push vào
   nhánh hạng mục. Subagent không bỏ ca test trong khung; muốn bỏ phải nêu lý do.
4. **Idempotent.** Chạy lại `/thi-hanh <mã>` bất kỳ lúc nào: đọc bảng B, bỏ qua mã đã `xong #n`, tiếp từ gói dở.
   Trạng thái sống trong file, không trong đầu phiên (khuôn 2 `TRAPS.md`).
5. **Dừng chỉ khi**: thao tác không đảo ngược ngoài PR thường (xoá dữ liệu, đổi lịch sử git); việc nhạy cảm bảo
   mật; kế hoạch hỏng tới mức mọi hướng là đoán (ví dụ test đỏ ba lần liên tiếp với ba cách sửa khác nhau); gói
   cần **người** (máy có key, ký gate). Khi dừng: ghi rõ trong bảng B cột "khi nào" là `chờ người: <lý do>` và
   session log, rồi tiếp gói khác không phụ thuộc. Không hỏi "tiếp không?".
6. **Mỗi PR một hạng mục** (không phải một mã), tiêu đề `<type>(<scope>): <hạng mục> — <một câu>`, scope một từ.
   Trần một hạng mục: **≤ 8 mã, ≤ 2 package** — vượt là hai hạng mục, không phải một PR to hơn. Mã nào chạm
   `agents/`/`skills/` đi đủ 7 bước `CONTRIBUTING.md` §3 — không có ngoại lệ vì "đang thi hành tự động". Mã giữa
   hạng mục lòi ra kiến trúc sai (luật bắt buộc 6: vá 3 lần lòi vấn đề mới ⇒ dừng hỏi người): các mã đã `xong`
   trước đó trong hạng mục vẫn `ready` + merge nếu tự đứng được; mã hỏng tách sang hạng mục mới trong bảng B,
   không giam cả hạng mục chờ một mã không giải quyết được.
7. **Xong** = mọi mã trong B `xong #n`, mọi PR merge, `make test` gốc xanh, session log có mục kết. Phiên chính
   in bảng B cuối cùng. Không tuyên bố xong khi còn `chờ người`.

## 4. Khuôn giao việc cho subagent (phiên chính dán nguyên)

```
Bạn là subagent thực thi tiểu gói <mã.y> của X-Agents. Worktree <đường dẫn>, nhánh <tên>. Đọc AGENTS.md trước.
Task pack dưới đây là toàn bộ phạm vi — không làm ngoài, không "sửa cạnh bên".
<khối 7 mục của gói ở phần C, chỉ phần liên quan tiểu gói>
Làm: (1) viết test theo khung, chạy, dán output ĐỎ; (2) code; (3) chạy lại, dán output XANH; (4) chạy lệnh CI
package, dán output; (5) báo cáo ≤ 20 dòng: file đổi, ca test, số đo, điều chưa chắc. Không commit, không push.
```

Subagent `Explore` (giai đoạn 1) nhận: mảng cần khảo sát, danh sách câu hỏi đánh số, yêu cầu "trả lời kèm
`file:dòng`, factual, không suy đoán". Trợ lý `sc-*` (chấm) nhận: đường dẫn diff hoặc worktree + gói việc.

## 5. Khung file `docs/thi-hanh/<mã>.md`

```markdown
# <Tên đề bài> — hiện trạng, kế hoạch, gói việc
Ngày lập · căn cứ `main@<sha>` (#<PR>) · một dòng nói file này dùng cho ai, đọc khi nào.

## A. Hiện trạng
### A1. Kết luận (≤ 6 dòng)      ### A2. Bảng đối chiếu (… · ở đâu · mã việc)
## B. Kế hoạch — một bảng (mã · việc · mảng · hạng mục · mức · ưu · nhược · khi nào) + cố ý không làm + rủi ro của file
## C. Gói việc (mỗi mã 7 mục; mục 5 khung code, mục 7 ca test + tiêu đề PR)
## D. Điều phối (bảng đợt; mức → model; sc-* chấm; khuôn giao việc = §4 file này, chỉ tham chiếu)
## E. Khuôn cho lần sau (tuỳ chọn)
## F. Lệnh thi hành
    /thi-hanh <mã>                        # thi hành tới xong (idempotent, chạy lại tiếp từ chỗ dở)
    /thi-hanh <mã> --dung-sau-ke-hoach    # chỉ in bảng B rồi dừng
    Trước khi gõ: <nhánh chứa file này đã merge main? cần gh CLI / key ở đâu? gói nào sẽ "chờ người">
```

Ví dụ thật, đầy đủ: `docs/KIEN-TRUC-4-LOP.md` (đề bài "áp dụng đặc tả bốn lớp LLM", mã `4L`).

## 6. Vì sao khuôn có hình này (để không "cải tiến" nhầm)

- Một file thay ba: ba file cùng nói tám việc từ ba góc, sửa một chỗ là lệch hai chỗ (bệnh #168 ở quy mô nhỏ).
- Bảng B vừa là kế hoạch vừa là bảng theo dõi: không có bảng thứ hai để trôi.
- Mức C1/C2/C3 gắn theo *hình dạng việc*, không theo *tên gói*: một gói có cả ba mức, giao đúng phần cho đúng model.
- Dừng chỉ ở bốn trường hợp và ghi vào file: "hỏi tiếp không?" là cách phiên tự cho phép mình không làm.
- Idempotent qua file: phiên bị cắt (context, quota, máy tắt) chạy lại không làm lại việc đã xong — khuôn 4
  `TRAPS.md` (event cũ phát lại như mới) áp cho chính quy trình này.
