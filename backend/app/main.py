"""BH-ERP 后端应用入口。

职责：
1. 创建 FastAPI 应用实例
2. 注册 CORS 与统一异常处理
3. 把五个业务模块的路由统一挂载到 `/api/v1/<module>` 前缀下

新增接口请写在**对应模块的 router.py** 中，不要直接改本文件（除非是新增模块）。
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.exceptions import register_exception_handlers
from app.common.response import ApiResponse
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.inventory.router import router as inventory_router
from app.modules.planning.router import router as planning_router
from app.modules.procurement.router import router as procurement_router
from app.modules.sales.router import router as sales_router
from app.modules.system.router import router as system_router
from app.modules.system.seed import seed_roles_and_permissions
from app.shared.enums import AppStatus, ModuleName
from app.shared.types import AppHealthData

logger = logging.getLogger(__name__)

# 模块路由注册表：(模块标识, 模块路由器)
# 最终前缀为 /api/v1/<模块标识>
MODULE_ROUTERS = (
    (ModuleName.SYSTEM, system_router),
    (ModuleName.SALES, sales_router),
    (ModuleName.PLANNING, planning_router),
    (ModuleName.PROCUREMENT, procurement_router),
    (ModuleName.INVENTORY, inventory_router),
)


@asynccontextmanager
async def lifespan(_application: FastAPI):
    """应用生命周期：启动时幂等写入 RBAC 种子数据。

    种子写入九种身份角色、权限资源树与角色-权限绑定（按编码存在即跳过）。
    共享数据库暂时不可用（如 Tailscale 未连上）时只告警，不阻断应用启动。
    """
    try:
        with SessionLocal() as db:
            seed_roles_and_permissions(db)
    except Exception:
        logger.warning("RBAC 种子初始化失败（数据库不可用？），将在下次启动时重试", exc_info=True)
    yield


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "基于转椅 BOM 与主生产计划 MPS 的 Web 版 MTS ERP 系统。"
            "已实现 system / sales / planning / procurement / inventory 五个模块，"
            "含多层 BOM 展开 MRP 引擎与课程转椅数据的端到端闭环。"
        ),
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)

    for module, router in MODULE_ROUTERS:
        application.include_router(router, prefix=f"{settings.API_V1_PREFIX}/{module.value}")

    @application.get(
        "/health",
        response_model=ApiResponse[AppHealthData],
        tags=["app"],
        summary="应用健康检查",
    )
    def health() -> ApiResponse[AppHealthData]:
        """应用级健康检查，不访问数据库。"""
        return ApiResponse(
            data=AppHealthData(
                name=settings.APP_NAME,
                version=settings.APP_VERSION,
                status=AppStatus.OK.value,
            )
        )

    return application


app = create_app()
