"""数据库基础设施：引擎、会话、声明式基类。

本文件只提供**框架级**能力，不定义任何 ERP 业务表。

注意：`create_engine()` 是惰性的，不会在 import 时真正连接 MySQL，
因此本机没装 MySQL 也能正常 import 本模块、启动应用并访问健康检查接口。
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。

    各模块的 `models.py` 统一继承本类，Alembic 通过 `Base.metadata` 自动收集表结构。
    当前 `Base.metadata` 中**没有任何业务表**，业务表由模块负责人在自己模块的 `models.py` 中定义。
    """


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供一个请求级数据库会话，请求结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
