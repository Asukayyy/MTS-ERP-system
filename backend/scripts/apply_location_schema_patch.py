"""共享库库位（location）结构幂等补丁。

背景：共享库当前停留在旧版结构（49 张表），落后于代码模型（53 张表）。
旧版把库位信息放在 inv_warehouse（location_code/location_name）与 inv_balance
（reorder_point/reorder_quantity），新版拆分为独立库位功能：

- 新增 6 张表：inv_location / inv_reorder_rule / inv_stocktake /
  inv_stocktake_item / inv_transfer / inv_transfer_item；
- 7 张已有表补充 `location_id` 列（外键 → inv_location，可空）。

原则：只增不删、可重复执行（按 information_schema 检查，存在即跳过）、
不触碰现有表数据与旧列。DDL 与基线迁移
`migrations/versions/9e6fa0de8416_baseline_schema_for_five_modules.py` 保持一致。

用法（在 backend 目录下）：
    python scripts/apply_location_schema_patch.py
"""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DB = dict(
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
)

# --------------------------------------------------------------------------- #
# 一、新增 6 张表（与基线迁移一致）
# --------------------------------------------------------------------------- #
CREATE_TABLES: list[str] = [
    """CREATE TABLE inv_location (
        id BIGINT NOT NULL AUTO_INCREMENT,
        location_code VARCHAR(50) NOT NULL COMMENT '库位编码',
        location_name VARCHAR(100) NOT NULL COMMENT '库位名称',
        warehouse_id BIGINT NOT NULL COMMENT '仓库ID',
        status VARCHAR(20) NOT NULL COMMENT '状态',
        remark TEXT NULL COMMENT '备注',
        created_by BIGINT NULL COMMENT '创建人ID（sys_user.id）',
        updated_by BIGINT NULL COMMENT '更新人ID（sys_user.id）',
        created_at DATETIME NOT NULL COMMENT '创建时间',
        updated_at DATETIME NOT NULL COMMENT '更新时间',
        PRIMARY KEY (id),
        CONSTRAINT ck_inv_location_status CHECK (status IN ('ACTIVE','INACTIVE')),
        CONSTRAINT uq_inv_location UNIQUE (warehouse_id, location_code),
        CONSTRAINT fk_inv_location_warehouse FOREIGN KEY (warehouse_id)
            REFERENCES inv_warehouse (id) ON DELETE CASCADE
    )""",
    """CREATE TABLE inv_reorder_rule (
        id BIGINT NOT NULL AUTO_INCREMENT,
        material_id BIGINT NOT NULL COMMENT '物料ID',
        warehouse_id BIGINT NOT NULL COMMENT '仓库ID',
        reorder_point DECIMAL(18,4) NOT NULL COMMENT '订货点',
        reorder_quantity DECIMAL(18,4) NOT NULL COMMENT '建议订货量',
        status VARCHAR(20) NOT NULL COMMENT '状态',
        remark TEXT NULL COMMENT '备注',
        created_by BIGINT NULL,
        updated_by BIGINT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_inv_reorder_rule_status CHECK (status IN ('ACTIVE','INACTIVE')),
        CONSTRAINT ck_inv_reorder_point CHECK (reorder_point >= 0),
        CONSTRAINT ck_inv_reorder_qty CHECK (reorder_quantity >= 0),
        CONSTRAINT uq_inv_reorder_rule UNIQUE (material_id, warehouse_id),
        CONSTRAINT fk_inv_reorder_rule_material FOREIGN KEY (material_id)
            REFERENCES sys_material (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_reorder_rule_warehouse FOREIGN KEY (warehouse_id)
            REFERENCES inv_warehouse (id) ON DELETE RESTRICT
    )""",
    """CREATE TABLE inv_stocktake (
        id BIGINT NOT NULL AUTO_INCREMENT,
        stocktake_no VARCHAR(50) NOT NULL COMMENT '盘点单号',
        warehouse_id BIGINT NOT NULL COMMENT '仓库ID',
        stocktake_date DATE NOT NULL COMMENT '盘点日期',
        status VARCHAR(20) NOT NULL COMMENT '状态',
        remark TEXT NULL COMMENT '备注',
        created_by BIGINT NULL,
        updated_by BIGINT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_inv_stocktake_status
            CHECK (status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')),
        CONSTRAINT uq_inv_stocktake_no UNIQUE (stocktake_no),
        CONSTRAINT fk_inv_stocktake_warehouse FOREIGN KEY (warehouse_id)
            REFERENCES inv_warehouse (id) ON DELETE RESTRICT
    )""",
    """CREATE TABLE inv_transfer (
        id BIGINT NOT NULL AUTO_INCREMENT,
        transfer_no VARCHAR(50) NOT NULL COMMENT '移库单号',
        from_warehouse_id BIGINT NOT NULL COMMENT '源仓库ID',
        to_warehouse_id BIGINT NOT NULL COMMENT '目标仓库ID',
        transfer_date DATE NOT NULL COMMENT '移库日期',
        status VARCHAR(20) NOT NULL COMMENT '状态',
        remark TEXT NULL COMMENT '备注',
        created_by BIGINT NULL,
        updated_by BIGINT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_inv_transfer_status
            CHECK (status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')),
        CONSTRAINT uq_inv_transfer_no UNIQUE (transfer_no),
        CONSTRAINT fk_inv_transfer_from FOREIGN KEY (from_warehouse_id)
            REFERENCES inv_warehouse (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_transfer_to FOREIGN KEY (to_warehouse_id)
            REFERENCES inv_warehouse (id) ON DELETE RESTRICT
    )""",
    """CREATE TABLE inv_stocktake_item (
        id BIGINT NOT NULL AUTO_INCREMENT,
        stocktake_id BIGINT NOT NULL COMMENT '盘点单头ID',
        material_id BIGINT NOT NULL COMMENT '物料ID',
        location_id BIGINT NULL COMMENT '库位ID',
        book_qty DECIMAL(18,4) NOT NULL COMMENT '账面数量',
        actual_qty DECIMAL(18,4) NOT NULL COMMENT '实盘数量',
        difference DECIMAL(18,4) NOT NULL COMMENT '差异数量',
        remark VARCHAR(200) NULL COMMENT '备注',
        created_by BIGINT NULL,
        updated_by BIGINT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_inv_stocktake_actual CHECK (actual_qty >= 0),
        CONSTRAINT fk_inv_stocktake_item_location FOREIGN KEY (location_id)
            REFERENCES inv_location (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_stocktake_item_material FOREIGN KEY (material_id)
            REFERENCES sys_material (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_stocktake_item_head FOREIGN KEY (stocktake_id)
            REFERENCES inv_stocktake (id) ON DELETE CASCADE
    )""",
    """CREATE TABLE inv_transfer_item (
        id BIGINT NOT NULL AUTO_INCREMENT,
        transfer_id BIGINT NOT NULL COMMENT '移库单头ID',
        material_id BIGINT NOT NULL COMMENT '物料ID',
        from_location_id BIGINT NULL COMMENT '源库位ID',
        to_location_id BIGINT NULL COMMENT '目标库位ID',
        quantity DECIMAL(18,4) NOT NULL COMMENT '移库数量',
        remark VARCHAR(200) NULL COMMENT '备注',
        created_by BIGINT NULL,
        updated_by BIGINT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_inv_transfer_item_qty CHECK (quantity > 0),
        CONSTRAINT fk_inv_transfer_item_from FOREIGN KEY (from_location_id)
            REFERENCES inv_location (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_transfer_item_to FOREIGN KEY (to_location_id)
            REFERENCES inv_location (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_transfer_item_material FOREIGN KEY (material_id)
            REFERENCES sys_material (id) ON DELETE RESTRICT,
        CONSTRAINT fk_inv_transfer_item_head FOREIGN KEY (transfer_id)
            REFERENCES inv_transfer (id) ON DELETE CASCADE
    )""",
]

