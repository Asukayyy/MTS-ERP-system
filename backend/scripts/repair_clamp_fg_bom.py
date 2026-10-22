# -*- coding: utf-8 -*-
"""修复「大众自动钳」成品 BOM 为真实结构（幂等，可重复执行）。

背景：共享库中 FG-CLAMP-001 的成品 BOM 曾被改成版本 "1.0"、只剩 2 个子项且未激活。
BOM 结构树只沿"当前激活 + 启用"的 BOM 递归，因此左侧结构树展开后看不到任何子项。

本脚本以 `seed_clamp_demo.BOMS` 中 FG-CLAMP-001 的定义为准，把该 BOM 修回真实结构：
    壳体 SF-HOUSING-001  ×2  损耗 1%  提前期偏置 3 天
    支架 RM-BRACKET-001  ×1  损耗 1%  提前期偏置 3 天
    配件包 SF-KIT-001    ×1  损耗 1%  提前期偏置 2 天
只动 FG-CLAMP-001 这一张 BOM，不清空任何其它数据。

执行方式（cwd = backend）：
    .venv/Scripts/python.exe scripts/repair_clamp_fg_bom.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.modules.system import models, service
from app.modules.system import repository as repo
from app.modules.system.schemas import BomCreate, BomItemCreate

PARENT_CODE = "FG-CLAMP-001"
REAL_VERSION = "V1.0"
REAL_BOM_CODE = "BOM-FG-CLAMP-001"
LEGACY_VERSION = "1.0"

# (子件编码, 用量, 损耗率, 序号, 提前期偏置)
REAL_ITEMS = [
    ("SF-HOUSING-001", "2", "0.01", 1, 3),
    ("RM-BRACKET-001", "1", "0.01", 2, 3),
    ("SF-KIT-001", "1", "0.01", 3, 2),
]


def _material_id(db, code: str) -> int:
    row = (
        db.query(models.SysMaterial)
        .filter(models.SysMaterial.material_code == code)
        .first()
    )
    if row is None:
        raise SystemExit(f"物料不存在：{code}")
    return row.id


def main() -> None:
    db = SessionLocal()
    try:
        parent_id = _material_id(db, PARENT_CODE)
        wanted = {
            _material_id(db, code): (Decimal(qty), Decimal(scrap), seq, offset)
            for code, qty, scrap, seq, offset in REAL_ITEMS
        }

        bom = repo.get_bom_by_material_version(db, parent_id, REAL_VERSION)
        if bom is None:
            legacy = repo.get_bom_by_material_version(db, parent_id, LEGACY_VERSION)
            if legacy is None:
                bom = service.create_bom(
                    db,
                    BomCreate(
                        bom_code=REAL_BOM_CODE,
                        material_id=parent_id,
                        bom_version=REAL_VERSION,
                        effective_date=date.today(),
                        is_active=True,
                        status="ACTIVE",
                        items=[
                            BomItemCreate(
                                material_id=mid,
                                quantity=qty,
                                scrap_rate=scrap,
                                sequence_no=seq,
                                lead_time_offset=offset,
                            )
                            for mid, (qty, scrap, seq, offset) in sorted(
                                wanted.items(), key=lambda kv: kv[1][2]
                            )
                        ],
                    ),
                )
                print(f"已新建 {REAL_BOM_CODE}（版本 {REAL_VERSION}），子项 {len(wanted)} 条")
            else:
                bom = legacy
                bom.bom_version = REAL_VERSION
                print(f"已把版本 {LEGACY_VERSION} 的记录改回 {REAL_VERSION}")

        bom.bom_code = REAL_BOM_CODE
        bom.effective_date = bom.effective_date or date.today()
        bom.expiry_date = None

        # 子项按真实结构对齐：缺的补、多的删、已有的一律覆盖为真实值
        existing = {item.material_id: item for item in repo.list_bom_items(db, bom.id)}
        for mid, (qty, scrap, seq, offset) in wanted.items():
            item = existing.pop(mid, None)
            if item is None:
                item = models.SysBomItem(bom_id=bom.id, material_id=mid)
                db.add(item)
                print(f"  补充子件 {mid}")
            item.quantity = qty
            item.scrap_rate = scrap
            item.sequence_no = seq
            item.lead_time_offset = offset
        for mid, item in existing.items():
            db.delete(item)
            print(f"  移除多余子件 {mid}")
        db.flush()

        # 状态与激活位保持一致：保证它是该物料唯一的激活版本
        bom.status = "ACTIVE"
        repo.deactivate_other_boms(db, parent_id, bom.id)
        bom.is_active = True
        db.commit()

        # 用与页面同一个契约函数验证：结构树能不能看到子项
        tree = service.get_bom_tree(db, parent_id)

        def dump(node, depth: int = 0) -> None:
            print("  " * depth + f"- {node.material_code} {node.material_name} ×{node.quantity}")
            for child in node.children:
                dump(child, depth + 1)

        print(f"结构树展开结果（根 {PARENT_CODE}，版本 {bom.bom_version}，激活 {bom.is_active}）：")
        dump(tree)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
