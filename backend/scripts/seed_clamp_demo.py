# -*- coding: utf-8 -*-
"""「大众自动钳」演示数据种子脚本（幂等，可重复执行）。

功能：
1. 清空共享库中全部示例业务数据：计划/销售/采购/库存单据、物料/BOM/工艺路线，
   **保留**组织/人员/账号/角色权限体系（RBAC）与字典数据；
2. 按产品结构图创建 16 个物料（1 成品 + 2 半成品 + 7 自制件 + 6 外购件）；
3. 创建 3 张多层 BOM（成品 → 壳体/支架/配件包 → 零件，与结构图层级一致）；
4. 创建 10 条经典工艺路线（7 个自制零件机加工 + 2 个半成品装配 + 成品总装，共 50 道工序）。

执行方式（cwd = backend）：
    .venv/Scripts/python.exe scripts/seed_clamp_demo.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from app.core.database import SessionLocal, engine
from app.modules.system import models
from app.modules.inventory import models as inv_models
from app.modules.planning import models as pln_models

# ============================ 1. 清空历史示例数据 ============================

# 仅清业务示例，RBAC（organization/personnel/user/role/permission 及字典、日志）不动
TRUNCATE_EXACT = (
    "sys_material",
    "sys_bom",
    "sys_bom_item",
    "sys_routing",
    "sys_routing_operation",
)


def clear_demo_data() -> list[str]:
    """TRUNCATE 所有业务示例表（动态按前缀收集，重跑安全）。"""
    existing = set(inspect(engine).get_table_names())
    targets = sorted(
        t
        for t in existing
        if t in TRUNCATE_EXACT or t.startswith(("pln_", "sal_", "pur_", "inv_"))
    )
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for t in targets:
            conn.execute(text(f"TRUNCATE TABLE {t}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    return targets


# ============================ 2. 物料主数据 ============================

# (编码, 名称, 类型, 供应方式, 规格, 提前期(天), 安全库存)
MATERIALS = [
    # 成品
    ("FG-CLAMP-001", "大众自动钳", "FINISHED", "MAKE", "手动夹紧工装", 2, 0),
    # 半成品（组件）
    ("SF-HOUSING-001", "壳体", "SEMI", "MAKE", "铝合金壳体总成", 3, 0),
    ("SF-KIT-001", "配件包", "SEMI", "MAKE", "标准件配套包", 2, 0),
    # 自制零件（有工艺路线）
    ("RM-HOUSING-L", "左壳体", "SEMI", "MAKE", "铝合金压铸件", 4, 10),
    ("RM-HOUSING-R", "右壳体", "SEMI", "MAKE", "铝合金压铸件", 4, 10),
    ("RM-BRACKET-001", "支架", "SEMI", "MAKE", "冷轧钢板 t=2", 3, 10),
    ("RM-PISTON-001", "活塞", "SEMI", "MAKE", "45# 钢", 3, 5),
    ("RM-SLEEVE-001", "开口导向套管", "SEMI", "MAKE", "铜合金", 3, 5),
    ("RM-FRICTION-001", "摩擦片", "SEMI", "MAKE", "铜基摩擦材料", 3, 5),
    ("RM-SPACER-001", "隔垫", "SEMI", "MAKE", "尼龙 PA66", 2, 5),
    # 外购标准件
    ("RM-SEAL-001", "密封圈", "PURCHASED", "BUY", "NBR 丁腈橡胶", 7, 20),
    ("RM-PLASTIC-001", "塑料套", "PURCHASED", "BUY", "PE 聚乙烯", 7, 20),
    ("RM-RUBBER-001", "橡胶套", "PURCHASED", "BUY", "EPDM 三元乙丙", 7, 20),
    ("RM-VALVE-001", "放气螺栓", "PURCHASED", "BUY", "黄铜 M8", 7, 10),
    ("RM-CAP-001", "防尘帽", "PURCHASED", "BUY", "橡胶", 7, 20),
    ("RM-BOLT-001", "内六角螺栓", "PURCHASED", "BUY", "8.8 级 M6×16", 7, 50),
]

# ============================ 3. BOM 结构（与产品结构图一致） ============================

# (母件编码, BOM版本, [子件编码, 数量, 损耗率, 序号, 提前期偏置])
BOMS = [
    (
        "FG-CLAMP-001",
        [
            ("SF-HOUSING-001", 2, 0, 1, 0),
            ("RM-BRACKET-001", 1, 0, 2, 0),
            ("SF-KIT-001", 1, 0, 3, 0),
        ],
    ),
    (
        "SF-HOUSING-001",
        [
            ("RM-HOUSING-L", 1, 0, 1, 0),
            ("RM-HOUSING-R", 1, 0, 2, 0),
        ],
    ),
    (
        "SF-KIT-001",
        [
            ("RM-SEAL-001", 2, 0, 1, 0),
            ("RM-PISTON-001", 1, 0, 2, 0),
            ("RM-PLASTIC-001", 1, 0, 3, 0),
            ("RM-RUBBER-001", 1, 0, 4, 0),
            ("RM-VALVE-001", 1, 0, 5, 0),
            ("RM-CAP-001", 1, 0, 6, 0),
            ("RM-BOLT-001", 1, 0, 7, 0),
            ("RM-FRICTION-001", 2, 0, 8, 0),
            ("RM-SPACER-001", 1, 0, 9, 0),
            ("RM-SLEEVE-001", 2, 0, 10, 0),
        ],
    ),
]

# ============================ 4. 经典机加工工艺路线 ============================

# (物料编码, [(工序号, 工序编码, 工序名称, 工作中心, 准备工时, 单件工时)])
ROUTINGS = [
    (
        "RM-HOUSING-L",
        [
            (10, "OP-10", "下料", "锯床 G4230", 10, 3),
            (20, "OP-20", "铣平面", "立式铣床 X5042", 15, 8),
            (30, "OP-30", "钻孔", "台钻 Z512", 10, 5),
            (40, "OP-40", "攻丝", "攻丝机 S4016", 10, 4),
            (50, "OP-50", "去毛刺", "钳工台", 5, 3),
            (60, "OP-60", "检验", "检具/三坐标", 5, 6),
        ],
    ),
    (
        "RM-HOUSING-R",
        [
            (10, "OP-10", "下料", "锯床 G4230", 10, 3),
            (20, "OP-20", "铣平面", "立式铣床 X5042", 15, 8),
            (30, "OP-30", "钻孔", "台钻 Z512", 10, 5),
            (40, "OP-40", "攻丝", "攻丝机 S4016", 10, 4),
            (50, "OP-50", "去毛刺", "钳工台", 5, 3),
            (60, "OP-60", "检验", "检具/三坐标", 5, 6),
        ],
    ),
    (
        "RM-BRACKET-001",
        [
            (10, "OP-10", "下料", "剪板机 Q11-3", 10, 2),
            (20, "OP-20", "冲压成型", "冲床 J23-63", 20, 2),
            (30, "OP-30", "钻孔", "台钻 Z512", 10, 3),
            (40, "OP-40", "去毛刺", "钳工台", 5, 2),
            (50, "OP-50", "检验", "检具台", 5, 3),
        ],
    ),
    (
        "RM-PISTON-001",
        [
            (10, "OP-10", "下料", "锯床 G4230", 10, 2),
            (20, "OP-20", "粗车外圆", "车床 CA6140", 15, 6),
            (30, "OP-30", "精车", "数控车 CK6140", 20, 8),
            (40, "OP-40", "磨外圆", "外圆磨 M1332", 15, 6),
            (50, "OP-50", "检验", "检具台", 5, 4),
        ],
    ),
    (
        "RM-SLEEVE-001",
        [
            (10, "OP-10", "下料", "锯床 G4230", 10, 2),
            (20, "OP-20", "车外圆", "车床 CA6140", 15, 5),
            (30, "OP-30", "铣开口", "立式铣床 X5042", 15, 4),
            (40, "OP-40", "去毛刺", "钳工台", 5, 2),
            (50, "OP-50", "检验", "检具台", 5, 3),
        ],
    ),
    (
        "RM-FRICTION-001",
        [
            (10, "OP-10", "配料混料", "混料机", 15, 2),
            (20, "OP-20", "压制成型", "液压机 Y32-100", 20, 3),
            (30, "OP-30", "烧结", "烧结炉", 30, 2),
            (40, "OP-40", "磨削平面", "平面磨 M7130", 15, 5),
            (50, "OP-50", "检验", "检具台", 5, 3),
        ],
    ),
    (
        "RM-SPACER-001",
        [
            (10, "OP-10", "下料", "剪板机 Q11-3", 10, 1),
            (20, "OP-20", "冲裁成型", "冲床 J23-63", 15, 2),
            (30, "OP-30", "去毛刺", "钳工台", 5, 2),
            (40, "OP-40", "检验", "检具台", 5, 2),
        ],
    ),
    (
        "SF-HOUSING-001",
        [
            (10, "OP-10", "领料配套", "配料区", 10, 2),
            (20, "OP-20", "压装组合", "装配台", 15, 4),
            (30, "OP-30", "紧固", "装配台", 10, 3),
            (40, "OP-40", "检验", "检验台", 5, 3),
        ],
    ),
    (
        "SF-KIT-001",
        [
            (10, "OP-10", "领料配套", "配料区", 10, 2),
            (20, "OP-20", "分拣配套", "配料区", 10, 3),
            (30, "OP-30", "装包", "包装台", 5, 2),
            (40, "OP-40", "检验", "检验台", 5, 2),
        ],
    ),
    (
        "FG-CLAMP-001",
        [
            (10, "OP-10", "领料配套", "配料区", 15, 2),
            (20, "OP-20", "部件预装", "装配台", 20, 6),
            (30, "OP-30", "总装", "装配线", 20, 8),
            (40, "OP-40", "气密/功能调试", "试验台", 15, 6),
            (50, "OP-50", "终检", "检验台", 10, 5),
            (60, "OP-60", "包装入库", "包装台", 10, 3),
        ],
    ),
]


# ============================ 5. 演示业务数据 ============================

# (仓库编码, 仓库名称)
WAREHOUSES = [
    ("WH-FG-01", "成品库"),
    ("WH-SF-01", "半成品库"),
    ("WH-RM-01", "原料库"),
]

# 市场需求 1000：pln_demand（source_type=SALES）
DEMO_DEMAND = {
    "demand_no": "DM-2026-0001",
    "source_type": "SALES",
    "material_code": "FG-CLAMP-001",
    "quantity": 1000,
    "due_date": date(2026, 11, 30),
    "status": "CONFIRMED",
}

# 计划生产 500：pln_mps + 行
DEMO_MPS = {
    "mps_no": "MPS-2026-0001",
    "plan_year": 2026,
    "start_date": date(2026, 11, 1),
    "end_date": date(2026, 11, 30),
    "status": "CONFIRMED",
    "item": {
        "material_code": "FG-CLAMP-001",
        "period_label": "2026-11",
        "planned_qty": 500,
    },
}

# 成品初始库存 500
DEMO_STOCK = {
    "warehouse_code": "WH-FG-01",
    "material_code": "FG-CLAMP-001",
    "quantity": 500,
}

# ============================ 6. 主流程 ============================


def seed() -> None:
    cleared = clear_demo_data()
    print(f"[1/5] 已清空示例表 {len(cleared)} 张：{', '.join(cleared)}")

    db = SessionLocal()
    try:
        # 物料
        mat_ids: dict[str, int] = {}
        op_count = 0
        for code, name, mtype, supply, spec, lead, safety in MATERIALS:
            m = models.SysMaterial(
                material_code=code,
                material_name=name,
                material_type=mtype,
                supply_type=supply,
                specification=spec,
                material_group="大众自动钳项目",
                lead_time_days=lead,
                safety_stock=Decimal(safety),
                standard_cost=Decimal(0),
                status="ACTIVE",
            )
            db.add(m)
            db.flush()
            mat_ids[code] = m.id
        print(f"[2/5] 已创建物料 {len(mat_ids)} 个（成品 1 / 半成品 2 / 自制件 7 / 外购件 6）")

        # BOM
        for parent, items in BOMS:
            bom = models.SysBom(
                bom_code=f"BOM-{parent}",
                material_id=mat_ids[parent],
                bom_version="V1.0",
                effective_date=date.today(),
                is_active=True,
                status="ACTIVE",
            )
            db.add(bom)
            db.flush()
            for child, qty, scrap, seq, offset in items:
                db.add(
                    models.SysBomItem(
                        bom_id=bom.id,
                        material_id=mat_ids[child],
                        quantity=Decimal(qty),
                        scrap_rate=Decimal(scrap),
                        sequence_no=seq,
                        lead_time_offset=offset,
                    )
                )
        print(f"[3/5] 已创建 BOM {len(BOMS)} 张（含多层结构）")

        # 工艺路线
        for material_code, ops in ROUTINGS:
            routing = models.SysRouting(
                routing_code=f"ROUT-{material_code}",
                material_id=mat_ids[material_code],
                routing_version="V1.0",
                status="ACTIVE",
            )
            db.add(routing)
            db.flush()
            for seq, op_code, op_name, wc, setup, run in ops:
                db.add(
                    models.SysRoutingOperation(
                        routing_id=routing.id,
                        sequence_no=seq,
                        operation_code=op_code,
                        operation_name=op_name,
                        work_center=wc,
                        setup_time=Decimal(setup),
                        run_time=Decimal(run),
                    )
                )
                op_count += 1
        print(f"[4/5] 已创建工艺路线 {len(ROUTINGS)} 条、工序 {op_count} 道")

        # 仓库 + 成品库存 500 + 市场需求 1000 + 计划生产 500
        wh_ids: dict[str, int] = {}
        for code, name in WAREHOUSES:
            wh = inv_models.InvWarehouse(warehouse_code=code, warehouse_name=name, status="ACTIVE")
            db.add(wh)
            db.flush()
            wh_ids[code] = wh.id

        db.add(
            inv_models.InvBalance(
                warehouse_id=wh_ids[DEMO_STOCK["warehouse_code"]],
                material_id=mat_ids[DEMO_STOCK["material_code"]],
                quantity=Decimal(DEMO_STOCK["quantity"]),
                locked_quantity=Decimal(0),
            )
        )

        db.add(
            pln_models.PlnDemand(
                demand_no=DEMO_DEMAND["demand_no"],
                source_type=DEMO_DEMAND["source_type"],
                material_id=mat_ids[DEMO_DEMAND["material_code"]],
                quantity=Decimal(DEMO_DEMAND["quantity"]),
                due_date=DEMO_DEMAND["due_date"],
                status=DEMO_DEMAND["status"],
                remark="市场销售需求（演示数据）",
            )
        )

        mps = pln_models.PlnMps(
            mps_no=DEMO_MPS["mps_no"],
            mps_name="大众自动钳 11 月主生产计划",
            plan_year=DEMO_MPS["plan_year"],
            start_date=DEMO_MPS["start_date"],
            end_date=DEMO_MPS["end_date"],
            status=DEMO_MPS["status"],
        )
        db.add(mps)
        db.flush()
        item = DEMO_MPS["item"]
        db.add(
            pln_models.PlnMpsItem(
                mps_id=mps.id,
                material_id=mat_ids[item["material_code"]],
                period_label=item["period_label"],
                planned_qty=Decimal(item["planned_qty"]),
                finished_qty=Decimal(0),
                start_date=DEMO_MPS["start_date"],
                end_date=DEMO_MPS["end_date"],
                status="CONFIRMED",
            )
        )
        print(
            f"[5/5] 已创建仓库 {len(WAREHOUSES)} 个、成品库存 {DEMO_STOCK['quantity']}、"
            f"市场需求 {DEMO_DEMAND['quantity']}、计划生产 {item['planned_qty']}"
        )

        db.commit()
        print("种子执行完成，数据已写入共享库。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()