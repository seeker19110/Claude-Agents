# Backlog tính năng MEPF

> **Trạng thái: đã xử lý hết.** Toàn bộ các mục từng ghi nhận trong backlog nay đã được
> triển khai (xem dấu ~~gạch ngang~~ kèm tên tool/file tương ứng). Giữ lại lịch sử này để
> tra cứu tính năng nào nằm ở đâu; thêm mục mới vào đúng nhóm hệ khi phát sinh nhu cầu.

## HVAC (Cơ khí)
- [x] ~~**Kiểm tra tiếng ồn (NC level)**~~ — đã làm: `src/hvac_tools.py` → `calc_nc_level`
  (Lw -> Lp theo thể tích phòng/khoảng cách, cộng nhiều nguồn, trừ tiêu âm, đối chiếu NC
  khuyến nghị theo loại phòng của ASHRAE, kèm biện pháp giảm ồn khi không đạt).

## Điện
- [x] ~~**Kiểm tra sụt áp (voltage drop)** theo chiều dài cáp~~ — đã làm:
  `src/elec_tools.py` → `calc_voltage_drop`, và `calc_cable_size` nay nhận `length_m`,
  tự tăng tiết diện tới khi %sụt áp nằm trong giới hạn TCVN 9206 (3% chiếu sáng / 5%
  động lực). Không có `length_m` thì tool cảnh báo rõ là CHƯA kiểm tra sụt áp.
- [x] ~~**Chống sét & tiếp địa**~~ — đã làm: `calc_lightning_protection` (bán kính bảo vệ
  kim thu sét theo quả cầu lăn TCVN 9385/IEC 62305, số cọc tiếp địa theo điện trở suất đất
  bằng công thức Dwight, có hệ số sử dụng khi ghép cọc).
- [x] ~~**Tổng hợp phụ tải & hệ số đồng thời**~~ — đã làm: `calc_total_load` (hệ số đồng
  thời theo loại phụ tải TCVN 9206, ra công suất tính toán, chọn máy biến áp theo gam chuẩn
  và ước lượng máy phát dự phòng).
- [x] ~~**Dòng ngắn mạch & phối hợp bảo vệ**~~ — đã làm: `calc_short_circuit` (Isc tại
  thanh cái theo Uk% máy biến áp, Isc suy giảm ở cuối tuyến theo tổng trở cáp, chọn Icu và
  nêu quy tắc phối hợp bảo vệ giữa các cấp aptomat).
- [x] ~~**Xuất bảng tủ điện / sơ đồ nguyên lý**~~ — đã làm: `src/panel_schedule.py` →
  `generate_panel_schedule` (tự tính dòng/aptomat/cáp có kiểm tra sụt áp cho từng lộ, xuất
  Excel bảng tủ 2 sheet và vẽ file DXF sơ đồ nguyên lý một sợi mở được bằng AutoCAD).
- [x] ~~**Tính máng cáp / ống luồn dây**~~ — đã làm: `calc_cable_tray_size` (tổng tiết diện
  cáp + dự phòng, chia hệ số điền đầy, chọn máng theo gam chuẩn hoặc ống luồn dây tương
  đương).

## PCCC
- [x] ~~**Tính thủy lực mạng đầu phun sprinkler**~~ — đã làm: `calc_sprinkler_hydraulics`
  (duyệt từ đầu phun bất lợi nhất về nguồn, q = K√P cho từng đầu, tổn thất Hazen-Williams
  giữa các đoạn, đối chiếu cường độ phun TCVN 7336 — tổng lưu lượng thật lớn hơn phép nhân
  đơn giản số đầu × lưu lượng một đầu).
- [x] ~~**Họng nước vách tường / standpipe**~~ — đã làm: `calc_standpipe` (lưu lượng theo
  số họng hoạt động đồng thời, cỡ ống đứng theo vận tốc cho phép, cột áp yêu cầu, cảnh báo
  chia vùng áp lực cho nhà trên 10 tầng).
- [x] ~~**Cột áp bơm PCCC (H)**~~ — đã làm: `calc_fire_pump` nay tính H = cột áp hình học
  + tổn thất ma sát + tổn thất cục bộ + áp yêu cầu tại điểm bất lợi nhất (0.5 bar đầu
  phun theo TCVN 7336 / 2.0 bar họng vách tường theo TCVN 3890), trả về cả Q (m3/h) và H (m).
- [x] ~~**Quạt tăng áp / hút khói theo QCVN 06**~~ — đã làm: `calc_smoke_control` (tăng áp
  buồng thang theo số cửa mở + rò rỉ khe cửa, giới hạn chênh áp 50 Pa và van xả áp; hút khói
  theo bội số trao đổi, tiết diện ống và lưu lượng gió bù tối thiểu).
