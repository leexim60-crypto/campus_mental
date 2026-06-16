from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "user"

    id: int = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username: str = Column(String(50), unique=True, nullable=False)
    password: str = Column(String(255), nullable=False)
    role: str = Column(String(20), nullable=False, default="student")
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)


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
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)

    user = relationship("User")


class MentalResource(Base):
    __tablename__ = "mental_resource"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    title: str = Column(String(100), nullable=False)
    type: str = Column(String(20), nullable=False)
    content: Optional[str] = Column(Text, nullable=True)
    url: Optional[str] = Column(String(200), nullable=True)
    create_time: datetime = Column(DateTime, nullable=False, default=datetime.now)


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
