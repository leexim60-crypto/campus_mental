"""成员A：学生账号与心理测评"""
import logging
from datetime import datetime
from typing import List

_log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from config import LLM_EVAL_MAX_TOKENS, LLM_TEMP_EVAL, LLM_TIMEOUT_SEC
from database import get_db
from deps import get_current_student_id
from llm_client import build_evaluation_messages, llm_chat
from models import EvaluationQuestion, EvaluationResult, User
from schemas import (
    ApiResponse, CalculateResultBody, ResetPasswordBody,
    UserLoginBody, UserRegisterBody, err, ok,
)
from security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1")


# ── 评分辅助 ──────────────────────────────────────────────

def score_phq9(total_score: int) -> tuple[str, str]:
    if total_score <= 4:
        return "正常", "保持良好的作息与心态，如有需要可适当参加放松活动"
    if total_score <= 9:
        return "轻度抑郁倾向", "建议关注情绪变化，适当与朋友或家人沟通，必要时联系学校心理咨询中心"
    if total_score <= 14:
        return "中度抑郁倾向", "建议尽快联系学校心理咨询中心，进行专业评估与咨询"
    return "重度抑郁倾向", "强烈建议立即联系学校心理咨询中心或专业机构，必要时告知家长与辅导员"


def score_scl90_demo(scores: List[int]) -> tuple[str, str, int]:
    n = len(scores)
    total = sum(scores)
    mean = total / n if n else 0.0
    if mean < 1.0:
        return "总体正常", "各维度症状感受较轻，建议保持规律生活与适度运动，继续关注自我状态即可。", total
    if mean < 1.5:
        return "轻度症状倾向", "部分项目得分偏高，建议增加休息与社交支持，必要时可预约心理咨询做一次交流。", total
    if mean < 2.0:
        return "中度症状倾向", "建议尽快联系学校心理咨询中心进行面谈评估，并告知辅导员或家长以获得支持。", total
    return "重度症状倾向", "建议立即寻求专业心理帮助，如出现自伤念头请拨打心理援助热线或前往医院急诊。", total


def score_gad7(total_score: int) -> tuple[str, str]:
    if total_score <= 4:
        return "正常", "焦虑程度在正常范围内，建议继续保持良好的生活习惯与心态"
    if total_score <= 9:
        return "轻度焦虑", "存在轻度焦虑倾向，建议适当放松、规律作息，必要时可与朋友或家人倾诉"
    if total_score <= 14:
        return "中度焦虑", "建议尽快联系学校心理咨询中心，进行专业评估与干预"
    return "重度焦虑", "强烈建议立即联系学校心理咨询中心或专业机构，必要时告知家长与辅导员"


def score_pss10(scores: List[int]) -> tuple[str, str, int]:
    # 第4、5、7、8题为正向题（感觉事情可控），需反向计分
    reverse_indices = {3, 4, 6, 7}  # 0-based
    adjusted = []
    for i, s in enumerate(scores):
        if i in reverse_indices:
            adjusted.append(3 - s)
        else:
            adjusted.append(s)
    total = sum(adjusted)
    if total <= 10:
        return "低压力", "当前压力感知较低，心理状态良好，建议继续保持积极的生活节奏", total
    if total <= 20:
        return "中等压力", "存在一定压力感知，建议适当调整作息、增加放松活动，必要时可寻求心理支持", total
    return "高压力", "压力感知较高，建议尽快联系学校心理咨询中心，学习有效的压力管理方法", total


def score_ses(scores: List[int]) -> tuple[str, str, int]:
    # 第3、5、6、9、10题为反向题（负向表述），需反向计分
    reverse_indices = {2, 4, 5, 8, 9}  # 0-based
    adjusted = []
    for i, s in enumerate(scores):
        if i in reverse_indices:
            adjusted.append(3 - s)
        else:
            adjusted.append(s)
    total = sum(adjusted)
    if total >= 22:
        return "高自尊", "自尊水平良好，对自我有积极的认知，建议继续保持自信与自我接纳", total
    if total >= 15:
        return "中等自尊", "自尊水平处于中等，建议多关注自身优点与成就，培养积极的自我认知", total
    return "低自尊", "自尊水平偏低，建议联系学校心理咨询中心，探索提升自我价值感的方法", total



