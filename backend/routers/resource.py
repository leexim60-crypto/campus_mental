"""成员C：心理资源库"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import MentalResource
from schemas import ApiResponse, err, ok

router = APIRouter(prefix="/api/v1")


@router.get("/resource/list", response_model=ApiResponse)
def resource_list(
    type: Optional[str] = Query(None, pattern="^(article|audio)$"),
    page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = db.query(MentalResource)
    if type:
        query = query.filter(MentalResource.type == type)
    total = query.count()
    items = query.order_by(MentalResource.create_time.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"total": total, "list": [{
        "id": r.id, "title": r.title, "type": r.type,
        "content": r.content, "url": r.url,
        "create_time": r.create_time.strftime("%Y-%m-%d"),
    } for r in items]}, "获取成功")


@router.get("/resource/detail", response_model=ApiResponse)
def resource_detail(id: int = Query(...), db: Session = Depends(get_db)):
    r = db.query(MentalResource).filter(MentalResource.id == id).first()
    if not r:
        return err(400, "资源不存在")
    return ok({
        "id": r.id, "title": r.title, "type": r.type,
        "content": r.content, "url": r.url,
        "create_time": r.create_time.strftime("%Y-%m-%d"),
    }, "获取成功")
