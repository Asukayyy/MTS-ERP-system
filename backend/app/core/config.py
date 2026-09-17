"""应用配置。

统一从环境变量 / `.env` 读取配置，**禁止在代码里硬编码数据库密码等敏感信息**。

本地开发时把 `backend/.env.example` 复制为 `backend/.env` 并按需修改；
`.env` 已在 .gitignore 中，不会入库。
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项。字段名与 `.env` 中的键名一一对应。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------- 应用 ----------
    APP_NAME: str = "BH-ERP"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    """允许跨域的前端地址，多个用英文逗号分隔。"""
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- MySQL ----------
    # 默认值只用于本地开发占位，真实值请写在 .env 中
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str = "bh_erp"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_CHARSET: str = "utf8mb4"

    # ---------- SQLAlchemy ----------
    DB_ECHO: bool = False
    """连接池参数，课程设计规模下保持默认即可。"""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600

    @property
    def database_url(self) -> str:
        """SQLAlchemy 连接串（PyMySQL 驱动）。"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}"
        )

    @property
    def cors_origin_list(self) -> List[str]:
        """把逗号分隔的 CORS_ORIGINS 解析成列表。"""
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """带缓存的配置读取入口，供依赖注入使用。"""
    return Settings()


settings = get_settings()
