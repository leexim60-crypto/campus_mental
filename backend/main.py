from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import CORS_ORIGINS
from database import get_db
from schemas import ok
from seed import run_startup
from routers import user, admin, resource, appointment, ai


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup()
    yield


app = FastAPI(
    title="校园心理健康智能评估与干预平台 API",
    version="1.2.0",
    lifespan=lifespan,
)

_origins = CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"]
_credentials = False if _origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──────────────────────────────────────────────
app.include_router(user.router)        # 成员A：学生账号 + 测评
app.include_router(admin.router)       # 成员B：管理员 + 统计
app.include_router(resource.router)    # 成员C：资源库
app.include_router(appointment.router) # 成员C：预约
app.include_router(ai.router)          # 成员C：心灵树洞


# ── 系统路由 ──────────────────────────────────────────────

@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "time": datetime.now().isoformat(),
    }


@app.get("/")
def root():
    return {"message": "校园心理健康智能评估与预防系统 API 运行中", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