CREATE_INDEXES: list[str] = [
    "CREATE INDEX ix_inv_location_warehouse_id ON inv_location (warehouse_id)",
    "CREATE INDEX ix_inv_reorder_rule_material_id ON inv_reorder_rule (material_id)",
    "CREATE INDEX ix_inv_reorder_rule_warehouse_id ON inv_reorder_rule (warehouse_id)",
    "CREATE INDEX ix_inv_stocktake_item_stocktake_id ON inv_stocktake_item (stocktake_id)",
    "CREATE INDEX ix_inv_transfer_item_transfer_id ON inv_transfer_item (transfer_id)",
]
# ix_inv_balance_location_id 依赖步骤三补的 location_id 列，故单独在步骤三之后补建。

# --------------------------------------------------------------------------- #
# 二、已有表补 location_id 列（外键 → inv_location，可空）
# --------------------------------------------------------------------------- #
LOCATION_ID_TABLES: list[str] = [
    "inv_balance",
    "inv_transaction",
    "pln_completion_report",
    "pln_material_requisition_item",
    "pur_receipt_item",
    "sal_return_item",
    "sal_shipment_item",
]


def _column_names(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (DB["database"], table),
    )
    return {row[0] for row in cur.fetchall()}


def _index_names(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (DB["database"], table),
    )
    return {row[0] for row in cur.fetchall()}


