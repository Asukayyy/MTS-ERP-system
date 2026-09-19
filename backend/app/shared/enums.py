"""跨模块共享枚举。

只放**被两个及以上模块共同引用**的枚举；
只属于单个模块的业务枚举请定义在该模块的 `models.py` / `schemas.py` 中，避免公共层膨胀。

约定（规格 §23 / §25）：所有业务状态使用**明确枚举**（字符串），
不使用 0/1/2/3 这类魔法数字；数据库以 `VARCHAR(20)` + `CHECK` 约束落地。
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


class RecordStatus(str, Enum):
    """基础数据（物料 / BOM / 客户 / 供应商 等）的启用状态。

    规格 §20：已被业务引用的数据不物理删除，改为 `INACTIVE`。
    """

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class MaterialType(str, Enum):
    """统一 Material Master 的物料类型（规格 §8）。"""

    RAW = "RAW"  # 原材料
    PURCHASED = "PURCHASED"  # 采购件
    SEMI = "SEMI"  # 半成品
    FINISHED = "FINISHED"  # 成品


class SupplyType(str, Enum):
    """物料的供应方式：自制 / 采购（决定 MRP 结果的分流方向）。"""

    MAKE = "MAKE"  # 自制（MRP → 生产作业计划）
    BUY = "BUY"  # 采购（MRP → 采购计划）


class DocStatus(str, Enum):
    """单据基础状态机（规格 §25）。

    不同业务单据使用适合自己的子集；各表通过 `CHECK` 约束限定允许值。
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InventoryTxnType(str, Enum):
    """库存流水类型（规格 §24 / §36）。"""

    IN = "IN"  # 入库（采购到货 / 生产完工 / 销售退货）
    OUT = "OUT"  # 出库（销售发货 / 生产领料）
    TRANSFER_IN = "TRANSFER_IN"  # 移库入库
    TRANSFER_OUT = "TRANSFER_OUT"  # 移库出库
    ADJUST = "ADJUST"  # 盘点调整


class InventorySourceType(str, Enum):
    """库存流水的来源业务类型，用于可追溯性（规格 §24）。"""

    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    PRODUCTION_COMPLETION = "PRODUCTION_COMPLETION"
    MATERIAL_REQUISITION = "MATERIAL_REQUISITION"
    SALES_SHIPMENT = "SALES_SHIPMENT"
    SALES_RETURN = "SALES_RETURN"
    TRANSFER = "TRANSFER"
    STOCKTAKE = "STOCKTAKE"
    MANUAL = "MANUAL"


class ReplenishmentSource(str, Enum):
    """补库需求来源：订货点触发采购 / 生产补库（规格 §14）。"""

    REORDER = "REORDER"  # 库存不足 → 采购补货
    PRODUCTION = "PRODUCTION"  # 库存不足 → 生产补库 → Planning 形成正式生产计划


class MrpSourceType(str, Enum):
    """MRP / 计划需求的来源类型。"""

    SALES = "SALES"  # 销售订单 / 预测
    STOCKFILL = "STOCKFILL"  # 库存补库需求
    MPS = "MPS"  # 主生产计划