# 【学生用户登录认证】
@router.post("/user/login", response_model=ApiResponse)
def user_login(body: UserLoginBody, db: Session = Depends(get_db)):
    # 1. 身份与角色校验：通过用户名（username）和角色（role="student"）联合查询数据库，确保只有学生角色可以登录。
    # 2. 密码验证与防枚举安全：将“用户不存在”与“密码错误”合并为同一个错误提示（“学生账号或密码错误”），防止恶意攻击者通过不同的报错信息探测系统中是否存在某个账号。
    # 3. 生成访问令牌：验证通过后，调用 create_access_token 函数，基于用户 ID 和角色生成 JWT 访问令牌（access_token）。
    # 4. 返回登录凭证与用户信息：向客户端返回 JWT 令牌、令牌类型（bearer），以及当前登录用户的核心信息（ID、用户名、角色），供前端后续请求携带并展示。
    user = (
        db.query(User)
        .filter(User.username == body.username, User.role == "student")
        .first()
    )
    if not user or not verify_password(body.password, user.password):
        return err(400, "学生账号或密码错误")
    token = create_access_token(str(user.id), "student")
    return ok({
        "access_token": token, "token_type": "bearer",
        "user_id": user.id, "username": user.username, "role": user.role,
    }, "登录成功")


# 【学生用户注册】
@router.post("/user/register", response_model=ApiResponse)
def user_register(body: UserRegisterBody, db: Session = Depends(get_db)):
    # 1. 密码一致性校验：校验请求体中的 password 与 confirm_password 是否完全一致。
    # 2. 密码强度校验：校验密码长度是否满足最低要求（大于等于 6 位）。
    # 3. 账号唯一性校验：在数据库中查询用户名是否已被占用，若存在则拒绝注册。
    # 4. 数据脱敏与持久化：使用 hash_password 对明文密码进行哈希加密后，连同用户名、固定角色（student）和当前时间一起构建 User 对象，写入数据库并提交事务。
    # 5. 返回注册结果：注册成功后返回空数据体与成功提示。
    if body.password != body.confirm_password:
        return err(400, "两次密码不一致")
    if len(body.password) < 6:
        return err(400, "密码长度≥6位")
    if db.query(User).filter(User.username == body.username).first():
        return err(400, "用户名已存在")
    user = User(
        username=body.username, password=hash_password(body.password),
        role="student", create_time=datetime.now(),
    )
    db.add(user)
    db.commit()
    return ok({}, "注册成功")


# 【用户密码重置】
@router.post("/user/reset-password", response_model=ApiResponse)
def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    # 1. 新密码强度校验：校验请求体中的新密码长度是否满足最低安全要求（大于等于 6 位）。
    # 2. 用户存在性校验：根据传入的用户名（username）在数据库中查询用户记录，若未找到则返回 400 错误提示“用户不存在”。
    # 3. 密码加密与更新：使用 hash_password 对新密码进行哈希加密后，更新到对应用户的 password 字段。
    # 4. 持久化与返回：提交数据库事务完成密码更新，并返回空数据体与成功提示。
    if len(body.new_password) < 6:
        return err(400, "新密码长度≥6位")
    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        return err(400, "用户不存在")
    user.password = hash_password(body.new_password)
    db.commit()
    return ok({}, "密码重置成功")


#【获取当前登录学生个人信息】
@router.get("/user/info", response_model=ApiResponse)
def user_info(db: Session = Depends(get_db), user_id: int = Depends(get_current_student_id)):
    # 1. 身份获取与隔离：通过依赖注入（get_current_student_id）获取当前已登录学生的 user_id，确保数据隔离，学生只能查看自己的信息。
    # 2. 用户存在性校验：根据解析出的 user_id 在 User 表中查询记录，若未找到（极端异常情况），返回 400 错误提示“用户不存在”。
    # 3. 数据脱敏与格式化：仅返回前端展示所需的基础字段（用户名 username）。
    # 4. 时间格式化：将用户的注册时间（create_time）格式化为标准的 YYYY-MM-DD 格式，方便前端直接展示。
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return err(400, "用户不存在")
    return ok({"username": u.username, "register_time": u.create_time.strftime("%Y-%m-%d")}, "获取成功")


