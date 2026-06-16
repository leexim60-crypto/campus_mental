"""成员B：管理员与数据统计"""
import csv
import hashlib
import hmac
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import ADMIN_REGISTER_SECRET
from database import get_db
from deps import get_current_admin_id
from models import EvaluationResult, User
from schemas import (
    AdminChangePasswordBody, AdminLoginBody, AdminRegisterBody,
    ApiResponse, ExportDataBody, err, ok,
)
from security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1")


def _admin_register_secret_ok(provided: str, expected: str) -> bool:
    if not expected or not provided:
        return False
    p = hashlib.sha256(provided.encode("utf-8")).digest()
    e = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(p, e)


# ── 管理员账号 ────────────────────────────────────────────

@router.post("/admin/register", response_model=ApiResponse)
def admin_register(body: AdminRegisterBody, db: Session = Depends(get_db)):
    if not ADMIN_REGISTER_SECRET:
        return err(403, "管理员自助注册未启用：请在服务端 .env 配置 ADMIN_REGISTER_SECRET")
    if not _admin_register_secret_ok(body.register_secret.strip(), ADMIN_REGISTER_SECRET):
        return err(403, "注册密钥错误")
    if body.password != body.confirm_password:
        return err(400, "两次密码不一致")
    if len(body.password) < 6:
        return err(400, "密码长度≥6位")
    uname = body.username.strip()
    if len(uname) < 2:
        return err(400, "用户名至少2个字符")
    if db.query(User).filter(User.username == uname).first():
        return err(400, "用户名已存在")
    user = User(username=uname, password=hash_password(body.password), role="admin", create_time=datetime.now())
    db.add(user)
    db.commit()
    return ok({"username": user.username}, "管理员注册成功，请登录")


@router.post("/admin/login", response_model=ApiResponse)
def admin_login(body: AdminLoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username, User.role == "admin").first()
    if not user or not verify_password(body.password, user.password):
        return err(400, "账号或密码错误")
    token = create_access_token(str(user.id), "admin")
    return ok({
        "access_token": token, "token_type": "bearer",
        "admin_id": user.id, "username": user.username,
    }, "登录成功")


@router.get("/admin/check-permission", response_model=ApiResponse)
def admin_check_permission(_: int = Depends(get_current_admin_id)):
    return ok({"permission": True}, "权限验证通过")


@router.get("/admin/info", response_model=ApiResponse)
def admin_info(db: Session = Depends(get_db), admin_id: int = Depends(get_current_admin_id)):
    u = db.query(User).filter(User.id == admin_id).first()
    if not u:
        return err(400, "用户不存在")
    return ok({
        "admin_id": u.id, "username": u.username,
        "role": u.role, "register_time": u.create_time.strftime("%Y-%m-%d"),
    }, "获取成功")


@router.post("/admin/change-password", response_model=ApiResponse)
def admin_change_password(
    body: AdminChangePasswordBody,
    db: Session = Depends(get_db),
    admin_id: int = Depends(get_current_admin_id),
):
    if len(body.new_password) < 6:
        return err(400, "新密码长度≥6位")
    u = db.query(User).filter(User.id == admin_id).first()
    if not u or not verify_password(body.old_password, u.password):
        return err(400, "原密码错误")
    u.password = hash_password(body.new_password)
    db.commit()
    return ok({}, "密码已修改")


# ── 统计与导出 ────────────────────────────────────────────

@router.get("/admin/statistic/emotion", response_model=ApiResponse)
def statistic_emotion(
    start_time: Optional[str] = None, end_time: Optional[str] = None,
    db: Session = Depends(get_db), _: int = Depends(get_current_admin_id),
):
    query = db.query(EvaluationResult)
    if start_time:
        try:
            query = query.filter(EvaluationResult.create_time >= datetime.strptime(start_time, "%Y-%m-%d"))
        except ValueError:
            pass
    if end_time:
        try:
            query = query.filter(EvaluationResult.create_time < datetime.strptime(end_time, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    stats: dict[str, int] = {}
    for r in query.all():
        stats[r.emotion_label] = stats.get(r.emotion_label, 0) + 1
    return ok({"emotion_stats": [{"label": l, "count": c} for l, c in stats.items()]}, "获取成功")


@router.get("/admin/statistic/scale", response_model=ApiResponse)
def statistic_scale(
    start_time: Optional[str] = None, end_time: Optional[str] = None,
    db: Session = Depends(get_db), _: int = Depends(get_current_admin_id),
):
    query = db.query(EvaluationResult)
    if start_time:
        try:
            query = query.filter(EvaluationResult.create_time >= datetime.strptime(start_time, "%Y-%m-%d"))
        except ValueError:
            pass
    if end_time:
        try:
            query = query.filter(EvaluationResult.create_time < datetime.strptime(end_time, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    stats: dict[str, int] = {}
    for r in query.all():
        stats[r.scale_type] = stats.get(r.scale_type, 0) + 1
    return ok({"scale_stats": [{"scale_type": s, "count": c} for s, c in stats.items()]}, "获取成功")


@router.post("/admin/export-data", response_model=ApiResponse)
def admin_export_data(body: ExportDataBody, _: int = Depends(get_current_admin_id)):
    return ok({
        "hint": "请使用「导出测评 CSV」按钮下载文件",
        "download_path": "/api/v1/admin/export/evaluations.csv",
    }, "请使用 GET /api/v1/admin/export/evaluations.csv 携带管理员 Token 下载")


@router.get("/admin/export/evaluations.csv")
def admin_export_evaluations_csv(db: Session = Depends(get_db), _: int = Depends(get_current_admin_id)):
    rows = (
        db.query(EvaluationResult, User.username)
        .join(User, EvaluationResult.user_id == User.id)
        .order_by(EvaluationResult.create_time.desc()).all()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "username", "scale_type", "total_score", "emotion_label", "ai_generated", "llm_backend", "create_time"])
    for r, username in rows:
        w.writerow([
            r.id, username, r.scale_type, r.total_score, r.emotion_label,
            "1" if bool(getattr(r, "ai_generated", False)) else "0",
            getattr(r, "llm_backend", None) or "",
            r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="evaluations_export.csv"'},
    )


@router.get("/admin/evaluation/list", response_model=ApiResponse)
def admin_evaluation_list(
    page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db), _: int = Depends(get_current_admin_id),
):
    query = (
        db.query(EvaluationResult)
        .join(User, EvaluationResult.user_id == User.id)
        .order_by(EvaluationResult.create_time.desc())
    )
    total = query.count()
    page_items = query.offset((page - 1) * size).limit(size).all()
    return ok({"total": total, "list": [{
        "id": r.id, "username": r.user.username if r.user else "",
        "scale_type": r.scale_type, "total_score": r.total_score,
        "emotion_label": r.emotion_label,
        "ai_generated": bool(getattr(r, "ai_generated", False)),
        "llm_backend": getattr(r, "llm_backend", None),
        "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
    } for r in page_items]}, "获取成功")
