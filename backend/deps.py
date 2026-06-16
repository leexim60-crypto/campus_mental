from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import User
from security import decode_access_token

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


def get_current_student_username(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> str:
    if payload.get("role") != "student":
        raise HTTPException(status_code=403, detail="需要学生账号登录")
    uid = int(payload["sub"])
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user.username


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
