import os
from celery import Celery

# Khởi tạo Celery Application sử dụng Redis làm Broker và Backend
app = Celery(
    'mep_celery',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

app.conf.update(
    task_serializer='json',
    accept_content=['json', 'pickle'],
    result_serializer='json',
    timezone='Asia/Ho_Chi_Minh',
    enable_utc=True,
    worker_concurrency=4,  # Default concurrency, can be overridden by worker startup
)

@app.task(bind=True)
def parse_cad_to_db_task(self, dwg_path: str, user_id: str):
    """
    Task phân tán: Bóc tách bản vẽ CAD nặng chuyển lên database.
    Được gọi qua `parse_cad_to_db_task.delay(dwg_path, user_id)`
    """
    import time
    # Import logic từ cad_geometry
    # from src.cad_geometry import detect_fittings
    time.sleep(2)  # Simulate heavy processing
    return {"status": "success", "file": dwg_path, "fittings_count": 120}
