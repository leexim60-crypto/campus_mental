import csv
import hashlib
import json
import hmac
import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Date,
    create_engine,
    ForeignKey,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

from config import (
    ADMIN_REGISTER_SECRET,
    CORS_ORIGINS,
    DATABASE_URL,
    DEEPSEEK_API_KEY,
    LLM_CHAT_MAX_TOKENS,
    LLM_EVAL_MAX_TOKENS,
    LLM_PROVIDER,
    LLM_TEMP_CHAT,
    LLM_TEMP_EVAL,
    LLM_TIMEOUT_SEC,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from llm_client import (
    SYSTEM_COMPANION_CHAT,
    build_evaluation_messages,
    chat_available,
    iter_llm_chat_sse,
    llm_chat,
    ollama_effective_base_url,
)
from security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

bearer_scheme = HTTPBearer(auto_error=True)


def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="无效或过期的登录状态")


def get_current_student_id(payload: dict = Depends(get_token_payload)) -> int:
    if payload.get("role") != "student":
        raise HTTPException(status_code=403, detail="需要学生账号登录")
    return int(payload["sub"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_admin_id(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> int:
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    uid = int(payload["sub"])
    user = db.query(User).filter(User.id == uid, User.role == "admin").first()
    if not user:
        raise HTTPException(status_code=401, detail="管理员账号无效")
    return uid


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="校园心理健康智能评估与干预平台 API",
    version="1.1.0",
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

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ApiResponse(BaseModel):
    code: int
    msg: str
    data: Optional[dict] = None


def ok(data: Optional[dict] = None, msg: str = "操作成功") -> ApiResponse:
    return ApiResponse(code=200, msg=msg, data=data)


def err(code: int, msg: str) -> ApiResponse:
    return ApiResponse(code=code, msg=msg)


class User(Base):
    __tablename__ = "user"

    id: int = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username: str = Column(String(50), unique=True, nullable=False)
    password: str = Column(String(255), nullable=False)
    role: str = Column(String(20), nullable=False, default="student")
    create_time: datetime = Column(
        DateTime, nullable=False, default=datetime.now
    )


class EvaluationQuestion(Base):
    __tablename__ = "evaluation_question"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    scale_type: str = Column(String(20), nullable=False)
    content: str = Column(String(200), nullable=False)
    sort: int = Column(Integer, nullable=False, default=0)


class EvaluationResult(Base):
    __tablename__ = "evaluation_result"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("user.id"), nullable=False)
    scale_type: str = Column(String(20), nullable=False)
    total_score: int = Column(Integer, nullable=False, default=0)
    emotion_label: str = Column(String(50), nullable=False)
    suggestion: str = Column(Text, nullable=False)
    ai_generated: bool = Column(Boolean, nullable=False, default=False)
    llm_backend: Optional[str] = Column(String(20), nullable=True)
    create_time: datetime = Column(
        DateTime, nullable=False, default=datetime.now
    )

    user = relationship("User")


class MentalResource(Base):
    __tablename__ = "mental_resource"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    title: str = Column(String(100), nullable=False)
    type: str = Column(String(20), nullable=False)
    content: Optional[str] = Column(Text, nullable=True)
    url: Optional[str] = Column(String(200), nullable=True)
    create_time: datetime = Column(
        DateTime, nullable=False, default=datetime.now
    )


class CounselingAppointment(Base):
    __tablename__ = "counseling_appointment"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("user.id"), nullable=False)
    date: date = Column(Date, nullable=False)
    time: str = Column(String(20), nullable=False)
    content: Optional[str] = Column(Text, nullable=True)
    status: str = Column(String(20), nullable=False, default="已预约")
    create_time: datetime = Column(
        DateTime, nullable=False, default=datetime.now
    )

    user = relationship("User")


Base.metadata.create_all(bind=engine)

_log = logging.getLogger(__name__)

# MySQL 旧库在接入 AI 前建的表没有 ai_generated 列，会导致提交测评 500 —— 启动时自动补齐
def _ensure_evaluation_result_ai_column() -> None:
    if "mysql" not in DATABASE_URL.lower():
        return
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'evaluation_result'
                      AND COLUMN_NAME = 'ai_generated'
                    """
                )
            ).fetchone()
            if row and row[0] == 0:
                conn.execute(
                    text(
                        """
                        ALTER TABLE evaluation_result
                        ADD COLUMN ai_generated TINYINT(1) NOT NULL DEFAULT 0
                        AFTER suggestion
                        """
                    )
                )
                _log.info("已为 evaluation_result 自动添加 ai_generated 列（旧库升级）")
    except Exception as e:
        _log.warning("自动检查/添加 ai_generated 列未成功（可手动执行 migrations 下 SQL）: %s", e)


_ensure_evaluation_result_ai_column()


def _ensure_evaluation_result_llm_backend_column() -> None:
    if "mysql" not in DATABASE_URL.lower():
        return
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'evaluation_result'
                      AND COLUMN_NAME = 'llm_backend'
                    """
                )
            ).fetchone()
            if row and row[0] == 0:
                conn.execute(
                    text(
                        """
                        ALTER TABLE evaluation_result
                        ADD COLUMN llm_backend VARCHAR(20) NULL
                        AFTER ai_generated
                        """
                    )
                )
                _log.info("已为 evaluation_result 自动添加 llm_backend 列")
    except Exception as e:
        _log.warning("自动检查/添加 llm_backend 列未成功: %s", e)


