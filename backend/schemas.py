from typing import List, Optional

from pydantic import BaseModel, Field


# ── 通用响应 ──────────────────────────────────────────────

class ApiResponse(BaseModel):
    code: int
    msg: str
    data: Optional[dict] = None


def ok(data: Optional[dict] = None, msg: str = "操作成功") -> ApiResponse:
    return ApiResponse(code=200, msg=msg, data=data)


def err(code: int, msg: str) -> ApiResponse:
    return ApiResponse(code=code, msg=msg)


# ── 学生账号 ─────────────────────────────────────────────

class UserLoginBody(BaseModel):
    username: str
    password: str
    remember: Optional[bool] = False


class UserRegisterBody(BaseModel):
    username: str
    password: str
    confirm_password: str


class ResetPasswordBody(BaseModel):
    username: str
    new_password: str


# ── 测评 ─────────────────────────────────────────────────

class CalculateResultBody(BaseModel):
    scale_type: str = Field(pattern="^(PHQ-9|SCL-90|GAD-7|PSS-10|SES)$")
    scores: List[int]


# ── AI 对话 ──────────────────────────────────────────────

class AiChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AiChatBody(BaseModel):
    messages: List[AiChatMessage] = Field(min_length=1, max_length=32)


# ── 管理员 ──────────────────────────────────────────────

class AdminLoginBody(BaseModel):
    username: str
    password: str


class AdminRegisterBody(BaseModel):
    username: str
    password: str
    confirm_password: str
    register_secret: str


class AdminChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


class ExportDataBody(BaseModel):
    export_type: str


# ── 预约 ─────────────────────────────────────────────────

class AppointmentAddBody(BaseModel):
    date: str
    time: str
    content: Optional[str] = ""


class AppointmentCancelBody(BaseModel):
    appointment_id: int