def main() -> None:
    conn = pymysql.connect(
        **DB, connect_timeout=5, charset="utf8mb4", autocommit=False
    )
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    existing_tables = {row[0] for row in cur.fetchall()}

    try:
        # 1. 建缺失的表（inv_location 必须先建，其余表外键依赖它）
        created, exists = [], []
        for ddl in CREATE_TABLES:
            table = ddl.strip().split("(", 1)[0].replace("CREATE TABLE", "").strip()
            if table in existing_tables:
                exists.append(table)
                continue
            cur.execute(ddl.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
            created.append(table)
        existing_tables |= set(created)
        print(f"[表] 新建 {len(created)}: {created}")
        print(f"[表] 已存在跳过 {len(exists)}: {exists}")

        # 2. 补索引
        idx_added = []
        for idx_ddl in CREATE_INDEXES:
            name = idx_ddl.split("INDEX", 1)[1].split("ON", 1)[0].strip()
            table = idx_ddl.split("ON", 1)[1].split("(", 1)[0].strip()
            if name not in _index_names(cur, table):
                cur.execute(idx_ddl)
                idx_added.append(name)
        print(f"[索引] 新增 {len(idx_added)}: {idx_added}")

        # 3. 已有表补 location_id 列 + 外键
        col_added = []
        for table in LOCATION_ID_TABLES:
            cols = _column_names(cur, table)
            if "location_id" not in cols:
                cur.execute(
                    f"ALTER TABLE {table} ADD COLUMN location_id BIGINT NULL "
                    "COMMENT '库位ID'"
                )
                conn.commit()
                col_added.append(table)
            # 外键：存在即跳过
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = %s AND TABLE_NAME = %s "
                "AND CONSTRAINT_NAME = %s",
                (DB["database"], table, f"fk_{table}_location_id"),
            )
            if cur.fetchone()[0] == 0:
                cur.execute(
                    f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_location_id "
                    "FOREIGN KEY (location_id) REFERENCES inv_location (id) "
                    "ON DELETE RESTRICT"
                )
                col_added.append(f"{table}:fk")
        print(f"[列/外键] 新增 {len(col_added)}: {col_added}")

        # 4. inv_balance 的 location_id 索引（依赖步骤三的列）
        if "ix_inv_balance_location_id" not in _index_names(cur, "inv_balance"):
            cur.execute("CREATE INDEX ix_inv_balance_location_id ON inv_balance (location_id)")
            idx_added.append("ix_inv_balance_location_id")
        print(f"[索引] 新增 {len(idx_added)}: {idx_added}")

        conn.commit()
        print("补丁执行完成。")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())