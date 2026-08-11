import os
import shutil
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from src.celery_app import parse_cad_to_db_task
from src.workspace import get_project_root

app = FastAPI(
    title="MEP-Agents Cloud API",
    description="SaaS Backend for MEP-Agents Phase 3 (BIM & Cloud Era)",
    version="3.0.0"
)

UPLOAD_DIR = os.path.join(get_project_root(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class TaskResponse(BaseModel):
    task_id: str
    message: str

@app.get("/")
def root():
    return {"status": "ok", "message": "Welcome to MEP-Agents Cloud API v3.0"}

@app.post("/api/v1/takeoff", response_model=TaskResponse)
async def upload_and_takeoff(file: UploadFile = File(...)):
    """
    Nhận file CAD (.dwg/.dxf) từ Client (Web App), lưu trữ và đẩy vào hàng đợi Celery (Redis)
    để xử lý phân tán, trả về Task ID cho client theo dõi tiến độ (Real-time).
    """
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Gửi sang Celery Queue (Distributed Processing)
    task = parse_cad_to_db_task.delay(file_path, user_id="web_client")
    
    return TaskResponse(
        task_id=task.id,
        message=f"File {file.filename} đã được đưa vào hàng đợi xử lý phân tán. Dùng task_id để theo dõi."
    )
