from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import User
from security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=True)


"""
    提取并验证 JWT Token 的依赖注入函数。

    工作流程：
    1. 自动从请求头中提取 Bearer Token。
    2. 调用 decode_access_token 解析 Token 载荷（Payload）。
    3. 若 Token 无效或过期，抛出 401 异常拦截请求。
    4. 若验证通过，返回包含用户信息的字典。
"""
def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="无效或过期的登录状态")


"""
    获取当前登录学生的 ID，并进行学生角色权限校验。

    工作流程：
    1. 依赖 get_token_payload 获取已验证的 Token 载荷。
    2. 校验载荷中的 role 字段是否为 "student"，若非学生角色则抛出 403 异常。
    3. 校验通过后，提取载荷中的 sub 字段（用户ID）并转为整数返回。
"""
def get_current_student_id(payload: dict = Depends(get_token_payload)) -> int:
    if payload.get("role") != "student":
        raise HTTPException(status_code=403, detail="需要学生账号登录")
    return int(payload["sub"])

"""
    获取当前登录学生的用户名，包含角色校验与数据库存在性校验。

    工作流程：
    1. 依赖 get_token_payload 验证 Token 并获取载荷。
    2. 校验载荷中的 role 字段是否为 "student"，否则抛出 403 异常。
    3. 根据载荷中的 sub (用户ID) 查询数据库，若用户不存在则抛出 401 异常。
    4. 校验全部通过后，返回该学生的 username。
"""
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


"""
    获取当前登录管理员的 ID，包含角色权限校验与数据库双重存在性校验。

    1. 依赖 get_token_payload 验证 Token 并获取载荷。
    2. 校验载荷中的 role 字段是否为 "admin"，否则抛出 403 异常。
    3. 根据载荷中的 sub (用户ID) 和 role="admin" 联合查询数据库，
       防止管理员被删除或降级后旧 Token 依然有效。若查无此人则抛出 401 异常。
    4. 校验全部通过后，返回该管理员的 ID。
"""
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
