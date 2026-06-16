"""成员A：学生账号与心理测评"""
from datetime import datetime
from typing import List

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
        return "正常", "焦虑水平较低，继续保持当前的生活节奏就好"
    if total_score <= 9:
        return "轻度焦虑", "最近可能有些操心的事，试试每天留几分钟做深呼吸或散步，帮自己松一松"
    if total_score <= 14:
        return "中度焦虑", "焦虑已经开始影响你的状态了，建议找学校心理咨询中心聊一聊，早点调整会轻松很多"
    return "重度焦虑", "你现在的焦虑程度比较高，建议尽快联系学校心理咨询中心或专业机构，不需要一个人扛着"


def score_pss10(total_score: int) -> tuple[str, str]:
    if total_score <= 13:
        return "压力正常", "你目前的压力感知在可控范围内，继续做好日常的自我照顾就行"
    if total_score <= 26:
        return "中度压力", "你最近承受着不小的压力，试着把一些不紧急的事情放一放，给自己留点喘息的空间"
    return "高压力", "你现在的压力水平比较高，长期下去身体和情绪都会吃不消，建议主动寻求支持，和信任的人聊聊或联系学校心理咨询中心"


def score_ses(total_score: int) -> tuple[str, str]:
    if total_score <= 15:
        return "低自尊", "你可能经常对自己不够满意，容易看到自己的不足。试着每天记录一件自己做得还不错的小事，慢慢积累对自己的认可"
    if total_score <= 25:
        return "自尊水平中等", "你对自己有基本的认可，偶尔也会自我怀疑，这很正常。继续关注自己的优点，不用太苛刻地要求自己"
    return "高自尊", "你对自己有比较积极的看法，这是很宝贵的心理资源，继续保持就好"


# ── 学生账号路由 ──────────────────────────────────────────

@router.post("/user/login", response_model=ApiResponse)
def user_login(body: UserLoginBody, db: Session = Depends(get_db)):
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


@router.post("/user/register", response_model=ApiResponse)
def user_register(body: UserRegisterBody, db: Session = Depends(get_db)):
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


@router.post("/user/reset-password", response_model=ApiResponse)
def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    if len(body.new_password) < 6:
        return err(400, "新密码长度≥6位")
    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        return err(400, "用户不存在")
    user.password = hash_password(body.new_password)
    db.commit()
    return ok({}, "密码重置成功")


@router.get("/user/info", response_model=ApiResponse)
def user_info(db: Session = Depends(get_db), user_id: int = Depends(get_current_student_id)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return err(400, "用户不存在")
    return ok({"username": u.username, "register_time": u.create_time.strftime("%Y-%m-%d")}, "获取成功")


# ── 测评路由 ──────────────────────────────────────────────

@router.get("/evaluation/get-questions", response_model=ApiResponse)
def get_questions(scale_type: str = Query(..., pattern="^(PHQ-9|SCL-90|GAD-7|PSS-10|SES)$"), db: Session = Depends(get_db)):
    qs = (
        db.query(EvaluationQuestion)
        .filter(EvaluationQuestion.scale_type == scale_type)
        .order_by(EvaluationQuestion.sort).all()
    )
    return ok({"questions": [{"id": q.id, "content": q.content, "options": [0, 1, 2, 3]} for q in qs]}, "获取成功")


@router.post("/evaluation/calculate-result", response_model=ApiResponse)
def calculate_result(
    body: CalculateResultBody,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return err(400, "用户不存在")

    qs = (
        db.query(EvaluationQuestion)
        .filter(EvaluationQuestion.scale_type == body.scale_type)
        .order_by(EvaluationQuestion.sort).all()
    )
    expected = len(qs)
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
        total_score = sum(body.scores)
        emotion_label, suggestion = score_pss10(total_score)
    elif body.scale_type == "SES":
        total_score = sum(body.scores)
        emotion_label, suggestion = score_ses(total_score)
    else:
        return err(400, "不支持的量表类型")

    ai_messages = build_evaluation_messages(body.scale_type, total_score, emotion_label, suggestion, body.scores)
    ai_res = llm_chat(ai_messages, max_tokens=LLM_EVAL_MAX_TOKENS, temperature=LLM_TEMP_EVAL, timeout=LLM_TIMEOUT_SEC)
    ai_text = ai_res.text
    ai_user_hint = ai_res.user_hint if not ai_text else None
    _raw = (ai_text if ai_text else suggestion) or ""
    final_suggestion = _raw[:62000] if len(_raw) > 62000 else _raw
    ai_generated = bool(ai_text)

    now = datetime.now()
    result = EvaluationResult(
        user_id=user_id, scale_type=body.scale_type, total_score=total_score,
        emotion_label=emotion_label, suggestion=final_suggestion,
        ai_generated=ai_generated, llm_backend=(ai_res.backend if ai_text else None),
        create_time=now,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return ok({
        "id": result.id, "scale_type": body.scale_type, "total_score": total_score,
        "emotion_label": emotion_label, "suggestion": final_suggestion,
        "ai_generated": ai_generated, "ai_user_hint": ai_user_hint,
        "llm_backend": ai_res.backend if ai_text else None,
        "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }, "测评完成")


@router.get("/evaluation/get-my-results", response_model=ApiResponse)
def get_my_results(db: Session = Depends(get_db), user_id: int = Depends(get_current_student_id)):
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


@router.get("/evaluation/result-detail", response_model=ApiResponse)
def result_detail(
    result_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
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
