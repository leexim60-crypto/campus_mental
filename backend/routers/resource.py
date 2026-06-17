"""成员C：心理资源库"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import MentalResource
from schemas import ApiResponse, err, ok

router = APIRouter(prefix="/api/v1")

# 【分页获取心理健康资源列表】的接口，具备严格的参数校验与动态查询机制：
@router.get("/resource/list", response_model=ApiResponse)
def resource_list(
    type: Optional[str] = Query(None, pattern="^(article|audio)$"),
    page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    # 1. 类型安全过滤：通过正则表达式严格限制 type 参数，仅允许查询 article（文章）或 audio（音频），防止非法参数注入。
    # 2. 安全分页机制：强制校验分页参数（page 最小为 1，size 限制在 1~50 之间），防止恶意请求拉取过多数据导致数据库崩溃。
    # 3. 动态条件构建：若未传 type 则查询全部资源；若传了则追加过滤条件。
    # 4. 总数与列表分离查询：先执行 count() 获取符合条件的总条数（供前端计算总页数），再使用 offset 和 limit 获取当前页数据。
    # 5. 时间倒序与格式化：结果按创建时间倒序排列，确保最新发布的资源在最前面，并将时间格式化为标准的 YYYY-MM-DD 格式。
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


# 这是一个【获取心理健康资源详情】的接口，核心逻辑如下：
@router.get("/resource/detail", response_model=ApiResponse)
def resource_detail(id: int = Query(...), db: Session = Depends(get_db)):
    # 1. 参数获取：通过 Query 接收必填的资源 ID 参数。
    # 2. 存在性校验：根据 ID 在数据库中查询 MentalResource 表，若未找到对应记录，直接返回 400 错误提示“资源不存在”。
    # 3. 数据格式化与返回：校验通过后，提取资源的核心字段（ID、标题、类型、内容、链接），并将创建时间格式化为标准的 YYYY-MM-DD 格式，返回给前端。
    r = db.query(MentalResource).filter(MentalResource.id == id).first()
    if not r:
        return err(400, "资源不存在")
    return ok({
        "id": r.id, "title": r.title, "type": r.type,
        "content": r.content, "url": r.url,
        "create_time": r.create_time.strftime("%Y-%m-%d"),
    }, "获取成功")
