"""BH-ERP 后端应用入口。

职责：
1. 创建 FastAPI 应用实例
2. 注册 CORS 与统一异常处理
3. 把五个业务模块的路由统一挂载到 `/api/v1/<module>` 前缀下

新增接口请写在**对应模块的 router.py** 中，不要直接改本文件（除非是新增模块）。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.exceptions import register_exception_handlers
from app.common.response import ApiResponse
from app.core.config import settings
from app.modules.inventory.router import router as inventory_router
from app.modules.planning.router import router as planning_router
from app.modules.procurement.router import router as procurement_router
from app.modules.sales.router import router as sales_router
from app.modules.system.router import router as system_router
from app.shared.enums import AppStatus, ModuleName
from app.shared.types import AppHealthData

# 模块路由注册表：(模块标识, 模块路由器)
# 最终前缀为 /api/v1/<模块标识>
MODULE_ROUTERS = (
    (ModuleName.SYSTEM, system_router),
    (ModuleName.SALES, sales_router),
    (ModuleName.PLANNING, planning_router),
    (ModuleName.PROCUREMENT, procurement_router),
    (ModuleName.INVENTORY, inventory_router),
)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "基于转椅 BOM 与主生产计划 MPS 的 Web 版 MTS ERP 系统。"
            "当前为**基础工程框架**，业务功能尚未实现。"
        ),
        debug=settings.DEBUG,
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
