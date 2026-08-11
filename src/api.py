import os
import shutil
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from celery.result import AsyncResult
from src.celery_app import app as celery_app, parse_cad_to_db_task
from src.workspace import get_project_root

app = FastAPI(
    title="MEP-Agents Cloud API",
    description="SaaS Backend for MEP-Agents Phase 3 (BIM & Cloud Era)",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/api/v1/task/{task_id}")
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'PENDING':
        return {"status": "Processing", "logs": ["Đang khởi tạo Swarm...", "Mechanical: Đang phân tích ống gió..."]}
    elif task_result.state != 'FAILURE':
        return {
            "status": "success",
            "logs": ["Phân tích hoàn tất", "Bảng BOQ đã sẵn sàng."],
            "result": task_result.result
        }
    else:
        return {"status": "error", "logs": [str(task_result.info)]}

@app.get("/api/v1/download/{task_id}")
def download_boq(task_id: str):
    # Trả về file Excel thật từ Celery result
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'SUCCESS':
        excel_path = task_result.result.get("excel_path")
        if excel_path and os.path.exists(excel_path):
            return FileResponse(excel_path, filename=f"Bao_Cao_BOQ_{task_id[:8]}.xlsx")
            
    return {"error": "File not found"}
