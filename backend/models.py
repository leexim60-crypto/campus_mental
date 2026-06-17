from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from database import Base

"""
用户实体 ORM 模型，映射数据库中的 user 表。
Attributes:
        id (int): 用户唯一主键，自增且建立索引。
        username (str): 用户名，必须唯一且不能为空。
        password (str): 用户密码（建议存储哈希值），不能为空。
        role (str): 用户角色（如 student, admin 等），默认为 'student'。
        create_time (datetime): 账户创建时间，默认为当前时间。
"""
class User(Base):
    __tablename__ = "user"

    id: int = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username: str = Column(String(50), unique=True, nullable=False)
    password: str = Column(String(255), nullable=False)
    role: str = Column(String(20), nullable=False, default="student")
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)

"""
    评价问卷题目 ORM 模型，映射数据库中的 evaluation_question 表。
    Attributes:
        id (int): 题目的唯一主键，自增。
        scale_type (str): 量表/问卷类型（如 'mbti', 'big_five' 等），不能为空。
        content (str): 题目的具体文本内容，不能为空。
        sort (int): 题目的展示排序权重，默认为 0。
"""
class EvaluationQuestion(Base):
    __tablename__ = "evaluation_question"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    scale_type: str = Column(String(20), nullable=False)
    content: str = Column(String(200), nullable=False)
    sort: int = Column(Integer, nullable=False, default=0)

"""
    评价结果/测评报告 ORM 模型，映射数据库中的 evaluation_result 表。
    Attributes:
        id (int): 测评结果的唯一主键，自增。
        user_id (int): 关联的用户 ID（外键），不能为空。
        scale_type (str): 测评的量表/问卷类型，不能为空。
        total_score (int): 量表计算的总分，默认为 0。
        emotion_label (str): 测评得出的情感标签或诊断结果，不能为空。
        suggestion (str): 针对测评结果的个性化建议（通常由 AI 生成），不能为空。
        ai_generated (bool): 标记该建议是否由 AI 生成，默认为 False。
        llm_backend (Optional[str]): 实际生成建议的大模型后端标识（如 'deepseek', 'ollama'），可为空。
        create_time (datetime): 测评结果的生成时间，默认为当前时间。
        user (User): 关联的用户 ORM 对象（关系映射）。
    """
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
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)

    user = relationship("User")

"""
    心理健康资源 ORM 模型，映射数据库中的 mental_resource 表。
    Attributes:
        id (int): 资源的唯一主键，自增。
        title (str): 资源标题，不能为空。
        type (str): 资源类型（如 'article', 'video', 'external_link' 等），不能为空。
        content (Optional[str]): 资源的正文内容（富文本或纯文本），可为空。
        url (Optional[str]): 外部资源链接，可为空。
        create_time (datetime): 资源的创建/发布时间，默认为当前时间。
"""
class MentalResource(Base):
    __tablename__ = "mental_resource"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    title: str = Column(String(100), nullable=False)
    type: str = Column(String(20), nullable=False)
    content: Optional[str] = Column(Text, nullable=True)
    url: Optional[str] = Column(String(200), nullable=True)
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)


"""
    心理咨询预约 ORM 模型，映射数据库中的 counseling_appointment 表。
    Attributes:
        id (int): 预约记录的唯一主键，自增。
        user_id (int): 发起预约的用户 ID（外键），不能为空。
        date (date): 预约的日期，不能为空。
        time (str): 预约的具体时间段（如 '14:00-15:00'），不能为空。
        content (Optional[str]): 用户的咨询诉求、问题描述或备注，可为空。
        status (str): 预约状态（如 '已预约', '已完成', '已取消'），默认为 '已预约'。
        create_time (datetime): 预约记录的创建时间，默认为当前时间。
        user (User): 关联的用户 ORM 对象（关系映射）。
"""
class CounselingAppointment(Base):
    __tablename__ = "counseling_appointment"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("user.id"), nullable=False)
    date: date = Column(Date, nullable=False)
    time: str = Column(String(20), nullable=False)
    content: Optional[str] = Column(Text, nullable=True)
    status: str = Column(String(20), nullable=False, default="已预约")
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)

    user = relationship("User")