# 【获取指定心理量表题目列表】
@router.get("/evaluation/get-questions", response_model=ApiResponse)
def get_questions(scale_type: str = Query(..., pattern="^(PHQ-9|SCL-90|GAD-7|PSS-10|SES)$"), db: Session = Depends(get_db)):
    # 1. 参数安全校验：通过 Query 接收必填的量表类型参数（scale_type），并使用正则表达式严格限制只能传入 "PHQ-9" 或 "SCL-90"，防止非法查询。
    # 2. 排序查询：根据传入的量表类型在 EvaluationQuestion 表中检索题目，并严格按照 sort 字段进行升序排列，保证前端展示的题目顺序正确。
    # 3. 数据格式化与返回：遍历查询结果，仅提取前端渲染问卷所需的核心字段（题目 ID、题目内容），并硬编码返回固定的选项列表 [0, 1, 2, 3]。
    qs = (
        db.query(EvaluationQuestion)
        .filter(EvaluationQuestion.scale_type == scale_type)
        .order_by(EvaluationQuestion.sort).all()
    )
    return ok({"questions": [{"id": q.id, "content": q.content, "options": [0, 1, 2, 3]} for q in qs]}, "获取成功")


# 【心理测评结果计算与落库】
@router.post("/evaluation/calculate-result", response_model=ApiResponse)
def calculate_result(
    body: CalculateResultBody,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return err(400, "用户不存在")

        qs = (
            db.query(EvaluationQuestion)
            .filter(EvaluationQuestion.scale_type == body.scale_type)
            .order_by(EvaluationQuestion.sort).all()
        )
        expected = len(qs)
        _log.info("calculate_result: scale=%s, expected=%d, got=%d", body.scale_type, expected, len(body.scores))
        if expected == 0:
            return err(400, "该量表暂无题目，请联系管理员")
        if len(body.scores) != expected:
            return err(400, f"题目数量不符，应为 {expected} 题")
        for s in body.scores:
            if s not in (0, 1, 2, 3):
                return err(400, "每题得分须为 0–3")

        if body.scale_type == "PHQ-9":
            total_score = sum(body.scores)
            emotion_label, suggestion = score_phq9(total_score)
        elif body.scale_type == "SCL-90":
            emotion_label, suggestion, total_score = score_scl90_demo(body.scores)
        elif body.scale_type == "GAD-7":
            total_score = sum(body.scores)
            emotion_label, suggestion = score_gad7(total_score)
        elif body.scale_type == "PSS-10":
            emotion_label, suggestion, total_score = score_pss10(body.scores)
        elif body.scale_type == "SES":
            emotion_label, suggestion, total_score = score_ses(body.scores)
        else:
            return err(400, "不支持的量表类型")

        question_texts = [q.content for q in qs]
        ai_messages = build_evaluation_messages(body.scale_type, total_score, emotion_label, suggestion, body.scores, questions=question_texts)
        try:
            ai_res = llm_chat(ai_messages, max_tokens=LLM_EVAL_MAX_TOKENS, temperature=LLM_TEMP_EVAL, timeout=LLM_TIMEOUT_SEC)
            ai_text = ai_res.text
            ai_user_hint = ai_res.user_hint if not ai_text else None
            ai_backend = ai_res.backend if ai_text else None
        except Exception as e:
            _log.warning("LLM 调用失败，降级使用规则模板: %s", e)
            ai_text = None
            ai_user_hint = None
            ai_backend = None
        _raw = (ai_text if ai_text else suggestion) or ""
        final_suggestion = _raw[:62000] if len(_raw) > 62000 else _raw
        ai_generated = bool(ai_text)

        now = datetime.now()
        result = EvaluationResult(
            user_id=user_id, scale_type=body.scale_type, total_score=total_score,
            emotion_label=emotion_label, suggestion=final_suggestion,
            ai_generated=ai_generated, llm_backend=ai_backend,
            create_time=now,
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return ok({
            "id": result.id, "scale_type": body.scale_type, "total_score": total_score,
            "emotion_label": emotion_label, "suggestion": final_suggestion,
            "ai_generated": ai_generated, "ai_user_hint": ai_user_hint,
            "llm_backend": ai_backend,
            "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }, "测评完成")
    except Exception as e:
        _log.exception("calculate_result 异常: scale=%s", body.scale_type)
        # 返回 200 + 错误码，让前端能读到 msg
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=200, content={"code": 500, "msg": f"测评处理失败: {e}", "data": {}})

# 【获取当前学生所有心理测评结果列表】的接口
@router.get("/evaluation/get-my-results", response_model=ApiResponse)
def get_my_results(db: Session = Depends(get_db), user_id: int = Depends(get_current_student_id)):
    # 1. 数据隔离（安全）：通过依赖注入获取当前登录学生的 user_id，严格过滤，确保学生只能查看自己名下的测评记录。
    # 2. 时间倒序排列：查询结果按照 create_time（创建时间）进行降序（desc）排列，保证最新的测评结果始终展示在列表最前面。
    # 3. 数据脱敏与格式化：在返回数据前，仅暴露前端需要的核心字段（ID、量表类型、总分、情绪标签等）。
    # 4. 兼容 AI 扩展字段：使用 getattr 安全地获取 AI 生成标识（ai_generated）和使用的模型后端（llm_backend），防止旧数据因缺少这些字段而报错。
    # 5. 时间格式化：将创建时间精确格式化为 YYYY-MM-DD HH:MM:SS 格式，方便前端展示。
    rs = (
        db.query(EvaluationResult)
        .filter(EvaluationResult.user_id == user_id)
        .order_by(EvaluationResult.create_time.desc()).all()
    )
    return ok({"results": [{
        "id": r.id, "scale_type": r.scale_type, "total_score": r.total_score,
        "emotion_label": r.emotion_label,
        "ai_generated": bool(getattr(r, "ai_generated", False)),
        "llm_backend": getattr(r, "llm_backend", None),
        "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
    } for r in rs]}, "获取成功")


# 【获取心理测评结果详情】的接口
@router.get("/evaluation/result-detail", response_model=ApiResponse)
def result_detail(
    result_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    # 1. 参数获取与校验：通过 Query 接收必填的测评结果 ID（result_id），且限制其必须大于等于 1。
    # 2. 数据隔离与权限校验（核心安全点）：在数据库查询时，同时使用 result_id 和当前登录用户的 user_id 进行联合过滤。
    #    这确保了学生只能查看自己的测评结果，有效防止了水平越权漏洞。
    # 3. 存在性校验：若联合查询未找到记录（可能是 ID 不存在，或该记录不属于当前用户），统一返回 404 错误提示“记录不存在或无权查看”。
    # 4. 数据格式化与返回：提取核心字段返回给前端，包括量表类型、总分、情绪标签和建议。
    #    同时兼容了 AI 生成标识（ai_generated）和使用的模型后端（llm_backend），并将时间精确格式化到秒（YYYY-MM-DD HH:MM:SS）。
    r = (
        db.query(EvaluationResult)
        .filter(EvaluationResult.id == result_id, EvaluationResult.user_id == user_id)
        .first()
    )
    if not r:
        return err(404, "记录不存在或无权查看")
    return ok({
        "id": r.id, "scale_type": r.scale_type, "total_score": r.total_score,
        "emotion_label": r.emotion_label, "suggestion": r.suggestion,
        "ai_generated": bool(getattr(r, "ai_generated", False)),
        "llm_backend": getattr(r, "llm_backend", None),
        "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
    }, "获取成功")
