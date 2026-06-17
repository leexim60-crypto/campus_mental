from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


"""
将用户的明文密码转换为不可逆的哈希值（加盐哈希）。
Args:
    plain (str): 用户输入的原始明文密码。
Returns:
    str: 加密后的密码哈希字符串（包含算法标识、工作因子、盐值和哈希值）。
"""
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


"""
    验证明文密码是否与数据库中存储的密码凭证匹配。
    Args:
        plain (str): 用户在登录时输入的原始明文密码。
        stored (str): 数据库中存储的密码凭证（可能是 bcrypt 哈希值，也可能是历史明文）。

    Returns:
        bool: 如果密码匹配返回 True，否则返回 False。
    """
def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        return pwd_context.verify(plain, stored)
    return plain == stored

"""
    生成用于 API 鉴权的 JWT 访问令牌（Access Token）。

    Args:
        subject (str): 令牌的主题，通常为用户的唯一标识（如 user_id 或 username）。
        role (str): 用户的角色权限标识（如 'student', 'admin'），用于后续接口鉴权。
        extra (Optional[dict[str, Any]]): 需要附加到令牌中的额外自定义声明（Claims），默认为 None。
    Returns:
        str: 签名后的 JWT 字符串。
"""
def create_access_token(subject: str, role: str, extra: Optional[dict[str, Any]] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": now,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

"""
    解码并验证 JWT 访问令牌，提取其载荷（Payload）信息。
    Args:
        token (str): 客户端在 HTTP Header 中携带的 JWT 字符串。

    Returns:
        dict[str, Any]: 解码后的 JWT 载荷字典（包含 sub, role, exp, iat 等）。

    Raises:
        jwt.ExpiredSignatureError: 当令牌已超过过期时间（exp）时抛出。
        jwt.InvalidTokenError: 当令牌签名无效、格式错误或算法不匹配时抛出。
    """
def decode_access_token(token: str) -> dict[str, Any]:
    # 1. 使用配置的密钥和算法对令牌进行解码与验签
    # 2. 注意：algorithms 参数必须传入一个列表，这是 PyJWT 2.x+ 版本的强制安全要求
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
