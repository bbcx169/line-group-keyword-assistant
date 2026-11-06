from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import auth_router, keywords, upload, webhook

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """應用程式啟動時確保資料表存在（搭配 Alembic 遷移相容）"""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="LINE 群組關鍵字助手 API",
    description="自動化處理 LINE 群組常見問題的關鍵字助手，整合 FastAPI、PostgreSQL、Cloudinary 與 CSV 批次管理。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載各功能路由
app.include_router(webhook.router)
app.include_router(auth_router.router)
app.include_router(keywords.router)
app.include_router(upload.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health", tags=["System"], summary="系統健康檢查")
def health_check():
    return {"status": "healthy", "service": "line-keyword-assistant"}


@app.get("/", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def serve_admin_panel():
    """提供後台管理單頁式介面"""
    return FileResponse(STATIC_DIR / "index.html")
