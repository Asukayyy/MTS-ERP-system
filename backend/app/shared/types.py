"""跨模块共享数据类型。

用于模块之间、以及前后端之间需要保持一致的基础结构。
业务实体类型请定义在各模块自己的 `schemas.py` 中。
"""

from pydantic import BaseModel, Field


class HealthData(BaseModel):
    """模块占位健康检查返回体，五个模块结构完全一致。"""

    module: str = Field(description="模块标识，如 sales")
    status: str = Field(description="模块状态，当前固定为 up")


class AppHealthData(BaseModel):
    """应用级健康检查返回体。"""

    name: str = Field(description="应用名称")
    version: str = Field(description="应用版本")
    status: str = Field(description="应用状态")
