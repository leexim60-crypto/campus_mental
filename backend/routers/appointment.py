"""成员C：咨询预约"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_student_id
from models import CounselingAppointment, User
from schemas import AppointmentAddBody, AppointmentCancelBody, ApiResponse, err, ok

router = APIRouter(prefix="/api/v1")


@router.post("/appointment/add", response_model=ApiResponse)
def appointment_add(
    body: AppointmentAddBody,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return err(400, "用户不存在")
    try:
        d = datetime.strptime(body.date, "%Y-%m-%d").date()
    except ValueError:
        return err(400, "日期格式错误")
    dup = (
        db.query(CounselingAppointment)
        .filter(
            CounselingAppointment.user_id == user_id,
            CounselingAppointment.date == d,
            CounselingAppointment.time == body.time,
            CounselingAppointment.status == "已预约",
        ).first()
    )
    if dup:
        return err(400, "该时段您已有预约，请勿重复提交")
    appt = CounselingAppointment(
        user_id=user_id, date=d, time=body.time,
        content=body.content, status="已预约", create_time=datetime.now(),
    )
    db.add(appt)
    db.commit()
    return ok({"appointment_id": appt.id, "date": body.date, "time": body.time}, "预约成功")


@router.get("/appointment/my-list", response_model=ApiResponse)
def appointment_my_list(db: Session = Depends(get_db), user_id: int = Depends(get_current_student_id)):
    items = (
        db.query(CounselingAppointment)
        .filter(CounselingAppointment.user_id == user_id)
        .order_by(CounselingAppointment.date.desc(), CounselingAppointment.time.desc()).all()
    )
    return ok({"appointments": [{
        "id": a.id, "date": a.date.strftime("%Y-%m-%d"),
        "time": a.time, "content": a.content, "status": a.status,
    } for a in items]}, "获取成功")


@router.post("/appointment/cancel", response_model=ApiResponse)
def appointment_cancel(
    body: AppointmentCancelBody,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    a = db.query(CounselingAppointment).filter(CounselingAppointment.id == body.appointment_id).first()
    if not a:
        return err(400, "预约不存在")
    if a.user_id != user_id:
        return err(403, "无权取消他人预约")
    if a.status != "已预约":
        return err(400, "仅可取消状态为「已预约」的记录")
    a.status = "已取消"
    db.commit()
    return ok({}, "取消成功")
