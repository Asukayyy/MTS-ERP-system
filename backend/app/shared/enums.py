"""跨模块共享枚举。

只放**被两个及以上模块共同引用**的枚举；
只属于单个模块的业务枚举请定义在该模块的 `models.py` / `schemas.py` 中，避免公共层膨胀。
"""

from enum import Enum


class ModuleName(str, Enum):
    """系统五个业务模块的标识。"""

    SYSTEM = "system"
    SALES = "sales"
    PLANNING = "planning"
    PROCUREMENT = "procurement"
    INVENTORY = "inventory"


class ModuleStatus(str, Enum):
    """模块运行状态，用于占位健康检查接口。"""

    UP = "up"
    DOWN = "down"


class AppStatus(str, Enum):
    """应用级状态。"""

    OK = "ok"
    DEGRADED = "degraded"
