from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


"""
    数据库会话（Session）生成器，用于 FastAPI 的依赖注入。

    工作流程：
    1. 请求开始前：创建并返回一个新的数据库会话。
    2. 请求处理中：将 db 会话注入到路由处理函数中。
    3. 请求结束后：无论业务逻辑是否抛出异常，都会通过 finally 块安全关闭会话，
       有效防止数据库连接泄漏。
"""
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

