# Backlog tính năng MEPF (chưa triển khai)

Ghi lại các đề xuất tối ưu đã thảo luận nhưng **chưa** đưa vào vòng triển khai hiện tại
(vòng hiện tại: 4 tool HVAC + 4 tool Cấp thoát nước, xem `src/hvac_tools.py` /
`src/plumb_tools.py`). Giữ danh sách này để không thất lạc, ưu tiên xử lý ở các đợt sau.

## HVAC (Cơ khí)
- [ ] **Kiểm tra tiếng ồn (NC level)** cho miệng gió/quạt — chưa có tool, cần cho phòng
  yêu cầu yên tĩnh (phòng họp, phòng ngủ, studio...).

## Điện
- [x] ~~**Kiểm tra sụt áp (voltage drop)** theo chiều dài cáp~~ — đã làm:
  `src/elec_tools.py` → `calc_voltage_drop`, và `calc_cable_size` nay nhận `length_m`,
  tự tăng tiết diện tới khi %sụt áp nằm trong giới hạn TCVN 9206 (3% chiếu sáng / 5%
  động lực). Không có `length_m` thì tool cảnh báo rõ là CHƯA kiểm tra sụt áp.
- [ ] **Chống sét & tiếp địa** (lightning protection / grounding) — chưa có tool nào dù
  đây là hạng mục phổ biến trong scope Điện MEPF.
- [ ] **Tổng hợp phụ tải & hệ số đồng thời** để chọn máy biến áp/máy phát.
- [ ] **Dòng ngắn mạch & phối hợp bảo vệ** (short-circuit + selectivity giữa các cấp
  aptomat).
- [ ] **Xuất bảng tủ điện / sơ đồ nguyên lý** (panel schedule / single-line diagram).
- [ ] **Tính máng cáp / ống luồn dây** (cable tray & conduit sizing).

## PCCC
- [ ] **Tính thủy lực mạng đầu phun sprinkler** (pressure/flow tại từng đầu phun theo
  mạng đường ống) — hiện `calc_sprinkler_qty` chỉ ước tính theo diện tích bao phủ, chưa
  phải tính thủy lực thật.
- [ ] **Họng nước vách tường / standpipe**.
- [x] ~~**Cột áp bơm PCCC (H)**~~ — đã làm: `calc_fire_pump` nay tính H = cột áp hình học
  + tổn thất ma sát + tổn thất cục bộ + áp yêu cầu tại điểm bất lợi nhất (0.5 bar đầu
  phun theo TCVN 7336 / 2.0 bar họng vách tường theo TCVN 3890), trả về cả Q (m3/h) và H (m).
- [ ] **Quạt tăng áp / hút khói theo QCVN 06** — có thể tái dùng `calc_ventilation_rate`
  nhưng cần logic riêng theo quy chuẩn PCCC (áp suất dương cầu thang, tốc độ hút khói...).
- [ ] **Số lượng đầu báo khói/nhiệt** (fire alarm detector spacing).

## QS (Lập dự toán)
- [x] ~~**CSDL đơn giá vật tư/nhân công + tool tính giá trị dự toán**~~ — đã làm:
  `data/unit_prices.csv` (tra theo từ khóa, có VT/NC/máy) + `src/qs_tools.py` →
  `lookup_unit_price`, `calc_boq_cost` (đọc thẳng Excel khối lượng của
  `auto_quantity_takeoff`, nhân khối lượng × đơn giá, xuất bảng dự toán 2 sheet theo cấu
  trúc Thông tư 11/2021/TT-BXD: trực tiếp → chung → TNCTTT → VAT → tổng). Hạng mục thiếu
  đơn giá được đánh dấu "CHƯA CÓ ĐƠN GIÁ" thay vì bỏ qua âm thầm.
- [ ] **Xuất BOQ theo mẫu chuẩn Việt Nam** (định dạng bảng tổng hợp khối lượng quen
  thuộc với hồ sơ thầu).
- [x] ~~Bóc khối lượng bằng 1 tool duy nhất, thuần toán học (không phụ thuộc LLM tự đếm
  /soạn JSON)~~ — đã làm: `src/tools.py` → `auto_quantity_takeoff` (đọc CAD, đếm Block,
  cộng chiều dài theo Layer, liên kết ghi chú không gian, ghi Excel — 1 lần gọi). Mục
  tiêu: để model AI yếu/chạy offline (Ollama) vẫn bóc khối lượng đúng, vì gánh nặng suy
  luận đã chuyển hết sang code Python xác định (deterministic), LLM chỉ cần gọi đúng tool.

