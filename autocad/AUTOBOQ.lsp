(defun c:AUTOBOQ ()
  (princ "\nĐang kích hoạt MEP-Agents Swarm AI...")
  
  ;; Chạy script Python qua shell
  ;; Giả định đang dùng uv run để chạy môi trường ảo
  (command "start" "uv" "run" "python" "C:\\Users\\liend\\MEP-Agents\\autocad\\autoboq.py")
  
  (princ "\nĐã gửi dữ liệu bản vẽ hiện tại lên Máy chủ AI (FastAPI). Vui lòng xem kết quả trên Web!")
  (princ)
)