_ensure_evaluation_result_llm_backend_column()


PHQ9_ITEMS = [
    "做事时提不起劲或只有少许乐趣",
    "感到心情低落、沮丧或绝望",
    "入睡困难、易醒或睡得过多",
    "感到疲倦或没有活力",
    "食欲不振或吃太多",
    "觉得自己很糟、或让自己或家人失望",
    "对事物专注有困难",
    "动作或说话缓慢，或烦躁不安、动来动去更严重",
    "有不如死掉或用某种方式伤害自己的念头",
]

SCL90_DEMO_ITEMS = [
    "头痛",
    "神经过敏或紧张不安",
    "头脑中有不必要的想法或字句盘旋",
    "头晕或昏倒",
    "对异性的兴趣减退",
    "对旁人责备求全",
    "感到别人能控制您的思想",
    "责怪别人制造麻烦",
    "忘性大",
    "担心自己的衣饰整齐及仪态的端正",
]


def seed_if_empty(db: Session) -> None:
    if db.query(EvaluationQuestion).count() == 0:
        for i, text in enumerate(PHQ9_ITEMS, start=1):
            db.add(
                EvaluationQuestion(
                    scale_type="PHQ-9",
                    content=text,
                    sort=i,
                )
            )
        for i, text in enumerate(SCL90_DEMO_ITEMS, start=1):
            db.add(
                EvaluationQuestion(
                    scale_type="SCL-90",
                    content=text,
                    sort=i,
                )
            )

    _seed_mental_resources(db)
    db.commit()