## BIM
- [x] ~~**Clash detection**~~ — đã làm: `src/bim_tools.py` → `detect_clashes` (phân loại
  hệ theo tên Layer, tìm giao điểm đoạn thẳng 2D giữa HAI hệ khác nhau, xuất Excel tọa độ
  xung đột). Thuần hình học, không cần LLM. Giới hạn trung thực: chỉ xét mặt bằng 2D nên
  báo cáo luôn nhắc phải đối chiếu cao độ trước khi kết luận.

## Tối ưu bản vẽ CAD
- [x] ~~Tool tối ưu/dọn dẹp bản vẽ tự động, thuần hình học (không cần LLM suy luận)~~ —
  đã làm: `src/tools.py` → `optimize_cad_drawing` (audit, xóa rác vẽ chiều dài 0, xóa
  Block trùng lặp cùng tên+vị trí, xóa Layer rỗng). Gọi được bởi CAD/BIM Agent chỉ bằng
  1 lần gọi tool, phù hợp model AI yếu/offline.

## Khác (cross-cutting)
- [ ] Mở rộng CSDL tiêu chuẩn cho RAG — hiện `data/standards/` chỉ có 2 file mẫu
  (`ashrae_hvac.txt`, `tcvn_mau.txt`), tra cứu tiêu chuẩn còn rất mỏng.
- [x] ~~Cho phép `search_standards` hoạt động khi KHÔNG có `OPENAI_API_KEY` (offline hoàn
  toàn)~~ — đã làm: `src/tools.py` → `_offline_keyword_search` tự động được dùng làm
  fallback (so khớp từ khóa Jaccard trên toàn bộ `data/standards/*.txt`, không cần
  internet/API key nào) khi chưa cấu hình OpenAI hoặc chưa `ingest` FAISS. Xem
  `AI_MODEL_SETUP.md` mục "Chế độ Offline hoàn toàn".
- [ ] Theo dõi phiên bản/revision bản vẽ CAD giữa các lần chỉnh sửa.
- [x] ~~Tách tool schema theo từng vai trò để giảm token mỗi lượt gọi LLM~~ — đã làm
  (`src/tools.py` → `TOOLS_BY_ROLE`/`get_tools_for_role`), xem `AI_MODEL_SETUP.md` §6.
- [ ] **Prompt caching (Anthropic)** — cache system prompt lặp lại giữa các lượt hội
  thoại để giảm ~90% chi phí phần được cache. Cần tích hợp riêng cho provider Anthropic
  (không áp dụng chung được qua lớp trừu tượng đa provider hiện tại).
- [ ] **Tool search (Anthropic beta)** — chỉ nạp schema tool khi cần thay vì nạp hết
  ngay từ đầu, giảm thêm token cho các vai trò còn nhiều tool (Mechanical, Plumbing,
  CAD). Cũng đặc thù Anthropic API.

## Đã xử lý ở đợt nâng cấp nền tảng
- [x] ~~Vòng lặp Reviewer auto-pass~~ — `retry_count` trong `AgentState` + hạn mức
  `MAX_REVIEW_RETRIES`: mọi lần thử đều được kiểm duyệt thật, chạm trần thì dừng kèm
  cảnh báo "CHƯA ĐẠT" (trước đây lần sửa thứ hai luôn được auto-pass mà không ai xem).
- [x] ~~Chặn "trả lời suông" bằng blacklist chuỗi tiếng Việt~~ — thay bằng kiểm tra
  CẤU TRÚC: nhiệm vụ đòi file sản phẩm mà cả luồng chưa gọi tool tạo file nào thì REJECT.
- [x] ~~Supervisor chỉ nhìn `messages[-1]`~~ — nay nhận tóm tắt diễn biến + danh sách bộ
  phận đã chạy, nên mới thực hiện được kịch bản nhiều bước (electrical → qs).
- [x] ~~`sender` không khớp tên node~~ — `sender` từng là 'mechanicalagent' trong khi
  graph so khớp 'mechanical', khiến kết quả tool không quay về đúng agent và mọi lần
  TỪ CHỐI đều rơi về 'qs'. Đã chuẩn hóa bằng `agent_node_key`.
- [x] ~~Mất lịch sử hội thoại khi restart~~ — checkpoint SQLite (`CHECKPOINT_DB`), tự
  rơi về RAM nếu môi trường không hỗ trợ.
- [x] ~~Token hiển thị là số bịa `len(text)/4`~~ — `src/usage.py` đọc `usage_metadata`
  thật của nhà cung cấp, tách theo vai trò, kèm ước tính chi phí USD.