- [x] ~~**Số lượng đầu báo khói/nhiệt**~~ — đã làm: `calc_fire_detector_qty` (diện tích bảo
  vệ và khoảng cách theo chiều cao trần TCVN 5738, phân biệt đầu báo khói/nhiệt, cảnh báo
  trần trên 12 m phải dùng đầu báo hút hoặc beam).

## QS (Lập dự toán)
- [x] ~~**CSDL đơn giá vật tư/nhân công + tool tính giá trị dự toán**~~ — đã làm:
  `data/unit_prices.csv` (tra theo từ khóa, có VT/NC/máy) + `src/qs_tools.py` →
  `lookup_unit_price`, `calc_boq_cost` (đọc thẳng Excel khối lượng của
  `auto_quantity_takeoff`, nhân khối lượng × đơn giá, xuất bảng dự toán 2 sheet theo cấu
  trúc Thông tư 11/2021/TT-BXD: trực tiếp → chung → TNCTTT → VAT → tổng). Hạng mục thiếu
  đơn giá được đánh dấu "CHƯA CÓ ĐƠN GIÁ" thay vì bỏ qua âm thầm.
- [x] ~~**Xuất BOQ theo mẫu chuẩn Việt Nam**~~ — đã làm: `src/qs_tools.py` →
  `export_boq_vietnam` (gom hạng mục theo chương mục A/B/C/D theo hệ, đánh số theo chương,
  cộng tiểu tổng từng chương và tổng cộng, kèm sheet trang bìa công trình).
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
- [x] ~~Mở rộng CSDL tiêu chuẩn cho RAG~~ — đã làm: thêm `tcvn_dien.txt` (TCVN 9206 sụt áp,
  hệ số đồng thời, ngắn mạch, máng cáp; TCVN 9385 chống sét & tiếp địa), `tcvn_pccc.txt`
  (TCVN 7336 sprinkler, TCVN 3890 họng nước & bơm, TCVN 5738 báo cháy, QCVN 06 kiểm soát
  khói), `tcvn_cap_thoat_nuoc.txt` (TCVN 4513 cấp nước, TCVN 4474 thoát nước) và
  `ashrae_tieng_on_hvac.txt` (NC level). Kho tiêu chuẩn phủ đủ 4 hệ.
- [x] ~~Cho phép `search_standards` hoạt động khi KHÔNG có `OPENAI_API_KEY` (offline hoàn
  toàn)~~ — đã làm: `src/tools.py` → `_offline_keyword_search` tự động được dùng làm
  fallback (so khớp từ khóa Jaccard trên toàn bộ `data/standards/*.txt`, không cần
  internet/API key nào) khi chưa cấu hình OpenAI hoặc chưa `ingest` FAISS. Xem
  `AI_MODEL_SETUP.md` mục "Chế độ Offline hoàn toàn".
- [x] ~~Theo dõi phiên bản/revision bản vẽ CAD~~ — đã làm: `src/cad_revision.py`
  (`snapshot_cad`, `list_cad_revisions`, `diff_cad_revisions`, `restore_cad_revision`).
  `edit_cad` / `optimize_cad_drawing` / `ai_block_recovery` tự chụp bản vẽ TRƯỚC khi ghi đè,
  nên một lần AI sửa sai không còn làm mất bản gốc; diff so sánh số Block, chiều dài theo
  Layer và danh sách Layer.
- [x] ~~Tách tool schema theo từng vai trò để giảm token mỗi lượt gọi LLM~~ — đã làm
  (`src/tools.py` → `TOOLS_BY_ROLE`/`get_tools_for_role`), xem `AI_MODEL_SETUP.md` §6.
- [x] ~~**Prompt caching (Anthropic)**~~ — đã làm: `src/agents.py` → `build_system_message`
  đánh dấu `cache_control` lên phần system prompt CỐ ĐỊNH và tách cảnh báo lỗi của Reviewer
  (thay đổi mỗi lượt) thành block riêng đứng sau, vì cache là so khớp theo prefix. Chỉ bật
  khi provider là Anthropic và prompt đủ dài — prompt ngắn hơn ngưỡng sẽ không được cache
  mà cũng không báo lỗi, nên tránh tạo cảm giác tiết kiệm giả.
- [x] ~~**Tool search (Anthropic beta)**~~ — đã làm: `src/agents.py` → `build_tools_for_llm`
  chuyển tool nghiệp vụ sang schema `defer_loading=True` và thêm `tool_search_tool_regex`.
  MẶC ĐỊNH TẮT (bật bằng `ANTHROPIC_TOOL_SEARCH=true`): đây là beta đặc thù Anthropic, chưa
  kiểm chứng được với API key thật, và chỉ đáng dùng khi vai trò còn nhiều tool.

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
