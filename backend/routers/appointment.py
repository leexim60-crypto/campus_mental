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
        body: AppointmentAddBody,  # 请求体：包含预约所需的日期、时间、内容等字段
        db: Session = Depends(get_db),  # 依赖注入：获取数据库会话
        user_id: int = Depends(get_current_student_id),  # 依赖注入：获取当前登录学生的 ID
):
    # 1. 用户存在性校验：确保当前操作的学生账号在系统中真实存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return err(400, "用户不存在")

    # 2. 日期格式解析与校验：
    # 尝试将前端传来的字符串日期转换为 date 对象
    try:
        d = datetime.strptime(body.date, "%Y-%m-%d").date()
    except ValueError:
        # 如果格式不符合 "%Y-%m-%d"，捕获异常并返回错误提示
        return err(400, "日期格式错误")

    # 3. 防重复预约校验（核心防冲突逻辑）：
    # 查询是否存在：同一用户 + 同一日期 + 同一时间 + 状态为「已预约」的记录
    dup = (
        db.query(CounselingAppointment)
        .filter(
            CounselingAppointment.user_id == user_id,
            CounselingAppointment.date == d,
            CounselingAppointment.time == body.time,
            CounselingAppointment.status == "已预约",  # 仅校验有效预约，已取消的不算冲突
        ).first()
    )
    if dup:
        return err(400, "该时段您已有预约，请勿重复提交")

    # 4. 创建并持久化新预约记录
    appt = CounselingAppointment(
        user_id=user_id,  # 关联当前学生
        date=d,  # 解析后的日期对象
        time=body.time,  # 预约时间段
        content=body.content,  # 预约内容/问题描述
        status="已预约",  # 初始状态设为「已预约」
        create_time=datetime.now(),  # 记录创建时间
    )
    db.add(appt)  # 将新记录加入数据库会话
    db.commit()  # 提交事务，写入数据库

    # 5. 返回成功响应：包含新生成的预约 ID 及预约时间，方便前端展示
    return ok({"appointment_id": appt.id, "date": body.date, "time": body.time}, "预约成功")


@router.get("/appointment/my-list", response_model=ApiResponse)
def appointment_my_list(
        db: Session = Depends(get_db),  # 依赖注入：获取数据库会话
        user_id: int = Depends(get_current_student_id),  # 依赖注入：获取当前登录学生的 ID
):
    """
    获取当前学生的个人预约列表。
    结果按时间倒序排列，确保最新预约在最前。
    """

    # 1. 数据库查询：
    # - 过滤条件：仅查询 user_id 等于当前登录学生 ID 的记录
    # - 排序规则：先按 date 降序，若日期相同再按 time 降序
    items = (
        db.query(CounselingAppointment)
        .filter(CounselingAppointment.user_id == user_id)
        .order_by(CounselingAppointment.date.desc(), CounselingAppointment.time.desc())
        .all()
    )

    # 2. 数据组装与格式化返回：
    # 使用列表推导式遍历查询结果，仅提取前端所需的字段
    return ok({
        "appointments": [{
            "id": a.id,  # 预约唯一标识
            "date": a.date.strftime("%Y-%m-%d"),  # 将日期对象格式化为 "YYYY-MM-DD" 字符串
            "time": a.time,  # 预约时间段
            "content": a.content,  # 预约内容/问题描述
            "status": a.status,  # 预约状态（如：已预约、已取消等）
        } for a in items]
    }, "获取成功")

@router.post("/appointment/cancel", response_model=ApiResponse)
def appointment_cancel(
        body: AppointmentCancelBody,  # 请求体：包含要取消的预约 ID
        db: Session = Depends(get_db),  # 依赖注入：获取数据库会话
        user_id: int = Depends(get_current_student_id),  # 依赖注入：获取当前登录学生的 ID
):
    # 1. 根据前端传来的预约 ID 查询数据库
    a = db.query(CounselingAppointment).filter(CounselingAppointment.id == body.appointment_id).first()

    # 2. 校验预约是否存在
    if not a:
        return err(400, "预约不存在")

    # 3. 校验归属权：防止越权操作（用户只能取消自己的预约）
    if a.user_id != user_id:
        return err(403, "无权取消他人预约")

    # 4. 校验当前状态：只有处于「已预约」状态的记录才允许被取消
    if a.status != "已预约":
        return err(400, "仅可取消状态为「已预约」的记录")

    # 5. 更新状态为「已取消」，并提交数据库事务
    a.status = "已取消"
    db.commit()

    # 6. 返回成功响应
    return ok({}, "取消成功")