# 心理资源库：按标题去重，便于在已有库上增量补充更丰富内容
RESOURCE_SEED_ROWS: list[tuple[str, str, str, Optional[str]]] = [
    (
        "如何应对考试焦虑",
        "article",
        """考试前适度紧张是正常的，说明你在意、也想发挥好。可以试试：提前一周调整作息，避免通宵；复习时拆成小目标，完成一项划掉一项，减少「一片空白」的压迫感。
感到心慌时，用 4-7-8 呼吸（吸气 4 秒、屏息 7 秒、呼气 8 秒）做两三轮；对自己说「我已经准备了一部分，接下来尽力就好」。
若连续失眠、食欲明显变差、或一想到考试就情绪崩溃，建议尽快联系学校心理咨询中心，不必独自硬扛。""",
        None,
    ),
    (
        "睡眠与情绪",
        "article",
        """睡眠和情绪互相影响：睡不够时人更容易烦躁、注意力下降；长期情绪低落也常伴随入睡困难或早醒。
尽量固定每天上床和起床时间；睡前一小时调暗灯光，少刷短视频；下午以后少喝含咖啡因饮料。白天有 20～30 分钟户外活动或散步，也有助于夜间睡眠。
若自我调节两周仍无明显改善，或白天严重困倦影响上课，建议向校医院或心理中心咨询，排查是否需要进一步支持。""",
        None,
    ),
    (
        "认识抑郁情绪：何时需要寻求帮助",
        "article",
        """情绪低落、对很多事提不起兴趣，持续超过两周，并明显影响学习、社交或自理时，值得认真对待——这不代表「软弱」，而是身心在提醒你需要支持。
你可以：向信任的朋友或家人说一句「我最近状态不太好」；记录一周里心情与睡眠的简单变化，便于与咨询师沟通；继续保持力所能及的运动与规律三餐。
若出现伤害自己或不想活的想法，请立即联系身边可信赖的人、学校心理中心，或拨打当地心理援助热线；紧急时前往医院急诊。你值得被帮助。""",
        None,
    ),
    (
        "社交焦虑与陌生场合：小步练习",
        "article",
        """在人多场合紧张、担心被评价，很多同学都有过。可以从「小步」开始：先在小组里发言一句，再尝试课间和同桌多聊两句；提前想好一两句开场白，降低临场大脑空白。
把注意力从「别人会不会觉得我奇怪」转到「我想完成的小目标」上。事后不必反复回放尴尬瞬间，大多数人注意力很快会转移到自己身上。
若回避社交已严重到不敢上课、不敢去食堂，建议预约心理咨询，系统练习会更有效。""",
        None,
    ),
    (
        "正念呼吸：三分钟回到当下",
        "article",
        """正念不是「什么都不想」，而是温和地注意当下：找一个安静坐姿，双脚自然落地，轻轻闭上眼睛或目光下垂。
将注意力放在鼻腔或腹部的呼吸上，吸气时知道在吸气，呼气时知道在呼气。走神了很正常，发现后不带责备地把注意力带回到呼吸即可，重复几次。
每天练习 3～5 分钟，有助于在压力大时快速「踩刹车」。若练习时出现强烈恐慌或创伤闪回，请暂停并寻求专业指导。""",
        None,
    ),
    (
        "与室友、同学矛盾时可以怎么做",
        "article",
        """冲突里先照顾好自己的安全与底线。若可以沟通，选双方都比较平静的时间，用「我」开头描述感受，例如「我最近睡得浅，晚上十二点后外放声音我会很难休息」，避免一上来就指责人格。
听对方版本时先不打断，再一起商量具体可执行的约定（如熄灯时间、卫生轮值）。若涉及欺凌、威胁或你感到人身安全受威胁，请立刻向辅导员、宿管或学校相关部门反映，必要时保留聊天记录。
长期压抑委屈也会伤身心，学校心理咨询可以帮你梳理边界与表达方式。""",
        None,
    ),
    (
        "临近毕业的压力与不确定感",
        "article",
        """面对升学、求职或gap，不确定感会带来焦虑，这很常见。可以把「大问号」拆成：我本周能完成的一件小事是什么？我需要向谁打听哪类信息？
允许自己有不完美的计划；和同龄人、学长姐或职业指导老师聊聊，往往能减少「只有我一个人迷茫」的孤独感。
若长期失眠、情绪低落、对任何事都提不起劲，请及时寻求心理咨询或医疗支持——照顾好自己，才是长远发展的基础。""",
        None,
    ),
    (
        "情绪低落时的自我照护清单",
        "article",
        """状态不好时，不必强迫自己「立刻好起来」。可以从最小可行的事开始：喝一杯水、洗把脸、到窗边站两分钟、给植物浇点水。
写下一两句「此刻真实感受」；若愿意，给信任的人发一条简短消息。避免在极度疲惫时做重大决定。
清单不是任务表，选做其中一两项即可。若情绪持续低落或有自伤念头，请把寻求帮助放进清单的第一项。""",
        None,
    ),
    (
        "温和而坚定地表达边界",
        "article",
        """边界不是冷漠，而是让关系可持续：你可以拒绝不合理请求，同时保持礼貌。例如「这次我帮不了，但祝你顺利」比长时间拖延更不消耗彼此。
若对方用内疚、冷战或贬低施压，可能是情绪勒索的信号。你可以重复自己的底线，必要时减少接触，并向辅导员或咨询师讨论应对方式。
你不需要为拒绝而过度道歉；保护自己的精力与尊严，与善良并不矛盾。""",
        None,
    ),
    (
        "手机与短视频：减少「越刷越空」",
        "article",
        """短视频带来的即时刺激容易让大脑习惯高频奖赏，停下来时反而更空虚。可以尝试：设定每日使用上限或「无手机半小时」；睡前把手机放在伸手够不到的地方。
用一件具体小事替代滑动，如听一首完整的歌、做几个拉伸。若发现自己靠刷手机麻痹强烈情绪，建议把感受写下来或找人聊聊，必要时寻求心理咨询。
改变习惯需要反复，不必因偶尔破功而全盘否定自己。""",
        None,
    ),
    (
        "考前一周作息与复习节奏建议",
        "article",
        """考前一周以「巩固」为主：回顾错题与框架，少啃全新大块内容。每天留出 7～8 小时睡眠，比多熬两小时更能保住考场上的专注力。
把最难的科目放在自己精力最好的时段；每 45～50 分钟起来活动一次。考前一天以轻松浏览笔记、早睡为主，避免通宵。
若焦虑已影响进食或睡眠，请及时联系学校心理中心，考前调整同样重要。""",
        None,
    ),
    (
        "放松冥想引导（示例音频）",
        "audio",
        "请戴耳机或调小音量，在安静环境中坐下或半躺，跟随音乐节奏放慢呼吸，从肩颈到全身逐步放松。仅为演示用音频，若需系统冥想课程请咨询专业人员。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    ),
    (
        "舒缓阅读背景音乐（示例）",
        "audio",
        "适合作为阅读或写笔记时的轻背景音；若易分心可关小音量或改用静音番茄钟。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    ),
    (
        "渐进放松：节奏舒缓示例音频",
        "audio",
        "可配合深呼吸：呼气略长于吸气，想象紧张随呼气离开身体。身体不适或眩晕时请停止并休息。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    ),
    (
        "专注学习背景音乐（示例）",
        "audio",
        "无歌词示例曲目，部分同学习惯边听边学；若你发现影响记忆可关闭。音量以不掩盖内心朗读为宜。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
    ),
    (
        "睡前放松轻音乐（示例）",
        "audio",
        "睡前半小时可试听，仍建议配合调暗屏幕、少看刺激性内容。长期失眠请结合「睡眠与情绪」一文或就医咨询。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
    ),
    (
        "课间休息：短音频提振（示例）",
        "audio",
        "两节课之间闭眼听 3～5 分钟，帮助切换注意力；若在教室外放请尊重他人。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",
    ),
    (
        "自然氛围音：森林鸟鸣（示例）",
        "audio",
        "模拟户外氛围的示例音频，可用于想象放松或短暂脱离屏幕；仅为演示资源。",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-7.mp3",
    ),
]


def _seed_mental_resources(db: Session) -> None:
    for title, rtype, content, url in RESOURCE_SEED_ROWS:
        exists = db.query(MentalResource).filter(MentalResource.title == title).first()
        if exists:
            continue
        db.add(
            MentalResource(
                title=title,
                type=rtype,
                content=content,
                url=url,
                create_time=datetime.now(),
            )
        )


# 启动时同步种子（lifespan 外再执行一次，确保首次 import 后也有数据）
_init_db = SessionLocal()
try:
    seed_if_empty(_init_db)
finally:
    _init_db.close()


class UserLoginBody(BaseModel):
    username: str
    password: str
    remember: Optional[bool] = False


@app.post("/api/v1/user/login", response_model=ApiResponse)
def user_login(body: UserLoginBody, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.username == body.username, User.role == "student")
        .first()
    )
    if not user or not verify_password(body.password, user.password):
        return err(400, "学生账号或密码错误")
    token = create_access_token(str(user.id), "student")
    return ok(
        {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
        },
        "登录成功",
    )


class UserRegisterBody(BaseModel):
    username: str
    password: str
    confirm_password: str


@app.post("/api/v1/user/register", response_model=ApiResponse)
def user_register(body: UserRegisterBody, db: Session = Depends(get_db)):
    if body.password != body.confirm_password:
        return err(400, "两次密码不一致")
    if len(body.password) < 6:
        return err(400, "密码长度≥6位")
    exists = db.query(User).filter(User.username == body.username).first()
    if exists:
        return err(400, "用户名已存在")

    user = User(
        username=body.username,
        password=hash_password(body.password),
        role="student",
        create_time=datetime.now(),
    )
    db.add(user)
    db.commit()
    return ok({}, "注册成功")


class ResetPasswordBody(BaseModel):
    username: str
    new_password: str


@app.post("/api/v1/user/reset-password", response_model=ApiResponse)
def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    if len(body.new_password) < 6:
        return err(400, "新密码长度≥6位")
    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        return err(400, "用户不存在")
    user.password = hash_password(body.new_password)
    db.commit()
    return ok({}, "密码重置成功")


@app.get("/api/v1/evaluation/get-questions", response_model=ApiResponse)
def get_questions(
    scale_type: str = Query(..., pattern="^(PHQ-9|SCL-90)$"),
    db: Session = Depends(get_db),
):
    qs = (
        db.query(EvaluationQuestion)
        .filter(EvaluationQuestion.scale_type == scale_type)
        .order_by(EvaluationQuestion.sort)
        .all()
    )
    data = {
        "questions": [
            {
                "id": q.id,
                "content": q.content,
                "options": [0, 1, 2, 3],
            }
            for q in qs
        ]
    }
    return ok(data, "获取成功")


class CalculateResultBody(BaseModel):
    scale_type: str = Field(pattern="^(PHQ-9|SCL-90)$")
    scores: List[int]


def score_phq9(total_score: int) -> tuple[str, str]:
    if total_score <= 4:
        return (
            "正常",
            "保持良好的作息与心态，如有需要可适当参加放松活动",
        )
    if total_score <= 9:
        return (
            "轻度抑郁倾向",
            "建议关注情绪变化，适当与朋友或家人沟通，必要时联系学校心理咨询中心",
        )
    if total_score <= 14:
        return (
            "中度抑郁倾向",
            "建议尽快联系学校心理咨询中心，进行专业评估与咨询",
        )
    return (
        "重度抑郁倾向",
        "强烈建议立即联系学校心理咨询中心或专业机构，必要时告知家长与辅导员",
    )


def score_scl90_demo(scores: List[int]) -> tuple[str, str, int]:
    n = len(scores)
    total = sum(scores)
    mean = total / n if n else 0.0
    if mean < 1.0:
        label = "总体正常"
        sug = (
            "各维度症状感受较轻，建议保持规律生活与适度运动，继续关注自我状态即可。"
        )
    elif mean < 1.5:
        label = "轻度症状倾向"
        sug = "部分项目得分偏高，建议增加休息与社交支持，必要时可预约心理咨询做一次交流。"
    elif mean < 2.0:
        label = "中度症状倾向"
        sug = "建议尽快联系学校心理咨询中心进行面谈评估，并告知辅导员或家长以获得支持。"
    else:
        label = "重度症状倾向"
        sug = "建议立即寻求专业心理帮助，如出现自伤念头请拨打心理援助热线或前往医院急诊。"
    return label, sug, total


@app.post("/api/v1/evaluation/calculate-result", response_model=ApiResponse)
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
        .order_by(EvaluationQuestion.sort)
        .all()
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
    else:
        emotion_label, suggestion, total_score = score_scl90_demo(body.scores)

    ai_messages = build_evaluation_messages(
        body.scale_type,
        total_score,
        emotion_label,
        suggestion,
        body.scores,
    )
    ai_res = llm_chat(
        ai_messages,
        max_tokens=LLM_EVAL_MAX_TOKENS,
        temperature=LLM_TEMP_EVAL,
        timeout=LLM_TIMEOUT_SEC,
    )
    ai_text = ai_res.text
    ai_user_hint = ai_res.user_hint if not ai_text else None
    # TEXT 上限约 64KB，过长会导致 MySQL 报错
    _raw = (ai_text if ai_text else suggestion) or ""
    final_suggestion = _raw[:62000] if len(_raw) > 62000 else _raw
    ai_generated = bool(ai_text)

    now = datetime.now()
    result = EvaluationResult(
        user_id=user_id,
        scale_type=body.scale_type,
        total_score=total_score,
        emotion_label=emotion_label,
        suggestion=final_suggestion,
        ai_generated=ai_generated,
        llm_backend=(ai_res.backend if ai_text else None),
        create_time=now,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    data = {
        "id": result.id,
        "scale_type": body.scale_type,
        "total_score": total_score,
        "emotion_label": emotion_label,
        "suggestion": final_suggestion,
        "ai_generated": ai_generated,
        # 已配置密钥但调用失败时，说明原因（常见：余额不足）；成功时标明 deepseek / ollama
        "ai_user_hint": ai_user_hint,
        "llm_backend": ai_res.backend if ai_text else None,
        "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return ok(data, "测评完成")


@app.get("/api/v1/evaluation/get-my-results", response_model=ApiResponse)
def get_my_results(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    rs = (
        db.query(EvaluationResult)
        .filter(EvaluationResult.user_id == user_id)
        .order_by(EvaluationResult.create_time.desc())
        .all()
    )
    data = {
        "results": [
            {
                "id": r.id,
                "scale_type": r.scale_type,
                "total_score": r.total_score,
                "emotion_label": r.emotion_label,
                "ai_generated": bool(getattr(r, "ai_generated", False)),
                "llm_backend": getattr(r, "llm_backend", None),
                "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in rs
        ]
    }
    return ok(data, "获取成功")


@app.get("/api/v1/evaluation/result-detail", response_model=ApiResponse)
def result_detail(
    result_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    r = (
        db.query(EvaluationResult)
        .filter(
            EvaluationResult.id == result_id,
            EvaluationResult.user_id == user_id,
        )
        .first()
    )
    if not r:
        return err(404, "记录不存在或无权查看")
    return ok(
        {
            "id": r.id,
            "scale_type": r.scale_type,
            "total_score": r.total_score,
            "emotion_label": r.emotion_label,
            "suggestion": r.suggestion,
            "ai_generated": bool(getattr(r, "ai_generated", False)),
            "llm_backend": getattr(r, "llm_backend", None),
            "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "获取成功",
    )


class AiChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AiChatBody(BaseModel):
    messages: List[AiChatMessage] = Field(min_length=1, max_length=32)


def _looks_like_messages_json_echo(text: str) -> bool:
    """部分小模型会把 API 载荷误当成回复正文输出。"""
    t = (text or "").strip()
    if len(t) < 15 or not t.startswith("{"):
        return False
    head = t[:280].lower()
    return '"messages"' in head


@app.post(
    "/api/v1/ai/chat",
    response_model=ApiResponse,
    summary="心灵树洞多轮对话",
    description=(
        "请求体为 `messages`：OpenAI 风格对话数组，最后一项的 `role` 须为 `user`。\n\n"
        "成功时 `data` 形如 `{\"reply\": \"模型自然语言正文\", \"llm_backend\": \"ollama\"|\"deepseek\"}`，"
        "不会在响应里回显请求中的 `messages`。"
    ),
)
def ai_chat(body: AiChatBody, _: int = Depends(get_current_student_id)):
    if body.messages[-1].role != "user":
        return err(400, "最后一条消息须来自用户")
    if not chat_available():
        return err(
            503,
            "当前为仅 DeepSeek 模式但未配置密钥。请在 .env 设置 DEEPSEEK_API_KEY，"
            "或设置 LLM_PROVIDER=ollama（或 auto 且不配置密钥）以使用免费本机 Ollama。",
        )

    api_messages: list[dict] = [{"role": "system", "content": SYSTEM_COMPANION_CHAT}]
    for m in body.messages:
        api_messages.append({"role": m.role, "content": m.content.strip()})

    res = llm_chat(
        api_messages,
        max_tokens=LLM_CHAT_MAX_TOKENS,
        temperature=LLM_TEMP_CHAT,
        timeout=LLM_TIMEOUT_SEC,
    )
    if not res.text:
        return err(503, res.user_hint or "AI 暂时无法响应，请稍后重试")
    if _looks_like_messages_json_echo(res.text):
        logging.getLogger(__name__).warning("AI 回复疑似误输出 messages JSON 载荷")
        return err(
            503,
            "模型误把对话 JSON 当作内容输出。请重试；若反复出现请更换 Ollama 模型（如 qwen2.5:7b）或检查温度等参数。",
        )
    return ok({"reply": res.text, "llm_backend": res.backend}, "ok")


def _ai_chat_sse_line(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post(
    "/api/v1/ai/chat/stream",
    summary="心灵树洞流式对话（SSE）",
    description=(
        "请求体与 `/api/v1/ai/chat` 相同。响应为 `text/event-stream`，"
        "每行 `data: {\"type\":\"chunk\",\"text\":\"...\"}`，结束为 "
        '`{"type":"done","llm_backend":"..."}` 或 `{"type":"error","message":"..."}`。'
    ),
)
def ai_chat_stream(body: AiChatBody, _: int = Depends(get_current_student_id)):
    if body.messages[-1].role != "user":
        return err(400, "最后一条消息须来自用户")
    if not chat_available():
        return err(
            503,
            "当前为仅 DeepSeek 模式但未配置密钥。请在 .env 设置 DEEPSEEK_API_KEY，"
            "或设置 LLM_PROVIDER=ollama（或 auto 且不配置密钥）以使用免费本机 Ollama。",
        )

    api_messages: list[dict] = [{"role": "system", "content": SYSTEM_COMPANION_CHAT}]
    for m in body.messages:
        api_messages.append({"role": m.role, "content": m.content.strip()})

    def generate():
        acc: list[str] = []
        try:
            for item in iter_llm_chat_sse(
                api_messages,
                max_tokens=LLM_CHAT_MAX_TOKENS,
                temperature=LLM_TEMP_CHAT,
                timeout=LLM_TIMEOUT_SEC,
            ):
                ev = item.get("event")
                if ev == "chunk":
                    t = item.get("text") or ""
                    acc.append(t)
                    yield _ai_chat_sse_line({"type": "chunk", "text": t})
                elif ev == "done":
                    full = "".join(acc)
                    if _looks_like_messages_json_echo(full):
                        logging.getLogger(__name__).warning(
                            "AI 流式回复疑似误输出 messages JSON 载荷"
                        )
                        yield _ai_chat_sse_line(
                            {
                                "type": "error",
                                "message": "模型误把对话 JSON 当作内容输出，请重试或更换模型。",
                            }
                        )
                    else:
                        yield _ai_chat_sse_line(
                            {
                                "type": "done",
                                "llm_backend": item.get("llm_backend"),
                            }
                        )
                elif ev == "error":
                    yield _ai_chat_sse_line(
                        {
                            "type": "error",
                            "message": item.get("message") or "AI 暂时无法响应",
                        }
                    )
        except Exception as e:
            logging.getLogger(__name__).warning("ai/chat/stream: %s", e)
            yield _ai_chat_sse_line(
                {"type": "error", "message": str(e)[:400]}
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class AdminLoginBody(BaseModel):
    username: str
    password: str


def _admin_register_secret_ok(provided: str, expected: str) -> bool:
    if not expected or not provided:
        return False
    p = hashlib.sha256(provided.encode("utf-8")).digest()
    e = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(p, e)


class AdminRegisterBody(BaseModel):
    username: str
    password: str
    confirm_password: str
    register_secret: str


@app.post("/api/v1/admin/register", response_model=ApiResponse)
def admin_register(body: AdminRegisterBody, db: Session = Depends(get_db)):
    if not ADMIN_REGISTER_SECRET:
        return err(403, "管理员自助注册未启用：请在服务端 .env 配置 ADMIN_REGISTER_SECRET")
    if not _admin_register_secret_ok(
        body.register_secret.strip(), ADMIN_REGISTER_SECRET
    ):
        return err(403, "注册密钥错误")
    if body.password != body.confirm_password:
        return err(400, "两次密码不一致")
    if len(body.password) < 6:
        return err(400, "密码长度≥6位")
    uname = body.username.strip()
    if len(uname) < 2:
        return err(400, "用户名至少2个字符")
    exists = db.query(User).filter(User.username == uname).first()
    if exists:
        return err(400, "用户名已存在")
    user = User(
        username=uname,
        password=hash_password(body.password),
        role="admin",
        create_time=datetime.now(),
    )
    db.add(user)
    db.commit()
    return ok({"username": user.username}, "管理员注册成功，请登录")


@app.post("/api/v1/admin/login", response_model=ApiResponse)
def admin_login(body: AdminLoginBody, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(
            User.username == body.username,
            User.role == "admin",
        )
        .first()
    )
    if not user or not verify_password(body.password, user.password):
        return err(400, "账号或密码错误")
    token = create_access_token(str(user.id), "admin")
    return ok(
        {
            "access_token": token,
            "token_type": "bearer",
            "admin_id": user.id,
            "username": user.username,
        },
        "登录成功",
    )


@app.get("/api/v1/admin/check-permission", response_model=ApiResponse)
def admin_check_permission(_: int = Depends(get_current_admin_id)):
    return ok({"permission": True}, "权限验证通过")


@app.get("/api/v1/admin/info", response_model=ApiResponse)
def admin_info(
    db: Session = Depends(get_db),
    admin_id: int = Depends(get_current_admin_id),
):
    u = db.query(User).filter(User.id == admin_id).first()
    if not u:
        return err(400, "用户不存在")
    data = {
        "admin_id": u.id,
        "username": u.username,
        "role": u.role,
        "register_time": u.create_time.strftime("%Y-%m-%d"),
    }
    return ok(data, "获取成功")


class AdminChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/v1/admin/change-password", response_model=ApiResponse)
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


@app.get("/api/v1/admin/statistic/emotion", response_model=ApiResponse)
def statistic_emotion(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    db: Session = Depends(get_db),
    _: int = Depends(get_current_admin_id),
):
    query = db.query(EvaluationResult)
    if start_time:
        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d")
            query = query.filter(EvaluationResult.create_time >= start_dt)
        except ValueError:
            pass
    if end_time:
        try:
            end_dt = datetime.strptime(end_time, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(EvaluationResult.create_time < end_dt)
        except ValueError:
            pass

    stats: dict[str, int] = {}
    for r in query.all():
        stats[r.emotion_label] = stats.get(r.emotion_label, 0) + 1

    data = {
        "emotion_stats": [
            {"label": label, "count": count} for label, count in stats.items()
        ]
    }
    return ok(data, "获取成功")


@app.get("/api/v1/admin/statistic/scale", response_model=ApiResponse)
def statistic_scale(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    db: Session = Depends(get_db),
    _: int = Depends(get_current_admin_id),
):
    query = db.query(EvaluationResult)
    if start_time:
        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d")
            query = query.filter(EvaluationResult.create_time >= start_dt)
        except ValueError:
            pass
    if end_time:
        try:
            end_dt = datetime.strptime(end_time, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(EvaluationResult.create_time < end_dt)
        except ValueError:
            pass
    stats: dict[str, int] = {}
    for r in query.all():
        stats[r.scale_type] = stats.get(r.scale_type, 0) + 1

    data = {
        "scale_stats": [
            {"scale_type": scale_type, "count": count}
            for scale_type, count in stats.items()
        ]
    }
    return ok(data, "获取成功")


class ExportDataBody(BaseModel):
    export_type: str


@app.post("/api/v1/admin/export-data", response_model=ApiResponse)
def admin_export_data(
    body: ExportDataBody,
    _: int = Depends(get_current_admin_id),
):
    _ = body
    return ok(
        {
            "hint": "请使用「导出测评 CSV」按钮下载文件",
            "download_path": "/api/v1/admin/export/evaluations.csv",
        },
        "请使用 GET /api/v1/admin/export/evaluations.csv 携带管理员 Token 下载",
    )


@app.get("/api/v1/admin/export/evaluations.csv")
def admin_export_evaluations_csv(
    db: Session = Depends(get_db),
    _: int = Depends(get_current_admin_id),
):
    rows = (
        db.query(EvaluationResult, User.username)
        .join(User, EvaluationResult.user_id == User.id)
        .order_by(EvaluationResult.create_time.desc())
        .all()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "username",
            "scale_type",
            "total_score",
            "emotion_label",
            "ai_generated",
            "llm_backend",
            "create_time",
        ]
    )
    for r, username in rows:
        w.writerow(
            [
                r.id,
                username,
                r.scale_type,
                r.total_score,
                r.emotion_label,
                "1" if bool(getattr(r, "ai_generated", False)) else "0",
                getattr(r, "llm_backend", None) or "",
                r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="evaluations_export.csv"'
        },
    )


@app.get("/api/v1/admin/evaluation/list", response_model=ApiResponse)
def admin_evaluation_list(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: int = Depends(get_current_admin_id),
):
    query = (
        db.query(EvaluationResult)
        .join(User, EvaluationResult.user_id == User.id)
        .order_by(EvaluationResult.create_time.desc())
    )
    total = query.count()
    page_items = query.offset((page - 1) * size).limit(size).all()

    data_list = []
    for r in page_items:
        username = r.user.username if r.user else ""
        data_list.append(
            {
                "id": r.id,
                "username": username,
                "scale_type": r.scale_type,
                "total_score": r.total_score,
                "emotion_label": r.emotion_label,
                "ai_generated": bool(getattr(r, "ai_generated", False)),
                "llm_backend": getattr(r, "llm_backend", None),
                "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return ok({"total": total, "list": data_list}, "获取成功")


@app.get("/api/v1/resource/list", response_model=ApiResponse)
def resource_list(
    type: Optional[str] = Query(None, pattern="^(article|audio)$"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = db.query(MentalResource)
    if type:
        query = query.filter(MentalResource.type == type)

    total = query.count()
    items = (
        query.order_by(MentalResource.create_time.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    data = {
        "total": total,
        "list": [
            {
                "id": r.id,
                "title": r.title,
                "type": r.type,
                "content": r.content,
                "url": r.url,
                "create_time": r.create_time.strftime("%Y-%m-%d"),
            }
            for r in items
        ],
    }
    return ok(data, "获取成功")


@app.get("/api/v1/resource/detail", response_model=ApiResponse)
def resource_detail(id: int = Query(...), db: Session = Depends(get_db)):
    r = db.query(MentalResource).filter(MentalResource.id == id).first()
    if not r:
        return err(400, "资源不存在")
    data = {
        "id": r.id,
        "title": r.title,
        "type": r.type,
        "content": r.content,
        "url": r.url,
        "create_time": r.create_time.strftime("%Y-%m-%d"),
    }
    return ok(data, "获取成功")


class AppointmentAddBody(BaseModel):
    date: str
    time: str
    content: Optional[str] = ""


@app.post("/api/v1/appointment/add", response_model=ApiResponse)
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
        )
        .first()
    )
    if dup:
        return err(400, "该时段您已有预约，请勿重复提交")

    appt = CounselingAppointment(
        user_id=user_id,
        date=d,
        time=body.time,
        content=body.content,
        status="已预约",
        create_time=datetime.now(),
    )
    db.add(appt)
    db.commit()
    data = {
        "appointment_id": appt.id,
        "date": body.date,
        "time": body.time,
    }
    return ok(data, "预约成功")


@app.get("/api/v1/appointment/my-list", response_model=ApiResponse)
def appointment_my_list(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    items = (
        db.query(CounselingAppointment)
        .filter(CounselingAppointment.user_id == user_id)
        .order_by(CounselingAppointment.date.desc(), CounselingAppointment.time.desc())
        .all()
    )
    data = {
        "appointments": [
            {
                "id": a.id,
                "date": a.date.strftime("%Y-%m-%d"),
                "time": a.time,
                "content": a.content,
                "status": a.status,
            }
            for a in items
        ]
    }
    return ok(data, "获取成功")


class AppointmentCancelBody(BaseModel):
    appointment_id: int


@app.post("/api/v1/appointment/cancel", response_model=ApiResponse)
def appointment_cancel(
    body: AppointmentCancelBody,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    a = (
        db.query(CounselingAppointment)
        .filter(CounselingAppointment.id == body.appointment_id)
        .first()
    )
    if not a:
        return err(400, "预约不存在")
    if a.user_id != user_id:
        return err(403, "无权取消他人预约")
    if a.status != "已预约":
        return err(400, "仅可取消状态为「已预约」的记录")
    a.status = "已取消"
    db.commit()
    return ok({}, "取消成功")


@app.get("/api/v1/user/info", response_model=ApiResponse)
def user_info(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_student_id),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return err(400, "用户不存在")
    data = {
        "username": u.username,
        "register_time": u.create_time.strftime("%Y-%m-%d"),
    }
    return ok(data, "获取成功")


@app.get("/api/v1/ai/public-config", response_model=ApiResponse)
def ai_public_config():
    """不鉴权：仅告知是否配置密钥，便于前端展示提示（不包含任何敏感信息）。"""
    return ok(
        {
            "deepseek_configured": bool(DEEPSEEK_API_KEY),
            "llm_provider": LLM_PROVIDER,
            "ollama_model": OLLAMA_MODEL,
            "ollama_base_url": OLLAMA_BASE_URL,
            "ollama_effective_url": ollama_effective_base_url(),
            "chat_available": chat_available(),
            "free_local_tip": (
                f"免费本机对话：安装 Ollama 后执行 ollama pull {OLLAMA_MODEL}，"
                "并设置 LLM_PROVIDER=ollama（或保持 auto 且不配置 DeepSeek 密钥）"
            ),
        },
        "ok",
    )


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
